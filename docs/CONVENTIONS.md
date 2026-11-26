# QUY ƯỚC PHÁT TRIỂN CHO CÁC MODULE M1–M8 (CONVENTIONS)

Tài liệu này là hợp đồng kỹ thuật giữa gói nền tảng **M0** và các module nghiệp vụ **M1–M8**.

## 1. Danh sách tệp thuộc sở hữu M0 (KHÔNG ĐƯỢC SỬA)

Các module M1–M8 **chỉ được dùng, tuyệt đối không sửa** những tệp và thư mục sau. Nếu cần thay đổi, gửi Change Request cho Owner:

- `apps/core/*` (toàn bộ models, `permissions.py`, `mixins.py`, `workflow.py`, `codes.py`, `storage.py`, `audit.py`, `finance.py`, `signals.py`)
- `apps/accounts/*`
- `portal/settings/base.py`
- `templates/base.html`
- `templates/partials/*` (`nav.html`, `messages.html`, `pagination.html`, `chunked_upload.html`)

## 2. Quy tắc phân quyền và Mixin bắt buộc

- **Không bao giờ** tự viết `if request.user.role == ...` trong view hay template.
- Mọi view phải kế thừa mixin trong `apps/core/mixins.py`:
  - `CustomerRequiredMixin`, `EditorRequiredMixin`, `AdminRequiredMixin` (đều đã bao gồm `LoginRequiredMixin`).
  - `CaseAccessMixin`: tự động truy vấn hồ sơ theo UUID qua `cases_visible_to(request.user)` và trả **404** nếu không có quyền (không trả 403).
  - `FinanceViewMixin`, `FinanceManageMixin`, `PublicationStatsMixin`: trả **404** nếu thiếu quyền.
- Truy vấn danh sách hồ sơ luôn bắt đầu bằng `cases_visible_to(request.user)`.
- Hiển thị ghi chú luôn lọc qua `can_view_note(request.user, note)`.
- Hiển thị nút chuyển trạng thái chỉ dựa trên `allowed_transitions(request.user, case)`.
- ADMIN tuyệt đối không xem nội dung hồ sơ. Khách hàng và BTV `finance_access=NONE` tuyệt đối không thấy số liệu tài chính.

## 3. Quy tắc chuyển trạng thái hồ sơ (`apps/core/workflow.py`)

- **Cấm gán trực tiếp** `case.status = ...` (model `PublicationCase.save()` sẽ ném `ValidationError`).
- Luôn gọi hàm duy nhất:

```python
from apps.core.workflow import WorkflowError, allowed_transitions, change_status

next_statuses = allowed_transitions(request.user, case)
try:
    change_status(case, to_status, actor=request.user, note=note, request=request)
except WorkflowError as exc:
    messages.error(request, str(exc))
```

- Khi chuyển trạng thái thành công, M0 tự động ghi đúng 1 `StatusHistory`, 1 `AuditEvent` và phát tín hiệu `apps.core.signals.case_status_changed` để M4 gửi email.
- Đổi người đại diện (chỉ EDITOR): gọi `change_case_owner(case, new_owner, actor, note, request)`.

## 4. Upload chia phần (8 MiB) và Tải xuống dạng stream (`apps/core/storage.py`)

Vì Cloud Run giới hạn mỗi HTTP/1 request ≤ 32 MiB và ổ đĩa tạm nằm trong RAM:

- **Không dùng** `<input type="file">` gửi trực tiếp qua form POST cho bản thảo/tài liệu hồ sơ.
- Nhúng sẵn partial của M0 vào template:

```django
{% include "partials/chunked_upload.html" with case=case doc_type="MANUSCRIPT" form_code="" label="Tải lên bản thảo" %}
```

- Lắng nghe sự kiện DOM `ueh:upload-complete` (hoặc kết hợp HTMX) để cập nhật danh sách tài liệu không cần tải lại trang.
- Ở tầng service Python, luôn gọi tuần tự 3 bước:
  1. `begin_document_upload(user=..., case=..., doc_type=..., filename=..., total_size=..., mime_type=..., form_code=...)`
  2. `upload_chunk(user=..., session=..., offset=..., data=...)`
  3. `complete_document_upload(user=..., session=..., note=..., request=...)`
- Mọi liên kết tải tệp phải trỏ tới `{% url 'core:document_download' doc.id %}` (`/documents/<id>/download/`). Tuyệt đối không lộ đường dẫn lưu trữ trực tiếp.
- **Lưu ý riêng cho M1 (`GoogleDriveStorage`)**: cài đặt đúng `FileStorage` Protocol, lưu vào **Shared Drive** (Content Manager) và truyền `supportsAllDrives=True` cho mọi lời gọi Drive API.

## 5. Nhật ký thao tác (`apps/core/audit.py`)

Mọi thao tác quan trọng (tạo hồ sơ, sửa thông tin, đổi vai trò, đổi người đại diện, ghi nhận tài chính) gọi:

```python
from apps.core.audit import log_event

log_event(
    actor=request.user,
    action="case.update",
    object_type="PublicationCase",
    object_id=str(case.pk),
    case=case,
    data={"before": before_dict, "after": after_dict},
    request=request,
)
```

## 6. Tài chính & Công nợ (`apps/core/finance.py`)

- Dùng `create_receivable()` và `create_collection()` (đã kiểm tra `can_manage_finance`, ghi `AuditEvent`, chặn thu vượt mức trừ khi có ghi chú + `confirm_overpayment=True`).
- Tính số dư và phân nhóm tuổi nợ chỉ bằng: `outstanding(rec)`, `receivable_status(rec, today)`, `aging_bucket(rec, today)`.
- Không bao giờ gọi `.delete()` trên `Receivable` hay `Collection`; sửa sai bằng bút toán điều chỉnh (`is_adjustment=True`, bắt buộc `note`).

## 7. Quy ước URL, Template, Ngôn ngữ và Test

- URL: tiếng Việt không dấu, phân tách bằng gạch nối (`/khach-hang/`, `/noi-bo/`, `/bao-cao/`, `/tai-chinh/`, `/quan-tri/`).
- Template: mỗi module đặt trong `templates/<app_name>/...`, kế thừa `{% extends "base.html" %}`, chỉ dùng Bootstrap 5 + HTMX.
- Mã nguồn: tên biến, hàm, class, trường DB bằng tiếng Anh; chuỗi hiển thị cho người dùng bằng tiếng Việt bọc trong `gettext_lazy`.
- Test: dùng `pytest` + `factory_boy` từ `tests/factories.py`; mỗi PR bắt buộc qua CI (`ruff check`, `ruff format --check`, `pytest`).
- **Tuyệt đối ngoài phạm vi**: không thêm trường/màn hình về in ấn, phát hành, hạch toán kế toán, xuất hóa đơn, thanh toán trực tuyến, ký số, tự động duyệt hay lưu CCCD.
