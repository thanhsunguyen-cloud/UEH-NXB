"""Module M5 — Tra cứu và thống kê danh mục xuất bản (trang khung placeholder M0)."""

from django.urls import path
from django.views.generic import TemplateView

from apps.core.mixins import EditorRequiredMixin, PublicationStatsMixin


class ReportsSearchView(EditorRequiredMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Tra cứu hồ sơ xuất bản", "module_code": "M5"}


class ReportsCatalogStatsView(PublicationStatsMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Thống kê — Danh mục xuất bản", "module_code": "M5"}


app_name = "reports"

urlpatterns = [
    path("tra-cuu/", ReportsSearchView.as_view(), name="search"),
    path("danh-muc-xuat-ban/", ReportsCatalogStatsView.as_view(), name="catalog_stats"),
]
