# GÓI GIAO VIỆC M2 – CỔNG KHÁCH HÀNG
UEH Publishing Portal V2 · Đợt 3 · Người làm: **AI-6 (Claude)** · từ 27/11/2026, khoảng 1 tuần · Owner: Nguyễn Thanh Sử

> Đọc `AGENTS.md`, `docs/CONVENTIONS.md`, `docs/DATA_MODEL.md` và tài liệu này trước khi viết code. Nhánh `m2-customer`.
> **Chỉ sửa:** `apps/customer/`, `templates/customer/`, test mới `tests/test_customer_*.py`, `docs/QUESTIONS_M2.md`, `docs/TEST_REPORT_M2.md`.
> Không sửa file M0 (`apps/core`, `apps/accounts`, `portal/settings`, `templates/base.html`, `templates/partials/`, `tests/factories.py`). Không tạo model, không tạo migration. Factory riêng (nếu cần) đặt trong file test của M2.
> Gặp điểm chưa rõ: ghi vào `docs/QUESTIONS_M2.md`, chọn phương án đơn giản nhất, làm tiếp.

## 1. Mục tiêu
Người đại diện (tài khoản CUSTOMER) tự tạo hồ sơ xuất bản, khai thông tin tác phẩm và tác giả, tải tài liệu, nộp hồ sơ, theo dõi trạng thái, bổ sung khi NXB yêu cầu, nộp bản thảo sửa khi bị trả chỉnh sửa. Mỗi hồ sơ chỉ có **1 người đại diện** (chủ tài khoản); đồng tác giả chỉ là thông tin (`Contributor`), không có tài khoản.

Giữ nguyên tên URL đã có trong `apps/customer/urls.py` (`customer:home`, `customer:case_create`, `customer:profile`, `customer:case_detail`) vì menu M0 đang dùng; được thêm URL mới.

## 2. Màn hình

### 2.1 Hồ sơ của tôi – `customer:home` (`/khach-hang/`)
- Danh sách `cases_visible_to(request.user)`: mã hiển thị (`display_code`), tên sách, hình thức, trạng thái (nhãn màu, tên dễ hiểu cho khách – bảng ở mục 3), ngày cập nhật.
- Cột "Việc cần làm": DRAFT → "Hoàn thiện và nộp hồ sơ"; NEED_SUPPLEMENT → "Bổ sung theo yêu cầu NXB"; REVISION_REQUIRED → "Nộp bản thảo đã chỉnh sửa"; còn lại để trống.
- Lọc theo trạng thái, tìm theo tên sách/mã; phân trang 20 dòng (`partials/pagination.html`). Nút "Tạo hồ sơ mới".

### 2.2 Tạo hồ sơ – `customer:case_create` (`/khach-hang/tao-moi/`)
- Form một trang tạo hồ sơ ở trạng thái DRAFT với `owner = request.user`: tên tác phẩm (bắt buộc), phụ đề, thể loại (`Category` đang dùng), lĩnh vực (`Field` đang dùng), ngôn ngữ (mặc định "Tiếng Việt"), ngôn ngữ gốc (nếu sách dịch), lần xuất bản, tái bản (có/không), hình thức (Tự xuất bản / Liên kết), tên đơn vị liên kết (bắt buộc khi Liên kết), tóm tắt nội dung, số trang, khổ sách.
- Lưu xong chuyển sang trang chi tiết để thêm tác giả và tài liệu. Ghi `log_event(action="case.create", ...)`.

