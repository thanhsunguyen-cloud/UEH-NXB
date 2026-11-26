# UEH Publishing Portal V2 — Gói giao việc M0 (Nền tảng)

Hệ thống số hóa quy trình xuất bản của **Nhà xuất bản Kinh tế TP.HCM** (trực thuộc Đại học Kinh tế TP.HCM – UEH).

## 1. Cài đặt và khởi chạy nhanh bằng Docker

```bash
cp .env.example .env
docker compose up --build
```

Sau khi container `web`, `db` (PostgreSQL 16) và `mailpit` khởi chạy thành công (tự động chạy `migrate`):

```bash
# Khởi tạo tài khoản quản trị từ BOOTSTRAP_ADMIN_EMAILS
docker compose exec web python manage.py bootstrap_admin

# Khởi tạo dữ liệu mẫu (chỉ chạy khi DJANGO_DEBUG=True)
docker compose exec web python manage.py seed_demo
```

- Cổng ứng dụng: `http://localhost:8000`
- Django Admin (chỉ `ADMIN`): `http://localhost:8000/django-admin/`
- Hộp thư phát triển Mailpit: `http://localhost:8025`

## 2. Tài khoản mẫu (`seed_demo`)

| Email | Vai trò | Quyền tài chính | Hình thức đăng nhập |
| :--- | :--- | :--- | :--- |
| `admin@ueh.edu.vn` | `ADMIN` | `NONE` | Google `@ueh.edu.vn` |
| `bientap.taichinh@ueh.edu.vn` | `EDITOR` | `MANAGE` | Google `@ueh.edu.vn` |
| `bientap@ueh.edu.vn` | `EDITOR` | `NONE` | Google `@ueh.edu.vn` |
| `tacgia.a@gmail.com` | `CUSTOMER` | `NONE` | Email + mật khẩu (`Demo@123456`) |
| `tacgia.b@doitac.vn` | `CUSTOMER` | `NONE` | Email + mật khẩu (`Demo@123456`) |

## 3. Biến môi trường chính (`.env.example`)

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `STAFF_GOOGLE_DOMAIN=ueh.edu.vn`
- `BOOTSTRAP_ADMIN_EMAILS` (tối đa 2 email `@ueh.edu.vn`)
- `FILE_STORAGE_BACKEND` (`local` cho M0; `gdrive` do M1 triển khai), `MEDIA_ROOT`, `MAX_FILE_MB=200`
- `EMAIL_URL` (trỏ tới `smtp://mailpit:1025` khi phát triển)

## 4. Lệnh thường dùng

```bash
# Chạy toàn bộ test tự động kèm báo cáo độ phủ apps/core
docker compose run --rm web pytest

# Kiểm tra lint và định dạng mã nguồn
docker compose run --rm web ruff check .
docker compose run --rm web ruff format --check .

# Dọn các phiên upload chia phần quá 24 giờ
docker compose exec web python manage.py cleanup_uploads
```

## 5. Tài liệu cho đội ngũ phát triển M1–M8

- `docs/CONVENTIONS.md` — Quy ước bắt buộc khi phát triển các module M1–M8 trên nền M0.
- `docs/DATA_MODEL.md` — Mô tả chi tiết 15 bảng dữ liệu và sơ đồ ER dạng Mermaid.
- `docs/QUESTIONS.md` — Các quyết định kỹ thuật đã chọn và lý do.
- `docs/TEST_REPORT.md` — Lệnh kiểm thử và báo cáo kết quả nghiệm thu.
