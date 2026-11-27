"""Form của M3 — Tác nghiệp biên tập viên."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User, UserRole
from apps.core.codes import normalize_isbn
from apps.core.models import (
    CaseNote,
    CaseStatus,
    Category,
    Contributor,
    Document,
    DocumentType,
    NoteVisibility,
    PublicationCase,
    PublicationMode,
    ReviewResult,
)

UNASSIGNED = "none"


def active_editors():
    return User.objects.filter(role=UserRole.EDITOR, is_active=True).order_by("full_name", "email")


def _add_bootstrap(form: forms.Form) -> None:
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", "form-check-input")
        elif isinstance(widget, forms.Select):
            widget.attrs.setdefault("class", "form-select")
        else:
            widget.attrs.setdefault("class", "form-control")


class BootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _add_bootstrap(self)


# ---------------------------------------------------------------------------
# 2.1 Danh sách hồ sơ
# ---------------------------------------------------------------------------


class CaseFilterForm(BootstrapMixin, forms.Form):
    q = forms.CharField(
        label=_("Tìm kiếm"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": _("ISBN, mã NXB, mã tạm, tên sách, tác giả, email người đại diện")
            }
        ),
    )
    status = forms.ChoiceField(
        label=_("Trạng thái"),
        required=False,
        choices=[("", _("Mọi trạng thái (trừ Nháp)"))] + list(CaseStatus.choices),
    )
    mode = forms.ChoiceField(
        label=_("Hình thức"),
        required=False,
        choices=[("", _("Mọi hình thức"))] + list(PublicationMode.choices),
    )
    category = forms.ModelChoiceField(
        label=_("Thể loại"),
        required=False,
        queryset=Category.objects.order_by("sort_order", "name"),
        empty_label=_("Mọi thể loại"),
    )
    editor = forms.ChoiceField(label=_("BTV phụ trách"), required=False)
    mine = forms.BooleanField(label=_("Của tôi"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["editor"].choices = [
            ("", _("Mọi BTV")),
            (UNASSIGNED, _("Chưa giao")),
        ] + [(str(u.pk), u.full_name or u.email) for u in active_editors()]


# ---------------------------------------------------------------------------
# 2.3 Tab Tổng quan
# ---------------------------------------------------------------------------


class CaseInfoForm(BootstrapMixin, forms.ModelForm):
    # Cho phép nhập ISBN có dấu gạch nối (ví dụ 978-604-...), chuẩn hóa trong clean_isbn.
    isbn = forms.CharField(label=_("Mã ISBN-13"), required=False, max_length=20)

    class Meta:
        model = PublicationCase
        fields = [
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
            "page_count",
            "book_size",
            "summary",
            "isbn",
            "registration_number",
            "registration_date",
            "decision_number",
            "decision_date",
            "contract_number",
            "contract_date",
            "deposit_date",
        ]
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "registration_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "decision_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "contract_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "deposit_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def clean_isbn(self):
        value = self.cleaned_data.get("isbn")
        if not value:
            return None
        try:
            isbn = normalize_isbn(value)
        except ValidationError as exc:
            raise ValidationError(exc.messages) from exc
        duplicate = PublicationCase.objects.filter(isbn=isbn).exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise ValidationError(_("Mã ISBN này đã được dùng cho một hồ sơ khác."))
        return isbn


class AssignEditorForm(BootstrapMixin, forms.Form):
    primary_editor = forms.ModelChoiceField(
        label=_("BTV phụ trách chính"),
        queryset=User.objects.none(),
        required=False,
        empty_label=_("— Chưa giao —"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["primary_editor"].queryset = active_editors()


class ChangeOwnerForm(BootstrapMixin, forms.Form):
    email = forms.EmailField(label=_("Email tài khoản khách hàng mới"))
    reason = forms.CharField(
        label=_("Lý do đổi người đại diện"),
        widget=forms.Textarea(attrs={"rows": 2}),
        error_messages={"required": _("Bắt buộc nhập lý do khi đổi người đại diện.")},
    )

    def clean_reason(self):
        reason = (self.cleaned_data.get("reason") or "").strip()
        if not reason:
            raise ValidationError(_("Bắt buộc nhập lý do khi đổi người đại diện."))
        return reason

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        user = User.objects.filter(
            email__iexact=email, role=UserRole.CUSTOMER, is_active=True
        ).first()
        if user is None:
            raise ValidationError(
                _("Không tìm thấy tài khoản khách hàng đang hoạt động với email này.")
            )
        self.new_owner = user
        return email


# ---------------------------------------------------------------------------
# 2.3 Tab Tác giả
# ---------------------------------------------------------------------------


class ContributorForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Contributor
        fields = ["full_name", "academic_title", "role", "email", "phone", "affiliation", "order"]


# ---------------------------------------------------------------------------
# 2.3 Tab Quy trình
# ---------------------------------------------------------------------------


class TransitionForm(forms.Form):
    to_status = forms.ChoiceField(choices=CaseStatus.choices)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def clean(self):
        cleaned = super().clean()
        note = (cleaned.get("note") or "").strip()
        cleaned["note"] = note
        if cleaned.get("to_status") == CaseStatus.NEED_SUPPLEMENT and not note:
            self.add_error("note", _("Bắt buộc nhập nội dung yêu cầu bổ sung."))
        return cleaned


class ManuscriptReviewForm(BootstrapMixin, forms.Form):
    manuscript = forms.ModelChoiceField(
        label=_("Phiên bản bản thảo được duyệt"),
        queryset=Document.objects.none(),
        error_messages={
            "required": _("Chọn phiên bản bản thảo của hồ sơ này."),
            "invalid_choice": _("Bản thảo không thuộc hồ sơ này."),
        },
    )
    form4 = forms.ModelChoiceField(
        label=_("Mẫu 4 đã ký"),
        queryset=Document.objects.none(),
        error_messages={
            "required": _("Chọn Mẫu 4 đã ký của hồ sơ này."),
            "invalid_choice": _("Mẫu 4 không thuộc hồ sơ này."),
        },
    )
    result = forms.ChoiceField(
        label=_("Kết quả"),
        choices=ReviewResult.choices,
        widget=forms.RadioSelect,
    )
    note = forms.CharField(
        label=_("Ghi chú"), required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    confirm = forms.BooleanField(
        label=_(
            "Tôi xác nhận Mẫu 4 đúng tên sách, đúng tác giả và đúng phiên bản bản thảo "
            "của hồ sơ này"
        ),
        error_messages={"required": _("Bắt buộc tích ô xác nhận Mẫu 4 đúng hồ sơ.")},
    )

    def __init__(self, *args, case: PublicationCase, **kwargs):
        super().__init__(*args, **kwargs)
        docs = Document.objects.filter(case=case).order_by("-version")
        self.fields["manuscript"].queryset = docs.filter(doc_type=DocumentType.MANUSCRIPT)
        self.fields["manuscript"].label_from_instance = lambda d: (
            f"v{d.version} — {d.original_filename} ({d.uploaded_at:%d/%m/%Y %H:%M})"
        )
        self.fields["form4"].queryset = docs.filter(doc_type=DocumentType.FORM_4)
        self.fields["form4"].label_from_instance = lambda d: (
            f"v{d.version} — {d.original_filename} ({d.uploaded_at:%d/%m/%Y %H:%M})"
        )
        self.fields["result"].widget.attrs["class"] = "form-check-input"


# ---------------------------------------------------------------------------
# 2.3 Tab Ghi chú & trao đổi
# ---------------------------------------------------------------------------


class CaseNoteForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = CaseNote
        fields = ["body", "visibility"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3})}
        labels = {"body": _("Nội dung ghi chú"), "visibility": _("Phạm vi")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["visibility"].initial = NoteVisibility.INTERNAL
        self.fields["visibility"].required = False

    def clean_visibility(self):
        return self.cleaned_data.get("visibility") or NoteVisibility.INTERNAL
