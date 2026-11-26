"""Đăng ký model User trong Django Admin."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from apps.accounts.admin_site import portal_admin_site
from apps.accounts.models import User


class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "role", "finance_access", "organization", "is_active")
    list_filter = ("role", "finance_access", "is_active")
    search_fields = ("email", "full_name", "organization", "phone")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Thông tin cá nhân"), {"fields": ("full_name", "phone", "organization")}),
        (_("Phân quyền"), {"fields": ("role", "finance_access", "is_active")}),
        (_("Thời gian"), {"fields": ("last_login", "created_at", "updated_at")}),
    )
    readonly_fields = ("last_login", "created_at", "updated_at")
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "finance_access", "is_active"),
            },
        ),
    )


portal_admin_site.register(User, UserAdmin)
admin.site.register(User, UserAdmin)
