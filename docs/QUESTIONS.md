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

# M6 — TRANG CÔNG KHAI (AI-3, nhánh `m6-public-site`): CÁC ĐIỂM CẦN OWNER XÁC NHẬN

Các điểm dưới đây **chưa được tự quyết**. Mỗi mục ghi cách làm *tạm thời* trong mã (dễ đổi) để CI chạy được; Owner trả lời thì AI-3 sửa theo.

1. **`meta description` trong `<head>`** — `templates/base.html` (M0) chỉ có `block title`, không có block nào trong `<head>`, nên M6 không thể đặt `<meta name="description">` đúng chỗ mà không sửa file M0.
   - *Tạm thời:* đặt thẻ `meta description` riêng của từng trang ở đầu `block content` (trình duyệt chấp nhận, nhưng không chuẩn HTML và công cụ tìm kiếm có thể bỏ qua).
   - *Đề xuất CR cho M0:* thêm `{% block meta %}{% endblock %}` vào `<head>` của `base.html`; M6 sẽ chuyển thẻ meta vào block đó.
2. **Link menu cho EDITOR** — không sửa `templates/partials/nav.html`. *Đề xuất* Owner thêm vào nhánh `user.is_editor`: `<li class="nav-item"><a class="nav-link" href="{% url 'public_site:news_manage' %}">Tin tức &amp; sách mới</a></li>`. Hiện EDITOR vào bằng địa chỉ `/tin-tuc/quan-ly/`.
3. **"Thêm 1 mục 'Tin tức & sách mới' vào giao diện của trang quản lý module"** — *tạm hiểu* là tiêu đề "Tin tức & sách mới" + 2 tab (Tin tức / Sách mới) trên các trang quản lý của M6. Nếu ý là thêm vào trang của module khác (ví dụ trang chủ `/noi-bo/` của M3) thì cần Owner chỉ rõ, vì nằm ngoài thư mục được sửa.
4. **Phạm vi thư mục tài liệu** — chỉ được sửa trong `apps/public_site/` và `templates/public_site/`, nhưng gói việc yêu cầu cập nhật `docs/TEST_REPORT.md` và tạo `docs/M6_NOI_DUNG_CAN_BO_SUNG.md`. *Tạm thời:* tạo mới `docs/M6_NOI_DUNG_CAN_BO_SUNG.md` và **thêm** mục M6 vào cuối `docs/TEST_REPORT.md` (không xóa báo cáo M0). Owner xác nhận có muốn tách thành tệp riêng không.
5. **Test đặt ở đâu** — vì giới hạn thư mục, test M6 nằm trong `apps/public_site/tests/` (không phải `tests/`), có `conftest.py` riêng và dùng lại `tests/factories.py`. CI hiện chỉ đo độ phủ `apps/core`; độ phủ `apps/public_site` đo bằng lệnh riêng (xem TEST_REPORT). *Đề xuất* Owner thêm `--cov=apps/public_site` vào `ci.yml` nếu muốn CI tự chặn.
6. **CR-001 chưa gộp** — mã gọi `get_storage().save_library_file("public_media", filename, fileobj, size, mime_type)`. Nếu kho lưu trữ chưa có hàm này, form báo lỗi "Chức năng lưu ảnh bìa chưa sẵn sàng" và không lưu gì. Test dùng kho giả cùng chữ ký CR-001. Sau khi CR-001 vào `main`, AI-3 cập nhật nhánh và chạy lại test với `LocalFileStorage` thật.
7. **"2 MB"** — *tạm hiểu* là 2 MiB = 2 097 152 byte (tệp đúng bằng mức này vẫn được nhận).
8. **Kiểm tra ảnh** — ngoài phần mở rộng (.jpg/.jpeg/.png/.webp) và dung lượng, mã còn kiểm tra chữ ký nhị phân của tệp (không cần thêm thư viện Pillow). Có chấp nhận đuôi `.jpeg` không? *Tạm thời:* có.
9. **Giá trị `<kind>` trong `/anh/<kind>/<pk>/`** — *tạm dùng* `tin-tuc` và `sach-moi` (giống đường dẫn trang công khai).
10. **Xem trước ảnh bìa của mục chưa đăng** — `/anh/...` chỉ trả ảnh của mục đã đăng cho **mọi** người (kể cả EDITOR); trang quản lý chỉ ghi "Có" ảnh bìa. Có cần cho EDITOR xem trước ảnh của mục chưa đăng không?
11. **Tải biểu mẫu bản cũ nhưng vẫn `is_active=True`** — trang `/bieu-mau/` chỉ liệt kê bản mới nhất mỗi `code`, nhưng `/bieu-mau/<pk>/tai/` (đúng như gói việc) cho tải **mọi** bản `is_active=True`. Có cần chặn bản đang áp dụng nhưng không phải mới nhất không?
12. **Slug tin tức** — tự sinh từ tiêu đề (bỏ dấu, `đ` → `d`), không sửa được, thêm `-2`, `-3`… khi trùng; chặn slug `quan-ly` để không đụng `/tin-tuc/quan-ly/`. Có cần cho EDITOR tự sửa slug không?
13. **Ngày đăng** — `published_at` được ghi ở lần đăng đầu tiên; gỡ đăng rồi đăng lại vẫn giữ ngày cũ. Owner có muốn cập nhật ngày khi đăng lại không?
14. **Phân trang `/sach-moi/`** — gói việc không nói; *tạm* 12 sách/trang. Trang quản lý: 20 mục/trang.
15. **Footer của `base.html`** — trên trang công khai vẫn hiện "UEH Publishing Portal V2 · Nền tảng M0" (file M0). Có muốn đổi chữ này không?
16. **Nội dung trang Quy trình** — các bước được viết dựa trên các trạng thái hồ sơ đã có trong M0 (`CaseStatus`). Danh sách giấy tờ lấy đúng theo gói việc. Tên đầy đủ của Mẫu 1/2/3, thời gian xử lý và yêu cầu trình bày bản thảo đang để `[CẦN NXB CUNG CẤP]`. Owner/NXB xem lại câu chữ các bước.

