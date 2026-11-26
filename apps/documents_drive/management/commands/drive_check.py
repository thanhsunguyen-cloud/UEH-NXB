"""Lệnh kiểm tra cấu hình Google Drive thật: `python manage.py drive_check` (gói M1)."""

from __future__ import annotations

import hashlib
import io

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

HEALTHCHECK_CONTENT = b"UEH Publishing Portal - drive_check\n"


class Command(BaseCommand):
    help = (
        "Kiểm tra kết nối Shared Drive: đọc Shared Drive, tạo/xóa một file thử trong "
        "Portal/_healthcheck/ và kiểm tra supportsAllDrives trên mọi lời gọi."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-file",
            action="store_true",
            help="Giữ lại file thử trên Drive (mặc định sẽ xóa).",
        )

    def __init__(self, *args, storage=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._storage = storage
        self.failures: list[str] = []

    def ok(self, message: str) -> None:
        self.stdout.write(self.style.SUCCESS(f"[ĐẠT] {message}"))

    def fail(self, message: str) -> None:
        self.failures.append(message)
        self.stdout.write(self.style.ERROR(f"[LỖI] {message}"))

    def handle(self, *args, **options):
        self.failures = []
        self.stdout.write("Kiểm tra cấu hình Google Drive cho UEH Publishing Portal")
        self.stdout.write(f"- FILE_STORAGE_BACKEND = {settings.FILE_STORAGE_BACKEND}")
        credentials = settings.GDRIVE_CREDENTIALS_FILE or "Application Default Credentials"
        self.stdout.write(f"- Thông tin xác thực: {credentials}")
        if settings.FILE_STORAGE_BACKEND != "gdrive":
            self.stdout.write(
                self.style.WARNING(
                    "Lưu ý: FILE_STORAGE_BACKEND chưa là 'gdrive', ứng dụng vẫn đang lưu cục bộ."
                )
            )

        try:
            storage = self._storage or self._build_storage()
        except Exception as exc:
            self.fail(f"Không khởi tạo được kết nối Google Drive: {exc}")
            raise CommandError("drive_check: KHÔNG ĐẠT.") from exc

        self.stdout.write(f"- Shared Drive ID: {storage.drive_id}")
        try:
            self._run_checks(storage, keep_file=options.get("keep_file", False))
        except ValidationError as exc:
            detail = getattr(exc, "detail", "") or ""
            self.fail(f"{'; '.join(exc.messages)} {detail}".strip())

        if self.failures:
            raise CommandError(f"drive_check: KHÔNG ĐẠT ({len(self.failures)} lỗi).")
        self.stdout.write(self.style.SUCCESS("drive_check: TẤT CẢ ĐẠT."))

    def _build_storage(self):
        from apps.documents_drive.storage import GoogleDriveStorage

        return GoogleDriveStorage()

    def _run_checks(self, storage, *, keep_file: bool) -> None:
        client = storage.client

        # 1. Đọc được Shared Drive
        drive_root = client.execute(
            client.files.get(
                fileId=storage.drive_id, fields="id,name,driveId", supportsAllDrives=True
            )
        )
        client.execute(
            client.files.list(
                corpora="drive",
                driveId=storage.drive_id,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                pageSize=1,
                fields="files(id)",
            )
        )
        self.ok(f"Đọc được Shared Drive '{drive_root.get('name', storage.drive_id)}'.")

        # 2. Thư mục Portal/_healthcheck/
        folder_id = storage.healthcheck_folder()
        self.ok("Tìm/tạo được thư mục Portal/_healthcheck/.")

        # 3. Tạo file thử
        name = f"drive_check_{timezone.now():%Y%m%d_%H%M%S}.txt"
        stored = storage.upload_fileobj(
            folder_id,
            name,
            io.BytesIO(HEALTHCHECK_CONTENT),
            len(HEALTHCHECK_CONTENT),
            "text/plain",
            {"portal_healthcheck": "1"},
        )
        expected_sha = hashlib.sha256(HEALTHCHECK_CONTENT).hexdigest()
        if stored.sha256 == expected_sha:
            self.ok(f"Tạo được file thử {name} (sha256 khớp).")
        else:
            self.fail("SHA-256 của file thử không khớp.")

        meta = storage._file_meta(stored.storage_ref)
        if meta.get("driveId") == storage.drive_id:
            self.ok("File thử nằm trong đúng Shared Drive.")
        else:
            self.fail("File thử không nằm trong Shared Drive đã cấu hình.")

        content = b"".join(storage.open_stream(stored.storage_ref))
        if content == HEALTHCHECK_CONTENT:
            self.ok("Đọc lại nội dung file thử dạng stream: đúng.")
        else:
            self.fail("Nội dung đọc lại khác nội dung đã ghi.")

        # 4. Xóa file thử
        if keep_file:
            self.stdout.write(f"Giữ lại file thử (ID {stored.storage_ref}).")
        else:
            storage.delete_file(stored.storage_ref)
            if storage.missing_reason(stored.storage_ref) is not None:
                self.ok("Xóa được file thử.")
            else:
                self.fail("File thử vẫn còn sau khi xóa.")

        # 5. supportsAllDrives trên mọi lời gọi
        missing = [
            f"{method} {uri.split('?')[0]}"
            for method, uri in client.request_log
            if "supportsAllDrives=true" not in uri
        ]
        if missing:
            self.fail("Có lời gọi thiếu supportsAllDrives=true: " + ", ".join(missing))
        else:
            self.ok(f"Cả {len(client.request_log)} lời gọi Drive đều có supportsAllDrives=true.")
