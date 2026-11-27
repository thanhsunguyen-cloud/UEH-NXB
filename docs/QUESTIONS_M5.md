# Câu hỏi và quyết định tạm thời – M5 Tra cứu, Thống kê, Nhập Excel (AI-8)

Các điểm chưa rõ trong gói M5. Mỗi điểm đã chọn phương án đơn giản nhất để làm tiếp; Owner xác nhận hoặc điều chỉnh sau.

1. **Hồ sơ Nháp trong Tra cứu.** Mặc định không hiện hồ sơ DRAFT (giống danh sách M3); chọn bộ lọc trạng thái "Nháp" thì mới hiện.

2. **Trạng thái nào được tính vào Thống kê.** Không lọc theo trạng thái: mọi đầu sách có ngày tính thống kê (`decision_date`, nếu trống thì `registration_date`) trong khoảng ngày đều được tính. Theo quy trình M0, hồ sơ đã có ngày XNĐK/QĐXB không thể về trạng thái Từ chối, nên không cần loại trừ thêm.

3. **Chuyển dữ liệu giữa Bước 1 (Kiểm tra) và Bước 2 (Xác nhận).** Để bước kiểm tra *không ghi gì* (kể cả bảng phiên `django_session` và kho tệp), dữ liệu các dòng đã đọc được ký bằng `django.core.signing` (nén, có hạn 1 giờ, gắn với người kiểm tra) và đặt vào trường ẩn của form xác nhận. Bước 2 **kiểm tra lại toàn bộ** (ISBN trùng, danh mục…) trong `transaction.atomic()` rồi mới nhập. Không cần tải lại file.

4. **Cột "Ghi chú"** không có trường tương ứng trong `PublicationCase`. Nếu có nội dung, tạo 1 `CaseNote` nội bộ (`INTERNAL`, tác giả là BTV nhập).

5. **Cột "Lần xuất bản"** để trống = 1; lớn hơn 1 thì đánh dấu `is_reprint=True`.

6. **Cột "Hình thức"** để trống = Tự xuất bản. "Liên kết" mà thiếu "Đơn vị liên kết" là lỗi (giống ràng buộc `PublicationCase.clean()`).

7. **"Ngôn ngữ"** để trống = "Tiếng Việt" (mặc định của model).

8. **ISBN** dùng `apps.core.codes.normalize_isbn` (chỉ nhận ISBN-13; ISBN-10 báo "Vui lòng nhập ISBN-13"). Trùng ISBN trong cùng file: dòng xuất hiện sau bị báo lỗi.

9. **Dòng tiêu đề** so khớp không phân biệt hoa thường, bỏ dấu `*` và khoảng trắng thừa; cột lạ bị bỏ qua. Chỉ đọc sheet đầu tiên. File mẫu có thêm sheet "Hướng dẫn".

10. **Lọc "Nguồn: Nhập Excel"** dựa vào `ImportBatch.case_ids` (gộp tất cả các lô), "Portal" là phần còn lại.

11. **Tên action nhật ký:** `report.export`, `case.import`, `import.batch` theo đúng gói. `case.import` lưu `batch_id`, số dòng, trạng thái; `report.export` lưu bộ lọc và tổng số đầu sách.

12. **Xuất Excel "dạng stream":** file được tạo bằng openpyxl chế độ `write_only` vào `SpooledTemporaryFile` và trả bằng `FileResponse` (stream theo khối).

13. **Quyền trang Nhập Excel / File mẫu / Lịch sử nhập** dùng `PublicationStatsMixin` (chỉ EDITOR). Gói chưa nói BTV nào được nhập; hiện mọi EDITOR đều nhập được.

14. **Menu:** không sửa `templates/partials/nav.html` (M0). Trang Nhập Excel và Lịch sử nhập được mở qua thanh tab ở đầu các trang M5 (Tra cứu, Danh mục xuất bản). *Hỏi:* có muốn thêm mục menu "Nhập Excel" vào nav M0 qua Change Request không?

15. **Biểu đồ theo kỳ** liệt kê đủ mọi kỳ trong khoảng (kỳ trống = 0), tối đa 600 kỳ.
