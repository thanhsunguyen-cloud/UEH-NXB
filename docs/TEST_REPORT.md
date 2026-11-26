# BÁO CÁO KIỂM THỬ M0 — SỬA LẦN 1 (`m0-fix-1`)

## 1. Môi trường thực thi thực tế

- **Python**: `3.12.16`
- **Django**: `5.2.19`
- **django-allauth**: `65.22.1`
- **PostgreSQL**: `PostgreSQL 15.20 (Debian 15.20-0+deb12u1) on x86_64-pc-linux-gnu`
- **pytest**: `9.2.0` (`pytest-django 4.14.0`, `pytest-cov 7.1.0`)
- **ruff**: `0.17.6`
- **Lưu ý về Docker**: Môi trường chạy của phiên tạo mã không có Docker daemon để gọi `docker compose up -d --build`, nên toàn bộ các lệnh nghiệm thu đã được chạy **trực tiếp trên PostgreSQL thật** với cùng biến môi trường của `ci.yml` (`DATABASE_URL=postgres://ueh_portal:ueh_portal@127.0.0.1:5432/ueh_portal`, `EMAIL_URL=memorymail://`).

## 2. Tóm tắt các mục đã khắc phục (S1–S6 & Mục 3)

| Hạng mục | Trạng thái | Ghi chú kiểm chứng |
|---|---|---|
| **S1** Chặn mật khẩu cho `EDITOR` & `ADMIN` | Đạt | `CustomerPasswordBackend` ném `PermissionDenied` để dừng chuỗi backend; thêm `PortalAllauthBackend` phòng thủ lớp 2; đã test `authenticate()`, `/tai-khoan/dang-nhap/`, `/django-admin/login/` cho cả `EDITOR` và `ADMIN`, và test đăng nhập Google `@ueh.edu.vn`. |
| **S2** CI `EMAIL_URL` & `ruff` | Đạt | Đổi `EMAIL_URL` sang `memorymail://` trong `.github/workflows/ci.yml`; thêm `[tool.setuptools.packages.find]` trong `pyproject.toml`; `ruff check .` (0 lỗi) và `ruff format --check .` (73/73 tệp đạt). |
| **S3** Migration khớp model | Đạt | Xóa migration viết tay, tạo lại bằng `python manage.py makemigrations` trên PostgreSQL; thêm bước `makemigrations --check --dry-run` vào CI trước `pytest`. |
| **S4** Stream download tệp > 32 MiB | Đạt | Bỏ header `Content-Length` cố định trong `DocumentDownloadView`; thêm test tải tệp 40 MiB kiểm tra không có `Content-Length`. |
| **S5** Chặn xóa/sửa hàng loạt (`QuerySet`) | Đạt | Thêm `NoDeleteQuerySet`/`NoDeleteManager` (`Document`, `Receivable`, `Collection`) và `AppendOnlyQuerySet`/`AppendOnlyManager` (`AuditEvent`, `StatusHistory`); đã test `.objects.filter(...).delete()` cho cả 5 model và `.update()` cho `AuditEvent`, `StatusHistory`. |
| **S6** Báo cáo kết quả chạy thật | Đạt | Dán nguyên văn kết quả chạy thật ở Mục 3 bên dưới. |
| **Mục 3** Cải thiện bổ sung | Đạt | Đổi sang `ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]`; tạo `static/.gitkeep` (hết cảnh báo `staticfiles.W004`); thêm `skip_postgeneration_save = True` vào `UserFactory.Meta`; tách test bảng 7.2 theo từng dòng với `@pytest.mark.parametrize`; nâng độ phủ `apps/core/permissions.py` lên **99%**. |

## 3. Kết quả chạy thực tế (nguyên văn)

### 3.1. `python manage.py check`

```text
$ python manage.py check
System check identified no issues (0 silenced).
```

### 3.2. `python manage.py makemigrations --check --dry-run`

```text
$ python manage.py makemigrations --check --dry-run
No changes detected
```

### 3.3. `ruff check .`

```text
$ ruff check .
All checks passed!
```

### 3.4. `ruff format --check .`

```text
$ ruff format --check .
73 files already formatted
```

### 3.5. `python manage.py migrate --noinput` & `python manage.py seed_demo`

