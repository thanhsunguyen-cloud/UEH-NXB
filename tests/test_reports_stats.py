"""Test M5 — Thống kê danh mục xuất bản và xuất Excel."""

from __future__ import annotations

import datetime
import io

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from apps.core.models import AuditEvent, CaseStatus, PublicationMode
from apps.reports import services
from tests.factories import (
    CategoryFactory,
    ContributorFactory,
    FieldFactory,
    PublicationCaseFactory,
)

D = datetime.date


@pytest.fixture
def catalog(db):
    cat = CategoryFactory(name="Giáo trình hư cấu")
    fld = FieldFactory(name="Kinh tế tưởng tượng")
    # Tính theo decision_date (dù registration_date khác năm)
    a = PublicationCaseFactory(
        title="Sách A",
        status=CaseStatus.DECISION_ISSUED,
        decision_date=D(2025, 1, 15),
        registration_date=D(2024, 12, 1),
        category=cat,
        field=fld,
        isbn="9786043000009",
        page_count=200,
        book_size="16x24",
    )
    ContributorFactory(case=a, full_name="Tác Giả Một")
    # Rơi về registration_date
    PublicationCaseFactory(
        title="Sách B",
        status=CaseStatus.REGISTERED,
        registration_date=D(2025, 2, 20),
        publication_mode=PublicationMode.LINKED,
        partner_name="Đối tác Hư Cấu",
    )
    PublicationCaseFactory(
        title="Sách C", status=CaseStatus.COMPLETED, decision_date=D(2025, 5, 3), category=cat
    )
    PublicationCaseFactory(title="Sách D", status=CaseStatus.COMPLETED, decision_date=D(2026, 3, 1))
    # Không có ngày -> không tính
    PublicationCaseFactory(title="Sách không ngày", status=CaseStatus.EDITING)
    return cat, fld


def _stats(client, **params):
    resp = client.get(reverse("reports:catalog_stats"), params)
    assert resp.status_code == 200
    return resp


def _by_period(resp):
    return [(p["label"], p["n"]) for p in resp.context["summary"]["by_period"]]


def test_counts_by_decision_then_registration_date(client, editor_none, catalog):
    client.force_login(editor_none)
    resp = _stats(client, date_from="2025-01-01", date_to="2025-12-31")
    s = resp.context["summary"]
    assert s["total"] == 3
    titles = {row["case"].title for row in resp.context["rows"]}
    assert titles == {"Sách A", "Sách B", "Sách C"}
    assert "Sách không ngày" not in resp.content.decode()
    # Sách A không bị tính vào 2024 dù có registration_date 2024
    resp = _stats(client, date_from="2024-01-01", date_to="2024-12-31")
    assert resp.context["summary"]["total"] == 0


def test_group_by_month(client, editor_none, catalog):
    client.force_login(editor_none)
    resp = _stats(client, date_from="2025-01-01", date_to="2025-06-30", group="month")
    assert _by_period(resp) == [
        ("Tháng 01/2025", 1),
        ("Tháng 02/2025", 1),
        ("Tháng 03/2025", 0),
        ("Tháng 04/2025", 0),
        ("Tháng 05/2025", 1),
        ("Tháng 06/2025", 0),
    ]


def test_group_by_quarter(client, editor_none, catalog):
    client.force_login(editor_none)
    resp = _stats(client, date_from="2025-01-01", date_to="2026-06-30", group="quarter")
    assert _by_period(resp) == [
        ("Quý 1/2025", 2),
        ("Quý 2/2025", 1),
        ("Quý 3/2025", 0),
        ("Quý 4/2025", 0),
        ("Quý 1/2026", 1),
        ("Quý 2/2026", 0),
    ]


def test_group_by_year(client, editor_none, catalog):
    client.force_login(editor_none)
    resp = _stats(client, date_from="2024-01-01", date_to="2026-12-31", group="year")
    assert _by_period(resp) == [("Năm 2024", 0), ("Năm 2025", 3), ("Năm 2026", 1)]


