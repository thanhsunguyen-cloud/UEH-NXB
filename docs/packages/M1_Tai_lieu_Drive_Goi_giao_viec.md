# GÓI GIAO VIỆC M1 – TÀI LIỆU & GOOGLE DRIVE (kèm CR-001)
UEH Publishing Portal V2 · Đợt 2 · Người làm: **AI-1** · 01/12 – 13/12/2026 · Owner: Nguyễn Thanh Sử

> Đọc `docs/CONVENTIONS.md`, `docs/DATA_MODEL.md` và tài liệu này trước khi viết code. Làm việc trên mã nguồn M0 đã gộp vào `main`. Gặp điểm chưa rõ: ghi vào `docs/QUESTIONS.md`, chọn phương án đơn giản nhất, không mở rộng phạm vi.

## 1. Mục tiêu

1. **CR-001** – sửa nhỏ phần nền để hỗ trợ Google Drive và file không thuộc hồ sơ. Làm **trước tiên**, PR riêng, cần gộp chậm nhất **03/12** vì M6 và M7 phụ thuộc.
2. **M1** – cài `GoogleDriveStorage` để mọi tài liệu hồ sơ lưu trên Shared Drive của NXB, thay cho ổ đĩa local.
3. Bổ sung test cho các view upload/download của M0 (độ phủ `apps/core/views.py` hiện khoảng 43%).

## 2. CR-001 – thay đổi phần nền (Owner đã duyệt)

Nhánh `cr-001-storage`. Đây là ngoại lệ duy nhất được sửa file thuộc M0, và **chỉ** những chỗ sau:

| File | Thay đổi |
|---|---|
| `apps/core/storage.py` | `get_storage()`: khi `FILE_STORAGE_BACKEND == "gdrive"` thì `from apps.documents_drive.storage import GoogleDriveStorage` và trả về `GoogleDriveStorage()` (import bên trong hàm để tránh vòng import) |
| `apps/core/storage.py` | Thêm vào `FileStorage` Protocol và `LocalFileStorage` phương thức `save_library_file(category: str, filename: str, fileobj, size: int, mime_type: str) -> StoredFile` cho file nhỏ không thuộc hồ sơ. `category` chỉ nhận `"form_templates"` hoặc `"public_media"`. Lưu tại `library/<category>/<uuid>_<tên an toàn>`. Từ chối file > `MAX_LIBRARY_FILE_MB` (mặc định 10) và category khác |
| `portal/settings/base.py` | Thêm biến môi trường: `GDRIVE_SHARED_DRIVE_ID` (str, mặc định rỗng), `GDRIVE_CREDENTIALS_FILE` (str, rỗng = dùng Application Default Credentials của Cloud Run), `MAX_LIBRARY_FILE_MB` (int, 10) |
| `.env.example`, `README.md` | Thêm 3 biến trên và cách cấu hình |
| `tests/test_storage.py` | Test `save_library_file` (đúng, quá dung lượng, sai category, tên file nguy hiểm) và `get_storage()` trả đúng backend |

Không đổi chữ ký hay hành vi các hàm hiện có. CI phải xanh trước khi gộp.

## 3. M1 – GoogleDriveStorage

Toàn bộ code nằm trong `apps/documents_drive/` (`storage.py`, `client.py`, `management/commands/`). Thêm `google-api-python-client` và `google-auth` vào `pyproject.toml`.

