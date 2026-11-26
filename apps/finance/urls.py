"""Module M8 — Thống kê tài chính và công nợ phí dịch vụ xuất bản (trang khung placeholder M0)."""

from django.urls import path
from django.views.generic import TemplateView

from apps.core.mixins import FinanceManageMixin, FinanceViewMixin


class FinanceOverviewView(FinanceViewMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Thống kê — Tài chính", "module_code": "M8"}


class FinanceReceivablesDebtView(FinanceViewMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Thống kê — Công nợ", "module_code": "M8"}


class FinanceManagePlaceholderView(FinanceManageMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Ghi nhận khoản thu / phải thu", "module_code": "M8"}


app_name = "finance"

urlpatterns = [
    path("", FinanceOverviewView.as_view(), name="overview"),
    path("cong-no/", FinanceReceivablesDebtView.as_view(), name="debt"),
    path("ghi-nhan/", FinanceManagePlaceholderView.as_view(), name="manage"),
]
