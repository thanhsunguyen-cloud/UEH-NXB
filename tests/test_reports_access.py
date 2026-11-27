"""Test M5 — phân quyền mọi URL: chưa đăng nhập -> đăng nhập; CUSTOMER, ADMIN -> 404."""

from __future__ import annotations

import pytest
from django.urls import reverse

GET_URLS = [
    "reports:search",
    "reports:catalog_stats",
    "reports:catalog_export",
    "reports:import",
    "reports:import_template",
    "reports:import_history",
]


@pytest.mark.django_db
@pytest.mark.parametrize("name", GET_URLS)
def test_anonymous_redirects_to_login(client, name):
    resp = client.get(reverse(name))
    assert resp.status_code == 302
    assert "dang-nhap" in resp["Location"] or "login" in resp["Location"]


@pytest.mark.django_db
def test_anonymous_post_import_redirects_to_login(client):
    resp = client.post(reverse("reports:import"))
    assert resp.status_code == 302


@pytest.mark.parametrize("name", GET_URLS)
@pytest.mark.parametrize("who", ["customer_a", "admin_user"])
def test_customer_and_admin_get_404(client, request, name, who):
    client.force_login(request.getfixturevalue(who))
    assert client.get(reverse(name)).status_code == 404


@pytest.mark.parametrize("who", ["customer_a", "admin_user"])
def test_customer_and_admin_post_import_404(client, request, who):
    client.force_login(request.getfixturevalue(who))
    assert client.post(reverse("reports:import")).status_code == 404


@pytest.mark.parametrize("name", GET_URLS)
def test_editor_can_open(client, editor_none, name):
    client.force_login(editor_none)
    assert client.get(reverse(name)).status_code == 200


def test_urls_paths():
    assert reverse("reports:search") == "/bao-cao/tra-cuu/"
    assert reverse("reports:catalog_stats") == "/bao-cao/danh-muc-xuat-ban/"
    assert reverse("reports:import") == "/bao-cao/nhap-excel/"
