# HƯỚNG DẪN ĐƯA PORTAL LÊN GOOGLE CLOUD (DÙNG THỬ)

Dành cho Owner, không cần biết lập trình. Làm lần lượt từ Phần A đến Phần G. Tổng thời gian khoảng 1–1,5 giờ, phần lớn là chờ máy chạy.

**Quy tắc an toàn:** mật khẩu ứng dụng, Client secret chỉ dán vào ô nhập của Cloud Shell (chữ sẽ không hiện ra khi dán – đó là bình thường). Không dán chúng vào bất kỳ cuộc trò chuyện AI nào, không gửi qua email/Zalo.

**Chi phí dự kiến:** cơ sở dữ liệu nhỏ nhất (db-f1-micro) khoảng 8–10 USD/tháng cộng tiền lưu trữ vài chục GB; Cloud Run gần như miễn phí ở mức dùng thử. Tài khoản Google Cloud mới thường được tặng 300 USD dùng thử.

---

## Phần A – Tạo dự án Google Cloud (tài khoản thanhsu.nguyen@gmail.com)
1. Mở https://console.cloud.google.com và đăng nhập bằng **thanhsu.nguyen@gmail.com**. Đồng ý điều khoản nếu được hỏi.
2. Nếu được mời "Dùng thử miễn phí / Start free": bấm vào, điền thông tin và thẻ thanh toán.
3. Trên thanh trên cùng, bấm ô chọn dự án → **Dự án mới (New project)**. Tên dự án: `UEH Portal NXB` → **Tạo**.
4. Ghi lại **Mã dự án (Project ID)** hiện dưới tên dự án (ví dụ `ueh-portal-nxb-123456`).
5. Vào menu ☰ → **Thanh toán (Billing)**, kiểm tra dự án đã được gắn tài khoản thanh toán.

## Phần B – Chuẩn bị hộp thư nxbkt@ueh.edu.vn
**B1. Mật khẩu ứng dụng (để Portal gửi email):**
1. Đăng nhập Google bằng **nxbkt@ueh.edu.vn**, mở https://myaccount.google.com/security.
2. Bật **Xác minh 2 bước** nếu chưa bật.
3. Mở https://myaccount.google.com/apppasswords, đặt tên `Portal NXB` → **Tạo**. Google hiện 16 ký tự: **giữ cửa sổ này mở** để dán ở Phần C (không chép ra nơi khác).
   - Nếu trang báo "không có sẵn": UEH đã tắt tính năng này → bỏ qua, Portal tạm không gửi email; báo nhóm trưởng để soạn đề nghị gửi phòng CNTT. Khi email tắt, khách hàng **chỉ đăng nhập được bằng Google** (đăng ký bằng email + mật khẩu cần email xác nhận).

**B2. Ổ dùng chung (Shared Drive) để lưu tài liệu hồ sơ:**
1. Vẫn bằng nxbkt@ueh.edu.vn, mở https://drive.google.com → mục **Bộ nhớ dùng chung (Shared drives)** → **Mới** → tên `Portal NXB – Tài liệu hồ sơ`.
   - Nếu không có nút **Mới**: UEH chưa cho phép tạo → báo nhóm trưởng.
2. Mở ổ vừa tạo. Địa chỉ trên trình duyệt có dạng `https://drive.google.com/drive/folders/0AbCdEf...` → phần sau `folders/` là **Mã Shared Drive**. Ghi lại.

## Phần C – Chạy lệnh triển khai lần 1
1. Quay lại https://console.cloud.google.com (tài khoản gmail, đúng dự án ở Phần A).
2. Bấm biểu tượng **Cloud Shell** `>_` ở góc phải trên cùng. Chờ cửa sổ dòng lệnh mở ở dưới, bấm **Ủy quyền (Authorize)** nếu được hỏi.
3. Dán nguyên dòng sau rồi bấm Enter:
   ```
   git clone https://github.com/thanhsunguyen-cloud/UEH-NXB.git && bash UEH-NXB/deploy/cloudrun/setup.sh
   ```
4. Trả lời các câu hỏi:
   - **Mã dự án**: Project ID ở Phần A.
   - **Email Quản trị viên**: email **@ueh.edu.vn** của người quản trị (tối đa 2, cách nhau dấu phẩy). Bắt buộc là email UEH.
   - **Mã Shared Drive**: bấm Enter (làm ở Phần D).
   - **Client ID đăng nhập Google**: bấm Enter (làm ở Phần E).
   - **Mật khẩu ứng dụng**: dán 16 ký tự ở Phần B1 (chữ không hiện) → Enter. Chưa có thì bấm Enter.
