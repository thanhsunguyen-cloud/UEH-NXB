"""Module M7 — Cổng quản trị hệ thống (chỉ ADMIN, không xem hồ sơ xuất bản)."""

from django.urls import path

from apps.administration import views

app_name = "administration"

urlpatterns = [
    path("", views.UserListView.as_view(), name="home"),
    path("nguoi-dung/tao-moi/", views.StaffCreateView.as_view(), name="user_create"),
    path("nguoi-dung/<int:pk>/sua/", views.UserUpdateView.as_view(), name="user_update"),
    path("danh-muc/", views.CatalogsView.as_view(), name="catalogs"),
    path(
        "danh-muc/<slug:kind>/<int:pk>/sua/",
        views.CatalogUpdateView.as_view(),
        name="catalog_update",
    ),
    path(
        "danh-muc/<slug:kind>/<int:pk>/bat-tat/",
        views.CatalogToggleView.as_view(),
        name="catalog_toggle",
    ),
    path("bieu-mau/", views.FormTemplateListView.as_view(), name="templates"),
    path("bieu-mau/them/", views.FormTemplateCreateView.as_view(), name="template_create"),
    path(
        "bieu-mau/<int:pk>/ap-dung/",
        views.FormTemplateToggleView.as_view(),
        name="template_toggle",
    ),
    path(
        "bieu-mau/<int:pk>/tai-ve/",
        views.FormTemplateDownloadView.as_view(),
        name="template_download",
    ),
    path("nhat-ky/", views.AuditLogListView.as_view(), name="audit_logs"),
]