## M6 — QUYẾT ĐỊNH CỦA NHÓM TRƯỞNG (Claude, 26/11/2026, Owner đã giao)

- Mục 1, 2, 15 (meta description, link menu, chân trang): đã làm trong CR-002 — thêm `{% block meta %}` vào `<head>` của `base.html`, link "Tin tức & sách mới" cho EDITOR trong `nav.html`, chân trang "© 2026 Nhà xuất bản Kinh tế TP. Hồ Chí Minh".
- Mục 3, 4, 7, 8, 9, 11, 12, 13, 14: chấp nhận cách AI-3 đã làm.
- Mục 5: CI đo độ phủ toàn bộ `apps` (`--cov=apps --cov-fail-under=85`).
- Mục 6: CR-001 đã gộp; ảnh bìa lưu qua `save_library_file` thật (đã kiểm tra đầu-cuối).
- Mục 10: chưa cần xem trước ảnh của mục chưa đăng (để giai đoạn 2 nếu biên tập viên yêu cầu).
- Mục 16 và toàn bộ `[CẦN NXB CUNG CẤP]`: đã điền theo phiếu NXB ngày 26/11/2026 (xem `docs/M6_NOI_DUNG_CAN_BO_SUNG.md`).
- Email gửi thư tự động mặc định: `nxbkt@ueh.edu.vn` (mục 7 của phiếu).

# CÂU HỎI & QUYẾT ĐỊNH TRONG GÓI M1 (AI-1)

6. **Đăng ký `apps.documents_drive` vào `INSTALLED_APPS` (`portal/settings/base.py`, file M0):**
   - *Câu hỏi:* Lệnh `python manage.py drive_check` chỉ chạy được khi app có trong `INSTALLED_APPS`, nhưng danh sách CR-001 không cho sửa dòng này.
   - *Owner trả lời (26/11/2026):* Thêm trong PR M1 (`m1-drive`). Đã thêm đúng 1 dòng `"apps.documents_drive.apps.DocumentsDriveConfig"`.

7. **Số lần thử lại khi Drive lỗi 429/5xx:**
   - *Câu hỏi:* Gói ghi "thử lại tối đa 5 lần" nhưng phần test ghi "dừng sau 5 lần".
   - *Owner trả lời (26/11/2026):* Tổng cộng 5 lần gọi (1 lần đầu + tối đa 4 lần thử lại). Thời gian chờ giữa các lần: 1, 2, 4, 8 giây (hằng `MAX_ATTEMPTS`, `BASE_DELAY_SECONDS` trong `apps/documents_drive/client.py`).


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

## M7 — QUYẾT ĐỊNH CỦA NHÓM TRƯỞNG (Claude, 26/11/2026, Owner đã giao)

- **Q1–Q7:** Chấp nhận toàn bộ cột "Đang làm tạm" (không đổi nhân sự về CUSTOMER – muốn ngừng thì khóa; bỏ mật khẩu cũ khi nâng CUSTOMER lên nhân sự; "Áp dụng ngay" mặc định bật; chặn trùng (mã, phiên bản); giữ bộ lọc bằng HTMX, không sửa partial M0; tìm người thực hiện bằng ô tìm; chỉ hiện `data` cho `user.*`, `auth.*`, `catalog.*`, `form_template.*`).
- **Q8:** Không cần sửa CI – `main` đã đo `--cov=apps --cov-fail-under=85` cho mọi module.
- **Q9:** CR-001 đã có trên `main`; nhóm trưởng đã gộp `main` vào nhánh và kiểm tra lại với `LocalFileStorage` thật (tải lên Mẫu 1, kích hoạt bản mới, tải về công khai qua `/bieu-mau/<pk>/tai/` – đạt).

---

# M4 – THÔNG BÁO EMAIL (AI-5, nhánh `m4-notifications`): ĐIỂM CHƯA RÕ ĐÃ TỰ CHỌN PHƯƠNG ÁN ĐƠN GIẢN NHẤT

