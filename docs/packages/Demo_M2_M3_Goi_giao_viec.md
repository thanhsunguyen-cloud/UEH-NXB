# GÓI GIAO VIỆC DEMO – MÀN HÌNH CỔNG KHÁCH HÀNG (M2) VÀ TÁC NGHIỆP (M3)
UEH Publishing Portal V2 · Đợt 2 · Người làm: **AI-4 (Gemini/Jules)** · từ 26/11/2026, khoảng 1 tuần · Owner: Nguyễn Thanh Sử

> Mục đích: cho biên tập viên NXB **bấm thử** các màn hình chính trước khi viết M2, M3 thật (đợt 3), để góp ý sớm. Đây là bản demo dùng dữ liệu giả, sẽ bị gỡ trước go-live. Nhánh `demo-m2-m3`. Chỉ tạo mới `apps/demo/` và `templates/demo/`.

## 1. Cách làm
- App mới `apps/demo` (không có model, không migration). URL `/demo/` chỉ hoạt động khi `settings.DEBUG=True` **hoặc** biến môi trường `DEMO_ENABLED=True`; còn lại trả 404. Được phép sửa đúng 2 dòng ngoài app: thêm `"apps.demo"` vào `INSTALLED_APPS` trong `portal/settings/base.py` và thêm `path("demo/", include("apps.demo.urls"))` vào `portal/urls.py` **trước** dòng `include("apps.public_site.urls")`. Ghi rõ 2 dòng này trong mô tả pull request.
- Dữ liệu giả viết cứng trong `apps/demo/fake_data.py` (5–8 hồ sơ ở các trạng thái khác nhau, tên sách và tác giả hư cấu). Không đọc/ghi database.
- Mỗi trang có dải cảnh báo cố định: **"BẢN DEMO – DỮ LIỆU GIẢ – THAO TÁC KHÔNG ĐƯỢC LƯU"**.
- Kế thừa `base.html`, Bootstrap 5 + HTMX, tiếng Việt, xem tốt trên điện thoại. Nút bấm chuyển trang hoặc mở hộp thoại; không cần xử lý thật.
- Trạng thái và nhãn theo đúng bảng 7.1 của gói M0; khách hàng thấy nhãn dễ hiểu (ví dụ "NXB đang biên tập" thay cho `EDITING`).

## 2. Màn hình cần có

**Khách hàng (người đại diện)**
1. Hồ sơ của tôi: danh sách, nhãn trạng thái màu, việc cần làm (ví dụ "Cần bổ sung Mẫu 2").
2. Tạo hồ sơ – 4 bước: (1) thông tin tác phẩm và hình thức tự xuất bản/liên kết; (2) danh sách tác giả, có vai trò và thứ tự, ghi rõ chỉ người đại diện có tài khoản; (3) tải tài liệu: bản thảo, Mẫu 1 (chỉ hiện khi liên kết), Mẫu 2, Mẫu 3, có thanh tiến trình giả; (4) xem lại và nộp, liệt kê điều kiện còn thiếu.
3. Chi tiết hồ sơ: dòng thời gian trạng thái, yêu cầu bổ sung đang mở, ghi chú NXB gửi khách hàng, danh sách tài liệu và phiên bản, nút tải lên bản mới.

**Biên tập viên**
4. Danh sách hồ sơ: tìm theo ISBN/mã NXB/tên sách/tác giả, lọc trạng thái, hình thức, biên tập viên phụ trách.
5. Hồ sơ cần xử lý: nhóm theo việc (mới nộp chờ tiếp nhận, khách đã bổ sung, chờ đăng ký…).
6. Chi tiết hồ sơ, 6 tab: Tổng quan (mã NXB, ISBN, số XNĐK, số QĐXB, ngày), Tác giả, Tài liệu & phiên bản, Quy trình (nút chuyển trạng thái hợp lệ và danh sách điều kiện còn thiếu), Ghi chú & trao đổi (nội bộ / gửi khách), Tài chính (chỉ hiện với người có quyền tài chính; khoản phải thu, đã thu, còn nợ).
7. Hộp thoại xác nhận Mẫu 4 "đúng hồ sơ": hiện mã hồ sơ, tên sách, phiên bản bản thảo, ô chọn kết quả, ô tích xác nhận.
8. Thống kê – Danh mục xuất bản: bộ lọc kỳ, bảng danh sách, biểu đồ cột số đầu sách theo tháng (dữ liệu giả).
9. Thống kê – Công nợ: bảng khoản còn nợ, nhóm tuổi nợ.

Trang chỉ mục `/demo/` liệt kê 9 màn hình, chia theo vai trò, kèm một dòng mô tả.

## 3. Không làm
- Không ghi database, không gọi service của M0 có ghi dữ liệu.
- Không thêm thư viện JS/CSS ngoài Bootstrap 5 + HTMX (biểu đồ vẽ bằng HTML/CSS hoặc SVG đơn giản).
- Không có chức năng in ấn, phát hành.

## 4. Bàn giao
- [ ] PR `demo-m2-m3`, CI xanh; 1 test kiểm tra `/demo/` trả 404 khi `DEBUG=False` và `DEMO_ENABLED` không bật, trả 200 khi bật.
- [ ] `docs/DEMO_HUONG_DAN.md`: cách mở demo và danh sách câu hỏi gợi ý để biên tập viên góp ý từng màn hình.
- [ ] Owner mở demo cùng 1–2 biên tập viên trước **14/12** (Mốc 2) và ghi góp ý; góp ý này là đầu vào của gói M2, M3.
