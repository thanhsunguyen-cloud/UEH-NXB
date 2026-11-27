# Báo cáo kiểm tra – M8 Tài chính & Công nợ

Ngày chạy: 27/11/2026 · Nhánh `m8-finance` · Python 3.13, PostgreSQL 16, biến môi trường giống `.github/workflows/ci.yml`.

| Lệnh | Kết quả |
| :--- | :--- |
| `ruff check .` | Đạt (All checks passed) |
| `ruff format --check .` | Đạt (119 files already formatted) |
| `python manage.py makemigrations --check --dry-run` | Đạt (No changes detected – M8 không tạo model/migration) |
| `pytest --cov=apps --cov-fail-under=85` | Đạt: **446 passed**, tổng độ phủ **96,95%** |

Độ phủ riêng `apps/finance`:

| File | Độ phủ |
| :--- | :--- |
| `views.py` | 100% |
| `services.py` | 100% |
| `forms.py` | 99% |
| `templatetags/finance_tags.py`, `urls.py`, `apps.py` | 100% |

## Test mới
- `tests/test_finance_access.py`: mọi URL M8 (kể cả xuất CSV và các trang ghi nhận). Chưa đăng nhập → trang đăng nhập; CUSTOMER, ADMIN, EDITOR `NONE` → 404 (cả GET và POST); EDITOR `VIEW` xem được tổng quan, công nợ, hồ sơ nhưng mọi URL/POST ghi nhận → 404, không tạo bản ghi và không thấy nút ghi nhận; `finance:case` đúng đường dẫn `/tai-chinh/ho-so/<uuid>/`, hồ sơ không tồn tại → 404; không có URL xóa.
- `tests/test_finance_entries.py`: thêm khoản phải thu (người phải trả mặc định là người đại diện hoặc đơn vị liên kết, chỉ hiện loại phí đang dùng, chặn số tiền ≤ 0 hoặc lẻ); ghi nhận thu; ngày thu ở tương lai bị chặn; thu vượt bị chặn khi thiếu xác nhận hoặc thiếu ghi chú, đủ cả hai thì lưu được; điều chỉnh thiếu ghi chú, bằng 0 hoặc làm âm bị chặn; đảo khoản thu thiếu ghi chú bị chặn, không đảo được hai lần. Mỗi thao tác đều kiểm tra AuditEvent và `outstanding()`. Ngoài ra: lỗi `ValidationError` từ M0 hiện ra form; trang Ghi nhận tìm theo mã tạm/ISBN có gạch nối/tên sách và hiện đúng 20 thao tác gần nhất; định dạng `3.500.000 đ`.
- `tests/test_finance_reports.py`: tổng quan theo kỳ với dữ liệu mẫu (có điều chỉnh, đảo, 2 loại phí, 2 hình thức, dữ liệu năm trước), bảng theo tháng/loại phí, còn nợ cuối kỳ, dùng ngày tạo khi không có ngày chứng từ, kỳ mặc định năm hiện tại, khoảng ngày sai; CSV có BOM, đúng cột, ghi `finance.export`. Công nợ: 5 nhóm tuổi nợ khớp `aging_bucket` (biên 30/31/90/91 ngày), khoản đã thu đủ hoặc điều chỉnh về 0 không hiện, bảng tổng theo nhóm, lọc theo nhóm/loại phí/người phải trả, tìm theo mã/tên, phân trang 25 dòng giữ bộ lọc, HTMX trả phần bảng, CSV đúng dòng. Trang hồ sơ: tổng phải thu/đã thu/còn nợ, hiện ghi chú điều chỉnh, đánh dấu khoản đã đảo.

## Kiểm tra giao diện
Đã chạy `seed_demo`, thêm vài khoản phải thu/đã thu và mở `/tai-chinh/`, `/tai-chinh/cong-no/`, `/tai-chinh/ho-so/<uuid>/`, `/tai-chinh/ghi-nhan/` và form ghi nhận thu vượt bằng Chromium headless với tài khoản BTV `MANAGE`. Các trang trả 200, không có lỗi JavaScript, cảnh báo thu vượt hiện đúng. Môi trường thử không tải được Bootstrap/HTMX từ CDN nên chưa xem được giao diện có định dạng; cần Owner xem lại trên máy có Internet.
