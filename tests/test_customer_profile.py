"""M2 — Trang tài khoản khách hàng."""

import pytest
from django.urls import reverse

from apps.core.models import AuditEvent


@pytest.mark.django_db
def test_profile_view_and_update(client, customer_a):
    client.force_login(customer_a)
    response = client.get(reverse("customer:profile"))
    html = response.content.decode()
    assert response.status_code == 200
    assert customer_a.email in html
    assert reverse("account_change_password") in html

    response = client.post(
        reverse("customer:profile"),
        {
            "full_name": "Tên Mới",
            "phone": "0911222333",
            "organization": "Trường ĐH X",
            "email": "hacker@example.com",
        },
    )
    assert response.status_code == 302
    customer_a.refresh_from_db()
    assert customer_a.full_name == "Tên Mới"
    assert customer_a.phone == "0911222333"
    assert customer_a.organization == "Trường ĐH X"
    assert customer_a.email == "customer_a@example.com"
    event = AuditEvent.objects.get(action="user.profile_update")
    assert event.data["before"]["full_name"] == "Khách hàng A"
    assert event.data["after"]["full_name"] == "Tên Mới"


@pytest.mark.django_db
def test_profile_requires_full_name(client, customer_a):
    client.force_login(customer_a)
    response = client.post(reverse("customer:profile"), {"full_name": "", "phone": ""})
    assert response.status_code == 200
    assert "full_name" in response.context["form"].errors
    assert not AuditEvent.objects.filter(action="user.profile_update").exists()