def test_breakdowns_and_filters(client, editor_none, catalog):
    cat, fld = catalog
    client.force_login(editor_none)
    resp = _stats(client, date_from="2025-01-01", date_to="2025-12-31")
    s = resp.context["summary"]
    assert {r["label"]: r["n"] for r in s["by_category"]} == {
        "Giáo trình hư cấu": 2,
        "(Chưa phân loại)": 1,
    }
    assert {r["label"]: r["n"] for r in s["by_field"]} == {
        "Kinh tế tưởng tượng": 1,
        "(Chưa phân loại)": 2,
    }
    assert {r["label"]: r["n"] for r in s["by_mode"]} == {"Tự xuất bản": 2, "Liên kết": 1}
    resp = _stats(client, date_from="2025-01-01", date_to="2025-12-31", category=cat.pk)
    assert resp.context["summary"]["total"] == 2
    resp = _stats(client, date_from="2025-01-01", date_to="2025-12-31", field=fld.pk)
    assert resp.context["summary"]["total"] == 1
    resp = _stats(client, date_from="2025-01-01", date_to="2025-12-31", mode="LINKED")
    assert resp.context["summary"]["total"] == 1


def test_default_period_is_current_year(client, editor_none, catalog):
    client.force_login(editor_none)
    resp = _stats(client)
    today = datetime.date.today()
    assert resp.context["date_from"] == D(today.year, 1, 1)
    assert resp.context["date_to"] == D(today.year, 12, 31)
    assert len(resp.context["summary"]["by_period"]) == 12


def test_invalid_range_falls_back_to_default(client, editor_none, catalog):
    client.force_login(editor_none)
    resp = _stats(client, date_from="2025-12-31", date_to="2025-01-01")
    assert resp.context["form"].errors
    assert resp.context["date_from"].month == 1


def test_page_explains_missing_dates(client, editor_none, catalog):
    client.force_login(editor_none)
    content = _stats(client).content.decode()
    assert "không được tính" in content
    assert "Xuất Excel" in content


def test_export_excel(client, editor_none, catalog):
    client.force_login(editor_none)
    resp = client.get(
        reverse("reports:catalog_export"), {"date_from": "2025-01-01", "date_to": "2025-12-31"}
    )
    assert resp.status_code == 200
    assert resp.streaming
    assert "spreadsheetml" in resp["Content-Type"]
    assert "attachment" in resp["Content-Disposition"]
    wb = load_workbook(io.BytesIO(b"".join(resp.streaming_content)))
    assert wb.sheetnames == ["Tổng hợp", "Danh mục"]
    ws = wb["Danh mục"]
    rows = list(ws.iter_rows(values_only=True))
    assert list(rows[0]) == services.CATALOG_COLUMNS
    header_text = " ".join(rows[0]).lower()
    for word in ("tiền", "phí", "giá", "thu"):
        assert word not in header_text
    assert len(rows) == 4
    first = rows[1]
    assert first[0] == 1 and first[1] == "Sách A"
    assert first[2] == "Tác Giả Một"
    assert first[7] == "9786043000009"
    assert first[11].date() == D(2025, 1, 15)
    assert first[13] == 200
    summary_values = [r for r in wb["Tổng hợp"].iter_rows(values_only=True)]
    assert ("Tổng số đầu sách", 3) in summary_values
    ev = AuditEvent.objects.get(action="report.export")
    assert ev.actor == editor_none
    assert ev.data["total"] == 3


def test_export_with_filters_label(client, editor_none, catalog):
    cat, fld = catalog
    client.force_login(editor_none)
    resp = client.get(
        reverse("reports:catalog_export"),
        {
            "date_from": "2025-01-01",
            "date_to": "2025-12-31",
            "category": cat.pk,
            "field": fld.pk,
            "mode": "SELF",
            "group": "quarter",
        },
    )
    wb = load_workbook(io.BytesIO(b"".join(resp.streaming_content)))
    values = [r for r in wb["Tổng hợp"].iter_rows(values_only=True)]
    assert ("Thể loại", "Giáo trình hư cấu") in values
    assert ("Hình thức", "Tự xuất bản") in values
    assert ("Nhóm theo", "Quý") in values


def test_detail_list_paginates(client, editor_none, db):
    client.force_login(editor_none)
    for i in range(30):
        PublicationCaseFactory(title=f"S{i}", decision_date=D(2025, 3, 1))
    resp = _stats(client, date_from="2025-01-01", date_to="2025-12-31")
    assert len(resp.context["rows"]) == 25
    assert resp.context["summary"]["total"] == 30
