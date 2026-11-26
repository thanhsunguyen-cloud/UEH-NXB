# GÓI GIAO VIỆC M5 – TRA CỨU, THỐNG KÊ DANH MỤC XUẤT BẢN, NHẬP EXCEL DỮ LIỆU CŨ
UEH Publishing Portal V2 · Đợt 3 · Người làm: **AI-8 (Claude)** · từ 27/11/2026, khoảng 1 tuần · Owner: Nguyễn Thanh Sử

> Đọc `AGENTS.md`, `docs/CONVENTIONS.md`, `docs/DATA_MODEL.md` và tài liệu này trước khi viết code. Nhánh `m5-reports`.
> **Chỉ sửa:** `apps/reports/` (kể cả `models.py` và `migrations/` cho model `ImportBatch`), `templates/reports/`, test mới `tests/test_reports_*.py`, `docs/QUESTIONS_M5.md`, `docs/TEST_REPORT_M5.md`.
> **Được sửa thêm đúng 1 dòng ngoài app:** thêm `"openpyxl>=3.1",` vào `dependencies` trong `pyproject.toml`. Nếu `apps.reports` chưa có migration, tạo `apps/reports/migrations/0001_initial.py` bằng `makemigrations reports`.
> Không sửa file M0 khác. Không sửa `tests/factories.py`.
> Gặp điểm chưa rõ: ghi vào `docs/QUESTIONS_M5.md`, chọn phương án đơn giản nhất, làm tiếp.
> **Không dùng dữ liệu thật** (danh mục GPXB thật của NXB) trong mã, test hay ví dụ – chỉ dùng tên sách, tác giả hư cấu.

## 1. Mục tiêu
1. BTV tra cứu nhanh mọi đầu sách (đang xử lý và đã xuất bản, kể cả dữ liệu cũ nhập từ Excel).
2. BTV xem thống kê danh mục xuất bản theo thời gian và xuất ra Excel.
3. BTV nhập danh mục xuất bản các năm trước từ file Excel theo mẫu chuẩn, để thống kê liền mạch.

Giữ nguyên tên URL đã có (`reports:search`, `reports:catalog_stats`); được thêm URL mới. Mọi view: `EditorRequiredMixin` hoặc `PublicationStatsMixin` (CUSTOMER, ADMIN → 404).

## 2. Màn hình

### 2.1 Tra cứu – `reports:search` (`/bao-cao/tra-cuu/`)
- Một ô tìm: ISBN (có hoặc không gạch nối), mã NXB, mã tạm, số XNĐK, số QĐXB, tên sách, tên tác giả/chủ biên.
- Bộ lọc: năm (theo ngày quyết định xuất bản, nếu trống thì ngày XNĐK), trạng thái, thể loại, lĩnh vực, hình thức, nguồn (Portal / Nhập Excel).
- Kết quả: mã hiển thị, tên sách, tác giả (nối tên theo thứ tự), số/ngày QĐXB, trạng thái; bấm vào mở `/noi-bo/ho-so/<uuid>/` (trang của M3, dùng chuỗi đường dẫn cố định). HTMX, phân trang 25 dòng.

### 2.2 Thống kê danh mục xuất bản – `reports:catalog_stats` (`/bao-cao/danh-muc-xuat-ban/`)
- **Ngày tính thống kê** của mỗi đầu sách = `decision_date`, nếu trống thì `registration_date`; đầu sách không có cả hai không được tính (ghi rõ trên trang).
- Bộ lọc: từ ngày – đến ngày (mặc định năm hiện tại), nhóm theo tháng/quý/năm, thể loại, lĩnh vực, hình thức.
- Hiển thị: tổng số đầu sách; bảng số đầu sách theo kỳ; bảng theo thể loại; bảng theo lĩnh vực; bảng theo hình thức (Tự xuất bản / Liên kết); biểu đồ cột theo kỳ vẽ bằng HTML/CSS hoặc SVG (không thêm thư viện JS).
- Danh sách chi tiết (phân trang) và nút **"Xuất Excel"**: file .xlsx gồm sheet "Tổng hợp" và sheet "Danh mục" (STT, Tên xuất bản phẩm, Tác giả, Thể loại, Lĩnh vực, Hình thức, Đơn vị liên kết, ISBN, Số XNĐK, Ngày XNĐK, Số QĐXB, Ngày QĐXB, Ngày nộp lưu chiểu, Số trang, Khổ). Không có cột số tiền. Tải về dạng stream, ghi `log_event(action="report.export")`.

