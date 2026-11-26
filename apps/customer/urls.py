"""Module M2 — Cổng khách hàng (trang khung placeholder M0)."""

from django.urls import path
from django.views.generic import TemplateView

from apps.core.mixins import CaseAccessMixin, CustomerRequiredMixin


class CustomerHomeView(CustomerRequiredMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Hồ sơ của tôi", "module_code": "M2"}


class CustomerNewCaseView(CustomerRequiredMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Tạo hồ sơ mới", "module_code": "M2"}


class CustomerProfileView(CustomerRequiredMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Tài khoản", "module_code": "M2"}


class CustomerCaseDetailView(CustomerRequiredMixin, CaseAccessMixin, TemplateView):
    template_name = "placeholder.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": f"Chi tiết hồ sơ {self.case.display_code}",
                "module_code": "M2",
                "case": self.case,
            }
        )
        return ctx


app_name = "customer"

urlpatterns = [
    path("", CustomerHomeView.as_view(), name="home"),
    path("tao-moi/", CustomerNewCaseView.as_view(), name="case_create"),
    path("tai-khoan/", CustomerProfileView.as_view(), name="profile"),
    path("ho-so/<uuid:case_id>/", CustomerCaseDetailView.as_view(), name="case_detail"),
]