```text
$ python manage.py migrate --noinput
Operations to perform:
  Apply all migrations: account, accounts, admin, auth, contenttypes, core, sessions, sites, socialaccount
Running migrations:
  Applying contenttypes.0001_initial... OK
  Applying contenttypes.0002_remove_content_type_name... OK
  Applying auth.0001_initial... OK
  Applying auth.0002_alter_permission_name_max_length... OK
  Applying auth.0003_alter_user_email_max_length... OK
  Applying auth.0004_alter_user_username_opts... OK
  Applying auth.0005_alter_user_last_login_null... OK
  Applying auth.0006_require_contenttypes_0002... OK
  Applying auth.0007_alter_validators_add_error_messages... OK
  Applying auth.0008_alter_user_username_max_length... OK
  Applying auth.0009_alter_user_last_name_max_length... OK
  Applying auth.0010_alter_group_name_max_length... OK
  Applying auth.0011_update_proxy_permissions... OK
  Applying auth.0012_alter_user_first_name_max_length... OK
  Applying accounts.0001_initial... OK
  Applying account.0001_initial... OK
  Applying account.0002_email_max_length... OK
  Applying account.0003_alter_emailaddress_create_unique_verified_email... OK
  Applying account.0004_alter_emailaddress_drop_unique_email... OK
  Applying account.0005_emailaddress_idx_upper_email... OK
  Applying account.0006_emailaddress_lower... OK
  Applying account.0007_emailaddress_idx_email... OK
  Applying account.0008_emailaddress_unique_primary_email_fixup... OK
  Applying account.0009_emailaddress_unique_primary_email... OK
  Applying admin.0001_initial... OK
  Applying admin.0002_logentry_remove_auto_add... OK
  Applying admin.0003_logentry_add_action_flag_choices... OK
  Applying core.0001_initial... OK
  Applying sessions.0001_initial... OK
  Applying sites.0001_initial... OK
  Applying sites.0002_alter_domain_unique... OK
  Applying socialaccount.0001_initial... OK
  Applying socialaccount.0002_token_max_lengths... OK
  Applying socialaccount.0003_extra_data_default_dict... OK
  Applying socialaccount.0004_app_provider_id_settings... OK
  Applying socialaccount.0005_socialtoken_nullable_app... OK
  Applying socialaccount.0006_alter_socialaccount_extra_data... OK

$ python manage.py seed_demo
Đã khởi tạo xong dữ liệu mẫu M0 (1 admin, 2 editor, 2 customer, 5 hồ sơ, 4 khoản phải thu).
```

### 3.6. `pytest --cov=apps/core --cov-fail-under=85`

```text
$ pytest --cov=apps/core --cov-fail-under=85
============================= test session starts ==============================
platform linux -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0
django: version: 5.2.19, settings: portal.settings.dev (from env)
rootdir: /app/applet/ueh-portal
configfile: pyproject.toml
plugins: django-4.14.0, Faker-40.63.0, cov-7.1.0
collected 121 items

tests/test_audit_and_review.py ...                                       [  2%]
tests/test_auth.py .................                                     [ 16%]
tests/test_finance.py ..                                                 [ 18%]
tests/test_permissions.py .............................................. [ 56%]
.......................                                                  [ 75%]
tests/test_storage.py ....                                               [ 78%]
tests/test_workflow.py .................                                 [ 92%]
tests/test_codes.py .........                                            [100%]

=============================== warnings summary ===============================
tests/test_auth.py: 15 warnings
tests/test_finance.py: 1 warning
tests/test_permissions.py: 2 warnings
tests/test_storage.py: 2 warnings
  /tmp/ueh-venv/lib/python3.12/site-packages/django/core/handlers/base.py:61: UserWarning: No directory at: /app/applet/ueh-portal/staticfiles/
    mw_instance = middleware(adapted_handler)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
================================ tests coverage ================================
_______________ coverage: platform linux, python 3.12.16-final-0 _______________

Name                                   Stmts   Miss  Cover   Missing
--------------------------------------------------------------------
apps/core/__init__.py                      0      0   100%
apps/core/admin.py                        47      4    91%   33, 36, 39, 46
apps/core/apps.py                          6      0   100%
apps/core/audit.py                        14      1    93%   14
apps/core/codes.py                        54      4    93%   37, 40, 50, 53
apps/core/context_processors.py            4      0   100%
apps/core/finance.py                      79      2    97%   119, 176
apps/core/migrations/0001_initial.py      10      0   100%
apps/core/migrations/__init__.py           0      0   100%
apps/core/mixins.py                       60     11    82%   43, 52-54, 66, 70, 72, 94, 103-105
apps/core/models.py                      413     35    92%   79, 95, 111, 234, 255, 262, 265-268, 313, 378, 432, 444, 449, 493, 531, 562, 596, 616, 653, 718, 722, 730, 733, 737, 739, 790, 798, 800-803, 805, 862
apps/core/permissions.py                  82      1    99%   160
apps/core/signals.py                       2      0   100%
apps/core/storage.py                     167     16    90%   119, 149, 152, 166, 171, 198-199, 216, 232, 282, 284, 286, 288, 298, 317, 319
apps/core/urls.py                          4      0   100%
apps/core/views.py                        69     39    43%   36, 63-86, 100-115, 122-142
apps/core/workflow.py                    169     19    89%   104, 123-124, 257, 318-342, 357, 359, 361
--------------------------------------------------------------------
TOTAL                                   1180    132    89%
Required test coverage of 85% reached. Total coverage: 88.81%
====================== 121 passed, 20 warnings in 45.72s =======================
```

