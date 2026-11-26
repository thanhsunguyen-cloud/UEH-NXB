"""GoogleDriveStorage – cài đặt FileStorage Protocol trên Shared Drive của NXB (gói M1).

Cấu trúc thư mục trên Shared Drive (tìm bằng appProperties, tạo khi chưa có):

    Portal/cases/<case_uuid>/<doc_type>/v<version>_<tên an toàn>
    Portal/library/<category>/<uuid>_<tên an toàn>
    Portal/_healthcheck/            (chỉ dùng cho lệnh drive_check)

`storage_ref` = Drive file ID. `UploadSession.backend_ref` = URL phiên resumable upload.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from collections.abc import Iterator
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.core.audit import log_event
from apps.core.storage import (
    CHUNK_SIZE,
    StoredFile,
    library_max_bytes,
    sanitize_filename,
    validate_library_file,
)
from apps.documents_drive.client import (
    DRIVE_API_URL,
    DRIVE_UPLOAD_URL,
    FOLDER_MIME,
    DriveApiError,
    DriveClient,
    get_shared_drive_id,
    is_retryable,
    with_all_drives,
)

logger = logging.getLogger(__name__)

# Tải xuống theo từng khối 4 MiB qua HTTP Range (không nạp cả file vào RAM)
DOWNLOAD_CHUNK_SIZE = 4 * 1024 * 1024
UPLOAD_GRANULARITY = 256 * 1024
FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,200}$")
FILE_FIELDS = "id,name,size,mimeType,sha256Checksum,driveId,trashed,parents"
MAX_BACKEND_REF_LENGTH = 500

MESSAGE_SESSION_MISSING = _("Phiên tải tệp không tồn tại hoặc đã bị hủy.")


def _q(value: str) -> str:
    """Thoát ký tự đặc biệt trong chuỗi truy vấn Drive (q=...)."""
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _parse_range_end(resp) -> int:
    """Đọc header Range của phản hồi 308 (`bytes=0-N`) → số byte Drive đã nhận (N + 1)."""
    header = resp.get("range") if resp is not None else None
    if not header:
        return 0
    match = re.search(r"(\d+)-(\d+)", header)
    return int(match.group(2)) + 1 if match else 0


def _read_exact(fileobj, size: int) -> bytes:
    """Đọc đủ `size` byte (hoặc đến hết dữ liệu) để mọi phần trừ phần cuối là bội số 256 KiB."""
    parts: list[bytes] = []
    remaining = size
    while remaining > 0:
        block = fileobj.read(remaining)
        if not block:
            break
        parts.append(block)
        remaining -= len(block)
    return b"".join(parts)


class GoogleDriveStorage:
    """Lưu tài liệu hồ sơ và file thư viện trên Shared Drive `GDRIVE_SHARED_DRIVE_ID`."""

    def __init__(self, client: DriveClient | None = None, drive_id: str | None = None):
        self.drive_id = drive_id or get_shared_drive_id()
        self.client = client or DriveClient()
        self._folder_cache: dict[tuple, str] = {}
        self._totals: dict[str, int] = {}

    # ------------------------------------------------------------------ thư mục

    def _ensure_folder(self, parent_id: str, name: str, props: dict[str, str]) -> str:
        key = (parent_id, tuple(sorted(props.items())))
        if key in self._folder_cache:
            return self._folder_cache[key]

        conditions = [
            f"mimeType='{FOLDER_MIME}'",
            "trashed=false",
            f"'{_q(parent_id)}' in parents",
        ]
        conditions += [
            f"appProperties has {{ key='{_q(k)}' and value='{_q(v)}' }}" for k, v in props.items()
        ]
        result = self.client.execute(
            self.client.files.list(
                q=" and ".join(conditions),
                corpora="drive",
                driveId=self.drive_id,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                fields="files(id,name)",
                orderBy="createdTime",
                pageSize=10,
            )
        )
        found = result.get("files") or []
        if found:
            folder_id = found[0]["id"]
        else:
            created = self.client.execute(
                self.client.files.create(
                    body={
                        "name": name,
                        "mimeType": FOLDER_MIME,
                        "parents": [parent_id],
                        "appProperties": props,
                    },
                    supportsAllDrives=True,
                    fields="id",
                )
            )
            folder_id = created["id"]
        self._folder_cache[key] = folder_id
        return folder_id

    def _root_folder(self) -> str:
        return self._ensure_folder(self.drive_id, "Portal", {"portal_folder": "root"})

    def case_folder(self, case_id: str, doc_type: str) -> str:
        cases = self._ensure_folder(self._root_folder(), "cases", {"portal_folder": "cases"})
        case_folder = self._ensure_folder(
            cases, case_id, {"portal_folder": "case", "portal_case_id": case_id}
        )
        return self._ensure_folder(
            case_folder,
            doc_type,
            {
                "portal_folder": "doc_type",
                "portal_case_id": case_id,
                "portal_doc_type": doc_type,
            },
        )

    def library_folder(self, category: str) -> str:
        library = self._ensure_folder(self._root_folder(), "library", {"portal_folder": "library"})
        return self._ensure_folder(
            library,
            category,
            {"portal_folder": "library_category", "portal_library_category": category},
        )

    def healthcheck_folder(self) -> str:
        return self._ensure_folder(
            self._root_folder(), "_healthcheck", {"portal_folder": "healthcheck"}
        )

    # ------------------------------------------------------------ resumable upload

    def _create_session(
        self, folder_id: str, name: str, total_size: int, mime_type: str, props: dict
    ) -> str:
        metadata = {"name": name, "parents": [folder_id], "appProperties": props}
        if mime_type:
            metadata["mimeType"] = mime_type
        resp, _content = self.client.send(
            f"{DRIVE_UPLOAD_URL}?uploadType=resumable&supportsAllDrives=true",
            "POST",
            body=json.dumps(metadata).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": mime_type or "application/octet-stream",
                "X-Upload-Content-Length": str(total_size),
            },
        )
        location = resp.get("location")
        if not location:
            logger.error("Drive không trả URL phiên resumable upload")
            raise DriveApiError(500, "missing Location header")
        session_url = with_all_drives(location)
        if len(session_url) > MAX_BACKEND_REF_LENGTH:
            logger.error("URL phiên resumable dài %s ký tự", len(session_url))
            raise DriveApiError(500, "session URL too long")
        self._totals[session_url] = int(total_size)
        return session_url

    def _query_status(self, session_url: str, total: int | None) -> tuple[int, dict | None]:
        """Hỏi trạng thái phiên: trả (số byte Drive đã nhận, metadata file nếu đã hoàn tất)."""
        total_str = str(total) if total is not None else "*"
        resp, content = self.client.send(
            session_url,
            "PUT",
            body=b"",
            headers={"Content-Length": "0", "Content-Range": f"bytes */{total_str}"},
            ok=(200, 201, 308),
        )
        if int(resp.status) in (200, 201):
            return (total or 0), json.loads(content or b"{}")
        return _parse_range_end(resp), None

    def _put_chunk(self, session_url: str, offset: int, data: bytes, total: int) -> dict | None:
        """Gửi một phần dữ liệu tại `offset`; trả metadata file nếu đây là phần cuối.

        Gặp lỗi tạm thời: chờ, hỏi Drive đã nhận tới đâu rồi gửi tiếp phần còn thiếu.
        """
        end = offset + len(data)
        position = offset
        for attempt in range(1, self.client.max_attempts + 1):
            body = data[position - offset :]
            try:
                resp, content = self.client.send(
                    session_url,
                    "PUT",
                    body=body,
                    headers={
                        "Content-Length": str(len(body)),
                        "Content-Range": f"bytes {position}-{end - 1}/{total}",
                    },
                    retry=False,
                )
                status = int(resp.status)
            except DriveApiError as exc:  # lỗi kết nối
                status, content = None, exc.detail

            if status in (200, 201):
                return json.loads(content or b"{}")
            if status == 308:
                received = _parse_range_end(resp)
                if received >= end:
                    return None
                if received < offset:
                    raise DriveApiError(500, f"Drive lost data: {received} < {offset}")
                position = received
                continue
            if status is not None and not is_retryable(status, content):
                logger.error("Drive từ chối phần dữ liệu: %s %s", status, content[:500])
                raise DriveApiError(status, str(content[:500]))
            if attempt == self.client.max_attempts:
                break
            self.client.backoff(attempt)
            received, file_meta = self._query_status(session_url, total)
            if file_meta is not None:
                return file_meta
            if received >= end:
                return None
            if received < offset:
                raise DriveApiError(500, f"Drive lost data: {received} < {offset}")
            position = received
        raise DriveApiError(503, "chunk upload failed after retries")

    def _total_for(self, upload_id: str) -> int:
        if upload_id in self._totals:
            return self._totals[upload_id]
        from apps.core.models import UploadSession

        total = (
            UploadSession.objects.filter(backend_ref=upload_id)
            .values_list("total_size", flat=True)
            .first()
        )
        if total is None:
            raise ValidationError(MESSAGE_SESSION_MISSING)
        return int(total)

    def _file_meta(self, file_id: str) -> dict:
        return self.client.execute(
            self.client.files.get(fileId=file_id, fields=FILE_FIELDS, supportsAllDrives=True)
        )

    def _stored_file(
        self, file_id: str, expected_size: int, local_sha256: str = "", meta: dict | None = None
    ) -> StoredFile:
        meta = meta or self._file_meta(file_id)
        size = int(meta.get("size", expected_size))
        if size != expected_size:
            raise ValidationError(
                _("Thiếu dữ liệu tải lên: đã nhận %(got)s / %(expected)s bytes.")
                % {"got": size, "expected": expected_size}
            )
        sha256 = meta.get("sha256Checksum") or local_sha256 or self._sha256_of(file_id)
        if local_sha256 and sha256 != local_sha256:
            logger.error("SHA-256 không khớp cho file %s", file_id)
            raise ValidationError(_("Dữ liệu tải lên bị sai lệch, vui lòng tải lại."))
        return StoredFile(
            storage_ref=file_id,
            size=size,
            mime=meta.get("mimeType") or "application/octet-stream",
            sha256=sha256,
        )

    def _sha256_of(self, file_id: str) -> str:
        digest = hashlib.sha256()
        for block in self.open_stream(file_id):
            digest.update(block)
        return digest.hexdigest()

    # ------------------------------------------------------------- FileStorage

    def start_upload(self, case, doc_type: str, filename: str, total_size: int, mime_type: str):
        case_id = str(case.pk)
        folder_id = self.case_folder(case_id, doc_type)
        return self._create_session(
            folder_id,
            sanitize_filename(filename),
            int(total_size),
            mime_type or "application/octet-stream",
            {"portal_case_id": case_id, "portal_doc_type": doc_type},
        )

    def append_chunk(self, upload_id: str, offset: int, data: bytes) -> int:
        total = self._total_for(upload_id)
        end = offset + len(data)
        if end > total:
            raise ValidationError(_("Tổng dữ liệu gửi lên vượt quá dung lượng tệp đã khai báo."))
        if end < total and len(data) % UPLOAD_GRANULARITY != 0:
            raise ValidationError(_("Mỗi phần tải lên (trừ phần cuối) phải là bội số của 256 KiB."))
        self._put_chunk(upload_id, offset, data, total)
        return end

    def finish_upload(self, upload_id: str, *, version: int = 1) -> StoredFile:
        total = self._total_for(upload_id)
        received, file_meta = self._query_status(upload_id, total)
        if file_meta is None or "id" not in file_meta:
            raise ValidationError(
                _("Thiếu dữ liệu tải lên: đã nhận %(got)s / %(expected)s bytes.")
                % {"got": received, "expected": total}
            )
        file_id = file_meta["id"]
        meta = self._file_meta(file_id)
        stored = self._stored_file(file_id, total, meta=meta)
        self.client.execute(
            self.client.files.update(
                fileId=file_id,
                body={"name": f"v{version}_{meta.get('name') or 'file'}"},
                supportsAllDrives=True,
                fields="id,name",
            )
        )
        return stored

    def abort_upload(self, upload_id: str) -> None:
        try:
            total = self._totals.get(upload_id)
            if total is None:
                try:
                    total = self._total_for(upload_id)
                except ValidationError:
                    total = None
            _received, file_meta = self._query_status(upload_id, total)
            if file_meta and file_meta.get("id"):
                # Phần cuối đã gửi nhưng chưa hoàn tất phiên: xóa file mồ côi trên Drive
                self.delete_file(file_meta["id"])
            else:
                self.client.send(upload_id, "DELETE", ok=(200, 204, 404, 410, 499))
        except DriveApiError as exc:
            if exc.status not in (404, 410):
                logger.warning("Không hủy được phiên resumable upload: %s", exc.detail)
        finally:
            self._totals.pop(upload_id, None)

    def open_stream(self, storage_ref: str) -> Iterator[bytes]:
        url = self._media_url(storage_ref)
        position = 0
        while True:
            resp, content = self.client.send(
                url,
                "GET",
                headers={"Range": f"bytes={position}-{position + DOWNLOAD_CHUNK_SIZE - 1}"},
                ok=(200, 206, 416),
            )
            status = int(resp.status)
            if status == 416 or not content:
                return
            yield content
            if status == 200:
                return
            position += len(content)
            match = re.search(r"/(\d+)\s*$", resp.get("content-range", ""))
            if match is None or position >= int(match.group(1)):
                return

    def exists(self, storage_ref: str) -> bool:
        reason = self.missing_reason(storage_ref)
        if reason is None:
            return True
        self._log_missing(storage_ref, reason)
        return False

    def save_library_file(
        self, category: str, filename: str, fileobj, size: int, mime_type: str
    ) -> StoredFile:
        validate_library_file(category, size)
        name = f"{uuid.uuid4().hex}_{sanitize_filename(filename)}"
        folder_id = self.library_folder(category)
        return self.upload_fileobj(
            folder_id,
            name,
            fileobj,
            int(size),
            mime_type or "application/octet-stream",
            {"portal_library_category": category},
            max_bytes=library_max_bytes(),
        )

    # ------------------------------------------------------------ tiện ích khác

    def upload_fileobj(
        self,
        folder_id: str,
        name: str,
        fileobj,
        size: int,
        mime_type: str,
        props: dict,
        *,
        max_bytes: int | None = None,
    ) -> StoredFile:
        """Tải một file-like lên `folder_id` qua resumable upload, đọc từng phần 8 MiB."""
        session_url = self._create_session(folder_id, name, size, mime_type, props)
        digest = hashlib.sha256()
        offset = 0
        file_meta = None
        try:
            while True:
                block = _read_exact(fileobj, CHUNK_SIZE)
                if not block:
                    break
                if offset + len(block) > size or (max_bytes and offset + len(block) > max_bytes):
                    raise ValidationError(_("Dung lượng tệp thực tế lớn hơn dung lượng khai báo."))
                digest.update(block)
                file_meta = self._put_chunk(session_url, offset, block, size)
                offset += len(block)
            if offset != size or not file_meta or "id" not in file_meta:
                raise ValidationError(
                    _("Thiếu dữ liệu tải lên: đã nhận %(got)s / %(expected)s bytes.")
                    % {"got": offset, "expected": size}
                )
        except BaseException:
            self.abort_upload(session_url)
            raise
        self._totals.pop(session_url, None)
        return self._stored_file(file_meta["id"], size, digest.hexdigest())

    def missing_reason(self, storage_ref: str) -> str | None:
        """Trả None nếu file còn trên Shared Drive, ngược lại trả lý do (không ghi AuditEvent)."""
        if not FILE_ID_RE.match(storage_ref or ""):
            return "invalid_ref"
        try:
            meta = self._file_meta(storage_ref)
        except DriveApiError as exc:
            if exc.status in (404, 410):
                return "not_found"
            if exc.status == 403:
                return "forbidden"
            raise
        if meta.get("trashed"):
            return "trashed"
        if meta.get("driveId") != self.drive_id:
            return "outside_shared_drive"
        return None

    def delete_file(self, file_id: str) -> None:
        """Xóa file (dùng cho drive_check và dọn file mồ côi); không có quyền xóa thì chuyển thùng rác."""
        try:
            self.client.execute(self.client.files.delete(fileId=file_id, supportsAllDrives=True))
        except DriveApiError as exc:
            if exc.status != 403:
                raise
            self.client.execute(
                self.client.files.update(
                    fileId=file_id, body={"trashed": True}, supportsAllDrives=True, fields="id"
                )
            )

    def _media_url(self, storage_ref: str) -> str:
        if not FILE_ID_RE.match(storage_ref or ""):
            raise DriveApiError(404, "invalid file id")
        return f"{DRIVE_API_URL}/files/{quote(storage_ref)}?alt=media&supportsAllDrives=true"

    def _log_missing(self, storage_ref: str, reason: str) -> None:
        from apps.core.models import Document

        doc = Document.objects.filter(storage_ref=storage_ref).select_related("case").first()
        log_event(
            action="document.missing",
            object_type="Document" if doc else "DriveFile",
            object_id=str(doc.pk) if doc else storage_ref,
            case=doc.case if doc else None,
            data={"storage_backend": "gdrive", "storage_ref": storage_ref, "reason": reason},
        )
        logger.warning("Tệp Drive %s không còn khả dụng (%s)", storage_ref, reason)
