"""Model của M5 — lô nhập danh mục xuất bản từ Excel."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils.translation import gettext_lazy as _


class ImportBatch(models.Model):
    """Một lần nhập danh mục cũ từ file Excel (không xóa)."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="import_batches",
        verbose_name=_("Người nhập"),
    )
    created_at = models.DateTimeField(_("Thời điểm nhập"), auto_now_add=True)
    original_filename = models.CharField(_("Tên file gốc"), max_length=255)
    total_rows = models.PositiveIntegerField(_("Tổng số dòng"), default=0)
    imported_rows = models.PositiveIntegerField(_("Số dòng đã nhập"), default=0)
    error_rows = models.PositiveIntegerField(_("Số dòng lỗi"), default=0)
    case_ids = models.JSONField(_("Danh sách hồ sơ đã tạo"), default=list, blank=True)

    class Meta:
        verbose_name = _("Lô nhập Excel")
        verbose_name_plural = _("Lô nhập Excel")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Lô #{self.pk} — {self.original_filename}"

    def delete(self, *args, **kwargs):
        raise PermissionDenied(_("Không được xóa lô nhập Excel."))