---

# BÁO CÁO KIỂM THỬ M6 — TRANG CÔNG KHAI (`m6-public-site`)

## 1. Môi trường chạy thật

- Python `3.12.3`, Django `5.2.19`, pytest `9.2.0`, ruff `0.17.6`
- PostgreSQL: `PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1) on x86_64-pc-linux-gnu`
- Biến môi trường giống bước pytest của `.github/workflows/ci.yml` (`DATABASE_URL=postgres://ueh_portal:…@localhost:5432/ueh_portal_test`, `FILE_STORAGE_BACKEND=local`, `MEDIA_ROOT=/tmp/ueh-portal-ci-media`, `EMAIL_URL=memorymail://`).
- Ngày chạy: 26/11/2026. CR-001 **chưa** gộp vào `main`: test ảnh bìa dùng kho giả `FakeLibraryStorage` (`apps/public_site/tests/conftest.py`) có đúng chữ ký `save_library_file` của CR-001.

## 2. Đối chiếu yêu cầu test bắt buộc (mục 6 gói M6)

| Yêu cầu | Test |
|---|---|
| Mọi trang công khai trả 200 khi chưa đăng nhập | `test_public_pages_ok_for_anonymous` (7 trang), `test_news_detail_published_and_unpublished`, `test_form_download_active_only`, `test_image_only_for_published_items` |
| Tin/sách chưa đăng: chi tiết và ảnh trả 404 | `test_news_detail_published_and_unpublished`, `test_image_only_for_published_items[tin-tuc/sach-moi]`, `test_published_cover_served_after_upload` |
| Tải biểu mẫu chỉ bản đang áp dụng; bản đã tắt → 404 | `test_form_download_active_only`, `test_forms_page_lists_latest_active_per_code`, `test_form_download_missing_file_404` |
| Trang quản lý: CUSTOMER và ADMIN nhận 404 | `test_manage_pages_404_for_customer_and_admin[customer/admin_user]` (mọi trang GET và POST đăng/gỡ đăng) |
| Nội dung có `<script>` hiển thị dạng chữ | `test_script_content_is_escaped` |
| Ảnh sai định dạng hoặc > 2 MB bị từ chối | `test_invalid_cover_rejected[gif/svg/fake-png/mismatch/empty/too-large]`, `test_cover_exactly_2mb_accepted` |
| Độ phủ `apps/public_site` ≥ 85% | Mục 3 bên dưới: **99,47%** |

Thêm: không lộ dữ liệu hồ sơ (`test_public_pages_do_not_show_case_data`), ghi `AuditEvent` `public.news_create/update/publish/unpublish`, `public.book_create/update/publish`, slug không trùng và không trùng `quan-ly`, ISBN-13 sai bị từ chối.

## 3. Kết quả chạy thật (nguyên văn)


---