5. Chờ (lần đầu khoảng 20 phút). Khi thấy chữ **XONG**, ghi lại 3 dòng: **Địa chỉ Portal**, **Tài khoản máy**, **Địa chỉ chuyển hướng đăng nhập Google**.

## Phần D – Cho Portal quyền ghi vào Shared Drive
1. Bằng nxbkt@ueh.edu.vn, mở Shared Drive ở Phần B2 → bấm **Quản lý thành viên**.
2. Dán **Tài khoản máy** (dạng `ueh-portal-run@....iam.gserviceaccount.com`), chọn quyền **Người quản lý nội dung (Content manager)**, bỏ chọn "Thông báo" → **Gửi**.
   - Nếu Google báo không thể chia sẻ ra ngoài tổ chức: UEH đang chặn → báo nhóm trưởng (sẽ soạn đề nghị gửi phòng CNTT).

## Phần E – Tạo nút "Đăng nhập bằng Google"
1. Trong https://console.cloud.google.com (đúng dự án), menu ☰ → **API và dịch vụ** → **Màn hình xin phép OAuth (OAuth consent screen)** / **Google Auth Platform** → **Bắt đầu**.
   - Tên ứng dụng: `Portal NXB Kinh tế TP.HCM`; email hỗ trợ: thanhsu.nguyen@gmail.com; Đối tượng: **Bên ngoài (External)**; email liên hệ: như trên → Tạo.
2. Mục **Đối tượng (Audience)** → **Xuất bản ứng dụng (Publish app)** → Xác nhận. (Chỉ dùng quyền cơ bản tên + email nên không cần Google xét duyệt.)
3. Mục **Ứng dụng khách (Clients)** → **Tạo ứng dụng khách** → Loại: **Ứng dụng web**, tên `Portal NXB`.
   - **URI chuyển hướng được ủy quyền** → Thêm URI → dán **Địa chỉ chuyển hướng đăng nhập Google** ở Phần C.
   - Bấm **Tạo**. Google hiện **Client ID** và **Client secret** – giữ cửa sổ mở.

## Phần F – Chạy lệnh triển khai lần 2
1. Mở lại Cloud Shell, dán:
   ```
   cd ~/UEH-NXB && git pull && bash deploy/cloudrun/setup.sh
   ```
2. Mã dự án, Email Quản trị viên: bấm Enter (giữ như cũ).
3. **Mã Shared Drive**: dán mã ở Phần B2. **Client ID**: dán Client ID ở Phần E.
4. Hỏi nhập lại mật khẩu email: gõ `K` rồi Enter. Hỏi **Client secret**: dán Client secret (chữ không hiện) → Enter.
5. Chờ đến **XONG**. Phải thấy dòng **"Kiểm tra Google Drive: ĐẠT"**. Nếu "CHƯA ĐẠT": kiểm tra lại Phần D rồi chạy lại lệnh ở bước 1.

## Phần G – Dùng thử
1. Mở **Địa chỉ Portal** → **Đăng nhập** → **Đăng nhập bằng Google** bằng email Quản trị viên @ueh.edu.vn.
2. Vào **Quản trị → Biểu mẫu**: tải lên Mẫu 1, 2, 3 bản trống (mã `MAU_1`, `MAU_2`, `MAU_3`, phiên bản `1`, ngày hiệu lực hôm nay, đánh dấu "Áp dụng ngay").
3. **Quản trị → Người dùng**: thêm biên tập viên (email @ueh.edu.vn), cấp quyền tài chính (Không / Xem / Quản lý) cho từng người.
4. Nhờ 1 biên tập viên và 1 người ngoài (Gmail) thử: người ngoài đăng ký tài khoản, tạo hồ sơ, nộp; biên tập viên tiếp nhận, yêu cầu bổ sung… Ghi lại góp ý gửi nhóm trưởng.

## Cập nhật khi có code mới
Mở Cloud Shell, dán `cd ~/UEH-NXB && git pull && bash deploy/cloudrun/setup.sh`, bấm Enter qua mọi câu hỏi (gõ `K` khi được hỏi nhập lại), chờ **XONG**.
