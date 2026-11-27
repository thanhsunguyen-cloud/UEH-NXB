# HƯỚNG DẪN MỞ BẢN DEMO M2/M3 VÀ CÂU HỎI GÓP Ý

Bản demo giúp biên tập viên **bấm thử** màn hình Cổng khách hàng (M2) và Tác nghiệp (M3) trước khi viết thật (đợt 3).
Mọi dữ liệu đều **hư cấu** (`apps/demo/fake_data.py`), không có gì được lưu, không đọc/ghi database. Bản demo sẽ bị gỡ trước go-live.

## 1. Cách mở demo

- Địa chỉ: `/demo/` (ví dụ `http://localhost:8000/demo/`).
- Trang chỉ hoạt động khi `DEBUG=True` **hoặc** biến môi trường `DEMO_ENABLED=True`; ngược lại trả 404.
- Chạy trên máy bằng Docker:
  ```bash
  docker compose up -d --build
  ```
  `docker-compose.yml` dùng `portal.settings.dev` (DEBUG=True) nên demo mở sẵn tại `http://localhost:8000/demo/`.
- Môi trường thử nghiệm có `DEBUG=False` (ví dụ Cloud Run): đặt biến môi trường `DEMO_ENABLED=True` rồi khởi động lại. **Production phải để trống hoặc `False`.**
- Chạy trực tiếp: `DEMO_ENABLED=True python manage.py runserver` rồi mở `http://localhost:8000/demo/`.
- **Không cần đăng nhập.** Mỗi trang có dải đỏ "BẢN DEMO – DỮ LIỆU GIẢ – THAO TÁC KHÔNG ĐƯỢC LƯU". Nút thao tác chỉ chuyển trang hoặc mở hộp thoại báo "không được lưu".
- Xem trên điện thoại: mở cùng địa chỉ (máy chủ phải truy cập được trong mạng nội bộ).

## 2. Danh sách màn hình

| # | Vai trò | Màn hình | Đường dẫn |
|---|---|---|---|
| 1 | Khách hàng | Hồ sơ của tôi | `/demo/khach-hang/ho-so/` |
| 2 | Khách hàng | Tạo hồ sơ – 4 bước | `/demo/khach-hang/tao-ho-so/` |
| 3 | Khách hàng | Chi tiết hồ sơ | `/demo/khach-hang/ho-so/hs-03/` |
| 4 | Biên tập viên | Danh sách hồ sơ (tìm, lọc) | `/demo/bien-tap/ho-so/` |
| 5 | Biên tập viên | Hồ sơ cần xử lý | `/demo/bien-tap/can-xu-ly/` |
| 6 | Biên tập viên | Chi tiết hồ sơ – 6 tab | `/demo/bien-tap/ho-so/hs-08/` |
| 7 | Biên tập viên | Hộp thoại xác nhận Mẫu 4 | `/demo/bien-tap/ho-so/hs-05/?tab=quy-trinh&mau_4=1` |
| 8 | Biên tập viên | Thống kê – Danh mục xuất bản | `/demo/thong-ke/danh-muc/` |
| 9 | Biên tập viên | Thống kê – Công nợ | `/demo/thong-ke/cong-no/` |

Mẹo:
- Khách hàng demo là "Trần Thị Mai (hư cấu)", có 5 hồ sơ ở các trạng thái khác nhau.
- Ở màn hình 6, dòng "Giả lập quyền" cho phép xem như BTV **không** có quyền tài chính (tab Tài chính biến mất).
- Ở bước 1 của màn hình 2, chọn "Liên kết" để thấy ô Mẫu 1 xuất hiện ở bước 3.

## 3. Câu hỏi gợi ý để biên tập viên góp ý

Ghi góp ý theo số màn hình (ví dụ "MH4 – câu b: ...").

**MH1 – Hồ sơ của tôi**
a. Nhãn trạng thái cho khách ("NXB đang biên tập", "Cần bổ sung hồ sơ"…) đã dễ hiểu chưa? Muốn đổi chữ nào?
b. Dòng "Việc cần làm" có đủ để khách biết phải làm gì tiếp không?
c. Dạng thẻ có ổn không, hay muốn dạng bảng?

**MH2 – Tạo hồ sơ 4 bước**
a. Bước 1 còn thiếu thông tin nào NXB cần ngay từ đầu (thể loại, lĩnh vực, số trang dự kiến…)?
b. Bước 2: vai trò tác giả (Tác giả, Chủ biên, Đồng tác giả, Dịch giả, Biên soạn) đã đủ chưa? Cần nhập thêm gì cho từng tác giả?
c. Bước 3: danh sách tài liệu bắt buộc (Bản thảo, Mẫu 1 khi liên kết, Mẫu 2, Mẫu 3) đã đúng chưa?
d. Bước 4: cách liệt kê "còn thiếu" có rõ không? Có cho lưu nháp khi còn thiếu không?

**MH3 – Chi tiết hồ sơ (khách hàng)**
a. Dòng thời gian nên hiện những bước nào cho khách? Có cần hiện tên biên tập viên không?
b. Yêu cầu bổ sung và ghi chú NXB gửi khách đã đặt đúng chỗ, đủ nổi bật chưa?
c. Khách có cần xem lại các phiên bản cũ của tài liệu không?

**MH4 – Danh sách hồ sơ**
a. Tìm theo ISBN/mã NXB/tên sách/tác giả đã đủ chưa? Có cần tìm theo tên người đại diện hay đơn vị liên kết?
b. Cần thêm cột hay bộ lọc nào (thể loại, năm, ngày nộp…)?

**MH5 – Hồ sơ cần xử lý**
a. Các nhóm việc (mới nộp, khách đã bổ sung, đang biên tập chờ Mẫu 4, chờ đăng ký, chờ quyết định/lưu chiểu) đã đúng thực tế chưa? Thiếu nhóm nào?
b. Có cần nhắc hạn (ví dụ hồ sơ nằm quá 7 ngày) không?

**MH6 – Chi tiết hồ sơ 6 tab**
a. Tab Tổng quan còn thiếu trường nào (mã NXB, ISBN, số XNĐK, số QĐXB, ngày…)?
b. Tab Quy trình: nút chuyển trạng thái và danh sách "điều kiện còn thiếu" có dễ hiểu không?
c. Tab Ghi chú: phân biệt "Nội bộ" và "Gửi khách hàng" đã đủ rõ để tránh gửi nhầm chưa?
d. Tab Tài chính: khoản phải thu / đã thu / còn nợ trình bày như vậy có phù hợp?

**MH7 – Hộp thoại Mẫu 4**
a. Thông tin hiển thị (mã hồ sơ, tên sách, phiên bản bản thảo) đã đủ để tránh gắn nhầm Mẫu 4 sang hồ sơ khác chưa?
b. Câu xác nhận có cần sửa chữ không? Có cần nhập thêm người duyệt, ngày duyệt?

**MH8 – Danh mục xuất bản**
a. Lọc theo năm/quý có đủ, hay cần lọc theo khoảng ngày, thể loại, hình thức?
b. Bảng cần thêm cột nào để nộp báo cáo định kỳ?

**MH9 – Công nợ**
a. Các nhóm tuổi nợ (chưa đến hạn, 1–30, 31–60, 61–90, trên 90 ngày) có phù hợp?
b. Có cần lọc theo người đại diện hoặc xuất danh sách để nhắc nợ không?

**Chung**
- Có màn hình nào khó dùng trên điện thoại không?
- Từ ngữ nào chưa quen với cách gọi trong NXB?
