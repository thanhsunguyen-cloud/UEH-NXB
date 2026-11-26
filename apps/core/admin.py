"""Đăng ký toàn bộ model lõi trong Django Admin (/django-admin/ chỉ cho ADMIN).

Quy tắc mục 10: AuditEvent, StatusHistory, Document ở chế độ chỉ đọc tuyệt đối.
"""

from django.contrib import admin

from apps.accounts.admin_site import portal_admin_site
from apps.core.models import (
    AuditEvent,
    CaseNote,
    Category,
    CodeSequence,
    Collection,
    Contributor,
    Document,
    FeeType,
    Field,
    FormTemplate,
    ManuscriptReview,
    PublicationCase,
    Receivable,
    StatusHistory,
    SupplementRequest,
    UploadSession,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Chế độ chỉ đọc tuyệt đối: không thêm, không sửa, không xóa trong Django admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class NoDeleteAdmin(admin.ModelAdmin):
    """Chặn thao tác xóa đối với model tài chính và dữ liệu bất biến."""

    def has_delete_permission(self, request, obj=None):
        return False


class AuditEventAdmin(ReadOnlyAdmin):
    list_display = ("at", "action", "actor", "object_type", "object_id", "case", "ip_address")
    list_filter = ("action", "object_type")
    search_fields = ("action", "object_id", "actor__email")
    readonly_fields = (
        "actor",
        "action",
        "object_type",
        "object_id",
        "case",
        "data",
        "ip_address",
        "at",
        "created_at",
        "updated_at",
    )


class StatusHistoryAdmin(ReadOnlyAdmin):
    list_display = ("at", "case", "from_status", "to_status", "actor")
    list_filter = ("from_status", "to_status")
    readonly_fields = (
        "case",
        "from_status",
        "to_status",
        "actor",
        "note",
        "at",
        "created_at",
        "updated_at",
    )


class DocumentAdmin(ReadOnlyAdmin):
    list_display = (
        "case",
        "doc_type",
        "form_code",
        "version",
        "is_current",
        "original_filename",
        "size_bytes",
        "uploaded_by",
        "uploaded_at",
    )
    list_filter = ("doc_type", "is_current", "storage_backend")
    search_fields = ("original_filename", "sha256", "form_code")
    readonly_fields = (
        "case",
        "doc_type",
        "form_code",
        "version",
        "is_current",
        "original_filename",
        "mime_type",
        "size_bytes",
        "sha256",
        "storage_backend",
        "storage_ref",
        "uploaded_by",
        "uploaded_at",
        "note",
        "created_at",
        "updated_at",
    )


class CatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "sort_order", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


class PublicationCaseAdmin(NoDeleteAdmin):
    list_display = (
        "display_code",
        "title",
        "status",
        "publication_mode",
        "owner",
        "primary_editor",
        "created_at",
    )
    list_filter = ("status", "publication_mode", "is_reprint")
    search_fields = ("temp_code", "nxb_code", "isbn", "title", "owner__email")
    readonly_fields = ("id", "temp_code", "nxb_code", "status", "created_at", "updated_at")


class ReceivableAdmin(NoDeleteAdmin):
    list_display = (
        "case",
        "fee_type",
        "amount",
        "payer_name",
        "due_date",
        "is_adjustment",
        "created_by",
    )
    list_filter = ("fee_type", "is_adjustment")
    search_fields = ("payer_name", "contract_number", "invoice_number")


class CollectionAdmin(NoDeleteAdmin):
    list_display = (
        "receivable",
        "paid_date",
        "amount",
        "method",
        "reference",
        "is_adjustment",
        "created_by",
    )
    list_filter = ("method", "is_adjustment")


REGISTRATIONS = [
    (Category, CatalogAdmin),
    (Field, CatalogAdmin),
    (FeeType, CatalogAdmin),
    (PublicationCase, PublicationCaseAdmin),
    (Contributor, admin.ModelAdmin),
    (Document, DocumentAdmin),
    (ManuscriptReview, NoDeleteAdmin),
    (CaseNote, admin.ModelAdmin),
    (SupplementRequest, admin.ModelAdmin),
    (StatusHistory, StatusHistoryAdmin),
    (FormTemplate, admin.ModelAdmin),
    (CodeSequence, admin.ModelAdmin),
    (AuditEvent, AuditEventAdmin),
    (Receivable, ReceivableAdmin),
    (Collection, CollectionAdmin),
    (UploadSession, admin.ModelAdmin),
]

for model_cls, admin_cls in REGISTRATIONS:
    portal_admin_site.register(model_cls, admin_cls)
    admin.site.register(model_cls, admin_cls)
