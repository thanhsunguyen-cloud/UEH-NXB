# M0 – YÊU CẦU SỬA LẦN 1
UEH Publishing Portal V2 · Kết quả rà soát ngày 25/11/2026 · Owner: Nguyễn Thanh Sử

> Giao nguyên văn tài liệu này cho AI đã làm M0. Sửa trên nhánh `m0-fix-1`. Chỉ được báo "xong" khi các lệnh ở mục 4 chạy **thật** và dán nguyên văn kết quả vào `docs/TEST_REPORT.md`.

## 1. Kết quả kiểm tra thực tế

Môi trường kiểm tra: Python 3.13, Django 5.2.19, PostgreSQL 16, django-allauth 65.22.

| Hạng mục | Kết quả |
|---|---|
| `manage.py check` | Chạy được, 3 cảnh báo |
| `makemigrations --check` | **Không đạt**: migration lệch với model (core và accounts) |
| `pytest` | **36 đạt, 1 không đạt** (`test_editor_cannot_login_with_password`) |
| Độ phủ `apps/core` | 87% (đạt ngưỡng 85%) |
| `ruff check` | **Không đạt**: 11 lỗi |
| `ruff format --check` | **Không đạt**: 18 file chưa định dạng |
| CI (GitHub Actions) | **Sẽ không chạy được**: `EMAIL_URL=locmem://` không hợp lệ |
| `seed_demo` | Đạt |
| ADMIN đăng nhập `/django-admin/` bằng mật khẩu | **Đăng nhập được** – vi phạm mục 5.1 |

## 2. Lỗi bắt buộc sửa

### S1. Nhân sự đăng nhập được bằng mật khẩu (bảo mật)
- Hiện tượng: ADMIN đặt mật khẩu rồi đăng nhập `/django-admin/login/` → thành công. Test `test_editor_cannot_login_with_password` không đạt.
- Nguyên nhân: `CustomerPasswordBackend` trả `None` cho EDITOR/ADMIN, Django chuyển sang backend tiếp theo `allauth.account.auth_backends.AuthenticationBackend`, backend này kiểm tra mật khẩu và cho qua.
- Yêu cầu: với EDITOR/ADMIN, `CustomerPasswordBackend.authenticate` phải `raise PermissionDenied` để dừng toàn bộ chuỗi backend; hoặc thay backend allauth bằng lớp con chặn mật khẩu cho EDITOR/ADMIN. Đăng nhập Google của nhân sự vẫn phải hoạt động.
- Thêm test: ADMIN và EDITOR không đăng nhập được qua `/django-admin/login/` và qua trang đăng nhập của Portal; `authenticate(...)` trả `None` cho cả hai.

### S2. CI không chạy được
- `.github/workflows/ci.yml`: đổi `EMAIL_URL: locmem://` thành `EMAIL_URL: memorymail://` (django-environ không hỗ trợ `locmem`).
- Chạy `ruff check . --fix`, sửa tay các lỗi còn lại, rồi `ruff format .`.

### S3. Migration lệch với model
- Xóa migration viết tay, tạo lại bằng `python manage.py makemigrations` trên PostgreSQL (hoặc thêm migration `0002` cho phần lệch).
- Thêm bước vào CI, trước pytest: `python manage.py makemigrations --check --dry-run`.

### S4. Tải xuống file lớn bị Cloud Run chặn
- `DocumentDownloadView` đang đặt `Content-Length` cố định cho `StreamingHttpResponse`, nên response không còn là dạng stream chunked. File trên 32 MiB có thể bị Cloud Run từ chối.
- Yêu cầu: không đặt `Content-Length` khi `size_bytes` > 32 MiB (hoặc bỏ hẳn). Thêm test kiểm tra response của file 40 MiB không có header `Content-Length`.

### S5. Xóa hàng loạt vượt qua chặn xóa
- `delete()` trên từng bản ghi đã bị chặn, nhưng `Model.objects.filter(...).delete()` và `.update(...)` vẫn xóa/sửa được `Document`, `AuditEvent`, `StatusHistory`, `Receivable`, `Collection`.
- Yêu cầu: thêm QuerySet/Manager dùng chung chặn `delete()` (cả 5 model) và chặn `update()` (AuditEvent, StatusHistory). Thêm test cho từng model.

### S6. Báo cáo kiểm thử không phản ánh việc chạy thật
- `docs/TEST_REPORT.md` hiện chỉ ghi `py_compile` và "đối chiếu trên cổng trực tuyến". Yêu cầu dán **nguyên văn** kết quả của các lệnh ở mục 4, chạy trong Docker với PostgreSQL.

## 3. Nên sửa trong lần này

- Thay `ACCOUNT_EMAIL_REQUIRED`, `ACCOUNT_USERNAME_REQUIRED` (đã lỗi thời) bằng `ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]`.
- Tạo thư mục `static/` (có `.gitkeep`) để hết cảnh báo `staticfiles.W004`.
- Thêm `skip_postgeneration_save = True` vào Meta của các factory để hết cảnh báo factory_boy.
- Tách `test_full_happy_path_and_missing_conditions_for_every_row` thành test theo từng dòng của bảng 7.2 (dùng `pytest.mark.parametrize`), để khi lỗi biết ngay dòng nào.
- Nâng độ phủ `permissions.py` (79%) lên ≥ 90%: thêm ca cho `can_edit_case_info`, `can_upload` theo từng trạng thái, `can_view_finance`/`can_manage_finance`.

## 4. Lệnh nghiệm thu (dán nguyên văn kết quả)

```bash
docker compose up -d --build
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web ruff check .
docker compose run --rm web ruff format --check .
docker compose run --rm web pytest --cov=apps/core --cov-fail-under=85
```

Và đẩy nhánh `m0-fix-1` lên GitHub, mở pull request để CI chạy: chỉ nghiệm thu khi CI xanh.