### 2.3 Chi tiết hồ sơ – `customer:case_detail` (`/khach-hang/ho-so/<uuid>/`)
Kế thừa `CustomerRequiredMixin` + `CaseAccessMixin` (404 nếu không phải hồ sơ của mình). Các khối:
1. **Thông tin chung**: hiển thị; nút "Sửa" chỉ khi `can_edit_case_info(user, case)` (DRAFT, NEED_SUPPLEMENT). Sửa ghi `log_event(action="case.update", data={"before":…, "after":…})`. Khách **không** sửa được ISBN, mã NXB, số XNĐK, số QĐXB, số hợp đồng, BTV phụ trách.
2. **Tác giả** (`Contributor`): thêm/sửa/xóa khi `can_edit_case_info`; trường họ tên, học hàm/học vị, vai trò, đơn vị công tác, email, điện thoại, thứ tự. Có ghi chú: "Chỉ người đại diện có tài khoản; các tác giả khác là thông tin ghi trên sách." Ghi `log_event` `case.contributor_add|update|remove`.
3. **Tài liệu**: bảng theo loại (Bản thảo, Mẫu 1 – chỉ hiện khi Liên kết, Mẫu 2, Mẫu 3, Tài liệu khác), mỗi loại hiện bản hiện hành và lịch sử phiên bản; tải về qua `core:document_download`. **Không hiện** tài liệu FORM_4 và mọi loại khách không được tải (`can_download`). Tải lên bằng `partials/chunked_upload.html`, chỉ hiện ô tải khi `can_upload(user, case, doc_type)`. Có link tới trang công khai "Tải biểu mẫu" (`public_site:forms` hoặc URL tương đương đang có).
4. **Danh sách điều kiện nộp** (khi DRAFT/NEED_SUPPLEMENT): liệt kê đủ/thiếu theo đúng điều kiện của `change_status` DRAFT→SUBMITTED (bản thảo, Mẫu 2, Mẫu 3, Mẫu 1 + tên đơn vị liên kết khi Liên kết, ít nhất 1 tác giả). Nút **"Nộp hồ sơ"** chỉ hiện khi `"SUBMITTED" in allowed_transitions(user, case)`; bấm → hộp xác nhận → gọi `change_status(case, "SUBMITTED", actor=user, note=…, request=request)`; lỗi `WorkflowError` hiện bằng `messages.error`.
5. **Yêu cầu bổ sung** (`SupplementRequest`): hiện các yêu cầu OPEN nổi bật đầu trang. Khi khách nộp lại thành công từ NEED_SUPPLEMENT → SUBMITTED, đánh dấu mọi yêu cầu OPEN của hồ sơ thành RESOLVED (`resolved_at=now`) và ghi `log_event(action="case.supplement_resolved")`.
6. **Bản thảo chỉnh sửa** (REVISION_REQUIRED): ô tải bản thảo mới + dòng nhắc "Sau khi tải bản mới, NXB sẽ tiếp tục biên tập". Khách không chuyển trạng thái ở bước này.
7. **Trao đổi với NXB**: hiện ghi chú qua `can_view_note` (chỉ `visibility=CUSTOMER`). Khách gửi ghi chú mới → tạo `CaseNote(visibility=CUSTOMER, author=user)`, ghi `log_event(action="case.note_add")`. Không bao giờ hiện ghi chú INTERNAL.
8. **Dòng thời gian**: `StatusHistory` của hồ sơ (thời điểm, trạng thái mới theo nhãn khách hàng). **Không hiện** `note` của StatusHistory (có thể là ghi chú nội bộ), trừ khi chuyển sang NEED_SUPPLEMENT (ghi chú đó là yêu cầu gửi khách).
9. Không hiện bất kỳ số liệu tài chính nào.

### 2.4 Hủy hồ sơ nháp
Không xóa hồ sơ. Gói này **không** làm chức năng hủy (ghi vào QUESTIONS nếu thấy cần).

### 2.5 Tài khoản – `customer:profile` (`/khach-hang/tai-khoan/`)
Xem/sửa họ tên, điện thoại, đơn vị (`full_name`, `phone`, `organization`). Email chỉ xem. Link đổi mật khẩu của allauth. Ghi `log_event(action="user.profile_update")`.

## 3. Nhãn trạng thái cho khách hàng
| Mã | Nhãn hiển thị cho khách |
|---|---|
| DRAFT | Đang soạn hồ sơ |
| SUBMITTED | Đã nộp – chờ NXB tiếp nhận |
| NEED_SUPPLEMENT | Cần bổ sung |
| ACCEPTED | NXB đã tiếp nhận |
| EDITING | NXB đang biên tập |
| REVISION_REQUIRED | Cần chỉnh sửa bản thảo |
| REVIEW_APPROVED | Bản thảo đã được duyệt |
| REJECTED | Không được chấp thuận xuất bản |
| REGISTERED | Đã đăng ký xuất bản |
| DECISION_ISSUED | Đã có quyết định xuất bản |
| DEPOSITED | Đã nộp lưu chiểu |
| COMPLETED | Hoàn tất |
| ARCHIVED | Đã lưu trữ |

Đặt bảng này trong `apps/customer/labels.py` (dùng chung trong M2).

## 4. Giao diện
Kế thừa `base.html`, Bootstrap 5 + HTMX, tiếng Việt, dùng tốt trên điện thoại. Lỗi form hiện cạnh ô nhập; thành công dùng `messages`.

## 5. Test bắt buộc (pytest, `tests/test_customer_*.py`)
- Mọi URL M2: chưa đăng nhập → chuyển tới đăng nhập; EDITOR và ADMIN → 404; khách xem hồ sơ của người khác → 404.
- Tạo hồ sơ: owner đúng, trạng thái DRAFT, có AuditEvent `case.create`; Liên kết thiếu tên đơn vị bị từ chối.
- Sửa thông tin/tác giả bị chặn khi trạng thái không cho phép (ví dụ SUBMITTED).
- Nộp hồ sơ thiếu điều kiện → thông báo liệt kê thiếu, trạng thái không đổi; đủ điều kiện → SUBMITTED, có StatusHistory.
- NEED_SUPPLEMENT → nộp lại → các SupplementRequest OPEN thành RESOLVED.
- Trang chi tiết không chứa: ghi chú INTERNAL, tài liệu FORM_4, số tiền tài chính.
- Ô tải lên chỉ xuất hiện đúng trạng thái/loại tài liệu được phép.
- Độ phủ `apps/customer` ≥ 85%.

## 6. Không làm
Không màn hình của BTV, không thống kê, không tài chính, không gửi email (M4 lo), không xóa hồ sơ/tài liệu, không lưu CCCD, không in ấn/phát hành.

## 7. Bàn giao
Chạy đủ: `ruff check .`, `ruff format --check .`, `python manage.py makemigrations --check --dry-run`, `pytest --cov=apps --cov-fail-under=85`. Ghi kết quả vào `docs/TEST_REPORT_M2.md`. Đẩy nhánh `m2-customer`, báo cáo tiếng Việt. Không gộp vào `main`.
