# Câu hỏi và quyết định tạm thời – M3 Tác nghiệp BTV (AI-7)

Các điểm chưa rõ trong gói M3. Mỗi điểm đã chọn phương án đơn giản nhất để làm tiếp; Owner xác nhận hoặc điều chỉnh sau.

1. **Nhóm "Khách đã bổ sung" trên trang Hồ sơ cần xử lý.**
   Định nghĩa đang dùng: hồ sơ SUBMITTED, đã từng chuyển sang NEED_SUPPLEMENT (có `StatusHistory`), và `SupplementRequest` mới nhất ở trạng thái RESOLVED.
   Nếu khách nộp lại mà yêu cầu vẫn OPEN (M2 không tự đánh dấu RESOLVED), hồ sơ hiện trong nhóm "Mới nộp". BTV có thể đánh dấu RESOLVED thủ công ở tab Ghi chú.
   *Hỏi:* M2 có tự đánh dấu RESOLVED khi khách nộp lại không?

2. **Nhóm "Khách đã nộp bản thảo sửa".** Phiên bản dùng để so sánh là bản thảo của lần duyệt Mẫu 4 **mới nhất**, cùng cách với validator `_check_revision_to_editing` của M0.

3. **Giao BTV và đổi người đại diện khi hồ sơ COMPLETED/ARCHIVED.** Gói chỉ nói "form sửa khi `can_edit_case_info`". M3 áp dụng cùng điều kiện cho giao BTV, đổi người đại diện và sửa tác giả, nên các thao tác này bị chặn khi hồ sơ đã hoàn tất hoặc lưu trữ.

4. **Nút chuyển trạng thái khi còn thiếu điều kiện.** Nút vẫn bấm được, nhưng danh sách điều kiện còn thiếu hiện ngay cạnh nút và trong hộp thoại. Máy chủ (`change_status`) chặn và báo lỗi tiếng Việt.

5. **Danh sách điều kiện còn thiếu** được lấy bằng cách gọi validator trong `apps.core.workflow.TRANSITIONS` (chỉ đọc, không sửa M0). Riêng "Yêu cầu bổ sung" không hiện điều kiện thiếu, vì nội dung được nhập trong hộp thoại.

6. **Tên action nhật ký mới** (gói không quy định): `contributor.add`, `contributor.update`, `contributor.delete`, `supplement.create`, `supplement.resolve`. Các action gói có quy định được dùng đúng tên: `case.update`, `case.assign_editor`, `case.note_add`. Hai action do M0 tự ghi: `case.owner_change`, `case.manuscript_review`.

7. **`case.update` chỉ ghi các trường thực sự thay đổi** (`before`/`after`). Lưu form mà không thay đổi gì thì không ghi nhật ký.

8. **Tải lên trong tab Tài liệu:** dùng một partial `chunked_upload.html` và một ô chọn loại tài liệu (cập nhật `data-doc-type`). Upload xong thì tải lại trang ở tab Tài liệu. Chưa có ô "ghi chú" khi tải lên, vì partial M0 luôn gửi `note=""`. Muốn có ghi chú thì cần Change Request cho M0.

9. **Hồ sơ ADMIN/CUSTOMER:** mọi URL M3 trả 404 nhờ `EditorRequiredMixin` (kể cả khách hàng là chủ hồ sơ).

10. **Môi trường thử:** `base.html` không gửi `X-CSRFToken` cho HTMX. Vì vậy M3 chỉ dùng HTMX cho GET (lọc, tìm, phân trang). Mọi thao tác ghi dùng form POST thường có `{% csrf_token %}`.
