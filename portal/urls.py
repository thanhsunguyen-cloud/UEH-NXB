"""Định tuyến URL gốc cho UEH Publishing Portal V2."""

from django.urls import include, path
from django.views.generic import RedirectView

from apps.accounts.admin_site import portal_admin_site

urlpatterns = [
    path("django-admin/", portal_admin_site.urls),
    # Trang đăng nhập mặc định của allauth chuyển về trang đăng nhập thống nhất của Portal.
    path(
        "accounts/login/",
        RedirectView.as_view(url="/tai-khoan/dang-nhap/", query_string=True),
    ),
    path("accounts/", include("allauth.urls")),
    path("tai-khoan/", include("apps.accounts.urls")),
    path("documents/", include("apps.core.urls")),
    path("khach-hang/", include("apps.customer.urls")),
    path("noi-bo/", include("apps.backoffice.urls")),
    path("bao-cao/", include("apps.reports.urls")),
    path("tai-chinh/", include("apps.finance.urls")),
    path("quan-tri/", include("apps.administration.urls")),
    path("", include("apps.public_site.urls")),
]
