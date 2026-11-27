"""Nghiệp vụ quản trị hệ thống (M7): tài khoản, danh mục, biểu mẫu tải về.

Mọi ràng buộc nghiệp vụ nằm ở đây để view chỉ lo hiển thị; mọi thao tác ghi `log_event`.
"""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import FinanceAccess, User, UserRole
from apps.core.audit import log_event
from apps.core.models import Category, FeeType, Field, FormTemplate
from apps.core.storage import get_storage

STAFF_ROLES = (UserRole.EDITOR, UserRole.ADMIN)
MIN_ACTIVE_ADMINS = 2

FORM_TEMPLATE_CATEGORY = "form_templates"
FORM_TEMPLATE_EXTENSIONS = (".doc", ".docx", ".xls", ".xlsx", ".pdf")
FORM_TEMPLATE_CODE_RE = re.compile(r"^[A-Z0-9_]{3,30}$")
SUGGESTED_FORM_CODES = [f"MAU_{i}" for i in range(1, 10)] + [
    f"BIZ_F4_{i:02d}" for i in range(1, 13)
]

# Danh mục quản lý được: khóa URL -> (model, nhãn tab)
CATALOG_KINDS: dict[str, tuple[type, str]] = {
    "the-loai": (Category, _("Thể loại")),
    "linh-vuc": (Field, _("Lĩnh vực")),
    "loai-phi": (FeeType, _("Loại phí")),
}


# ---------------------------------------------------------------------------
# Tài khoản
# ---------------------------------------------------------------------------


def staff_domain() -> str:
    return str(getattr(settings, "STAFF_GOOGLE_DOMAIN", "ueh.edu.vn")).strip().lower()


def is_staff_email(email: str) -> bool:
    return (email or "").strip().lower().endswith("@" + staff_domain())


def _staff_email_error() -> ValidationError:
    return ValidationError(
        _("Email nhân sự bắt buộc có đuôi @%(domain)s.") % {"domain": staff_domain()},
        code="staff_domain",
    )


def _locked_active_admin_ids() -> set[int]:
    """Khóa các dòng ADMIN đang hoạt động để đếm an toàn khi có thao tác đồng thời."""
    qs = User.objects.select_for_update().filter(role=UserRole.ADMIN, is_active=True)
    return set(qs.values_list("pk", flat=True))


def create_staff_user(
    *,
    actor,
    email: str,
    full_name: str,
    role: str,
    finance_access: str = FinanceAccess.NONE,
    request=None,
) -> User:
    """Tạo tài khoản nhân sự (EDITOR/ADMIN). Không có mật khẩu: nhân sự đăng nhập bằng Google."""
    email = (email or "").strip().lower()
    if role not in STAFF_ROLES:
        raise ValidationError(_("Chỉ tạo được tài khoản Biên tập viên hoặc Quản trị viên."))
    if not is_staff_email(email):
        raise _staff_email_error()
    if role != UserRole.EDITOR and finance_access != FinanceAccess.NONE:
        raise ValidationError(_("Quyền tài chính chỉ áp dụng cho Biên tập viên."))
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError(_("Email này đã có tài khoản."))

    with transaction.atomic():
        user = User.objects.create_user(
            email=email,
            password=None,
            full_name=(full_name or "").strip(),
            role=role,
            finance_access=finance_access,
        )
        log_event(
            actor=actor,
            action="user.create",
            object_type="User",
            object_id=str(user.pk),
            data={"before": {}, "after": _user_snapshot(user)},
            request=request,
        )
    return user


def _user_snapshot(user: User) -> dict:
    return {
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "finance_access": user.finance_access,
        "is_active": user.is_active,
    }


