"""URLs của ứng dụng accounts."""

from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("dang-nhap/", views.login_view, name="login"),
    path("dieu-huong/", views.role_redirect_view, name="role_redirect"),
    path("dang-xuat/", views.logout_view, name="logout"),
]
