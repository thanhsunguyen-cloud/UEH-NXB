"""Form của cổng khách hàng (M2)."""

from __future__ import annotations

from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.core.models import Category, Contributor, Field, PublicationCase, PublicationMode

# Các trường khách được khai/sửa. Tuyệt đối không có ISBN, mã NXB, số XNĐK, số QĐXB,
# số hợp đồng, BTV phụ trách (mục 2.3.1).
CASE_FIELDS = [
    "title",
    "subtitle",
    "category",
    "field",
    "language",
    "translated_from",
    "edition_number",
    "is_reprint",
    "publication_mode",
    "partner_name",
    "summary",
    "page_count",
    "book_size",
]

CONTRIBUTOR_FIELDS = [
    "full_name",
    "academic_title",
    "role",
    "affiliation",
    "email",
    "phone",
    "order",
]


class BootstrapFormMixin:
    """Gắn class Bootstrap 5 cho widget và đánh dấu ô lỗi."""

    def _apply_bootstrap(self) -> None:
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, forms.Select | forms.RadioSelect):
                css = "form-select"
            else:
                css = "form-control"
            if self.is_bound and name in self.errors:
                css += " is-invalid"
            widget.attrs["class"] = css

    def full_clean(self):
        super().full_clean()
        self._apply_bootstrap()


class CaseInfoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PublicationCase
        fields = CASE_FIELDS
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "translated_from": _("Chỉ điền nếu là sách dịch."),
            "partner_name": _("Bắt buộc khi chọn hình thức Liên kết."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        self.fields["category"].queryset = Category.objects.filter(
            Q(is_active=True) | Q(pk=getattr(instance, "category_id", None))
        )
        self.fields["field"].queryset = Field.objects.filter(
            Q(is_active=True) | Q(pk=getattr(instance, "field_id", None))
        )
        self._apply_bootstrap()

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("publication_mode")
        partner = (cleaned.get("partner_name") or "").strip()
        cleaned["partner_name"] = partner
        if mode == PublicationMode.LINKED and not partner:
            self.add_error(
                "partner_name",
                _("Bắt buộc nhập tên đơn vị liên kết khi chọn hình thức Liên kết."),
            )
        return cleaned


class ContributorForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Contributor
        fields = CONTRIBUTOR_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


class CaseNoteForm(BootstrapFormMixin, forms.Form):
    body = forms.CharField(
        label=_("Nội dung trao đổi"),
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=5000,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError(_("Vui lòng nhập nội dung."))
        return body


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "phone", "organization"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].required = True
        self._apply_bootstrap()
