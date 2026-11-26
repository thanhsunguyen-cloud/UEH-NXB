# CÁC ĐIỂM ĐÃ TỰ QUYẾT ĐỊNH TRONG M0 (QUESTIONS & DECISIONS)

Theo nguyên tắc tài liệu giao việc M0: khi gặp điểm cần làm rõ, chọn phương án đơn giản nhất, không mở rộng phạm vi và ghi lại tại đây để Owner xem xét.

1. **Cách tính `outstanding(receivable)` khi có bút toán điều chỉnh `Receivable(is_adjustment=True, adjusts=parent)`:**
   - *Quyết định:* `effective_receivable_amount(rec) = rec.amount + sum(rec.adjustments.amount)` và `outstanding(rec) = effective_receivable_amount(rec) - sum(rec.collections.amount)`.
   - *Lý do:* Nếu không có bút toán điều chỉnh gắn vào `adjusts`, công thức thu gọn về đúng `amount - tổng collections`. Nếu có bút toán điều chỉnh giảm/tăng gắn vào `adjusts`, số dư công nợ và trạng thái `PAID / PARTIAL / OVERDUE` của khoản gốc phản ánh đúng ngay lập tức mà không cần xóa hay sửa khoản gốc.

2. **Tính `is_current` của `Document` khi có `form_code`:**
   - *Quyết định:* Ràng buộc duy nhất `(case, doc_type, form_code, version)` và chuyển `is_current=False` cho các bản cũ cùng bộ `(case, doc_type, form_code)`.
   - *Lý do:* Mục 5.5 quy định bộ biểu mẫu `BIZ-F4-01…12` dùng chung `doc_type = OTHER` kết hợp `form_code` khác nhau. Việc nhóm `is_current` theo cả `form_code` giúp các biểu mẫu `OTHER` khác mã không vô tình ghi đè trạng thái hiện hành của nhau.

3. **Truy cập `/django-admin/` cho các vai trò:**
   - *Quyết định:* Dùng `PortalAdminSite` tùy biến kế thừa `AdminSite`, chỉ cho phép `user.role == ADMIN` đăng nhập `/django-admin/`.
   - *Lý do:* Đáp ứng chặt chẽ mục 10 ("Django admin chỉ cho ADMIN") và tránh rò rỉ quyền qua cờ `is_staff` mặc định của Django.

4. **Hiển thị nút đăng nhập Google và mật khẩu trên trang `/tai-khoan/dang-nhap/`:**
   - *Quyết định:* Tách rõ 2 khối trên cùng một trang: khối trên cho nhân sự (`@ueh.edu.vn` qua Google OAuth) và khối dưới cho khách hàng (Email + Mật khẩu). Nếu nhân sự nhập mật khẩu, backend từ chối ngay và báo rõ phải dùng Google `@ueh.edu.vn`.
   - *Lý do:* Đơn giản, trực quan, đúng mục 5.1 và 12.7.

5. **Kiểm soát vượt mức phải thu khi ghi nhận `Collection`:**
   - *Quyết định:* Hàm `create_collection(..., confirm_overpayment=False)` từ chối nếu tổng đã thu sau khi ghi nhận vượt quá `effective_receivable_amount(receivable)`, trừ khi đồng thời `confirm_overpayment=True` và `note` không rỗng.
   - *Lý do:* Đáp ứng chính xác quy tắc mục 5.14 ("Tổng đã thu không được vượt amount trừ khi có ghi chú và người dùng xác nhận").


---

# M7 – QUẢN TRỊ HỆ THỐNG: ĐIỂM CHƯA RÕ (chờ Owner quyết)

Các điểm dưới đây **chưa được Owner chốt**. Mã hiện tạm làm theo cột "Đang làm tạm" để có thể test; đổi lại rất nhanh nếu Owner chọn khác.

| # | Câu hỏi | Đang làm tạm | Phương án khác |
|---|---|---|---|
| Q1 | Có cho đổi tài khoản nhân sự (EDITOR/ADMIN) về CUSTOMER không? Gói chỉ nói về chiều CUSTOMER → nhân sự. | Không cho; ô "Vai trò" của nhân sự chỉ có EDITOR/ADMIN, muốn ngừng thì khóa. | Cho đổi về CUSTOMER (khi đó tài khoản không có mật khẩu, người dùng phải tự đặt lại). |
| Q2 | Khi đổi CUSTOMER (email @ueh.edu.vn) thành EDITOR/ADMIN, có xóa mật khẩu cũ không? | Có: đặt mật khẩu "không dùng được", nhân sự chỉ đăng nhập Google (M0 vốn đã chặn đăng nhập mật khẩu cho nhân sự). | Giữ nguyên mật khẩu cũ. |
| Q3 | Thêm phiên bản biểu mẫu mới có tự áp dụng ngay không? | Có ô "Áp dụng ngay", mặc định được chọn; nếu chọn thì tự tắt bản đang áp dụng cùng mã. | Luôn tạo ở trạng thái tắt, Admin bật sau; hoặc luôn áp dụng ngay. |
| Q4 | Có chặn trùng (mã, phiên bản) không? Model không có ràng buộc duy nhất. | Chặn, báo "Mã … đã có phiên bản …". | Cho trùng. |
| Q5 | `partials/pagination.html` (M0) tạo link `?page=N` nên mất điều kiện lọc khi trình duyệt tắt JavaScript. | Bọc partial bằng HTMX (`hx-include` form lọc) nên khi có JavaScript vẫn giữ bộ lọc; không sửa file M0. | Gửi Change Request để partial giữ tham số lọc. |
| Q6 | Lọc nhật ký theo "người thực hiện": danh sách chọn hay ô tìm? | Ô tìm theo tên/email (danh sách người dùng có thể dài). | Danh sách chọn. |
| Q7 | Trường `data` của nhật ký với action ngoài các nhóm đã nêu (ví dụ `status.*` hoặc nhóm "khác" chưa biết). | Chỉ hiện `data` cho `user.*`, `auth.*`, `catalog.*`, `form_template.*`; mọi nhóm khác đều ẩn (an toàn hơn). | Hiện cho mọi nhóm trừ `case.*`, `document.*`, `finance.*`. |
| Q8 | CI hiện chỉ đo độ phủ `apps/core`. Có thêm `--cov=apps/administration` vào `.github/workflows/ci.yml` không? (gói M7 chỉ cho sửa trong `apps/administration/`, `templates/administration/`) | Không sửa CI; độ phủ M7 đo bằng lệnh riêng trong `docs/TEST_REPORT.md` (100%). | Owner cho phép sửa CI. |
| Q9 | Tạo pull request khi nào? `save_library_file` (CR-001) chưa có trên `main`; trước khi có, nút "Thêm phiên bản" trên môi trường thật sẽ lỗi. | Chờ CR-001 vào `main`, cập nhật nhánh, chạy lại toàn bộ kiểm tra rồi mới mở PR. | Mở PR nháp ngay để CI chạy. |
