# Báo cáo kiểm tra – M5 Tra cứu, Thống kê danh mục xuất bản, Nhập Excel

Người làm: AI-8 (Claude) · Nhánh `m5-reports` · Ngày 27/11/2026
Môi trường: Python 3.13, Django 5.2.19, PostgreSQL 16 (cục bộ), biến môi trường giống `.github/workflows/ci.yml`.

## Lệnh đã chạy

| Lệnh | Kết quả |
| --- | --- |
| `ruff check .` | All checks passed! |
| `ruff format --check .` | 120 files already formatted |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `pytest --cov=apps --cov-fail-under=85` | **480 passed**, tổng độ phủ **97,25 %** |

## Độ phủ `apps/reports`

| File | Độ phủ |
| --- | --- |
| `forms.py` | 100 % |
| `importer.py` | 99 % |
| `models.py` | 100 % |
| `services.py` | 100 % |
| `urls.py` | 100 % |
| `views.py` | 99 % |
| `migrations/0001_initial.py` | 100 % |

## Test mới (69 test)

- `tests/test_reports_access.py`: mọi URL M5 – chưa đăng nhập → chuyển tới đăng nhập; CUSTOMER và ADMIN → 404 (GET và POST nhập); EDITOR mở được; đường dẫn URL đúng.
- `tests/test_reports_search.py`: tìm theo ISBN có gạch nối, tên tác giả, số QĐXB, số XNĐK, mã tạm; tác giả nối đúng thứ tự (kèm "(Chủ biên)"); liên kết `/noi-bo/ho-so/<uuid>/`; ẩn hồ sơ Nháp; lọc năm (QĐXB → XNĐK), thể loại, lĩnh vực, hình thức, nguồn; HTMX trả partial; phân trang 25 dòng.
- `tests/test_reports_stats.py`: tính theo `decision_date`, rơi về `registration_date`; đầu sách không có ngày không được tính; nhóm tháng/quý/năm đúng số (kể cả kỳ trống); bảng theo thể loại/lĩnh vực/hình thức; bộ lọc; mặc định năm hiện tại; xuất Excel mở được bằng openpyxl, đúng 2 sheet, đúng cột, không có cột tiền, ghi `report.export`.
- `tests/test_reports_import.py`: file mẫu đúng dòng tiêu đề; bước kiểm tra không ghi gì vào database; báo lỗi ISBN sai/trùng trong file/đã có trong hệ thống, thiếu cột/ô bắt buộc, ngày sai, hình thức sai, số trang sai; cảnh báo thể loại không khớp; xác nhận tạo đúng hồ sơ (COMPLETED/DECISION_ISSUED), tác giả đúng thứ tự và vai trò, StatusHistory, AuditEvent `case.import` và `import.batch`, ImportBatch; không cấp mã NXB; tài khoản hệ thống không đăng nhập được; nhập lại cùng file bị báo trùng ISBN; kiểm tra lại khi xác nhận; payload giả/của người khác bị từ chối; file .xls / file hỏng / quá lớn / quá nhiều dòng; không chạy công thức; lô nhập không xóa được.

## File ngoài thư mục module
- `pyproject.toml`: thêm đúng 1 dòng `"openpyxl>=3.1",` (gói cho phép).
