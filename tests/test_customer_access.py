"""M2 — Phân quyền truy cập mọi URL của cổng khách hàng."""

import pytest
from django.conf import settings
from django.urls import reverse

from tests.factories import ContributorFactory, PublicationCaseFactory


def _all_urls(case, contributor):
    return [
        ("get", reverse("customer:home")),
        ("get", reverse("customer:case_create")),
        ("get", reverse("customer:profile")),
        ("get", reverse("customer:case_detail", args=[case.pk])),
        ("get", reverse("customer:case_edit", args=[case.pk])),
        ("post", reverse("customer:case_submit", args=[case.pk])),
        ("post", reverse("customer:note_add", args=[case.pk])),
        ("get", reverse("customer:contributor_add", args=[case.pk])),
        ("get", reverse("customer:contributor_edit", args=[case.pk, contributor.pk])),
        ("post", reverse("customer:contributor_remove", args=[case.pk, contributor.pk])),
    ]


CASE_URLS = [
    ("get", "customer:case_detail", False),
    ("get", "customer:case_edit", False),
    ("post", "customer:case_submit", False),
    ("post", "customer:note_add", False),
    ("get", "customer:contributor_add", False),
    ("get", "customer:contributor_edit", True),
    ("post", "customer:contributor_remove", True),
]


@pytest.mark.django_db
def test_anonymous_redirected_to_login(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    contributor = ContributorFactory(case=case)
    for method, url in _all_urls(case, contributor):
        response = getattr(client, method)(url)
        assert response.status_code == 302, url
        assert response["Location"].startswith(settings.LOGIN_URL), url


@pytest.mark.django_db
@pytest.mark.parametrize("staff_fixture", ["editor_none", "editor_manage", "admin_user"])
def test_editor_and_admin_get_404(request, client, customer_a, staff_fixture):
    staff = request.getfixturevalue(staff_fixture)
    case = PublicationCaseFactory(owner=customer_a)
    contributor = ContributorFactory(case=case)
    client.force_login(staff)
    for method, url in _all_urls(case, contributor):
        response = getattr(client, method)(url)
        assert response.status_code == 404, url


@pytest.mark.django_db
def test_customer_cannot_access_other_customers_case(client, customer_a, customer_b):
    case = PublicationCaseFactory(owner=customer_a)
    contributor = ContributorFactory(case=case)
    client.force_login(customer_b)
    for method, name, with_contributor in CASE_URLS:
        args = [case.pk, contributor.pk] if with_contributor else [case.pk]
        response = getattr(client, method)(reverse(name, args=args))
        assert response.status_code == 404, name
    # Hồ sơ của người khác không lộ trên danh sách
    response = client.get(reverse("customer:home"))
    assert case.title not in response.content.decode()


@pytest.mark.django_db
def test_contributor_of_other_case_returns_404(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    other = ContributorFactory(case=PublicationCaseFactory(owner=customer_a))
    client.force_login(customer_a)
    url = reverse("customer:contributor_edit", args=[case.pk, other.pk])
    assert client.get(url).status_code == 404
    url = reverse("customer:contributor_remove", args=[case.pk, other.pk])
    assert client.post(url).status_code == 404


@pytest.mark.django_db
def test_inactive_customer_gets_404(client, customer_a):
    customer_a.is_active = False
    customer_a.save()
    client.force_login(customer_a)
    response = client.get(reverse("customer:home"))
    assert response.status_code in (302, 404)
