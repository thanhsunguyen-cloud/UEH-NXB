# CÂU HỎI & QUYẾT ĐỊNH TẠM CỦA GÓI M2 – CỔNG KHÁCH HÀNG

Theo gói giao việc: gặp điểm chưa rõ thì chọn phương án đơn giản nhất, làm tiếp và ghi lại đây để Owner xem xét.

1. **Phân trang làm mất bộ lọc.** `partials/pagination.html` (M0) chỉ tạo link `?page=N`, nên khi đang lọc theo trạng thái hoặc tìm kiếm mà sang trang 2 thì mất bộ lọc.
   - *Tạm thời:* vẫn dùng partial của M0 đúng như gói yêu cầu (khách thường có ít hồ sơ, hiếm khi quá 20).
   - *Đề xuất:* M0 sửa partial để giữ các tham số GET khác (Change Request).

2. **Trang "Tải biểu mẫu" công khai chưa có.** Chưa có URL `public_site:forms` (M6 chưa làm).
   - *Tạm thời:* hàm `public_forms_url()` thử `public_site:forms`, nếu chưa có thì trỏ về trang chủ công khai `public_site:home`. Khi M6 thêm URL `forms`, link tự đúng, không cần sửa M2.

3. **Ô tải lên khi REVISION_REQUIRED.** `can_upload` của M0 cho khách tải mọi loại (Bản thảo, Mẫu 1/2/3, khác) ở REVISION_REQUIRED, còn gói mô tả khối riêng "ô tải bản thảo mới".
   - *Tạm thời:* ở REVISION_REQUIRED chỉ hiện **một ô tải Bản thảo** trong khối "Nộp bản thảo đã chỉnh sửa"; bảng tài liệu không hiện ô tải. (Endpoint upload của M0 vẫn theo `can_upload`, M2 không đổi quyền.)

4. **Chặn sửa khi trạng thái không cho phép.** Khi `can_edit_case_info` = False, các URL sửa thông tin/thêm/sửa/xóa tác giả **chuyển về trang chi tiết kèm thông báo lỗi** (không trả 403/404, vì hồ sơ vẫn thuộc về khách). Không có thay đổi dữ liệu, không ghi AuditEvent.

5. **Xóa tác giả** là xóa thật bản ghi `Contributor` (gói cho phép "thêm/sửa/xóa"); dữ liệu trước khi xóa được lưu trong `AuditEvent case.contributor_remove`.

6. **Nhãn điều kiện nộp.** Danh sách điều kiện trên trang được tính trong `apps/customer/views.py::submit_checklist`, khớp với `_check_submit` của M0 (có test đối chiếu). Khi bấm nộp thiếu điều kiện, thông báo lỗi lấy nguyên văn từ `WorkflowError` của M0 (có kèm mã kỹ thuật như "(MANUSCRIPT)").
   - *Đề xuất:* nếu muốn thông báo thân thiện hơn cho khách, M0 bỏ mã kỹ thuật trong chuỗi lỗi.

7. **Gửi trao đổi với NXB** được phép ở mọi trạng thái của hồ sơ (gói không giới hạn).

8. **Hủy hồ sơ nháp:** chưa làm theo mục 2.4. Đề xuất cân nhắc chức năng "hủy" (trạng thái mới hoặc ẩn hồ sơ nháp) ở đợt sau vì khách có thể tạo nhầm hồ sơ và không xóa được.

9. **Dòng thời gian** hiện thêm mốc "Tạo hồ sơ" (lấy `created_at`), ngoài các bản ghi `StatusHistory`.
