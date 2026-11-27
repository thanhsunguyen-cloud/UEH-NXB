"""URL của M8 — Tài chính và công nợ phí dịch vụ xuất bản (`/tai-chinh/`).

Không có URL xóa: sửa sai bằng bút toán điều chỉnh (phải thu) hoặc đảo (đã thu).
"""

from django.urls import path

from apps.finance import views

app_name = "finance"

urlpatterns = [
    path("", views.FinanceOverviewView.as_view(), name="overview"),
    path("cong-no/", views.FinanceDebtView.as_view(), name="debt"),
    path("ghi-nhan/", views.FinanceManageView.as_view(), name="manage"),
    path("ho-so/<uuid:case_id>/", views.FinanceCaseView.as_view(), name="case"),
    path(
        "ho-so/<uuid:case_id>/phai-thu/them/",
        views.ReceivableCreateView.as_view(),
        name="receivable_create",
    ),
    path(
        "phai-thu/<int:pk>/dieu-chinh/",
        views.ReceivableAdjustView.as_view(),
        name="receivable_adjust",
    ),
    path(
        "phai-thu/<int:pk>/ghi-nhan-thu/",
        views.CollectionCreateView.as_view(),
        name="collection_create",
    ),
    path(
        "da-thu/<int:pk>/dao/",
        views.CollectionReverseView.as_view(),
        name="collection_reverse",
    ),
]
