"""Form của M5 — Tra cứu, thống kê, nhập Excel."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.models import CaseStatus, Category, Field, PublicationMode

from . import services
from .importer import MAX_FILE_BYTES


class BootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, forms.Select):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")


def _category_field():
    return forms.ModelChoiceField(
        label=_("Thể loại"),
        required=False,
        queryset=Category.objects.order_by("sort_order", "name"),
        empty_label=_("Mọi thể loại"),
    )


def _field_field():
    return forms.ModelChoiceField(
        label=_("Lĩnh vực"),
        required=False,
        queryset=Field.objects.order_by("sort_order", "name"),
        empty_label=_("Mọi lĩnh vực"),
    )


def _mode_field():
    return forms.ChoiceField(
        label=_("Hình thức"),
        required=False,
        choices=[("", _("Mọi hình thức"))] + list(PublicationMode.choices),
    )


class SearchForm(BootstrapMixin, forms.Form):
    q = forms.CharField(
        label=_("Tìm kiếm"),
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": _("ISBN, mã NXB, mã tạm, số XNĐK, số QĐXB, tên sách, tác giả")}
        ),
    )
    year = forms.IntegerField(
        label=_("Năm"),
        required=False,
        min_value=1900,
        max_value=2999,
        widget=forms.NumberInput(attrs={"placeholder": _("Năm")}),
    )
    status = forms.ChoiceField(
        label=_("Trạng thái"),
        required=False,
        choices=[("", _("Mọi trạng thái (trừ Nháp)"))] + list(CaseStatus.choices),
    )
    category = _category_field()
    field = _field_field()
    mode = _mode_field()
    source = forms.ChoiceField(
        label=_("Nguồn"),
        required=False,
        choices=[
            ("", _("Mọi nguồn")),
            (services.SOURCE_PORTAL, _("Portal")),
            (services.SOURCE_EXCEL, _("Nhập Excel")),
        ],
    )


class CatalogStatsForm(BootstrapMixin, forms.Form):
    date_from = forms.DateField(
        label=_("Từ ngày"), required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_to = forms.DateField(
        label=_("Đến ngày"), required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    group = forms.ChoiceField(
        label=_("Nhóm theo"),
        required=False,
        choices=[
            (services.GROUP_MONTH, _("Tháng")),
            (services.GROUP_QUARTER, _("Quý")),
            (services.GROUP_YEAR, _("Năm")),
        ],
    )
    category = _category_field()
    field = _field_field()
    mode = _mode_field()

    def clean(self):
        data = super().clean()
        d_from, d_to = data.get("date_from"), data.get("date_to")
        if d_from and d_to and d_from > d_to:
            self.add_error("date_to", _("“Đến ngày” phải sau hoặc bằng “Từ ngày”."))
        return data


class ImportUploadForm(BootstrapMixin, forms.Form):
    file = forms.FileField(
        label=_("File Excel (.xlsx)"),
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
        ),
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError(
                _("Chỉ nhận file .xlsx. Hãy Lưu thành .xlsx trước khi nhập.")
            )
        if f.size > MAX_FILE_BYTES:
            raise forms.ValidationError(_("File vượt quá 10 MB."))
        return f


class ImportConfirmForm(forms.Form):
    payload = forms.CharField(widget=forms.HiddenInput)
