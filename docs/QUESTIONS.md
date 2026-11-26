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