### 2.3 Nhập Excel dữ liệu cũ – `/bao-cao/nhap-excel/`
- **Mẫu file**: nút tải "File mẫu nhập danh mục" do code sinh ra bằng openpyxl, gồm dòng tiêu đề đúng các cột:
  `Tên xuất bản phẩm*`, `Tác giả*` (nhiều người cách nhau dấu `;`, chủ biên ghi "(Chủ biên)" sau tên), `Thể loại`, `Lĩnh vực`, `Ngôn ngữ`, `Hình thức` (Tự xuất bản/Liên kết), `Đơn vị liên kết`, `ISBN`, `Số XNĐK`, `Ngày XNĐK`, `Số QĐXB`, `Ngày QĐXB*`, `Ngày nộp lưu chiểu`, `Số trang`, `Khổ`, `Lần xuất bản`, `Ghi chú`. Dấu `*` = bắt buộc. Ngày nhận kiểu ngày của Excel hoặc chuỗi `dd/mm/yyyy`.
- **Bước 1 – Kiểm tra**: tải file (.xlsx, ≤ 10 MB, form thường vì file nhỏ). Hệ thống đọc, **chưa ghi gì**, hiện bảng kết quả từng dòng: hợp lệ / lỗi (lý do tiếng Việt: thiếu cột bắt buộc, ISBN sai hoặc đã có trong hệ thống, ngày sai định dạng, thể loại/lĩnh vực không có trong danh mục…). Thể loại/lĩnh vực so khớp theo tên (không phân biệt hoa thường); không khớp thì để trống và cảnh báo, không chặn.
- **Bước 2 – Xác nhận nhập**: chỉ nhập các dòng hợp lệ, trong một `transaction.atomic()`. Mỗi dòng tạo:
  - `PublicationCase` ở trạng thái **COMPLETED** nếu có ngày nộp lưu chiểu, ngược lại **DECISION_ISSUED** (gán khi tạo mới – được phép vì là bản ghi mới; không dùng `change_status`).
  - `owner` = tài khoản hệ thống **"Dữ liệu nhập từ Excel"** (CUSTOMER, `is_active=False`, email `du-lieu-cu@portal.invalid`), tạo nếu chưa có.
  - `Contributor` theo cột Tác giả (đúng thứ tự, vai trò Chủ biên/Tác giả).
  - 1 `StatusHistory` (DRAFT → trạng thái cuối, ghi chú "Nhập từ Excel – lô #<id>").
  - 1 `AuditEvent` `case.import` cho mỗi hồ sơ và 1 `AuditEvent` `import.batch` cho cả lô.
  - Không cấp mã NXB cho dữ liệu cũ.
- **Model `ImportBatch`** (trong `apps/reports/models.py`): `created_by`, `created_at`, `original_filename`, `total_rows`, `imported_rows`, `error_rows`, `case_ids` (JSON danh sách UUID). Không xóa (không có nút xóa). Dùng để lọc "Nguồn: Nhập Excel" ở mục 2.1.
- Trang lịch sử các lô nhập: thời điểm, người nhập, tên file, số dòng nhập/lỗi.
- Chỉ đọc giá trị ô (không chạy công thức, `data_only=True`), bỏ dòng trống, tối đa 5.000 dòng mỗi file.

## 3. Giao diện
Kế thừa `base.html`, Bootstrap 5 + HTMX, tiếng Việt. Thống kê ưu tiên dùng tốt trên máy tính.

## 4. Test bắt buộc (pytest, `tests/test_reports_*.py`)
- Mọi URL M5: chưa đăng nhập → đăng nhập; CUSTOMER và ADMIN → 404.
- Tra cứu tìm được theo ISBN có gạch nối, theo tên tác giả, theo số QĐXB.
- Thống kê: đầu sách tính theo `decision_date`, rơi về `registration_date`; đầu sách không có ngày không được tính; nhóm tháng/quý/năm đúng số.
- Xuất Excel mở được bằng openpyxl, đúng cột, không có cột tiền.
- Nhập Excel: bước kiểm tra không ghi gì vào database; dòng ISBN trùng/sai bị báo lỗi; dòng hợp lệ tạo đúng hồ sơ, tác giả, trạng thái, StatusHistory, AuditEvent; tài khoản hệ thống không đăng nhập được; nhập lại cùng file thì các dòng đã có ISBN bị báo trùng.
- Độ phủ `apps/reports` ≥ 85%.

## 5. Không làm
Không tài chính (M8), không sửa hồ sơ (M3), không nhập/xuất số tiền, không in ấn/phát hành, không đọc file .xls cũ (chỉ .xlsx – ghi hướng dẫn "Lưu thành .xlsx trước khi nhập").

## 6. Bàn giao
Chạy đủ: `ruff check .`, `ruff format --check .`, `python manage.py makemigrations --check --dry-run`, `pytest --cov=apps --cov-fail-under=85`. Ghi kết quả vào `docs/TEST_REPORT_M5.md`. Đẩy nhánh `m5-reports`, báo cáo tiếng Việt. Không gộp vào `main`.
