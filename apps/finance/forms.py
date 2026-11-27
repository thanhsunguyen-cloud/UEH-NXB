"""Form của M8: bộ lọc, khoản phải thu, đã thu, điều chỉnh, đảo khoản thu."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.finance import outstanding
from apps.core.models import CollectionMethod, FeeType, PublicationMode

from .services import AGING_LABELS
from .templatetags.finance_tags import format_vnd

DATE_WIDGET = forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d")
MAX_AMOUNT = 10**15 - 1


def _text(**attrs):
    return forms.TextInput(attrs={"class": "form-control", **attrs})


def _textarea():
    return forms.Textarea(attrs={"class": "form-control", "rows": 2})


def _select():
    return forms.Select(attrs={"class": "form-select"})


def _amount_field(label, min_value=1):
    return forms.IntegerField(
        label=label,
        min_value=min_value,
        max_value=MAX_AMOUNT,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": 1}),
    )


# ---------------------------------------------------------------------------
# Bộ lọc
# ---------------------------------------------------------------------------


class OverviewFilterForm(forms.Form):
    date_from = forms.DateField(label=_("Từ ngày"), required=False, widget=DATE_WIDGET)
    date_to = forms.DateField(label=_("Đến ngày"), required=False, widget=DATE_WIDGET)
    fee_type = forms.ModelChoiceField(
        label=_("Loại phí"),
        queryset=FeeType.objects.all(),
        required=False,
        empty_label=_("Tất cả loại phí"),
        widget=_select(),
    )
    publication_mode = forms.ChoiceField(
        label=_("Hình thức xuất bản"),
        choices=[("", _("Tất cả hình thức")), *PublicationMode.choices],
        required=False,
        widget=_select(),
    )

    def clean(self):
        cleaned = super().clean()
        today = timezone.localdate()
        cleaned["date_from"] = cleaned.get("date_from") or date(today.year, 1, 1)
        cleaned["date_to"] = cleaned.get("date_to") or date(today.year, 12, 31)
        if cleaned["date_from"] > cleaned["date_to"]:
            raise forms.ValidationError(_("“Từ ngày” phải trước hoặc bằng “Đến ngày”."))
        return cleaned


class DebtFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Tìm"),
        required=False,
        widget=_text(placeholder=_("Mã hồ sơ / tên sách")),
    )
    bucket = forms.ChoiceField(
        label=_("Nhóm tuổi nợ"),
        choices=[("", _("Mọi nhóm tuổi nợ")), *AGING_LABELS.items()],
        required=False,
        widget=_select(),
    )
    fee_type = forms.ModelChoiceField(
        label=_("Loại phí"),
        queryset=FeeType.objects.all(),
        required=False,
        empty_label=_("Tất cả loại phí"),
        widget=_select(),
    )
    payer = forms.CharField(
        label=_("Người phải trả"),
        required=False,
        widget=_text(placeholder=_("Đơn vị / tác giả phải trả")),
    )


class CaseSearchForm(forms.Form):
    q = forms.CharField(
        label=_("Tìm hồ sơ"),
        required=False,
        widget=_text(placeholder=_("Mã hồ sơ, ISBN hoặc tên sách")),
    )


# ---------------------------------------------------------------------------
# Ghi nhận
# ---------------------------------------------------------------------------


class ReceivableForm(forms.Form):
    fee_type = forms.ModelChoiceField(
        label=_("Loại phí"),
        queryset=FeeType.objects.filter(is_active=True),
        widget=_select(),
    )
    amount = _amount_field(_("Số tiền (VNĐ)"))
    description = forms.CharField(
        label=_("Diễn giải"), max_length=255, required=False, widget=_text()
    )
    payer_name = forms.CharField(
        label=_("Đơn vị / Tác giả phải trả"), max_length=255, required=False, widget=_text()
    )
    contract_number = forms.CharField(
        label=_("Số hợp đồng"), max_length=100, required=False, widget=_text()
    )
    invoice_number = forms.CharField(
        label=_("Số chứng từ"), max_length=100, required=False, widget=_text()
    )
    invoice_date = forms.DateField(label=_("Ngày chứng từ"), required=False, widget=DATE_WIDGET)
    due_date = forms.DateField(label=_("Hạn thanh toán"), required=False, widget=DATE_WIDGET)
    note = forms.CharField(label=_("Ghi chú"), required=False, widget=_textarea())


class CollectionForm(forms.Form):
    paid_date = forms.DateField(label=_("Ngày thu"), widget=DATE_WIDGET)
    amount = _amount_field(_("Số tiền (VNĐ)"))
    method = forms.ChoiceField(
        label=_("Hình thức"), choices=CollectionMethod.choices, widget=_select()
    )
    reference = forms.CharField(
        label=_("Số chứng từ"), max_length=100, required=False, widget=_text()
    )
    note = forms.CharField(label=_("Ghi chú"), required=False, widget=_textarea())
    confirm_overpayment = forms.BooleanField(
        label=_("Xác nhận thu vượt"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, receivable, **kwargs):
        self.receivable = receivable
        self.is_overpayment = False
        super().__init__(*args, **kwargs)

    def clean_paid_date(self):
        paid_date = self.cleaned_data["paid_date"]
        if paid_date > timezone.localdate():
            raise forms.ValidationError(_("Ngày thu không được ở tương lai."))
        return paid_date

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get("amount")
        if amount is None:
            return cleaned
        remaining = outstanding(self.receivable)
        if Decimal(amount) > remaining:
            self.is_overpayment = True
            warning = _("Số tiền thu (%(amount)s) vượt số còn nợ (%(remaining)s).") % {
                "amount": format_vnd(amount),
                "remaining": format_vnd(remaining),
            }
            if not cleaned.get("confirm_overpayment"):
                self.add_error(
                    "confirm_overpayment",
                    f"{warning} " + str(_("Tích “Xác nhận thu vượt” và ghi chú lý do để lưu.")),
                )
            elif not (cleaned.get("note") or "").strip():
                self.add_error("note", _("Thu vượt bắt buộc ghi chú lý do."))
        return cleaned


class AdjustmentForm(forms.Form):
    """Bút toán điều chỉnh khoản phải thu: số tiền âm (giảm) hoặc dương (tăng), khác 0."""

    amount = forms.IntegerField(
        label=_("Số tiền điều chỉnh (VNĐ)"),
        help_text=_("Nhập số âm để giảm, số dương để tăng khoản phải thu."),
        min_value=-MAX_AMOUNT,
        max_value=MAX_AMOUNT,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": 1}),
    )
    note = forms.CharField(label=_("Ghi chú lý do"), required=False, widget=_textarea())

    def __init__(self, *args, effective_amount: Decimal, **kwargs):
        self.effective_amount = effective_amount
        super().__init__(*args, **kwargs)

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount == 0:
            raise forms.ValidationError(_("Số tiền điều chỉnh phải khác 0."))
        if self.effective_amount + amount < 0:
            raise forms.ValidationError(
                _("Sau điều chỉnh, khoản phải thu không được âm (hiện là %(current)s).")
                % {"current": format_vnd(self.effective_amount)}
            )
        return amount

    def clean_note(self):
        note = self.cleaned_data["note"].strip()
        if not note:
            raise forms.ValidationError(_("Bút toán điều chỉnh bắt buộc ghi chú lý do."))
        return note


class ReversalForm(forms.Form):
    """Đảo toàn bộ một khoản thu (tạo Collection điều chỉnh có số tiền âm)."""

    paid_date = forms.DateField(label=_("Ngày đảo"), widget=DATE_WIDGET)
    note = forms.CharField(label=_("Ghi chú lý do"), required=False, widget=_textarea())

    def clean_paid_date(self):
        paid_date = self.cleaned_data["paid_date"]
        if paid_date > timezone.localdate():
            raise forms.ValidationError(_("Ngày đảo không được ở tương lai."))
        return paid_date

    def clean_note(self):
        note = self.cleaned_data["note"].strip()
        if not note:
            raise forms.ValidationError(_("Đảo khoản thu bắt buộc ghi chú lý do."))
        return note