def update_user(
    *,
    actor,
    user: User,
    role: str,
    finance_access: str,
    is_active: bool,
    request=None,
) -> list[str]:
    """Đổi vai trò, quyền tài chính, khóa/mở khóa. Trả về danh sách action đã ghi nhật ký.

    Ràng buộc: không tự hạ quyền/tự khóa; luôn còn ≥ 2 ADMIN hoạt động; CUSTOMER chỉ lên
    EDITOR/ADMIN khi email đúng domain UEH; không bao giờ xóa tài khoản.
    """
    if role not in UserRole.values:
        raise ValidationError(_("Vai trò không hợp lệ."))
    if finance_access not in FinanceAccess.values:
        raise ValidationError(_("Quyền tài chính không hợp lệ."))
    if role != UserRole.EDITOR:
        finance_access = FinanceAccess.NONE

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        before = _user_snapshot(user)

        if user.pk == actor.pk and (role != UserRole.ADMIN or not is_active):
            raise ValidationError(_("Bạn không thể tự hạ quyền hoặc tự khóa tài khoản của mình."))

        if role in STAFF_ROLES and user.role not in STAFF_ROLES and not is_staff_email(user.email):
            raise _staff_email_error()

        if user.role in STAFF_ROLES and role == UserRole.CUSTOMER:
            raise ValidationError(
                _("Không chuyển tài khoản nhân sự về Khách hàng; hãy khóa tài khoản nếu cần.")
            )

        loses_admin = (
            user.role == UserRole.ADMIN
            and user.is_active
            and (role != UserRole.ADMIN or not is_active)
        )
        if loses_admin:
            remaining = _locked_active_admin_ids() - {user.pk}
            if len(remaining) < MIN_ACTIVE_ADMINS:
                raise ValidationError(
                    _(
                        "Hệ thống phải luôn còn ít nhất %(n)s Quản trị viên đang hoạt động; "
                        "thao tác này bị từ chối."
                    )
                    % {"n": MIN_ACTIVE_ADMINS}
                )

        promoted_to_staff = user.role not in STAFF_ROLES and role in STAFF_ROLES
        user.role = role
        user.finance_access = finance_access
        user.is_active = is_active
        if promoted_to_staff:
            # Nhân sự chỉ đăng nhập bằng Google: bỏ mật khẩu cũ của tài khoản khách hàng.
            user.set_unusable_password()
        user.save()
        after = _user_snapshot(user)

        actions: list[str] = []
        if before["role"] != after["role"]:
            actions.append("user.role_change")
        if before["finance_access"] != after["finance_access"]:
            actions.append("user.finance_access_change")
        if before["is_active"] != after["is_active"]:
            actions.append("user.unlock" if after["is_active"] else "user.lock")

        field_of = {
            "user.role_change": "role",
            "user.finance_access_change": "finance_access",
            "user.lock": "is_active",
            "user.unlock": "is_active",
        }
        for action in actions:
            key = field_of[action]
            log_event(
                actor=actor,
                action=action,
                object_type="User",
                object_id=str(user.pk),
                data={
                    "email": user.email,
                    "before": {key: before[key]},
                    "after": {key: after[key]},
                },
                request=request,
            )
    return actions


# ---------------------------------------------------------------------------
# Danh mục
# ---------------------------------------------------------------------------


def catalog_snapshot(item) -> dict:
    return {"name": item.name, "sort_order": item.sort_order, "is_active": item.is_active}


def log_catalog_change(*, actor, item, before: dict | None, request=None) -> None:
    """Ghi catalog.create (before=None) hoặc catalog.update."""
    log_event(
        actor=actor,
        action="catalog.create" if before is None else "catalog.update",
        object_type=type(item).__name__,
        object_id=str(item.pk),
        data={"before": before or {}, "after": catalog_snapshot(item)},
        request=request,
    )


def toggle_catalog_item(*, actor, item, request=None):
    """Bật/tắt một mục danh mục (không bao giờ xóa)."""
    before = catalog_snapshot(item)
    item.is_active = not item.is_active
    item.save(update_fields=["is_active", "updated_at"])
    log_catalog_change(actor=actor, item=item, before=before, request=request)
    return item


# ---------------------------------------------------------------------------
# Biểu mẫu tải về
# ---------------------------------------------------------------------------


def max_library_file_mb() -> int:
    return int(getattr(settings, "MAX_LIBRARY_FILE_MB", 10))


def validate_form_template_code(code: str) -> str:
    code = (code or "").strip().upper()
    if not FORM_TEMPLATE_CODE_RE.match(code):
        raise ValidationError(
            _("Mã biểu mẫu chỉ gồm chữ in hoa, chữ số, dấu gạch dưới; dài 3–30 ký tự.")
        )
    return code


