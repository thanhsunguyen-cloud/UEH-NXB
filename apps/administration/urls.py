"""Module M7 — Cổng quản trị hệ thống (chỉ ADMIN, không xem hồ sơ xuất bản)."""

from django.urls import path
from django.views.generic import TemplateView

from apps.core.mixins import AdminRequiredMixin


class AdminUsersView(AdminRequiredMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Quản trị — Người dùng", "module_code": "M7"}


class AdminCatalogsView(AdminRequiredMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Quản trị — Danh mục", "module_code": "M7"}


class AdminTemplatesView(AdminRequiredMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Quản trị — Biểu mẫu", "module_code": "M7"}


class AdminAuditLogsView(AdminRequiredMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Quản trị — Nhật ký hệ thống", "module_code": "M7"}


app_name = "administration"

urlpatterns = [
    path("", AdminUsersView.as_view(), name="home"),
    path("danh-muc/", AdminCatalogsView.as_view(), name="catalogs"),
    path("bieu-mau/", AdminTemplatesView.as_view(), name="templates"),
    path("nhat-ky/", AdminAuditLogsView.as_view(), name="audit_logs"),
]
