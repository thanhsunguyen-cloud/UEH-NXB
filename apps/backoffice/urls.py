"""Module M3 — Cổng biên tập viên nội bộ (trang khung placeholder M0)."""

from django.urls import path
from django.views.generic import TemplateView

from apps.core.mixins import CaseAccessMixin, EditorRequiredMixin


class BackofficeHomeView(EditorRequiredMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Danh sách hồ sơ", "module_code": "M3"}


class BackofficeQueueView(EditorRequiredMixin, TemplateView):
    template_name = "placeholder.html"
    extra_context = {"page_title": "Hồ sơ cần xử lý", "module_code": "M3"}


class BackofficeCaseDetailView(EditorRequiredMixin, CaseAccessMixin, TemplateView):
    template_name = "placeholder.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "page_title": f"Xử lý hồ sơ {self.case.display_code}",
                "module_code": "M3",
                "case": self.case,
            }
        )
        return ctx


app_name = "backoffice"

urlpatterns = [
    path("", BackofficeHomeView.as_view(), name="home"),
    path("can-xu-ly/", BackofficeQueueView.as_view(), name="queue"),
    path("ho-so/<uuid:case_id>/", BackofficeCaseDetailView.as_view(), name="case_detail"),
]
