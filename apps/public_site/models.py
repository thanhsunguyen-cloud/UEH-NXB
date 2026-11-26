"""Model riêng của M6 — Trang công khai: tin tức và sách mới (Owner đã duyệt, mục 2)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.codes import validate_isbn13


class NewsPost(models.Model):
    """Tin tức đăng trên trang công khai. `body` là văn bản thuần, không nhận HTML."""

    title = models.CharField(_("Tiêu đề"), max_length=255)
    slug = models.SlugField(_("Đường dẫn"), max_length=255, unique=True)
    summary = models.CharField(_("Tóm tắt"), max_length=500)
    body = models.TextField(_("Nội dung (văn bản thuần)"))
    cover_storage_ref = models.CharField(_("Mã lưu trữ ảnh bìa"), max_length=255, blank=True)
    cover_mime = models.CharField(_("Kiểu MIME ảnh bìa"), max_length=100, blank=True)
    is_published = models.BooleanField(_("Đã đăng"), default=False)
    published_at = models.DateTimeField(_("Thời điểm đăng"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="news_posts",
        verbose_name=_("Người tạo"),
    )
    created_at = models.DateTimeField(_("Ngày tạo"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Ngày cập nhật"), auto_now=True)

    class Meta:
        verbose_name = _("Tin tức")
        verbose_name_plural = _("Tin tức")
        ordering = ["-published_at", "-id"]

    def __str__(self) -> str:
        return self.title


class FeaturedBook(models.Model):
    """Sách mới do biên tập viên nhập tay (không lấy tự động từ hồ sơ)."""

    title = models.CharField(_("Tên sách"), max_length=255)
    authors = models.CharField(_("Tác giả"), max_length=255)
    isbn = models.CharField(_("ISBN-13"), max_length=13, blank=True, validators=[validate_isbn13])
    year = models.PositiveIntegerField(_("Năm xuất bản"))
    description = models.TextField(_("Giới thiệu (văn bản thuần)"), blank=True)
    cover_storage_ref = models.CharField(_("Mã lưu trữ ảnh bìa"), max_length=255, blank=True)
    cover_mime = models.CharField(_("Kiểu MIME ảnh bìa"), max_length=100, blank=True)
    is_published = models.BooleanField(_("Đã đăng"), default=False)
    sort_order = models.PositiveIntegerField(_("Thứ tự hiển thị"), default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="featured_books",
        verbose_name=_("Người tạo"),
    )
    created_at = models.DateTimeField(_("Ngày tạo"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Ngày cập nhật"), auto_now=True)

    class Meta:
        verbose_name = _("Sách mới")
        verbose_name_plural = _("Sách mới")
        ordering = ["sort_order", "-year", "-id"]

    def __str__(self) -> str:
        return self.title
