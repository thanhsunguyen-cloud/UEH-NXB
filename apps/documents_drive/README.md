# apps/documents_drive (Gói giao việc M1)

Module này cài đặt `GoogleDriveStorage` tuân thủ giao diện `apps.core.storage.FileStorage`.

Lưu ý bắt buộc từ M0:
- Service account không có dung lượng lưu trữ riêng, chỉ ghi vào **Shared Drive** của NXB nơi service account có vai trò Content Manager.
- Mọi lời gọi Google Drive API bắt buộc truyền `supportsAllDrives=True`.
- Sử dụng Resumable Upload với `CHUNK_SIZE = 8 MiB` (bội số của 256 KiB).
