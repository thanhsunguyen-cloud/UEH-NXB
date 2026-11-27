# BÁO CÁO KIỂM TRA GÓI M2 – CỔNG KHÁCH HÀNG

Ngày chạy: 27/11/2026 · Nhánh `m2-customer` · PostgreSQL 16 cục bộ, biến môi trường giống `.github/workflows/ci.yml`.

| Lệnh | Kết quả |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 77 files already formatted |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `pytest --cov=apps --cov-fail-under=85` | **170 passed**, tổng độ phủ **89,46%** |

Độ phủ `apps/customer`: `views.py` 100%, `forms.py` 99%, `labels.py` 100%, `templatetags` 100%.

## Test mới (49 test)
- `tests/test_customer_access.py`: mọi URL M2 – chưa đăng nhập → chuyển tới đăng nhập; EDITOR (NONE/MANAGE), ADMIN → 404; khách xem hồ sơ/tác giả của người khác → 404.
- `tests/test_customer_cases.py`: nhãn trạng thái; danh sách, lọc, tìm, phân trang 20; tạo hồ sơ (owner, DRAFT, AuditEvent `case.create`, bỏ qua ISBN/mã NXB/số XNĐK/QĐXB/hợp đồng/BTV gửi lén); Liên kết thiếu tên đơn vị bị từ chối; sửa thông tin có before/after; sửa thông tin và tác giả bị chặn ở SUBMITTED/EDITING/REVISION_REQUIRED.
- `tests/test_customer_detail.py`: nộp thiếu điều kiện → liệt kê thiếu, trạng thái giữ nguyên; đủ → SUBMITTED + StatusHistory; Liên kết cần Mẫu 1; NEED_SUPPLEMENT → nộp lại → SupplementRequest OPEN thành RESOLVED + AuditEvent `case.supplement_resolved`; nộp lại thất bại giữ OPEN; trang chi tiết không chứa ghi chú INTERNAL, FORM_4, tài liệu nội bộ, số tiền; dòng thời gian không lộ ghi chú nội bộ; ô tải đúng trạng thái/loại tài liệu; gửi trao đổi luôn `visibility=CUSTOMER`.
- `tests/test_customer_profile.py`: sửa họ tên/điện thoại/đơn vị, email không đổi, AuditEvent `user.profile_update`.

## Kiểm tra thủ công
Chạy `runserver`, đăng nhập khách hàng bằng Chromium mô phỏng iPhone 13: trang danh sách và chi tiết hiển thị đủ các khối, không tràn ngang (scrollWidth = 390 px).