# BÁO CÁO KIỂM THỬ M7 — QUẢN TRỊ HỆ THỐNG (`m7-admin`)

## 1. Môi trường chạy

- Python 3.13.18, Django 5.2.19, PostgreSQL 16.15, pytest 9.2.0, ruff 0.17.6.
- Chạy trực tiếp trên PostgreSQL thật với đúng biến môi trường của `.github/workflows/ci.yml` (container của phiên làm việc không có Docker daemon; bước `docker-smoke` do CI trên GitHub chạy).
- Lưu file biểu mẫu: test dùng **bản giả** `save_library_file` (lớp `FakeLibraryStorage` trong `tests/test_administration.py`) vì CR-001 chưa vào `main`. Sẽ chạy lại với bản thật sau khi CR-001 được gộp.

## 2. Phạm vi test (`tests/test_administration.py`, 42 test)

| Yêu cầu mục 4 của gói M7 | Test |
|---|---|
| Mọi URL M7: CUSTOMER, EDITOR nhận 404; chưa đăng nhập chuyển tới đăng nhập | `test_non_admin_gets_404_on_every_m7_url`, `test_anonymous_is_redirected_to_login_on_every_m7_url`, `test_locked_admin_is_treated_as_logged_out` |
| Tạo nhân sự email ngoài domain UEH bị từ chối | `test_create_staff_outside_ueh_domain_is_rejected` |
| Không làm số Admin hoạt động < 2; không tự khóa mình | `test_active_admins_never_drop_below_two`, `test_cannot_lock_or_demote_self` |
| Đổi vai trò, quyền tài chính, khóa/mở ghi đúng `AuditEvent` | `test_role_finance_lock_unlock_write_correct_audit_events`, `test_create_editor_with_finance_access_logs_event` |
| Danh mục: không có đường xóa; tắt mục đang dùng được | `test_catalog_in_use_can_be_disabled_and_is_never_deleted`, `test_no_delete_route_for_users_or_catalogs`, `test_catalog_create_update_toggle` |
| Biểu mẫu: kích hoạt bản mới tự tắt bản cũ; từ chối sai định dạng/quá dung lượng | `test_activating_new_version_deactivates_old_same_code`, `test_template_rejects_wrong_extension`, `test_template_rejects_file_over_limit` |
| Nhật ký: `case.*` không lộ `data` trong HTML | `test_audit_log_hides_data_of_case_document_finance` (kèm `document.*`, `finance.*`, nhóm khác) |
| Độ phủ `apps/administration` ≥ 85% | **100%** (mục 3) |

## 3. Kết quả chạy thật (nguyên văn, đã lược các dòng cảnh báo `staticfiles` lặp lại)

