# GÓI GIAO VIỆC M3 – TÁC NGHIỆP CỦA BIÊN TẬP VIÊN
UEH Publishing Portal V2 · Đợt 3 · Người làm: **AI-7 (Claude)** · từ 27/11/2026, khoảng 1–1,5 tuần · Owner: Nguyễn Thanh Sử

> Đọc `AGENTS.md`, `docs/CONVENTIONS.md`, `docs/DATA_MODEL.md` và tài liệu này trước khi viết code. Nhánh `m3-backoffice`.
> **Chỉ sửa:** `apps/backoffice/`, `templates/backoffice/`, test mới `tests/test_backoffice_*.py`, `docs/QUESTIONS_M3.md`, `docs/TEST_REPORT_M3.md`.
> Không sửa file M0 (`apps/core`, `apps/accounts`, `portal/settings`, `templates/base.html`, `templates/partials/`, `tests/factories.py`). Không tạo model, không tạo migration. Factory riêng (nếu cần) đặt trong file test của M3.
> Gặp điểm chưa rõ: ghi vào `docs/QUESTIONS_M3.md`, chọn phương án đơn giản nhất, làm tiếp.

## 1. Mục tiêu
Biên tập viên (EDITOR) tiếp nhận, kiểm tra "đúng hồ sơ", biên tập, duyệt theo Mẫu 4 và đưa hồ sơ qua các bước đăng ký – quyết định – lưu chiểu – hoàn tất. Hệ thống **bán thủ công**: BTV tự làm giấy tờ bên ngoài, Portal ghi lại số liệu, tài liệu, trạng thái. Mọi BTV xem và hỗ trợ được mọi hồ sơ (`cases_visible_to`). ADMIN không vào được M3 (404).

Giữ nguyên tên URL đã có (`backoffice:home`, `backoffice:queue`, `backoffice:case_detail`); được thêm URL mới. Mọi view kế thừa `EditorRequiredMixin` (+ `CaseAccessMixin` cho trang hồ sơ).

## 2. Màn hình

### 2.1 Danh sách hồ sơ – `backoffice:home` (`/noi-bo/`)
- Cột: mã hiển thị, mã NXB, ISBN, tên sách, người đại diện, hình thức, trạng thái, BTV phụ trách, cập nhật lần cuối.
- Tìm theo ISBN / mã NXB / mã tạm / tên sách / tên tác giả (`Contributor.full_name`) / email người đại diện. Lọc trạng thái, hình thức, thể loại, BTV phụ trách (kể cả "Chưa giao"), "Của tôi". Lọc và tìm bằng HTMX, phân trang 25 dòng.
- **Không** hiện hồ sơ DRAFT của khách (khách chưa nộp) – trừ khi chọn lọc "Nháp" một cách tường minh.

### 2.2 Hồ sơ cần xử lý – `backoffice:queue` (`/noi-bo/can-xu-ly/`)
Nhóm theo việc, mỗi nhóm có số đếm và danh sách ngắn:
1. Mới nộp – chờ tiếp nhận (SUBMITTED).
2. Khách đã bổ sung (SUBMITTED và có `SupplementRequest` RESOLVED gần nhất sau lần NEED_SUPPLEMENT).
3. Đã tiếp nhận – chưa giao BTV hoặc chưa bắt đầu biên tập (ACCEPTED).
4. Khách đã nộp bản thảo sửa (REVISION_REQUIRED và có MANUSCRIPT phiên bản mới hơn bản đã duyệt).
5. Chờ đăng ký xuất bản (REVIEW_APPROVED), chờ quyết định (REGISTERED), chờ lưu chiểu (DECISION_ISSUED).
Có tùy chọn "Chỉ hồ sơ tôi phụ trách".

