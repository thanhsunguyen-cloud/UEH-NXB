# Báo cáo kiểm tra – M3 Tác nghiệp BTV

Ngày chạy: 27/11/2026 · Nhánh `m3-backoffice` · Python 3.13, PostgreSQL 16, biến môi trường giống `.github/workflows/ci.yml`.

| Lệnh | Kết quả |
| :--- | :--- |
| `ruff check .` | Đạt (All checks passed) |
| `ruff format --check .` | Đạt (97 files already formatted) |
| `python manage.py makemigrations --check --dry-run` | Đạt (No changes detected – M3 không tạo model/migration) |
| `pytest --cov=apps --cov-fail-under=85` | Đạt: **324 passed**, tổng độ phủ **96,07%** |

Độ phủ riêng `apps/backoffice`:

| File | Độ phủ |
| :--- | :--- |
| `views.py` | 100% |
| `forms.py` | 99% |
| `services.py` | 94% |
| `urls.py`, `apps.py` | 100% |

## Test mới (33 test)
- `tests/test_backoffice_views.py`:
  - phân quyền mọi URL M3 (ẩn danh → đăng nhập; CUSTOMER/ADMIN → 404);
  - danh sách ẩn Nháp; tìm theo ISBN (có gạch nối), mã NXB, mã tạm, tên tác giả, email; lọc "Chưa giao", "Của tôi", BTV, hình thức, thể loại; HTMX và phân trang 25 dòng;
  - các nhóm của trang hàng đợi;
  - 5 tab; tiếp nhận cấp mã NXB, rồi hiển thị ISBN; lỗi ISBN tiếng Việt (sai số kiểm tra, ISBN-10, trùng);
  - hồ sơ COMPLETED chỉ xem, mọi POST sửa bị chặn;
  - giao BTV (chỉ EDITOR hoạt động); đổi người đại diện (thiếu lý do bị chặn);
  - CRUD tác giả có nhật ký; ghi chú mặc định Nội bộ; đánh dấu yêu cầu bổ sung RESOLVED;
  - nút tài chính theo `finance_access`.
- `tests/test_backoffice_workflow.py`:
  - quy trình trọn vẹn hồ sơ **Liên kết** SUBMITTED → ARCHIVED qua POST, mỗi bước thử thiếu điều kiện (bị chặn kèm thông báo) rồi bổ sung đủ;
  - nhánh trả sửa / từ chối;
  - Mẫu 4 với tài liệu của hồ sơ khác hoặc sai loại bị từ chối; thiếu ô xác nhận bị từ chối; chỉ duyệt khi EDITING;
  - yêu cầu bổ sung tạo `SupplementRequest` OPEN + NEED_SUPPLEMENT; thiếu nội dung bị chặn; lỗi quy trình rollback.

## Kiểm tra giao diện
Đã chạy `seed_demo` và mở thử `/noi-bo/`, `/noi-bo/can-xu-ly/` và chi tiết hồ sơ (tab Quy trình, hộp thoại Mẫu 4) bằng Chromium headless: không có lỗi JavaScript. Môi trường thử không tải được CSS/JS Bootstrap từ CDN, nên chưa xem được giao diện có định dạng; cần Owner xem lại trên máy có Internet.
