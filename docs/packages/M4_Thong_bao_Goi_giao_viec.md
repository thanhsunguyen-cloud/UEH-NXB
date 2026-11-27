# GÓI GIAO VIỆC M4 – THÔNG BÁO EMAIL
UEH Publishing Portal V2 · Người làm: **AI-5 (ChatGPT/Codex)** · từ 26/11/2026, khoảng 1 tuần · Owner: Nguyễn Thanh Sử

> Đọc `docs/CONVENTIONS.md`, `docs/DATA_MODEL.md` và tài liệu này trước khi viết code. Nhánh `m4-notifications`. Chỉ sửa trong `apps/notifications/`, `templates/notifications/` và thêm test trong `tests/`. Không sửa phần nền M0 (`apps/core`, `apps/accounts`, `portal/settings`) ngoài 1 dòng ở mục 2. Không tạo model, không tạo migration. Gặp điểm chưa rõ: ghi vào `docs/QUESTIONS.md`, chọn phương án đơn giản nhất.

## 1. Mục tiêu

Gửi email tự động bằng tiếng Việt khi hồ sơ đổi trạng thái, để khách hàng (người đại diện) và biên tập viên biết việc cần làm. M4 **chỉ lắng nghe** tín hiệu có sẵn của M0, không sửa luồng nghiệp vụ.

## 2. Nguồn sự kiện

- Tín hiệu `apps.core.signals.case_status_changed`, gửi kèm `case`, `from_status`, `to_status`, `actor`, `note`. M0 phát tín hiệu này **sau khi giao dịch đã lưu** (`transaction.on_commit`), mỗi lần đổi trạng thái thành công một lần.
- Tạo `apps/notifications/apps.py` với `NotificationsConfig` và kết nối bộ nhận trong `ready()`. App này **chưa** có trong `INSTALLED_APPS`: được phép sửa đúng 1 dòng ngoài app, thêm `"apps.notifications.apps.NotificationsConfig",` vào cuối danh sách module nội bộ trong `portal/settings/base.py`, và ghi rõ dòng này trong mô tả pull request.

## 3. Quy tắc gửi

| Trạng thái mới (`to_status`) | Gửi cho | Nội dung chính |
|---|---|---|
| `SUBMITTED` | Biên tập viên phụ trách chính; nếu chưa có thì mọi EDITOR đang hoạt động | Có hồ sơ mới/hồ sơ đã bổ sung, tên sách, mã hiển thị, người đại diện |
| `NEED_SUPPLEMENT` | Người đại diện (`case.owner`) | NXB yêu cầu bổ sung; trích `note` (nội dung yêu cầu) |
| `ACCEPTED` | Người đại diện | Hồ sơ đã được tiếp nhận, kèm mã NXB |
| `REVISION_REQUIRED` | Người đại diện | Cần chỉnh sửa bản thảo; trích `note` |
| `REVIEW_APPROVED` | Người đại diện | Bản thảo đã được duyệt |
| `REJECTED` | Người đại diện | Hồ sơ không được chấp nhận; trích `note` nếu có |
| `REGISTERED` | Người đại diện | Đã đăng ký xuất bản, kèm ISBN |
| `DECISION_ISSUED` | Người đại diện | Đã có quyết định xuất bản |
| `COMPLETED` | Người đại diện | Hồ sơ hoàn tất |
| Trạng thái khác (`EDITING`, `DEPOSITED`, `ARCHIVED`, `DRAFT`) | Không gửi | – |

Quy tắc bổ sung:
- Không gửi cho chính người vừa thực hiện thao tác (`actor`).
- Không gửi cho tài khoản bị khóa (`is_active=False`) hoặc không có email.
- Ghi chú (`note`) chỉ đưa vào email gửi khách hàng ở các trạng thái `NEED_SUPPLEMENT`, `REVISION_REQUIRED`, `REJECTED`. Không bao giờ đưa ghi chú nội bộ (`CaseNote` có `visibility=INTERNAL`) vào email khách hàng.
- **Không đưa số liệu tài chính** vào bất kỳ email nào.
- Khách hàng thấy nhãn trạng thái dễ hiểu (ví dụ "NXB đang biên tập"), không thấy mã kỹ thuật.

## 4. Nội dung email

- Mỗi loại email có 2 template: `templates/notifications/<loai>.txt` (văn bản) và `<loai>.html` (HTML đơn giản, không ảnh, không CSS ngoài). Gửi bằng `EmailMultiAlternatives`, người gửi `settings.DEFAULT_FROM_EMAIL`.
- Tiêu đề có tiền tố `[NXB Kinh tế TP.HCM]` và mã hiển thị hồ sơ (`case.display_code`).
- Có đường dẫn mở hồ sơ: khách hàng → `customer:case_detail`, biên tập viên → `backoffice:case_detail`, ghép với địa chỉ gốc đọc từ biến môi trường `PORTAL_BASE_URL` (đọc trong `apps/notifications/conf.py` bằng `os.environ`, mặc định `http://localhost:8000`). Thêm biến này vào `.env.example` kèm chú thích (được phép sửa file này).
- Cuối email: "Đây là email tự động, vui lòng không trả lời." và thông tin liên hệ chung của NXB để trống dạng `[CẦN NXB CUNG CẤP]`.

## 5. Độ tin cậy

- Gửi email **không được làm hỏng** thao tác đổi trạng thái: bắt mọi lỗi gửi, ghi `log_event` action `email.failed` (kèm loại email, người nhận, lỗi rút gọn) rồi bỏ qua.
- Gửi thành công ghi `log_event` action `email.sent` (loại email, người nhận, mã hồ sơ). Không ghi nội dung email vào nhật ký.
- Không dùng hàng đợi hay thư viện ngoài (không Celery). Gửi trực tiếp trong bộ nhận tín hiệu.

## 6. Test bắt buộc (pytest, dùng `mail.outbox` của Django)

- Mỗi dòng của bảng mục 3: đúng người nhận, đúng tiêu đề, có đường dẫn đúng.
- Trạng thái không gửi: `mail.outbox` rỗng.
- Không gửi cho `actor`, tài khoản bị khóa, tài khoản không có email.
- Email khách hàng không chứa ghi chú nội bộ, không chứa số tiền, không chứa mã trạng thái kỹ thuật.
- Lỗi khi gửi (giả lập backend ném lỗi): `change_status` vẫn thành công, có `AuditEvent` `email.failed`.
- Thông qua `change_status` thật của M0 (không gọi bộ nhận trực tiếp) ở ít nhất 3 test.
- Độ phủ `apps/notifications` ≥ 90%.

## 7. Không làm

- Không gửi SMS, không thông báo trong trang, không nhắc việc theo lịch (để giai đoạn 2).
- Không sửa `apps/core`, `apps/accounts`, `portal/settings` ngoài 1 dòng ở mục 2; không tạo model, migration.
- Không gửi email về tài chính, in ấn, phát hành.

## 8. Bàn giao

- [ ] Pull request `m4-notifications` vào `main`, CI xanh (cả `lint-and-test` và `docker-smoke`).
- [ ] Mô tả pull request bằng tiếng Việt: danh sách loại email, cách thử bằng Mailpit (`http://localhost:8025`).
- [ ] `docs/TEST_REPORT.md` bổ sung kết quả chạy thật.
