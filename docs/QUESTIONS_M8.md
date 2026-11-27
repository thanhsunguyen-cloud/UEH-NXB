# Câu hỏi và quyết định tạm – M8 Tài chính & Công nợ

Mỗi mục: điểm chưa rõ → phương án đơn giản nhất đã chọn. Owner/nhóm trưởng xem lại và báo nếu cần đổi.

1. **Ngày của bút toán điều chỉnh trong Tổng quan.** Bút toán điều chỉnh là một `Receivable` riêng nên được tính vào kỳ theo ngày của chính nó (ngày chứng từ, trống thì ngày tạo), không theo ngày của khoản gốc. Cộng trọn đời thì tổng vẫn khớp `effective_receivable_amount`.
2. **Còn nợ tại ngày cuối kỳ** = tổng mọi `Receivable` (cả điều chỉnh) có ngày ≤ cuối kỳ − tổng mọi `Collection` (cả bút toán đảo) có `paid_date` ≤ cuối kỳ, áp cùng bộ lọc loại phí/hình thức. Khoản thu vượt làm số nợ âm và bù trừ vào tổng (không tách riêng "tiền thu thừa").
3. **Danh sách công nợ tính bằng hàm M0 cho từng khoản** (`outstanding`, `aging_bucket`, `receivable_status`), lọc `outstanding > 0` bằng Python. Đúng yêu cầu "chỉ dùng hàm M0", nhưng mỗi khoản tốn vài truy vấn. Với vài nghìn khoản thì vẫn chạy ổn; nếu dữ liệu lớn hơn nhiều, nên đề xuất M0 thêm hàm annotate công nợ ở tầng CSDL.
4. **Khoản phải thu gốc** = `Receivable` không có `adjusts`. Bút toán điều chỉnh hiện dưới khoản gốc, không có dòng riêng trong danh sách công nợ, không tự điều chỉnh tiếp, không ghi nhận thu riêng.
5. **Điều chỉnh**: nhập số âm (giảm) hoặc dương (tăng), khác 0, bắt buộc ghi chú. Chặn trường hợp phải thu sau điều chỉnh bị âm. Bút toán dùng lại loại phí, người phải trả, số hợp đồng của khoản gốc; diễn giải "Điều chỉnh khoản #id".
6. **Đảo khoản thu**: `Collection` không có trường liên kết tới khoản bị đảo, mà gói không cho tạo model hay migration. Vì vậy chỉ cho **đảo toàn bộ** một khoản thu (số tiền = −số đã thu), ghi chú bắt đầu bằng `[Đảo khoản thu #id]` để nhận diện và chặn đảo lần hai. Muốn đảo một phần thì đảo toàn bộ rồi ghi nhận lại số đúng.
7. **Thu vượt**: form so số tiền với `outstanding()` để cảnh báo; chỉ lưu khi tích "Xác nhận thu vượt" và có ghi chú, rồi truyền `confirm_overpayment=True` cho `create_collection` (M0 vẫn kiểm tra lại).
8. **Form ghi nhận là trang riêng** (GET hiện form, POST lưu) thay vì hộp thoại, cho đơn giản và dễ test. Nút trên trang hồ sơ dẫn tới các trang đó.
9. **CSV** dùng dấu phẩy, UTF-8 có BOM, số tiền là số nguyên thuần (không chấm phân cách) để Excel tính toán được. CSV tổng quan gồm các dòng theo tháng, theo loại phí, tổng kỳ và còn nợ cuối kỳ. CSV công nợ là toàn bộ danh sách đang lọc (không phân trang).
10. **Bảng tổng theo nhóm tuổi nợ** tính trên danh sách đã áp bộ lọc loại phí, người phải trả và từ khóa, nhưng **không** áp bộ lọc nhóm tuổi nợ, để vẫn thấy được cả 5 nhóm.
11. **Trang Ghi nhận – tìm hồ sơ**: tìm theo ISBN (bỏ gạch nối), mã NXB, mã tạm, tên sách. Có đúng 1 kết quả thì chuyển thẳng tới `finance:case`; nhiều kết quả thì hiện danh sách tối đa 20 hồ sơ.
12. **Loại phí trong bộ lọc** hiện cả loại đã ngừng dùng (để xem số liệu cũ); form thêm khoản phải thu chỉ hiện loại đang dùng.
