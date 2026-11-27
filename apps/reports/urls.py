"""Định tuyến M5 — Tra cứu, thống kê danh mục xuất bản, nhập Excel dữ liệu cũ."""

from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("tra-cuu/", views.ReportsSearchView.as_view(), name="search"),
    path("danh-muc-xuat-ban/", views.ReportsCatalogStatsView.as_view(), name="catalog_stats"),
    path(
        "danh-muc-xuat-ban/xuat-excel/",
        views.ReportsCatalogExportView.as_view(),
        name="catalog_export",
    ),
    path("nhap-excel/", views.ImportView.as_view(), name="import"),
    path(
        "nhap-excel/file-mau/", views.ImportTemplateDownloadView.as_view(), name="import_template"
    ),
    path("nhap-excel/lich-su/", views.ImportHistoryView.as_view(), name="import_history"),
]