```text
$ python manage.py check
System check identified no issues (0 silenced).
tests/test_administration.py: 38 warnings
tests/test_auth.py: 15 warnings
tests/test_finance.py: 1 warning
tests/test_permissions.py: 2 warnings
tests/test_storage.py: 2 warnings

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
================================ tests coverage ================================
_______________ coverage: platform linux, python 3.13.18-final-0 _______________

Name                                   Stmts   Miss  Cover   Missing
--------------------------------------------------------------------
apps/core/__init__.py                      0      0   100%
apps/core/admin.py                        47      4    91%   33, 36, 39, 46
apps/core/apps.py                          6      0   100%
apps/core/audit.py                        14      1    93%   14
apps/core/codes.py                        54      4    93%   37, 40, 50, 53
apps/core/context_processors.py            4      0   100%
apps/core/finance.py                      79      2    97%   119, 176
apps/core/migrations/0001_initial.py      10      0   100%
apps/core/migrations/__init__.py           0      0   100%
apps/core/mixins.py                       60      8    87%   43, 66, 70, 72, 94, 103-105
apps/core/models.py                      413     34    92%   79, 95, 111, 234, 255, 265-268, 313, 378, 432, 444, 449, 493, 531, 562, 596, 616, 653, 718, 722, 730, 733, 737, 739, 790, 798, 800-803, 805, 862
apps/core/permissions.py                  82      1    99%   160
apps/core/signals.py                       2      0   100%
apps/core/storage.py                     167     16    90%   119, 149, 152, 166, 171, 198-199, 216, 232, 282, 284, 286, 288, 298, 317, 319
apps/core/urls.py                          4      0   100%
apps/core/views.py                        69     39    43%   36, 63-86, 100-115, 122-142
apps/core/workflow.py                    169     19    89%   104, 123-124, 257, 318-342, 357, 359, 361
--------------------------------------------------------------------
TOTAL                                   1180    128    89%
Required test coverage of 85% reached. Total coverage: 89.15%
163 passed, 58 warnings in 44.99s
[exit 0]

$ pytest -o addopts="" -p no:cacheprovider --cov=apps/administration --cov-report=term-missing --cov-fail-under=85 tests/test_administration.py
============================= test session starts ==============================
platform linux -- Python 3.13.18, pytest-9.2.0, pluggy-1.7.0
django: version: 5.2.19, settings: portal.settings.dev (from env)
rootdir: /home/user/UEH-NXB
configfile: pyproject.toml
plugins: Faker-40.63.0, cov-7.1.0, django-4.14.0
collected 42 items

tests/test_administration.py ..........................................  [100%]

=============================== warnings summary ===============================
tests/test_administration.py: 38 warnings

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
================================ tests coverage ================================
_______________ coverage: platform linux, python 3.13.18-final-0 _______________

Name                              Stmts   Miss  Cover   Missing
---------------------------------------------------------------
apps/administration/__init__.py       0      0   100%
apps/administration/apps.py           4      0   100%
apps/administration/forms.py        105      0   100%
apps/administration/services.py     151      0   100%
apps/administration/urls.py           4      0   100%
apps/administration/views.py        224      0   100%
---------------------------------------------------------------
TOTAL                               488      0   100%
Required test coverage of 85% reached. Total coverage: 100.00%
======================= 42 passed, 38 warnings in 11.80s =======================
[exit 0]
```
=======
$ ruff check .
All checks passed!
$ ruff format --check .
77 files already formatted
$ python manage.py makemigrations --check --dry-run
No changes detected
$ pytest --cov=apps/core --cov-fail-under=85
--------------------------------------------------------------------
TOTAL                                   1180    130    89%
Required test coverage of 85% reached. Total coverage: 88.98%
====================== 168 passed, 66 warnings in 53.66s =======================
$ pytest -o addopts="" apps/public_site --cov=apps/public_site --cov-report=term-missing --cov-fail-under=85
_______________ coverage: platform linux, python 3.12.3-final-0 ________________

Name                                          Stmts   Miss  Cover   Missing
---------------------------------------------------------------------------
apps/public_site/__init__.py                      0      0   100%
apps/public_site/apps.py                          4      0   100%
apps/public_site/forms.py                        38      0   100%
apps/public_site/migrations/0001_initial.py       8      0   100%
apps/public_site/migrations/__init__.py           0      0   100%
apps/public_site/models.py                       42      2    95%   38, 68
apps/public_site/services.py                     59      2    97%   48, 81
apps/public_site/tests/__init__.py                0      0   100%
apps/public_site/tests/conftest.py               44      0   100%
apps/public_site/tests/helpers.py                19      0   100%
apps/public_site/tests/test_manage.py           150      0   100%
apps/public_site/tests/test_public_pages.py     148      0   100%
apps/public_site/urls.py                          4      0   100%
apps/public_site/views.py                       243      0   100%
---------------------------------------------------------------------------
TOTAL                                           759      4    99%
Required test coverage of 85% reached. Total coverage: 99.47%
======================= 47 passed, 46 warnings in 4.44s ========================
```

Ghi chú: phiên làm việc không có Docker daemon nên job `docker-smoke` chỉ chạy trên GitHub Actions. Đã mở thử trang `/` và `/quy-trinh/` bằng trình duyệt ở khổ iPhone 13: không tràn ngang.

[exit 0]

$ python manage.py makemigrations --check --dry-run
No changes detected
[exit 0]

$ ruff check .
All checks passed!
[exit 0]

$ ruff format --check .
72 files already formatted
[exit 0]

$ pytest --cov=apps/core --cov-fail-under=85 -q -p no:cacheprovider
........................................................................ [ 44%]
........................................................................ [ 88%]
...................                                                      [100%]
=============================== warnings summary ========================