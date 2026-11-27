"""URL bản demo M2/M3 (/demo/) – chỉ hoạt động khi DEBUG=True hoặc DEMO_ENABLED=True."""

from django.urls import path

from apps.demo import views

app_name = "demo"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("khach-hang/ho-so/", views.CustomerCaseListView.as_view(), name="customer_cases"),
    path("khach-hang/tao-ho-so/", views.CustomerCaseCreateView.as_view(), name="customer_create"),
    path(
        "khach-hang/ho-so/<slug:slug>/",
        views.CustomerCaseDetailView.as_view(),
        name="customer_case_detail",
    ),
    path("bien-tap/ho-so/", views.EditorCaseListView.as_view(), name="editor_cases"),
    path("bien-tap/can-xu-ly/", views.EditorQueueView.as_view(), name="editor_queue"),
    path(
        "bien-tap/ho-so/<slug:slug>/",
        views.EditorCaseDetailView.as_view(),
        name="editor_case_detail",
    ),
    path("thong-ke/danh-muc/", views.StatsCatalogView.as_view(), name="stats_catalog"),
    path("thong-ke/cong-no/", views.StatsDebtView.as_view(), name="stats_debt"),
]
