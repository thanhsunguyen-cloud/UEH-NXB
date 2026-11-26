# apps/documents_drive (Gói giao việc M1)

`GoogleDriveStorage` cài đặt đủ giao diện `apps.core.storage.FileStorage` (kể cả `save_library_file`) trên **Shared Drive** của NXB. Bật bằng `FILE_STORAGE_BACKEND=gdrive`.

## Cấu hình
- `GDRIVE_SHARED_DRIVE_ID`: ID Shared Drive; service account cần vai trò **Content Manager**.
- `GDRIVE_CREDENTIALS_FILE`: file JSON service account; để trống = Application Default Credentials (Cloud Run). Scope `https://www.googleapis.com/auth/drive`.

## Cấu trúc trên Drive
```
Portal/cases/<case_uuid>/<doc_type>/v<version>_<tên an toàn>
Portal/library/<category>/<uuid>_<tên an toàn>
Portal/_healthcheck/                       (lệnh drive_check)
```
Thư mục được tìm theo `appProperties` (`portal_folder`, `portal_case_id`, `portal_doc_type`, `portal_library_category`) và tạo khi chưa có; không lưu ID thư mục vào DB. `storage_ref` = Drive file ID, `UploadSession.backend_ref` = URL phiên resumable upload.

## Hành vi chính
- Mọi lời gọi có `supportsAllDrives=true`; truy vấn danh sách có thêm `includeItemsFromAllDrives=true`, `corpora=drive`, `driveId=...`.
- Upload: resumable upload, mỗi `append_chunk` gửi một `PUT` kèm `Content-Range` (phần giữa là bội số 256 KiB). Tổng dung lượng lấy từ `UploadSession.total_size`. `finish_upload` hỏi trạng thái phiên để lấy file ID, đổi tên thành `v<version>_...`, dùng `sha256Checksum` của Drive (nếu thiếu thì đọc stream để tính).
- Lỗi 429/5xx/403 vượt hạn mức: tổng cộng tối đa 5 lần gọi, chờ 1-2-4-8 giây. Khi gửi lại một phần dữ liệu, hệ thống hỏi Drive đã nhận tới đâu rồi gửi tiếp phần còn thiếu.
- Lỗi 403/404/khác: `DriveApiError` (là `ValidationError`) có thông báo tiếng Việt; chi tiết kỹ thuật chỉ ghi vào log.
- `open_stream` đọc theo HTTP Range, mỗi khối 4 MiB.
- `exists` = `False` khi file bị xóa, nằm trong thùng rác, ra khỏi Shared Drive hoặc không còn quyền truy cập, đồng thời ghi `AuditEvent` `document.missing`.
- `abort_upload` hủy phiên resumable; nếu Drive đã nhận đủ dữ liệu (file mồ côi) thì xóa file đó.

## Kiểm tra trên môi trường thật
```bash
python manage.py drive_check            # tạo rồi xóa file thử trong Portal/_healthcheck/
python manage.py drive_check --keep-file
```
Lệnh in từng bước `[ĐẠT]` / `[LỖI]`, kết thúc bằng `drive_check: TẤT CẢ ĐẠT.`, hoặc trả mã lỗi ≠ 0 nếu có bước không đạt.