| # | Câu hỏi | Đang làm tạm | Phương án khác |
|---|---|---|---|
| N1 | BTV phụ trách chính **có** nhưng bị khóa hoặc không có email thì gửi cho ai? | Coi như "chưa có" → gửi cho mọi EDITOR đang hoạt động (để hồ sơ không bị bỏ sót). Nếu BTV phụ trách chính là người thao tác thì không gửi cho ai. | Không gửi cho ai. |
| N2 | Thông tin liên hệ cuối email | Để `[CẦN NXB CUNG CẤP]` đúng như gói M4, dù `docs/M6_NOI_DUNG_CAN_BO_SUNG.md` đã có email `nxbkt@ueh.edu.vn`. | Điền `nxbkt@ueh.edu.vn`. |
| N3 | Nhãn trạng thái dễ hiểu | Bảng `FRIENDLY_STATUS_LABELS` riêng trong `apps/notifications/emails.py` (ví dụ `EDITING` → "NXB đang biên tập"); dùng chung cho cả email BTV. Khi M2 có bảng nhãn chung thì nên gộp về một chỗ. | Dùng nhãn `get_status_display()` của M0. |
| N4 | `AuditEvent` `email.sent` / `email.failed` ghi `actor` là ai? | `actor = None` (hệ thống gửi), gắn `case`; `data` chỉ gồm loại email, người nhận, mã hồ sơ (sent) hoặc lỗi rút gọn ≤ 200 ký tự (failed). | Ghi `actor` = người đổi trạng thái. |
| N5 | Ghi chú `note` khi chuyển trạng thái có thể là nội dung nội bộ không? | Chỉ đưa `note` vào email ở `NEED_SUPPLEMENT`, `REVISION_REQUIRED`, `REJECTED` (đúng gói); không bao giờ đọc `CaseNote`. Màn hình M3 cần nhắc BTV rằng ghi chú ở 3 thao tác này sẽ gửi cho khách hàng. | – |
| N6 | Test đặt ở đâu, đo phủ thế nào? | `tests/test_notifications.py` (đúng gói); CI đã chạy `--cov=apps`, `apps/notifications` đạt 100%. | – |

# DEMO M2/M3 (AI-4) – ĐIỂM CHƯA RÕ VÀ PHƯƠNG ÁN ĐÃ CHỌN

Theo chỉ đạo của Owner: ghi lại, chọn phương án đơn giản nhất, không dừng lại hỏi. Owner có thể đổi khi rà soát PR.

| # | Câu hỏi | Đã làm | Phương án khác |
|---|---|---|---|
| D1 | Demo có cần đăng nhập và dùng mixin phân quyền của M0 không? Mixin vai trò sẽ chặn BTV xem màn hình khách hàng. | Không cần đăng nhập. Mọi view kế thừa `DemoEnabledMixin` (trong `apps/demo/views.py`) – trả 404 khi demo tắt; không dùng dữ liệu thật nên không cần `CaseAccessMixin`. | Bắt buộc đăng nhập (`LoginRequiredMixin`) với mọi vai trò. |
| D2 | Đọc biến `DEMO_ENABLED` ở đâu? Gói chỉ cho sửa 1 dòng `INSTALLED_APPS` trong `base.py`. | Đọc trực tiếp `os.environ["DEMO_ENABLED"]` lúc xử lý request (chấp nhận `True/1/yes/on`), không thêm setting. | Thêm `DEMO_ENABLED = env.bool(...)` vào `base.py` (cần Owner cho phép). |
| D3 | Tab Tài chính "chỉ hiện với người có quyền tài chính" – demo không có người dùng thật. | Mặc định hiện; tham số `?tai_chinh=0` giả lập BTV không có quyền (tab ẩn hẳn). | Thêm trang chọn "vai trò giả" ở trang chỉ mục. |
| D4 | Test đặt ở đâu? Gói chỉ cho tạo `apps/demo/` và `templates/demo/`. | Đặt trong `apps/demo/tests/test_demo.py` (không sửa `tests/`). Test không dùng fixture `db` nên tự báo lỗi nếu view chạm database. | Đặt ở `tests/test_demo.py` như các module khác. |
| D5 | Nhóm tuổi nợ: `apps.core.finance.aging_bucket` nhận model `Receivable`, không dùng được với dữ liệu giả. | Chép lại đúng logic (5 nhóm) trong `fake_data.aging_bucket`, ngày "hôm nay" cố định 26/11/2026. | – |
| D6 | Tải tệp giả: quy ước cấm `<input type="file">` gửi qua form. | Không dùng ô chọn tệp; nút "Chọn tệp và tải lên" chỉ chạy thanh tiến trình giả bằng JavaScript. | Nhúng `partials/chunked_upload.html` (cần hồ sơ thật, sẽ ghi database). |
| D7 | Định dạng tiền: `floatformat:"g"` với ngôn ngữ `vi` không nhóm hàng nghìn. | Thêm bộ lọc `vnd` trong `apps/demo/templatetags/demo_tags.py` (25000000 → 25.000.000). | Bật `USE_THOUSAND_SEPARATOR` toàn hệ thống (sửa M0). |
| D8 | Nhánh: gói ghi `demo-m2-m3`. | Làm và đẩy lên nhánh `demo-m2-m3` (tách từ `main` mới nhất). | – |
