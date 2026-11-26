# GÓI GIAO VIỆC M8 – TÀI CHÍNH VÀ CÔNG NỢ PHÍ DỊCH VỤ XUẤT BẢN
UEH Publishing Portal V2 · Đợt 3 · Người làm: **AI-9 (Claude)** · từ 27/11/2026, khoảng 1 tuần · Owner: Nguyễn Thanh Sử

> Đọc `AGENTS.md`, `docs/CONVENTIONS.md`, `docs/DATA_MODEL.md` và tài liệu này trước khi viết code. Nhánh `m8-finance`.
> **Chỉ sửa:** `apps/finance/`, `templates/finance/`, test mới `tests/test_finance_*.py` (không sửa `tests/test_finance.py` của M0), `docs/QUESTIONS_M8.md`, `docs/TEST_REPORT_M8.md`.
> Không sửa file M0 (`apps/core`, `apps/accounts`, `portal/settings`, `templates/base.html`, `templates/partials/`, `tests/factories.py`, `pyproject.toml`). Không tạo model, không tạo migration.
> Gặp điểm chưa rõ: ghi vào `docs/QUESTIONS_M8.md`, chọn phương án đơn giản nhất, làm tiếp.

## 1. Mục tiêu
Theo dõi **phí dịch vụ xuất bản** của từng hồ sơ: khoản phải thu (`Receivable`), khoản đã thu (`Collection`), số còn nợ và tuổi nợ. Đây là sổ theo dõi nghiệp vụ, **không phải** hạch toán kế toán, không xuất hóa đơn, không thanh toán trực tuyến.

Quyền (đã có trong M0):
- Xem: EDITOR có `finance_access` VIEW hoặc MANAGE (`FinanceViewMixin`).
- Ghi nhận/điều chỉnh: EDITOR có MANAGE (`FinanceManageMixin`).
- Mọi người khác (CUSTOMER, ADMIN, EDITOR NONE) → 404.

Giữ nguyên tên URL đã có (`finance:overview`, `finance:debt`, `finance:manage`); được thêm URL mới. **Bắt buộc** có URL `/tai-chinh/ho-so/<uuid:case_id>/` tên `finance:case` (M3 trỏ tới bằng đường dẫn cố định).

Chỉ dùng hàm của M0: `create_receivable`, `create_collection`, `outstanding`, `receivable_status`, `aging_bucket`, `effective_receivable_amount`, `total_collected`. Không gọi `.delete()`, không sửa trực tiếp số tiền đã lưu.

## 2. Màn hình

### 2.1 Tổng quan tài chính – `finance:overview` (`/tai-chinh/`)
- Bộ lọc kỳ (từ ngày – đến ngày; mặc định năm hiện tại), loại phí (`FeeType`), hình thức xuất bản.
- Chỉ số: tổng phải thu phát sinh trong kỳ (theo `invoice_date`, nếu trống thì ngày tạo), tổng đã thu trong kỳ (theo `paid_date`), tổng còn nợ tại ngày cuối kỳ.
- Bảng theo tháng: phải thu, đã thu. Bảng theo loại phí. Bút toán điều chỉnh được tính đúng như hàm M0.
- Nút "Xuất CSV" (UTF-8 có BOM để mở được bằng Excel), ghi `log_event(action="finance.export")`.

### 2.2 Công nợ – `finance:debt` (`/tai-chinh/cong-no/`)
- Danh sách khoản phải thu còn nợ (`outstanding > 0`): mã hồ sơ, tên sách, đơn vị/tác giả phải trả, loại phí, số phải thu, đã thu, còn nợ, hạn thanh toán, nhóm tuổi nợ (Chưa đến hạn, 1–30, 31–60, 61–90, trên 90 ngày).
- Bảng tổng theo nhóm tuổi nợ; lọc theo nhóm tuổi nợ, loại phí, người phải trả; tìm theo mã hồ sơ/tên sách. Phân trang 25 dòng. Nút "Xuất CSV".

### 2.3 Tài chính một hồ sơ – `finance:case` (`/tai-chinh/ho-so/<uuid>/`)
- `FinanceViewMixin` + kiểm tra hồ sơ tồn tại (404 nếu không).
- Thông tin hồ sơ (mã hiển thị, tên sách, người đại diện); danh sách khoản phải thu (kể cả bút toán điều chỉnh, ghi chú), dưới mỗi khoản là các lần thu; tổng phải thu / đã thu / còn nợ của hồ sơ.
- Với người có MANAGE: nút "Thêm khoản phải thu", "Ghi nhận đã thu" (cho từng khoản), "Điều chỉnh" (tạo bút toán điều chỉnh, bắt buộc ghi chú), "Đảo khoản thu" (Collection điều chỉnh, bắt buộc ghi chú). Thu vượt số còn nợ: hiện cảnh báo, chỉ cho lưu khi tích "Xác nhận thu vượt" và có ghi chú (`confirm_overpayment=True`).
- Link quay lại `/noi-bo/ho-so/<uuid>/`.

### 2.4 Ghi nhận – `finance:manage` (`/tai-chinh/ghi-nhan/`)
Trang cho người MANAGE: ô tìm hồ sơ theo mã/ISBN/tên sách → chuyển tới `finance:case` của hồ sơ đó; danh sách 20 thao tác tài chính gần nhất (từ `AuditEvent` action `finance.*`).

### 2.5 Form
- Khoản phải thu: loại phí (đang dùng), số tiền (số nguyên dương, VNĐ), diễn giải, đơn vị/tác giả phải trả (mặc định tên đơn vị liên kết hoặc tên người đại diện), số hợp đồng, số chứng từ, ngày chứng từ, hạn thanh toán, ghi chú.
- Đã thu: ngày thu (không ở tương lai), số tiền, hình thức (Chuyển khoản/Tiền mặt/Khác), số chứng từ, ghi chú.
- Hiển thị tiền định dạng `3.500.000 đ`.

## 3. Giao diện
Kế thừa `base.html`, Bootstrap 5 + HTMX, tiếng Việt.

## 4. Test bắt buộc (pytest, `tests/test_finance_*.py`)
- Mọi URL M8: chưa đăng nhập → đăng nhập; CUSTOMER, ADMIN, EDITOR `NONE` → 404; EDITOR `VIEW` xem được nhưng mọi URL/POST ghi nhận → 404.
- Thêm khoản phải thu, ghi nhận thu, điều chỉnh, đảo khoản thu đều ghi AuditEvent và số còn nợ tính đúng.
- Thu vượt không xác nhận bị chặn; có xác nhận + ghi chú thì được.
- Điều chỉnh/đảo thiếu ghi chú bị chặn. Không có URL xóa.
- Công nợ: phân nhóm tuổi nợ đúng theo `aging_bucket`; khoản đã thu đủ không hiện.
- Tổng quan: số liệu theo kỳ đúng với dữ liệu mẫu; CSV mở được, đúng cột, có BOM.
- Độ phủ `apps/finance` ≥ 85%.

## 5. Không làm
Không hạch toán kế toán, không xuất hóa đơn, không thanh toán trực tuyến, không gửi email nhắc nợ, không hiển thị tài chính cho khách hàng, không sửa màn hình M3.

## 6. Bàn giao
Chạy đủ: `ruff check .`, `ruff format --check .`, `python manage.py makemigrations --check --dry-run`, `pytest --cov=apps --cov-fail-under=85`. Ghi kết quả vào `docs/TEST_REPORT_M8.md`. Đẩy nhánh `m8-finance`, báo cáo tiếng Việt. Không gộp vào `main`.
