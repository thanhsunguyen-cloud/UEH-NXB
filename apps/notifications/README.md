# apps/notifications (Gói giao việc M4 – Thông báo email)

Lắng nghe tín hiệu `apps.core.signals.case_status_changed` (M0 phát sau khi giao dịch đã lưu) và gửi email tiếng Việt.

- `emails.py`: bảng quy tắc `EMAIL_RULES` (trạng thái mới → loại email, người nhận), nhãn trạng thái dễ hiểu, hàm gửi.
- `receivers.py`: bộ nhận tín hiệu, bắt mọi lỗi để không làm hỏng thao tác đổi trạng thái.
- `conf.py`: đọc `PORTAL_BASE_URL` (mặc định `http://localhost:8000`).
- Template: `templates/notifications/<loai>.txt` và `<loai>.html`.

Người nhận: biên tập viên phụ trách (hoặc mọi EDITOR đang hoạt động) khi hồ sơ được nộp; người đại diện `case.owner` cho các trạng thái còn lại. Không gửi cho `Contributor`, người thao tác, tài khoản bị khóa hoặc không có email.
Nhật ký: `email.sent` / `email.failed` (không ghi nội dung email).
