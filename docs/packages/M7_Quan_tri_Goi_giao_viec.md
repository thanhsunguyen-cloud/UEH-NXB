# GÓI GIAO VIỆC M7 – QUẢN TRỊ HỆ THỐNG
UEH Publishing Portal V2 · Đợt 2 · Người làm: **AI-2** · 01/12 – 13/12/2026 · Owner: Nguyễn Thanh Sử

> Đọc `docs/CONVENTIONS.md`, `docs/DATA_MODEL.md` và tài liệu này trước khi viết code. Nhánh `m7-admin`. Chỉ sửa trong `apps/administration/` và `templates/administration/`. Mọi view kế thừa `AdminRequiredMixin`. Không tạo migration.

## 1. Mục tiêu

Thay 4 trang placeholder dưới `/quan-tri/` bằng màn hình thật để Admin quản lý tài khoản, danh mục, biểu mẫu tải về và xem nhật ký hệ thống. Admin chỉ quản lý **hệ thống**, không xem nội dung hồ sơ.

## 2. Màn hình

### 2.1 Người dùng – `administration:home` (`/quan-tri/`)
- Danh sách người dùng: họ tên, email, vai trò, quyền tài chính, trạng thái (hoạt động/khóa), lần đăng nhập cuối. Lọc theo vai trò, trạng thái; tìm theo tên/email; phân trang (dùng `partials/pagination.html`). Lọc và tìm bằng HTMX.
- **Tạo tài khoản nhân sự**: email (bắt buộc đuôi `@` + `STAFF_GOOGLE_DOMAIN`), họ tên, vai trò EDITOR hoặc ADMIN, quyền tài chính (chỉ cho EDITOR). Không có ô mật khẩu: nhân sự đăng nhập bằng Google.
- **Sửa tài khoản**: đổi vai trò, đổi quyền tài chính, khóa/mở khóa.
- Ràng buộc:
  - Không tự hạ quyền hoặc tự khóa chính mình.
  - Luôn còn ít nhất **2 ADMIN đang hoạt động**; thao tác làm số Admin hoạt động < 2 bị từ chối kèm thông báo.
  - Đổi một CUSTOMER thành EDITOR/ADMIN chỉ khi email đúng domain UEH.
  - Không xóa tài khoản (chỉ khóa).
- Mỗi thao tác ghi `log_event` với action: `user.create`, `user.role_change`, `user.finance_access_change`, `user.lock`, `user.unlock`, kèm `before`/`after`.

### 2.2 Danh mục – `administration:catalogs` (`/quan-tri/danh-muc/`)
- 3 tab: Thể loại (`Category`), Lĩnh vực (`Field`), Loại phí (`FeeType`).
- Thêm, sửa tên, đổi thứ tự (`sort_order`), bật/tắt (`is_active`). **Không xóa**; mục đang dùng chỉ được tắt.
- Ghi `log_event` action `catalog.create` / `catalog.update`.

### 2.3 Biểu mẫu tải về – `administration:templates` (`/quan-tri/bieu-mau/`)
- Danh sách `FormTemplate` nhóm theo `code`: phiên bản, ngày hiệu lực, đang áp dụng hay không, tên file.
- **Thêm phiên bản mới**: mã (`MAU_1`…`MAU_9`, `BIZ_F4_01`…`BIZ_F4_12`, hoặc mã khác đúng định dạng `[A-Z0-9_]{3,30}`), tên, phiên bản, ngày hiệu lực, file (.doc, .docx, .xls, .xlsx, .pdf; ≤ `MAX_LIBRARY_FILE_MB`). Lưu file bằng `get_storage().save_library_file("form_templates", ...)` (có sau CR-001, dự kiến gộp 03/12; trước đó làm giao diện và test với bản giả).
- Bật/tắt áp dụng. Khi bật một phiên bản, tự tắt các phiên bản khác cùng `code` (một mã chỉ có một bản đang áp dụng).
- Admin tải về để kiểm tra qua view của module (stream, có kiểm tra `AdminRequiredMixin`).
- Ghi `log_event` action `form_template.create` / `form_template.activate` / `form_template.deactivate`.

### 2.4 Nhật ký hệ thống – `administration:audit_logs` (`/quan-tri/nhat-ky/`)
- Bảng `AuditEvent` mới nhất trước: thời điểm, người thực hiện, action, đối tượng, mã hồ sơ (`display_code`), IP.
- Lọc theo khoảng ngày, người thực hiện, nhóm action (`case.*`, `document.*`, `finance.*`, `user.*`, `auth.*`, khác); phân trang 50 dòng.
- **Bảo vệ nội dung hồ sơ:** với action thuộc `case.*`, `document.*`, `finance.*`, **không hiển thị** trường `data` (chỉ hiện mã hồ sơ và loại thao tác). Trường `data` chỉ hiện cho `user.*`, `auth.*`, `catalog.*`, `form_template.*`.
- Chỉ đọc. Không có nút sửa/xóa.

## 3. Giao diện
- Kế thừa `base.html`, Bootstrap 5 + HTMX, tiếng Việt, dùng tốt trên điện thoại.
- Form lỗi hiển thị thông báo tiếng Việt cạnh ô nhập; thao tác thành công dùng `messages`.

## 4. Test bắt buộc (pytest)
- Mọi URL của M7: CUSTOMER và EDITOR nhận 404, chưa đăng nhập bị chuyển tới trang đăng nhập.
- Tạo nhân sự với email ngoài domain UEH bị từ chối.
- Không thể làm số Admin hoạt động < 2; không tự khóa mình.
- Đổi vai trò, quyền tài chính, khóa/mở đều ghi đúng `AuditEvent`.
- Danh mục: không có đường xóa; tắt mục đang dùng được.
- Biểu mẫu: kích hoạt bản mới tự tắt bản cũ cùng mã; từ chối file sai định dạng/quá dung lượng.
- Nhật ký: action `case.*` không lộ `data` trong HTML trả về.
- Độ phủ `apps/administration` ≥ 85%.

## 5. Không làm
- Không xem, sửa nội dung hồ sơ, tài liệu, tài chính.
- Không cài màn hình đặt mật khẩu cho nhân sự.
- Không tạo migration, không sửa file M0.

## 6. Bàn giao
- [ ] PR `m7-admin`, CI xanh, `docs/TEST_REPORT.md` có kết quả chạy thật.
- [ ] Owner đăng nhập bằng tài khoản Admin mẫu, tạo một biên tập viên, gán quyền tài chính, thêm một phiên bản Mẫu 2, xem nhật ký thấy đủ các thao tác vừa làm.
