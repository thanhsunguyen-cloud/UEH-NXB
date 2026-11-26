"""Django AdminSite tùy biến: chỉ cho phép vai trò ADMIN truy cập (/django-admin/)."""

from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import UserRole


class PortalAdminSite(AdminSite):
    site_header = _("Quản trị hệ thống — NXB Kinh tế TP.HCM")
    site_title = _("NXB UEH Admin")
    index_title = _("Bảng điều khiển quản trị kỹ thuật")

    def has_permission(self, request):
        return bool(
            request.user
            and request.user.is_active
            and request.user.is_authenticated
            and request.user.role == UserRole.ADMIN
        )


portal_admin_site = PortalAdminSite(name="portal_admin")
