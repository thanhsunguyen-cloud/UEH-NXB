"""Module M6 — Trang công khai (để khung tối giản trong M0)."""

from django.urls import path
from django.views.generic import TemplateView


class PublicHomeView(TemplateView):
    template_name = "placeholder.html"
    extra_context = {
        "page_title": "Cổng thông tin Nhà xuất bản Kinh tế TP.HCM",
        "module_code": "M6",
    }


app_name = "public_site"

urlpatterns = [
    path("", PublicHomeView.as_view(), name="home"),
]
