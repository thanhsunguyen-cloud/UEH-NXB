"""Form của M7 — thông báo lỗi tiếng Việt hiển thị cạnh ô nhập."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import FinanceAccess, UserRole
from apps.administration import services
from apps.core.models import Category

STAFF_ROLE_CHOICES = [
    (UserRole.EDITOR, UserRole.EDITOR.label),
    (UserRole.ADMIN, UserRole.ADMIN.label),
]


class BootstrapMixin:
    """Gắn class Bootstrap 5 cho widget."""

    def _apply_bootstrap(self) -> None:
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, forms.Select):
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs["class"] = (widget.attrs.get("class", "") + " " + css).strip()

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs["class"] = (widget.attrs.get("class", "") + " is-invalid").strip()


class UserFilterForm(BootstrapMixin, forms.Form):
    STATUS_CHOICES = [
        ("", _("Tất cả trạng thái")),
        ("active", _("Hoạt động")),
        ("locked", _("Đã khóa")),
    ]

    q = forms.CharField(label=_("Tìm theo tên hoặc email"), required=False)
    role = forms.ChoiceField(
        label=_("Vai trò"),
        required=False,
        choices=[("", _("Tất cả vai trò")), *UserRole.choices],
    )
    status = forms.ChoiceField(label=_("Trạng thái"), required=False, choices=STATUS_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


class StaffCreateForm(BootstrapMixin, forms.Form):
    email = forms.EmailField(label=_("Email"))
    full_name = forms.CharField(label=_("Họ và tên"), max_length=200)
    role = forms.ChoiceField(label=_("Vai trò"), choices=STAFF_ROLE_CHOICES)
    finance_access = forms.ChoiceField(
        label=_("Quyền tài chính"),
        choices=FinanceAccess.choices,
        initial=FinanceAccess.NONE,
        help_text=_("Chỉ áp dụng cho Biên tập viên."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()
        self.fields["email"].widget.attrs["placeholder"] = "ten@" + services.staff_domain()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if not services.is_staff_email(email):
            raise ValidationError(
                _("Email nhân sự bắt buộc có đuôi @%(domain)s.")
                % {"domain": services.staff_domain()}
            )
        return email

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("role") != UserRole.EDITOR
            and cleaned.get("finance_access", FinanceAccess.NONE) != FinanceAccess.NONE
        ):
            self.add_error("finance_access", _("Quyền tài chính chỉ áp dụng cho Biên tập viên."))
        return cleaned


class UserUpdateForm(BootstrapMixin, forms.Form):
    role = forms.ChoiceField(label=_("Vai trò"), choices=UserRole.choices)
    finance_access = forms.ChoiceField(
        label=_("Quyền tài chính"),
        choices=FinanceAccess.choices,
        help_text=_("Chỉ áp dụng cho Biên tập viên; vai trò khác luôn là “Không có quyền”."),
    )
    is_active = forms.BooleanField(label=_("Đang hoạt động (bỏ chọn để khóa)"), required=False)

    def __init__(self, *args, target_user, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_user = target_user
        if target_user.role != UserRole.CUSTOMER:
            # Nhân sự không chuyển về Khách hàng (chỉ khóa).
            self.fields["role"].choices = STAFF_ROLE_CHOICES
        self._apply_bootstrap()


class CatalogItemForm(BootstrapMixin, forms.ModelForm):
    """Dùng chung cho Category, Field, FeeType (cùng cấu trúc name/sort_order/is_active)."""

    class Meta:
        model = Category
        fields = ["name", "sort_order", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


def catalog_form_class(model):
    """Sinh ModelForm cho đúng model danh mục."""
    meta = type("Meta", (), {"model": model, "fields": ["name", "sort_order", "is_active"]})
    return type(f"{model.__name__}Form", (CatalogItemForm,), {"Meta": meta})


class FormTemplateCreateForm(BootstrapMixin, forms.Form):
    code = forms.CharField(
        label=_("Mã biểu mẫu"),
        max_length=30,
        help_text=_("Ví dụ MAU_2, BIZ_F4_01; hoặc mã khác gồm A–Z, 0–9, _ (3–30 ký tự)."),
    )
    name = forms.CharField(label=_("Tên biểu mẫu"), max_length=255)
    version = forms.CharField(label=_("Phiên bản"), max_length=30)
    effective_from = forms.DateField(
        label=_("Ngày hiệu lực"), widget=forms.DateInput(attrs={"type": "date"})
    )
    file = forms.FileField(label=_("Tệp biểu mẫu"))
    activate = forms.BooleanField(
        label=_("Áp dụng ngay (tự tắt phiên bản đang áp dụng cùng mã)"),
        required=False,
        initial=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()
        self.fields["code"].widget.attrs["list"] = "form-code-suggestions"
        self.fields["file"].widget.attrs["accept"] = ",".join(services.FORM_TEMPLATE_EXTENSIONS)
        self.fields["file"].help_text = _(
            "Chấp nhận .doc, .docx, .xls, .xlsx, .pdf; tối đa %(mb)s MB."
        ) % {"mb": services.max_library_file_mb()}

    def clean_code(self):
        return services.validate_form_template_code(self.cleaned_data["code"])

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        services.validate_form_template_file(uploaded.name, uploaded.size)
        return uploaded


class AuditFilterForm(BootstrapMixin, forms.Form):
    GROUP_CHOICES = [
        ("", _("Tất cả nhóm")),
        ("case", "case.*"),
        ("document", "document.*"),
        ("finance", "finance.*"),
        ("user", "user.*"),
        ("auth", "auth.*"),
        ("other", _("Khác")),
    ]

    date_from = forms.DateField(
        label=_("Từ ngày"), required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_to = forms.DateField(
        label=_("Đến ngày"), required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    actor = forms.CharField(label=_("Người thực hiện (tên/email)"), required=False)
    group = forms.ChoiceField(label=_("Nhóm thao tác"), required=False, choices=GROUP_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("date_from"), cleaned.get("date_to")
        if start and end and start > end:
            self.add_error("date_to", _("“Đến ngày” phải sau hoặc bằng “Từ ngày”."))
        return cleaned
