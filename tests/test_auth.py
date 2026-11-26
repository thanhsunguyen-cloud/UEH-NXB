"""Nhóm test 7 & kiểm tra bắt buộc đăng nhập và chặn mật khẩu nhân sự (mục 5.1 & S1)."""

from types import SimpleNamespace

import pytest
from django.contrib.auth import authenticate
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.adapters import PortalSocialAccountAdapter
from apps.accounts.models import User, UserRole


@pytest.mark.django_db
def test_editor_and_admin_cannot_login_with_password_via_authenticate_portal_or_django_admin(
    client,
    editor_none,
    admin_user,
    customer_a,
):
    # Cố tình đặt mật khẩu hợp lệ cho cả EDITOR và ADMIN để kiểm chứng lớp chặn mật khẩu
    for staff_user in (editor_none, admin_user):
        staff_user.set_password("Secret@123")
        staff_user.save()

        # 1. django.contrib.auth.authenticate phải trả None (không rơi xuống backend allauth)
        assert authenticate(email=staff_user.email, password="Secret@123") is None
        assert authenticate(username=staff_user.email, password="Secret@123") is None

        # 2. Đăng nhập qua trang Portal (/tai-khoan/dang-nhap/) bị từ chối
        portal_resp = client.post(
            reverse("accounts:login"),
            {"email": staff_user.email, "password": "Secret@123"},
        )
        assert portal_resp.status_code == 403
        assert "_auth_user_id" not in client.session

        # 3. Đăng nhập qua /django-admin/login/ bị từ chối (không chuyển hướng 302 vào admin)
        admin_resp = client.post(
            "/django-admin/login/",
            {"username": staff_user.email, "password": "Secret@123"},
        )
        assert admin_resp.status_code == 200
        assert "_auth_user_id" not in client.session

    # Khách hàng vẫn đăng nhập bằng mật khẩu bình thường
    authed_customer = authenticate(email=customer_a.email, password="TestPass@123")
    assert authed_customer == customer_a


@pytest.mark.django_db
def test_unassigned_ueh_google_user_defaults_to_customer():
    adapter = PortalSocialAccountAdapter()
    request = RequestFactory().get("/")
    user = User(email="nguoi.la@ueh.edu.vn")
    sociallogin = SimpleNamespace(user=user)
    populated = adapter.populate_user(
        request,
        sociallogin,
        {"email": "nguoi.la@ueh.edu.vn", "name": "Người lạ UEH"},
    )
    assert populated.role == UserRole.CUSTOMER


@pytest.mark.django_db
def test_staff_google_login_connects_valid_ueh_domain(admin_user, editor_none):
    adapter = PortalSocialAccountAdapter()
    request = RequestFactory().get("/")

    class DummySocialLogin:
        def __init__(self, email):
            self.user = User(email=email)
            self.connected = []

        def connect(self, req, user):
            self.connected.append(user)

    for staff_user in (admin_user, editor_none):
        sociallogin = DummySocialLogin(staff_user.email)
        adapter.pre_social_login(request, sociallogin)
        assert sociallogin.connected == [staff_user]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "customer:home",
        "customer:case_create",
        "customer:profile",
        "backoffice:home",
        "backoffice:queue",
        "reports:search",
        "reports:catalog_stats",
        "finance:overview",
        "finance:debt",
        "finance:manage",
        "administration:home",
        "administration:catalogs",
        "administration:templates",
        "administration:audit_logs",
    ],
)
def test_all_protected_urls_redirect_anonymous_to_login(client, url_name):
    response = client.get(reverse(url_name))
    assert response.status_code == 302
    assert "/tai-khoan/dang-nhap/" in response["Location"]
