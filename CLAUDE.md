# CLAUDE.md – Quy tắc chung (giống AGENTS.md) cho mọi phiên Claude trên kho UEH-NXB

Dự án: UEH Publishing Portal V2 – cổng quản lý quy trình xuất bản của NXB Kinh tế TP.HCM (Django 5.2, PostgreSQL 16, Bootstrap 5 + HTMX).
Owner (người duyệt và bấm gộp): Nguyễn Thanh Sử. Nhóm trưởng kỹ thuật, người rà soát mọi pull request: Claude.

## Trước khi viết code
1. Đọc `docs/CONVENTIONS.md` (hợp đồng kỹ thuật bắt buộc) và `docs/DATA_MODEL.md`.
2. Đọc **đúng gói giao việc** của bạn trong `docs/packages/`. Chỉ làm những gì gói yêu cầu, không mở rộng phạm vi.
3. Gặp điểm chưa rõ: ghi vào file câu hỏi mà gói chỉ định (ví dụ `docs/QUESTIONS_M2.md`; gói cũ dùng `docs/QUESTIONS.md`), chọn phương án đơn giản nhất và làm tiếp; không tự quyết định thay đổi lớn.

## Ranh giới
- Mỗi AI làm trên **một nhánh riêng** theo tên trong gói, tách từ `main` mới nhất, và chỉ sửa trong thư mục của module mình.
- **Không sửa phần nền M0**: `apps/core/`, `apps/accounts/`, `portal/settings/`, `templates/base.html`, `templates/partials/`, trừ đúng những dòng mà gói của bạn cho phép.
- Không tạo model hay migration nếu gói không cho phép.
- Mọi view kế thừa mixin trong `apps/core/mixins.py`; đổi trạng thái hồ sơ chỉ qua `apps.core.workflow.change_status`.
- Ngoài phạm vi tuyệt đối: in ấn, phát hành, hạch toán kế toán, xuất hóa đơn, thanh toán trực tuyến, ký số, tự động duyệt, lưu số CCCD.
- Không ghi mật khẩu, khóa bí mật, file JSON tài khoản dịch vụ vào kho.

## Kiểm tra trước khi nộp (giống CI trong `.github/workflows/ci.yml`)
```bash
pip install -e ".[dev]"
ruff check .
ruff format --check .
# Cần PostgreSQL; biến môi trường mẫu xem ci.yml (DATABASE_URL, EMAIL_URL=memorymail:// ...)
python manage.py makemigrations --check --dry-run
pytest --cov=apps --cov-fail-under=85
```
Không tắt, xóa hay bỏ qua test để có dấu xanh.

## Nộp bài
- Tạo pull request vào `main`, mô tả bằng **tiếng Việt**: đã làm gì, file nào ngoài thư mục module bị sửa (nếu có) và vì sao, cách kiểm tra.
- `main` được khóa: chỉ gộp khi CI xanh (`lint-and-test`, `docker-smoke`) và Claude rà soát đạt. Không tự gộp.
- Sau khi `main` có thay đổi mới, cập nhật nhánh của bạn từ `main` và chạy lại kiểm tra.
