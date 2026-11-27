"""Các trang đăng nhập/đăng ký của allauth hiển thị tiếng Việt trong khung Portal."""

import logging

import pytest
from django.urls import reverse

from apps.accounts.adapters import PortalSocialAccountAdapter


@pytest.mark.django_db
def test_allauth_login_redirects_to_portal_login(client):
    r = client.get("/accounts/login/?next=/khach-hang/")
    assert r.status_code == 302
    assert r["Location"] == "/tai-khoan/dang-nhap/?next=/khach-hang/"


@pytest.mark.django_db
def test_signup_page_is_vietnamese(client):
    html = client.get(reverse("account_signup")).content.decode()
    assert "Đăng ký tài khoản khách hàng" in html
    assert "Nhập lại mật khẩu" in html
    assert "Sign Up" not in html


@pytest.mark.django_db
def test_signup_sends_vietnamese_confirmation_email(client, mailoutbox):
    r = client.post(
        reverse("account_signup"),
        {
            "email": "tacgia@example.com",
            "password1": "Sach-moi-2026!",
            "password2": "Sach-moi-2026!",
        },
    )
    assert r.status_code == 302
    assert len(mailoutbox) == 1
    msg = mailoutbox[0]
    assert msg.subject.startswith("[NXB Kinh tế TP.HCM] Xác nhận email")
    assert "example.com" not in msg.body.replace("tacgia@example.com", "")
    html = client.get(r["Location"]).content.decode()
    assert "Vui lòng xác nhận email" in html


@pytest.mark.django_db
def test_social_login_and_error_pages_are_vietnamese(client, settings):
    settings.SOCIALACCOUNT_PROVIDERS["google"]["APP"]["client_id"] = "test-id"
    html = client.get("/accounts/google/login/").content.decode()
    assert "Tiếp tục với Google" in html
    html = client.get(reverse("socialaccount_login_error")).content.decode()
    assert "Đăng nhập Google không thành công" in html


@pytest.mark.django_db
def test_password_reset_page_is_vietnamese(client):
    html = client.get(reverse("account_reset_password")).content.decode()
    assert "Quên mật khẩu" in html


def test_social_auth_error_is_logged(rf, caplog):
    adapter = PortalSocialAccountAdapter()
    with caplog.at_level(logging.WARNING, logger="apps.accounts.adapters"):
        try:
            adapter.on_authentication_error(
                rf.get("/"), "google", error="unknown", exception=ValueError("invalid_client")
            )
        except Exception:  # noqa: BLE001 - lớp cha có thể ném ImmediateHttpResponse
            pass
    assert "invalid_client" in caplog.text