### 3.1 Yêu cầu
- Cài đủ mọi phương thức của `FileStorage` Protocol, kể cả `save_library_file`.
- Xác thực bằng service account: file JSON tại `GDRIVE_CREDENTIALS_FILE`, nếu rỗng thì dùng Application Default Credentials (tài khoản dịch vụ gắn vào Cloud Run). Scope: `https://www.googleapis.com/auth/drive`.
- Chỉ ghi vào Shared Drive `GDRIVE_SHARED_DRIVE_ID`. **Mọi** lời gọi Drive API có `supportsAllDrives=True`; truy vấn danh sách có thêm `includeItemsFromAllDrives=True`, `corpora="drive"`, `driveId=...`.
- Cấu trúc thư mục trên Drive: `Portal/cases/<case_uuid>/<doc_type>/` và `Portal/library/<category>/`. Tìm thư mục bằng `appProperties` (`portal_case_id`, `portal_doc_type`), tạo khi chưa có. **Không** thêm model mới để lưu ID thư mục.
- Tên file trên Drive: `v<version>_<tên an toàn>`. `storage_ref` = Drive file ID.
- Upload: `start_upload` tạo phiên **resumable upload** của Drive và lưu URL phiên vào `UploadSession.backend_ref` (do service của M0 ghi). `append_chunk` gửi `PUT` kèm `Content-Range`; mọi phần trừ phần cuối phải là bội số 256 KiB (8 MiB thỏa mãn). `finish_upload` lấy file ID và `sha256Checksum` do Drive trả về; nếu Drive không trả, tính sha256 bằng cách đọc stream.
- `open_stream` đọc theo khối (`MediaIoBaseDownload` hoặc HTTP range), không nạp cả file vào RAM.
- `exists` trả `False` nếu file đã bị xóa, chuyển vào thùng rác hoặc ra khỏi Shared Drive.
- `abort_upload` hủy phiên resumable.
- Lỗi 429/5xx: thử lại tối đa 5 lần với thời gian chờ tăng dần. Lỗi quyền (403) hoặc không tìm thấy (404): ném `ValidationError` tiếng Việt, không lộ thông tin kỹ thuật ra người dùng.
- File bị xóa/di chuyển trên Drive: view tải xuống trả 404 (M0 đã xử lý qua `exists`), đồng thời ghi `AuditEvent` action `document.missing` (gọi `log_event` trong `GoogleDriveStorage` hoặc qua tín hiệu; không sửa view của M0).

### 3.2 Lệnh quản trị
- `python manage.py drive_check`: kiểm tra cấu hình thật (đọc được Shared Drive, tạo/xóa một file thử trong `Portal/_healthcheck/`, kiểm tra `supportsAllDrives`). In kết quả tiếng Việt. Owner dùng lệnh này trên môi trường thật.

### 3.3 Test (không gọi Drive thật trong CI)
- Dùng bản giả lập (`HttpMockSequence` của googleapiclient hoặc lớp fake tự viết).
- Upload 3 phần (8 MiB + 8 MiB + phần lẻ): đúng thứ tự `Content-Range`, đúng file ID, đúng sha256.
- Thử lại khi gặp 503 rồi thành công; dừng sau 5 lần.
- `exists` = `False` khi file trong thùng rác.
- Mọi lời gọi đều có `supportsAllDrives=True` (kiểm tra trên request đã ghi lại).
- `save_library_file` lên Drive.
- **Test view của M0** (đặt trong `tests/test_core_views.py`): begin → chunk → complete qua HTTP với `LocalFileStorage`; tải xuống không có `Content-Length`; người không có quyền nhận 404/403 đúng quy ước. Mục tiêu: độ phủ `apps/core/views.py` ≥ 80%.

## 4. Không làm
- Không đổi model, không tạo migration.
- Không sửa file M0 ngoài danh sách CR-001.
- Không chia sẻ thư mục Drive cho người ngoài, không tạo link "ai có link cũng xem được".
- Không làm màn hình nghiệp vụ.

## 5. Bàn giao và nghiệm thu
- [ ] PR `cr-001-storage` gộp trước 03/12, CI xanh.
- [ ] PR `m1-drive` (có thể chia 2 PR), CI xanh, độ phủ `apps/documents_drive` ≥ 85%.
- [ ] `docs/TEST_REPORT.md` bổ sung kết quả chạy thật của `pytest` và hướng dẫn chạy `drive_check`.
- [ ] Owner chạy `drive_check` trên Shared Drive thật: đạt.
- [ ] Owner bật `FILE_STORAGE_BACKEND=gdrive`, tải lên một file 50 MB qua giao diện thử, tải xuống được, sha256 khớp.
