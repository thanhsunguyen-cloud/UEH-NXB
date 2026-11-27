"""Form quản lý nội dung trang công khai (EDITOR)."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.codes import normalize_isbn
from apps.public_site.models import FeaturedBook, NewsPost
from apps.public_site.services import validate_cover

COVER_ACCEPT = ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"


class CoverFormMixin(forms.Form):
    cover = forms.FileField(
        label=_("Ảnh bìa (.jpg, .png, .webp; tối đa 2 MB)"),
        required=False,
        widget=forms.FileInput(attrs={"accept": COVER_ACCEPT, "class": "form-control"}),
    )

    def clean_cover(self):
        cover = self.cleaned_data.get("cover")
        if not cover:
            self.cover_mime = ""
            return None
        self.cover_mime = validate_cover(cover)
        return cover


class NewsPostForm(CoverFormMixin, forms.ModelForm):
    class Meta:
        model = NewsPost
        fields = ["title", "summary", "body"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "summary": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 12}),
        }
        help_texts = {
            "body": _("Văn bản thuần, không nhận HTML. Mỗi dòng trống tách một đoạn."),
        }


class FeaturedBookForm(CoverFormMixin, forms.ModelForm):
    # Cho phép nhập ISBN có dấu gạch (tối đa 17 ký tự), lưu lại dạng 13 chữ số.
    isbn = forms.CharField(
        label=_("ISBN-13"),
        max_length=17,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = FeaturedBook
        fields = ["title", "authors", "isbn", "year", "description", "sort_order"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "authors": forms.TextInput(attrs={"class": "form-control"}),
            "year": forms.NumberInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control"}),
        }

    def clean_isbn(self):
        return normalize_isbn(self.cleaned_data.get("isbn"))

    def clean_year(self):
        year = self.cleaned_data.get("year")
        max_year = timezone.localdate().year + 1
        if year is not None and not (1900 <= year <= max_year):
            raise ValidationError(
                _("Năm xuất bản phải trong khoảng 1900 – %(max)s.") % {"max": max_year}
            )
        return year
