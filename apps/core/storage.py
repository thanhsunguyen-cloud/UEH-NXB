"""Lớp lưu trữ tệp trừu tượng, upload chia phần (8 MiB/chunk) và tải xuống dạng stream (mục 9).

Tuân thủ ràng buộc Cloud Run (request <= 32 MiB, ổ đĩa tạm nằm trong RAM):
- Mọi upload chia thành từng phần CHUNK_SIZE = 8 MiB (bội số của 256 KiB).
- Tính SHA-256 gia tăng theo từng phần mà không nạp toàn bộ tệp vào RAM.
- Tải xuống luôn trả StreamingHttpResponse qua open_stream().
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.audit import log_event
from apps.core.models import (
    Document,
    PublicationCase,
    UploadSession,
    UploadSessionStatus,
)
from apps.core.permissions import can_upload

# 8 MiB — bội số của 256 KiB (tương thích Google Drive Resumable Upload của M1)
CHUNK_SIZE = 8 * 1024 * 1024
STREAM_READ_SIZE = 256 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".png"}

# CR-001: nhóm file nhỏ không thuộc hồ sơ (biểu mẫu của M7, ảnh công khai của M6)
LIBRARY_CATEGORIES = ("form_templates", "public_media")


@dataclass(frozen=True)
class StoredFile:
    storage_ref: str
    size: int
    mime: str
    sha256: str


class FileStorage(Protocol):
    """Giao diện trừu tượng cho kho lưu trữ (M0 cài LocalFileStorage, M1 cài GoogleDriveStorage)."""

    def start_upload(
        self,
        case: PublicationCase,
        doc_type: str,
        filename: str,
        total_size: int,
        mime_type: str,
    ) -> str:
        """Khởi tạo phiên upload và trả về upload_id/backend_ref."""
        ...

    def append_chunk(self, upload_id: str, offset: int, data: bytes) -> int:
        """Ghi nối một phần dữ liệu tại đúng offset, trả về tổng số byte đã nhận."""
        ...

    def finish_upload(self, upload_id: str, *, version: int = 1) -> StoredFile:
        """Hoàn tất phiên upload, trả về thông tin StoredFile."""
        ...

    def abort_upload(self, upload_id: str) -> None:
        """Hủy phiên upload và dọn tệp tạm."""
        ...

    def open_stream(self, storage_ref: str) -> Iterator[bytes]:
        """Đọc tệp từng khối nhỏ, không nạp toàn bộ tệp vào RAM."""
        ...

    def exists(self, storage_ref: str) -> bool:
        """Kiểm tra tệp có tồn tại trong kho lưu trữ hay không."""
        ...

    def save_library_file(
        self,
        category: str,
        filename: str,
        fileobj,
        size: int,
        mime_type: str,
    ) -> StoredFile:
        """Lưu file nhỏ không thuộc hồ sơ vào library/<category>/<uuid>_<tên an toàn> (CR-001).

        `category` chỉ nhận "form_templates" hoặc "public_media"; từ chối file lớn hơn
        MAX_LIBRARY_FILE_MB.
        """
        ...


def validate_library_file(category: str, size: int) -> None:
    """Kiểm tra category và dung lượng khai báo của file thư viện (dùng chung cho mọi backend)."""
    if category not in LIBRARY_CATEGORIES:
        raise ValidationError(
            _("Nhóm lưu trữ '%(category)s' không hợp lệ.") % {"category": category}
        )
    if int(size) <= 0:
        raise ValidationError(_("Dung lượng tệp phải lớn hơn 0 bytes."))
    if int(size) > library_max_bytes():
        raise ValidationError(
            _("Tệp vượt quá dung lượng tối đa %(max_mb)s MiB.")
            % {"max_mb": int(getattr(settings, "MAX_LIBRARY_FILE_MB", 10))}
        )


def library_max_bytes() -> int:
    return int(getattr(settings, "MAX_LIBRARY_FILE_MB", 10)) * 1024 * 1024


def sanitize_filename(filename: str) -> str:
    """Làm sạch tên tệp an toàn chống path traversal."""
    base = os.path.basename(filename or "unnamed")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned[:180] or "file"


class LocalFileStorage:
    """Cài đặt lưu trữ cục bộ cho M0.

    Lưu tệp hoàn chỉnh tại:
    MEDIA_ROOT/cases/<case_id>/<doc_type>/v<version>_<tên file an toàn>
    """

    def __init__(self, media_root: Path | str | None = None):
        self.media_root = Path(media_root or settings.MEDIA_ROOT).resolve()
        self.tmp_root = self.media_root / ".uploads"
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        self._meta: dict[str, dict] = {}

    def _tmp_path(self, upload_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", upload_id)
        return self.tmp_root / f"{safe_id}.part"

    def _meta_path(self, upload_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", upload_id)
        return self.tmp_root / f"{safe_id}.meta"

    def _resolve_safe_ref(self, storage_ref: str) -> Path:
        target = (self.media_root / storage_ref).resolve()
        if not str(target).startswith(str(self.media_root)):
            raise ValidationError(_("Đường dẫn lưu trữ không hợp lệ."))
        return target

    def start_upload(
        self,
        case: PublicationCase,
        doc_type: str,
        filename: str,
        total_size: int,
        mime_type: str,
    ) -> str:
        upload_id = uuid.uuid4().hex
        tmp_file = self._tmp_path(upload_id)
        tmp_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file.write_bytes(b"")
        import json

        meta = {
            "case_id": str(case.pk),
            "doc_type": doc_type,
            "filename": sanitize_filename(filename),
            "total_size": int(total_size),
            "mime_type": mime_type or "application/octet-stream",
        }
        self._meta_path(upload_id).write_text(json.dumps(meta), encoding="utf-8")
        return upload_id

    def append_chunk(self, upload_id: str, offset: int, data: bytes) -> int:
        tmp_file = self._tmp_path(upload_id)
        if not tmp_file.exists():
            raise ValidationError(_("Phiên tải tệp không tồn tại hoặc đã bị hủy."))
        current_size = tmp_file.stat().st_size
        if offset != current_size:
            raise ValidationError(
                _("Sai vị trí phần dữ liệu (offset=%(offset)s, mong đợi=%(expected)s).")
                % {"offset": offset, "expected": current_size}
            )
        with tmp_file.open("ab") as fh:
            fh.write(data)
        return current_size + len(data)

    def finish_upload(self, upload_id: str, *, version: int = 1) -> StoredFile:
        import json

        tmp_file = self._tmp_path(upload_id)
        meta_file = self._meta_path(upload_id)
        if not tmp_file.exists() or not meta_file.exists():
            raise ValidationError(_("Không tìm thấy dữ liệu tạm của phiên tải tệp."))

        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        actual_size = tmp_file.stat().st_size
        if actual_size != meta["total_size"]:
            raise ValidationError(
                _("Thiếu dữ liệu tải lên: đã nhận %(got)s / %(expected)s bytes.")
                % {"got": actual_size, "expected": meta["total_size"]}
            )

        # Tính SHA-256 theo từng khối nhỏ (không nạp cả file vào RAM)
        digest = hashlib.sha256()
        with tmp_file.open("rb") as fh:
            while block := fh.read(STREAM_READ_SIZE):
                digest.update(block)

        rel_path = (
            Path("cases") / meta["case_id"] / meta["doc_type"] / f"v{version}_{meta['filename']}"
        )
        dest = self._resolve_safe_ref(str(rel_path))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_file), str(dest))
        meta_file.unlink(missing_ok=True)

        return StoredFile(
            storage_ref=rel_path.as_posix(),
            size=actual_size,
            mime=meta["mime_type"],
            sha256=digest.hexdigest(),
        )

    def abort_upload(self, upload_id: str) -> None:
        self._tmp_path(upload_id).unlink(missing_ok=True)
        self._meta_path(upload_id).unlink(missing_ok=True)

    def open_stream(self, storage_ref: str) -> Iterator[bytes]:
        target = self._resolve_safe_ref(storage_ref)
        with target.open("rb") as fh:
            while chunk := fh.read(STREAM_READ_SIZE):
                yield chunk

    def exists(self, storage_ref: str) -> bool:
        return self._resolve_safe_ref(storage_ref).is_file()

    def save_library_file(
        self,
        category: str,
        filename: str,
        fileobj,
        size: int,
        mime_type: str,
    ) -> StoredFile:
        validate_library_file(category, size)
        rel_path = Path("library") / category / f"{uuid.uuid4().hex}_{sanitize_filename(filename)}"
        dest = self._resolve_safe_ref(rel_path.as_posix())
        dest.parent.mkdir(parents=True, exist_ok=True)

        max_bytes = library_max_bytes()
        digest = hashlib.sha256()
        written = 0
        try:
            with dest.open("wb") as fh:
                while block := fileobj.read(STREAM_READ_SIZE):
                    written += len(block)
                    if written > max_bytes or written > int(size):
                        raise ValidationError(
                            _("Dung lượng tệp thực tế lớn hơn dung lượng khai báo.")
                        )
                    digest.update(block)
                    fh.write(block)
            if written != int(size):
                raise ValidationError(
                    _("Thiếu dữ liệu tải lên: đã nhận %(got)s / %(expected)s bytes.")
                    % {"got": written, "expected": int(size)}
                )
        except BaseException:
            dest.unlink(missing_ok=True)
            raise

        return StoredFile(
            storage_ref=rel_path.as_posix(),
            size=written,
            mime=mime_type or "application/octet-stream",
            sha256=digest.hexdigest(),
        )


def get_storage() -> FileStorage:
    """Trả về backend lưu trữ theo cấu hình FILE_STORAGE_BACKEND."""
    backend = getattr(settings, "FILE_STORAGE_BACKEND", "local")
    if backend == "local":
        return LocalFileStorage()
    if backend == "gdrive":
        # Import bên trong hàm để tránh vòng import (apps.documents_drive dùng apps.core.storage)
        from apps.documents_drive.storage import GoogleDriveStorage

        return GoogleDriveStorage()
    raise NotImplementedError(
        f"Backend lưu trữ '{backend}' không được hỗ trợ (chỉ nhận 'local' hoặc 'gdrive')."
    )


def _validate_upload_metadata(filename: str, total_size: int) -> None:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed_str = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValidationError(
            _("Định dạng tệp '%(ext)s' không được hỗ trợ. Chỉ chấp nhận: %(allowed)s.")
            % {"ext": ext or "(trống)", "allowed": allowed_str}
        )
    max_mb = int(getattr(settings, "MAX_FILE_MB", 200))
    max_bytes = max_mb * 1024 * 1024
    if total_size <= 0:
        raise ValidationError(_("Dung lượng tệp phải lớn hơn 0 bytes."))
    if total_size > max_bytes:
        raise ValidationError(
            _("Tệp vượt quá dung lượng tối đa %(max_mb)s MiB.") % {"max_mb": max_mb}
        )


def begin_document_upload(
    *,
    user,
    case: PublicationCase,
    doc_type: str,
    filename: str,
    total_size: int,
    mime_type: str = "application/octet-stream",
    form_code: str = "",
    storage: FileStorage | None = None,
) -> UploadSession:
    """Bước 1: Kiểm tra quyền + định dạng + dung lượng, khởi tạo UploadSession."""
    if not can_upload(user, case, doc_type):
        raise PermissionDenied(_("Bạn không có quyền tải tài liệu loại này lên hồ sơ."))
    _validate_upload_metadata(filename, total_size)

    backend = storage or get_storage()
    backend_ref = backend.start_upload(case, doc_type, filename, total_size, mime_type)
    return UploadSession.objects.create(
        case=case,
        doc_type=doc_type,
        form_code=form_code,
        filename=filename,
        mime_type=mime_type or "application/octet-stream",
        total_size=total_size,
        received_bytes=0,
        backend_ref=backend_ref,
        created_by=user,
        expires_at=timezone.now() + timedelta(hours=24),
        status=UploadSessionStatus.OPEN,
    )


def upload_chunk(
    *,
    user,
    session: UploadSession,
    offset: int,
    data: bytes,
    storage: FileStorage | None = None,
) -> int:
    """Bước 2: Kiểm tra quyền, kích thước phần <= CHUNK_SIZE, offset liên tiếp và ghi nối phần."""
    if session.status != UploadSessionStatus.OPEN:
        raise ValidationError(_("Phiên tải lên đã đóng hoặc bị hủy."))
    if session.expires_at < timezone.now():
        raise ValidationError(_("Phiên tải lên đã hết hạn (quá 24 giờ)."))
    if session.created_by_id != user.pk or not can_upload(user, session.case, session.doc_type):
        raise PermissionDenied(_("Bạn không có quyền gửi dữ liệu vào phiên tải lên này."))
    if len(data) == 0 or len(data) > CHUNK_SIZE:
        raise ValidationError(
            _("Mỗi phần tải lên phải lớn hơn 0 và tối đa %(max_size)s bytes (8 MiB).")
            % {"max_size": CHUNK_SIZE}
        )
    if offset != session.received_bytes:
        raise ValidationError(
            _("Sai offset: nhận %(offset)s nhưng hệ thống mong đợi %(expected)s.")
            % {"offset": offset, "expected": session.received_bytes}
        )
    if offset + len(data) > session.total_size:
        raise ValidationError(_("Tổng dữ liệu gửi lên vượt quá dung lượng tệp đã khai báo."))

    backend = storage or get_storage()
    new_received = backend.append_chunk(session.backend_ref, offset, data)
    session.received_bytes = new_received
    session.save(update_fields=["received_bytes", "updated_at"])
    return new_received


def complete_document_upload(
    *,
    user,
    session: UploadSession,
    note: str = "",
    request=None,
    storage: FileStorage | None = None,
) -> Document:
    """Bước 3: Hoàn tất ghép tệp, tính SHA-256, tăng version, cập nhật is_current và ghi AuditEvent."""
    if session.status != UploadSessionStatus.OPEN:
        raise ValidationError(_("Phiên tải lên không ở trạng thái OPEN."))
    if session.created_by_id != user.pk or not can_upload(user, session.case, session.doc_type):
        raise PermissionDenied(_("Bạn không có quyền hoàn tất phiên tải lên này."))
    if session.received_bytes != session.total_size:
        raise ValidationError(
            _("Tệp chưa tải đủ các phần (đã nhận %(got)s / %(expected)s bytes).")
            % {"got": session.received_bytes, "expected": session.total_size}
        )

    backend = storage or get_storage()
    backend_name = getattr(settings, "FILE_STORAGE_BACKEND", "local")

    with transaction.atomic():
        # Khóa các bản ghi cùng nhóm để tính version kế tiếp an toàn
        existing_qs = Document.objects.select_for_update().filter(
            case=session.case,
            doc_type=session.doc_type,
            form_code=session.form_code,
        )
        max_ver = existing_qs.aggregate(m=Max("version"))["m"] or 0
        next_version = max_ver + 1

        stored = backend.finish_upload(session.backend_ref, version=next_version)

        # Bản cũ của (case, doc_type, form_code) chuyển is_current = False
        existing_qs.filter(is_current=True).update(is_current=False)

        doc = Document.objects.create(
            case=session.case,
            doc_type=session.doc_type,
            form_code=session.form_code,
            version=next_version,
            is_current=True,
            original_filename=session.filename,
            mime_type=stored.mime,
            size_bytes=stored.size,
            sha256=stored.sha256,
            storage_backend=backend_name,
            storage_ref=stored.storage_ref,
            uploaded_by=user,
            note=note,
        )

        session.status = UploadSessionStatus.DONE
        session.save(update_fields=["status", "updated_at"])

        log_event(
            actor=user,
            action="document.upload",
            object_type="Document",
            object_id=str(doc.pk),
            case=session.case,
            data={
                "doc_type": doc.doc_type,
                "form_code": doc.form_code,
                "version": doc.version,
                "original_filename": doc.original_filename,
                "size_bytes": doc.size_bytes,
                "sha256": doc.sha256,
            },
            request=request,
        )

    return doc
