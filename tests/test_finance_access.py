"""M8 – Phân quyền mọi URL tài chính: ẩn danh → đăng nhập; CUSTOMER/ADMIN/EDITOR NONE → 404;
EDITOR VIEW xem được nhưng mọi URL/POST ghi nhận → 404."""

from datetime import date

import pytest
from django.urls import reverse

from apps.core.finance import create_collection, create_receivable
from apps.core.models import AuditEvent, Collection, Receivable
from tests.factories import FeeTypeFactory, PublicationCaseFactory


@pytest.fixture
def finance_objects(editor_manage, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    fee = FeeTypeFactory()
    rec = create_receivable(actor=editor_manage, case=case, fee_type=fee, amount=1_000_000)
    col = create_collection(
        actor=editor_manage, receivable=rec, paid_date=date(2026, 1, 5), amount=400_000
    )
    return {"case": case, "fee": fee, "rec": rec, "col": col}


def view_urls(o):
    return [
        reverse("finance:overview"),
        reverse("finance:overview") + "?export=csv",
        reverse("finance:debt"),
        reverse("finance:debt") + "?export=csv",
        reverse("finance:case", args=[o["case"].pk]),
    ]


def manage_urls(o):
    return [
        reverse("finance:manage"),
        reverse("finance:receivable_create", args=[o["case"].pk]),
        reverse("finance:receivable_adjust", args=[o["rec"].pk]),
        reverse("finance:collection_create", args=[o["rec"].pk]),
        reverse("finance:collection_reverse", args=[o["col"].pk]),
    ]


@pytest.mark.django_db
def test_anonymous_redirected_to_login(client, finance_objects):
    for url in view_urls(finance_objects) + manage_urls(finance_objects):
        resp = client.get(url)
        assert resp.status_code == 302, url
        assert reverse("accounts:login") in resp["Location"]


@pytest.mark.django_db
@pytest.mark.parametrize("user_fixture", ["customer_a", "admin_user", "editor_none"])
def test_non_finance_users_get_404(client, request, finance_objects, user_fixture):
    client.force_login(request.getfixturevalue(user_fixture))
    for url in view_urls(finance_objects) + manage_urls(finance_objects):
        assert client.get(url).status_code == 404, url
    for url in manage_urls(finance_objects)[1:]:
        assert client.post(url, {"amount": 1, "note": "x"}).status_code == 404, url


@pytest.mark.django_db
def test_editor_view_reads_but_cannot_write(client, editor_view, finance_objects):
    client.force_login(editor_view)
    for url in view_urls(finance_objects):
        assert client.get(url).status_code == 200, url
    for url in manage_urls(finance_objects):
        assert client.get(url).status_code == 404, url
    rec_count, col_count = Receivable.objects.count(), Collection.objects.count()
    for url in manage_urls(finance_objects)[1:]:
        resp = client.post(
            url,
            {
                "fee_type": finance_objects["fee"].pk,
                "amount": 100,
                "paid_date": "2026-01-10",
                "method": "CASH",
                "note": "thử",
            },
        )
        assert resp.status_code == 404, url
    assert Receivable.objects.count() == rec_count
    assert Collection.objects.count() == col_count
    # Trang hồ sơ không hiện nút ghi nhận cho người chỉ xem
    body = client.get(reverse("finance:case", args=[finance_objects["case"].pk])).content.decode()
    assert "Thêm khoản phải thu" not in body
    assert "Ghi nhận đã thu" not in body
    assert not AuditEvent.objects.filter(action="finance.receivable_create", actor=editor_view)


@pytest.mark.django_db
def test_case_url_is_fixed_path_and_404_for_unknown_case(client, editor_view):
    import uuid

    case = PublicationCaseFactory()
    assert reverse("finance:case", args=[case.pk]) == f"/tai-chinh/ho-so/{case.pk}/"
    client.force_login(editor_view)
    assert client.get(f"/tai-chinh/ho-so/{uuid.uuid4()}/").status_code == 404
    assert client.get(f"/tai-chinh/ho-so/{case.pk}/").status_code == 200


@pytest.mark.django_db
def test_no_delete_urls():
    from apps.finance import urls

    names = [p.name for p in urls.urlpatterns]
    assert {"overview", "debt", "manage", "case"} <= set(names)
    for p in urls.urlpatterns:
        assert "xoa" not in str(p.pattern)
        assert "delete" not in (p.name or "")


@pytest.mark.django_db
def test_unknown_objects_404_for_manager(client, editor_manage, finance_objects):
    client.force_login(editor_manage)
    assert client.get(reverse("finance:receivable_adjust", args=[999999])).status_code == 404
    assert client.get(reverse("finance:collection_create", args=[999999])).status_code == 404
    assert client.get(reverse("finance:collection_reverse", args=[999999])).status_code == 404