def validate_form_template_file(filename: str, size: int) -> None:
    ext = Path(filename or "").suffix.lower()
    if ext not in FORM_TEMPLATE_EXTENSIONS:
        raise ValidationError(
            _("Định dạng tệp '%(ext)s' không được hỗ trợ. Chỉ chấp nhận: %(allowed)s.")
            % {"ext": ext or "(trống)", "allowed": ", ".join(FORM_TEMPLATE_EXTENSIONS)}
        )
    if size <= 0:
        raise ValidationError(_("Tệp rỗng, vui lòng chọn tệp khác."))
    max_mb = max_library_file_mb()
    if size > max_mb * 1024 * 1024:
        raise ValidationError(
            _("Tệp vượt quá dung lượng tối đa %(max_mb)s MB.") % {"max_mb": max_mb}
        )


def guess_mime_type(filename: str) -> str:
    return mimetypes.guess_type(filename or "")[0] or "application/octet-stream"


def _deactivate_others(*, actor, template: FormTemplate, request=None) -> None:
    others = (
        FormTemplate.objects.select_for_update()
        .filter(code=template.code, is_active=True)
        .exclude(pk=template.pk)
    )
    for other in others:
        other.is_active = False
        other.save(update_fields=["is_active", "updated_at"])
        _log_template(actor, "form_template.deactivate", other, request, reason="auto")


def _log_template(actor, action: str, template: FormTemplate, request, **extra) -> None:
    data = {
        "code": template.code,
        "version": template.version,
        "name": template.name,
        "is_active": template.is_active,
        **extra,
    }
    log_event(
        actor=actor,
        action=action,
        object_type="FormTemplate",
        object_id=str(template.pk),
        data=data,
        request=request,
    )


def create_form_template(
    *,
    actor,
    code: str,
    name: str,
    version: str,
    effective_from,
    uploaded_file,
    activate: bool = True,
    request=None,
) -> FormTemplate:
    """Lưu file vào thư viện (CR-001 `save_library_file`) và tạo FormTemplate mới."""
    code = validate_form_template_code(code)
    version = (version or "").strip()
    if FormTemplate.objects.filter(code=code, version=version).exists():
        raise ValidationError(
            _("Mã %(code)s đã có phiên bản %(version)s.") % {"code": code, "version": version}
        )
    filename = uploaded_file.name
    size = int(uploaded_file.size or 0)
    validate_form_template_file(filename, size)
    mime_type = getattr(uploaded_file, "content_type", "") or guess_mime_type(filename)

    stored = get_storage().save_library_file(
        FORM_TEMPLATE_CATEGORY, filename, uploaded_file, size, mime_type
    )

    with transaction.atomic():
        template = FormTemplate.objects.create(
            code=code,
            name=(name or "").strip(),
            version=version,
            effective_from=effective_from,
            is_active=activate,
            storage_backend=getattr(settings, "FILE_STORAGE_BACKEND", "local"),
            storage_ref=stored.storage_ref,
            original_filename=Path(filename).name,
        )
        _log_template(
            actor,
            "form_template.create",
            template,
            request,
            effective_from=str(effective_from),
            original_filename=template.original_filename,
            size_bytes=stored.size,
        )
        if activate:
            _deactivate_others(actor=actor, template=template, request=request)
            _log_template(actor, "form_template.activate", template, request)
    return template


def set_form_template_active(
    *, actor, template: FormTemplate, active: bool, request=None
) -> FormTemplate:
    """Bật/tắt áp dụng; bật một phiên bản thì tắt các phiên bản khác cùng mã."""
    with transaction.atomic():
        template = FormTemplate.objects.select_for_update().get(pk=template.pk)
        if template.is_active == active:
            return template
        template.is_active = active
        template.save(update_fields=["is_active", "updated_at"])
        if active:
            _deactivate_others(actor=actor, template=template, request=request)
            _log_template(actor, "form_template.activate", template, request)
        else:
            _log_template(actor, "form_template.deactivate", template, request)
    return template
