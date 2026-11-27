"""Test M5 — Tra cứu đầu sách."""

from __future__ import annotations

import datetime

import pytest
from django.urls import reverse

from apps.core.models import CaseStatus, ContributorRole, PublicationMode
from apps.reports.models import ImportBatch
from tests.factories import (
    CategoryFactory,
    ContributorFactory,
    FieldFactory,
    PublicationCaseFactory,
)

ISBN = "9786043000009"


@pytest.fixture
def books(db):
    a = PublicationCaseFactory(
        title="Kinh tế học vườn rau",
        status=CaseStatus.DECISION_ISSUED,
        isbn=ISBN,
        decision_number="123/QĐ-NXBKT",
        decision_date=datetime.date(2024, 5, 10),
    )
    ContributorFactory(case=a, full_name="Trần Văn Hư Cấu", order=2)
    ContributorFactory(
        case=a, full_name="Lê Thị Giả Định", role=ContributorRole.CHIEF_EDITOR, order=1
    )
    b = PublicationCaseFactory(
        title="Quản trị chuồng gà",
        status=CaseStatus.EDITING,
        registration_number="XNĐK-777",
        registration_date=datetime.date(2023, 2, 1),
    )
    ContributorFactory(case=b, full_name="Phạm Mơ Mộng")
    draft = PublicationCaseFactory(title="Bản nháp bí mật", status=CaseStatus.DRAFT)
    return a, b, draft


def _search(client, **params):
    resp = client.get(reverse("reports:search"), params)
    assert resp.status_code == 200
    return resp


def _titles(resp):
    return [row["case"].title for row in resp.context["rows"]]


def test_search_by_isbn_with_hyphens(client, editor_none, books):
    client.force_login(editor_none)
    assert _titles(_search(client, q="978-604-300-000-9")) == ["Kinh tế học vườn rau"]


def test_search_by_author_name(client, editor_none, books):
    client.force_login(editor_none)
    assert _titles(_search(client, q="mơ mộng")) == ["Quản trị chuồng gà"]


def test_search_by_decision_number(client, editor_none, books):
    client.force_login(editor_none)
    assert _titles(_search(client, q="123/QĐ")) == ["Kinh tế học vườn rau"]


def test_search_by_registration_number_and_codes(client, editor_none, books):
    client.force_login(editor_none)
    a, b, _draft = books
    assert _titles(_search(client, q="XNĐK-777")) == ["Quản trị chuồng gà"]
    assert _titles(_search(client, q=b.temp_code)) == ["Quản trị chuồng gà"]


def test_authors_joined_in_order_and_link(client, editor_none, books):
    client.force_login(editor_none)
    resp = _search(client, q=ISBN)
    assert resp.context["rows"][0]["authors"] == "Lê Thị Giả Định (Chủ biên); Trần Văn Hư Cấu"
    a = books[0]
    assert f'href="/noi-bo/ho-so/{a.pk}/"'.encode() in resp.content


def test_draft_hidden_by_default_but_filterable(client, editor_none, books):
    client.force_login(editor_none)
    assert "Bản nháp bí mật" not in _titles(_search(client))
    assert _titles(_search(client, status="DRAFT")) == ["Bản nháp bí mật"]


def test_year_filter_uses_decision_then_registration_date(client, editor_none, books):
    client.force_login(editor_none)
    assert _titles(_search(client, year=2024)) == ["Kinh tế học vườn rau"]
    assert _titles(_search(client, year=2023)) == ["Quản trị chuồng gà"]


def test_category_field_mode_filters(client, editor_none, db):
    client.force_login(editor_none)
    cat, fld = CategoryFactory(), FieldFactory()
    PublicationCaseFactory(title="Có thể loại", status=CaseStatus.EDITING, category=cat, field=fld)
    PublicationCaseFactory(
        title="Liên kết",
        status=CaseStatus.EDITING,
        publication_mode=PublicationMode.LINKED,
        partner_name="Công ty Hư Cấu",
    )
    assert _titles(_search(client, category=cat.pk)) == ["Có thể loại"]
    assert _titles(_search(client, field=fld.pk)) == ["Có thể loại"]
    assert _titles(_search(client, mode="LINKED")) == ["Liên kết"]


def test_source_filter(client, editor_none, books):
    client.force_login(editor_none)
    a, b, _d = books
    ImportBatch.objects.create(
        created_by=editor_none, original_filename="x.xlsx", case_ids=[str(a.pk)]
    )
    assert _titles(_search(client, source="EXCEL")) == ["Kinh tế học vườn rau"]
    assert _titles(_search(client, source="PORTAL")) == ["Quản trị chuồng gà"]
    resp = _search(client, source="EXCEL")
    assert resp.context["rows"][0]["is_imported"] is True


def test_htmx_returns_partial_and_paginates(client, editor_none, db):
    client.force_login(editor_none)
    for i in range(30):
        PublicationCaseFactory(title=f"Sách hư cấu {i}", status=CaseStatus.EDITING)
    resp = client.get(reverse("reports:search"), {"q": "hư cấu"}, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    assert b"<html" not in resp.content
    assert len(resp.context["rows"]) == 25
    resp = client.get(reverse("reports:search"), {"q": "hư cấu", "page": 2})
    assert len(resp.context["rows"]) == 5


def test_invalid_filter_shows_all(client, editor_none, books):
    client.force_login(editor_none)
    resp = _search(client, year="abc")
    assert len(resp.context["rows"]) == 2