### 2.3 Chi tiết hồ sơ – `backoffice:case_detail` (`/noi-bo/ho-so/<uuid>/`), 5 tab
1. **Tổng quan**: mọi thông tin hồ sơ; người đại diện (họ tên, email, điện thoại, đơn vị); mã tạm, mã NXB, ISBN, số/ngày XNĐK, số/ngày QĐXB, số/ngày hợp đồng liên kết, ngày lưu chiểu. Form sửa khi `can_edit_case_info` (không sửa được khi COMPLETED/ARCHIVED). ISBN nhập kiểm tra bằng validator của model (báo lỗi tiếng Việt, không trùng). Mã NXB chỉ hiển thị (M0 tự cấp khi tiếp nhận, không sửa). Giao BTV phụ trách (`primary_editor`, chỉ chọn EDITOR đang hoạt động). Đổi người đại diện bằng `change_case_owner` (bắt buộc lý do; chọn tài khoản CUSTOMER theo email). Mọi thay đổi ghi `log_event` với `before`/`after` (`case.update`, `case.assign_editor`).
2. **Tác giả**: xem, thêm, sửa, xóa `Contributor` (khi `can_edit_case_info`), ghi `log_event`.
3. **Tài liệu**: mọi tài liệu theo loại và phiên bản, ai tải, lúc nào, ghi chú; tải về qua `core:document_download`. BTV tải lên mọi loại (bản thảo đã biên tập, Mẫu 4, 5, 6, 7, 9, minh chứng…) bằng `partials/chunked_upload.html`. Có link tải biểu mẫu nội bộ (trang Quản trị → Biểu mẫu là của Admin; ở đây chỉ cần link tới trang công khai `/bieu-mau/` và ghi chú "mẫu nội bộ lấy từ thư mục chung của NXB").
4. **Quy trình**:
   - Nút cho từng trạng thái đích trong `allowed_transitions(user, case)` (nhãn tiếng Việt). Bấm → hộp thoại có ô ghi chú → `change_status(...)`. Trước khi bấm, hiện danh sách điều kiện còn thiếu bằng cách gọi validator tương ứng (hoặc bắt `WorkflowError.missing` và hiển thị).
   - **Yêu cầu bổ sung** (SUBMITTED → NEED_SUPPLEMENT): ô nội dung bắt buộc; tạo `SupplementRequest(status=OPEN)` rồi gọi `change_status` với `note` là nội dung đó, trong cùng `transaction.atomic()`.
   - **Xác nhận duyệt theo Mẫu 4 "đúng hồ sơ"** (khi EDITING): hộp thoại hiện mã hồ sơ, tên sách, chọn **phiên bản bản thảo** (MANUSCRIPT của hồ sơ này) và **Mẫu 4 đã ký** (FORM_4 của hồ sơ này), chọn kết quả (Đồng ý / Yêu cầu chỉnh sửa / Từ chối), ô tích bắt buộc "Tôi xác nhận Mẫu 4 đúng tên sách, đúng tác giả và đúng phiên bản bản thảo của hồ sơ này". Gọi `record_manuscript_review(...)`. Sau đó gợi ý nút chuyển trạng thái tương ứng (REVIEW_APPROVED / REVISION_REQUIRED / REJECTED). Hiện lịch sử các lần duyệt.
   - Dòng thời gian `StatusHistory` đầy đủ (kể cả ghi chú).
5. **Ghi chú & trao đổi**: danh sách `CaseNote` (nhãn "Nội bộ" / "Gửi khách hàng"); thêm ghi chú chọn phạm vi, mặc định **Nội bộ**; ghi `log_event(action="case.note_add")`. Danh sách yêu cầu bổ sung (OPEN/RESOLVED); BTV đánh dấu RESOLVED thủ công được.
- **Tài chính**: M3 không làm màn hình tài chính. Chỉ khi `can_view_finance(user)` thì hiện một nút "Xem tài chính hồ sơ" trỏ tới `/tai-chinh/ho-so/<uuid>/` (URL do M8 làm; dùng chuỗi đường dẫn cố định, không `{% url %}`, để không phụ thuộc M8).

### 2.4 Nhãn trạng thái cho BTV
Dùng nhãn của `CaseStatus` (model). Nhãn nút chuyển trạng thái: "Tiếp nhận", "Yêu cầu bổ sung", "Bắt đầu biên tập", "Duyệt – đồng ý xuất bản", "Trả tác giả chỉnh sửa", "Từ chối", "Tiếp tục biên tập", "Đã đăng ký xuất bản", "Đã có quyết định xuất bản", "Đã nộp lưu chiểu", "Hoàn tất", "Lưu trữ".

## 3. Giao diện
Kế thừa `base.html`, Bootstrap 5 + HTMX, tiếng Việt, dùng tốt trên máy tính (ưu tiên) và điện thoại. Lỗi form cạnh ô nhập; thành công dùng `messages`.

## 4. Test bắt buộc (pytest, `tests/test_backoffice_*.py`)
- Mọi URL M3: chưa đăng nhập → đăng nhập; CUSTOMER và ADMIN → 404.
- Tìm theo ISBN, mã NXB, tên tác giả; lọc "Chưa giao".
- Đi trọn quy trình một hồ sơ Liên kết từ SUBMITTED tới ARCHIVED qua giao diện (POST), kiểm tra mỗi bước thiếu điều kiện bị chặn với thông báo, đủ thì qua.
- Tiếp nhận cấp mã NXB; trang hiển thị mã NXB, rồi ISBN sau khi nhập.
- Xác nhận Mẫu 4 với bản thảo/Mẫu 4 của **hồ sơ khác** bị từ chối; thiếu ô tích xác nhận bị từ chối.
- Yêu cầu bổ sung tạo SupplementRequest OPEN và trạng thái NEED_SUPPLEMENT; thiếu nội dung bị chặn.
- Ghi chú mặc định Nội bộ; đổi người đại diện thiếu lý do bị chặn; mọi thao tác ghi đúng AuditEvent.
- Hồ sơ COMPLETED: form sửa không hiện, POST sửa bị chặn.
- BTV `finance_access=NONE` không thấy nút tài chính; VIEW thấy.
- Độ phủ `apps/backoffice` ≥ 85%.

## 5. Không làm
Không thống kê (M5), không tài chính (M8), không email (M4), không sinh văn bản Mẫu 4–9 tự động (giai đoạn 2), không xóa hồ sơ/tài liệu, không in ấn/phát hành, không tự động duyệt.

## 6. Bàn giao
Chạy đủ: `ruff check .`, `ruff format --check .`, `python manage.py makemigrations --check --dry-run`, `pytest --cov=apps --cov-fail-under=85`. Ghi kết quả vào `docs/TEST_REPORT_M3.md`. Đẩy nhánh `m3-backoffice`, báo cáo tiếng Việt. Không gộp vào `main`.
