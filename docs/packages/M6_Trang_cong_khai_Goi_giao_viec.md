# GÓI GIAO VIỆC M6 – TRANG CÔNG KHAI
UEH Publishing Portal V2 · Đợt 2 · Người làm: **AI-3** · 01/12 – 07/12/2026 · Owner: Nguyễn Thanh Sử

> Đọc `docs/CONVENTIONS.md`, `docs/DATA_MODEL.md` và tài liệu này trước khi viết code. Nhánh `m6-public-site`. Chỉ sửa trong `apps/public_site/` và `templates/public_site/`. Sau M6, AI-3 làm tiếp gói **Demo M2/M3** (08/12 – 13/12).

## 1. Mục tiêu

Trang công khai của NXB Kinh tế TP.HCM cho người chưa đăng nhập: giới thiệu, hướng dẫn quy trình xuất bản, tải biểu mẫu, tin tức và sách mới, liên hệ, và lối vào đăng nhập/đăng ký. Trang công khai **không hiển thị bất kỳ dữ liệu hồ sơ nào** của khách hàng.

## 2. Model riêng của module (Owner đã duyệt trước)

Đặt trong `apps/public_site/models.py`, migration nằm trong app này:

- `NewsPost`: `title` (255), `slug` (unique), `summary` (500), `body` (TextField, **văn bản thuần**, xuống dòng thành đoạn; không nhận HTML), `cover_storage_ref` (255, blank), `cover_mime` (100, blank), `is_published` (bool), `published_at` (DateTime, null), `created_by` (FK User), `created_at`, `updated_at`.
- `FeaturedBook` (sách mới, do biên tập viên nhập tay, **không** lấy tự động từ hồ sơ): `title`, `authors` (255), `isbn` (13, blank, kiểm bằng `validate_isbn13` của M0 nếu có), `year` (int), `description` (TextField thuần), `cover_storage_ref`, `cover_mime`, `is_published`, `sort_order`, `created_by`, thời gian.

Không thêm model nào khác.

## 3. Trang công khai (không cần đăng nhập)

| URL | Tên URL | Nội dung |
|---|---|---|
| `/` | `public_site:home` | Giới thiệu ngắn, 3 nút: "Nộp hồ sơ xuất bản" (→ đăng nhập/đăng ký khách hàng), "Quy trình", "Tải biểu mẫu"; 3 tin mới nhất; 4 sách mới |
| `/gioi-thieu/` | `public_site:about` | Giới thiệu NXB |
| `/quy-trinh/` | `public_site:process` | Các bước từ nộp hồ sơ đến lưu chiểu, viết cho tác giả; danh sách giấy tờ cần nộp theo hình thức tự xuất bản và liên kết (Mẫu 1 nếu liên kết, Mẫu 2, Mẫu 3, bản thảo); yêu cầu định dạng bản thảo |
| `/bieu-mau/` | `public_site:forms` | Danh sách `FormTemplate` đang áp dụng (mỗi `code` một bản mới nhất), nút tải |
| `/bieu-mau/<int:pk>/tai/` | `public_site:form_download` | Tải file biểu mẫu qua `get_storage().open_stream`, **chỉ** bản `is_active=True`; bản khác → 404 |
| `/tin-tuc/`, `/tin-tuc/<slug>/` | `public_site:news_list`, `news_detail` | Tin đã đăng, phân trang 10 |
| `/sach-moi/` | `public_site:books` | Sách mới đã đăng |
| `/lien-he/` | `public_site:contact` | Địa chỉ, điện thoại, email, giờ làm việc (văn bản tĩnh) |
| `/anh/<str:kind>/<int:pk>/` | `public_site:image` | Trả ảnh bìa tin/sách qua stream; chỉ của mục đã đăng |

Nội dung văn bản chưa có từ NXB thì để chỗ trống rõ ràng: `[CẦN NXB CUNG CẤP: ...]`. Không tự bịa địa chỉ, số điện thoại, lịch sử NXB.

## 4. Màn hình quản lý nội dung (EDITOR)

- `/tin-tuc/quan-ly/` và `/sach-moi/quan-ly/`: danh sách, thêm, sửa, đăng/gỡ đăng. Kế thừa `EditorRequiredMixin`. Không có xóa (chỉ gỡ đăng).
- Ảnh bìa: .jpg, .png, .webp, ≤ 2 MB, lưu bằng `get_storage().save_library_file("public_media", ...)` (có sau CR-001, dự kiến 03/12; trước đó dùng bản giả trong test).
- Ghi `log_event` action `public.news_create`, `public.news_publish`, `public.book_create`, …
- Thêm 1 mục "Tin tức & sách mới" vào giao diện của trang quản lý module; **không** sửa `templates/partials/nav.html` của M0 (ghi vào QUESTIONS.md đề xuất thêm link menu để Owner sửa sau).

## 5. Yêu cầu chung
- Kế thừa `base.html`; giao diện riêng cho trang công khai nằm trong block nội dung (header thương hiệu NXB, footer có liên hệ). Không dùng ảnh hay logo khi chưa được NXB cung cấp: dùng tên chữ "Nhà xuất bản Kinh tế TP. Hồ Chí Minh".
- Responsive, đọc tốt trên điện thoại; mỗi trang có `<title>` và `meta description` riêng.
- Văn bản thuần được escape khi hiển thị (chống XSS); không dùng `|safe` với nội dung người nhập.
- Không hiển thị gì về in ấn, phát hành, giá bán.

## 6. Test bắt buộc
- Mọi trang công khai trả 200 khi chưa đăng nhập.
- Tin/sách chưa đăng: trang chi tiết và ảnh trả 404 cho khách.
- Tải biểu mẫu: chỉ bản đang áp dụng; bản đã tắt → 404.
- Trang quản lý: CUSTOMER và ADMIN nhận 404.
- Nội dung có `<script>` được hiển thị dưới dạng chữ, không chạy.
- Ảnh sai định dạng hoặc > 2 MB bị từ chối.
- Độ phủ `apps/public_site` ≥ 85%.

## 7. Bàn giao
- [ ] PR `m6-public-site`, CI xanh, `docs/TEST_REPORT.md` có kết quả chạy thật.
- [ ] Danh sách mọi chỗ `[CẦN NXB CUNG CẤP]` trong `docs/M6_NOI_DUNG_CAN_BO_SUNG.md` để Owner gửi NXB.
