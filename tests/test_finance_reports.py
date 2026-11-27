"""M8 – Tổng quan theo kỳ, công nợ theo tuổi nợ, xuất CSV."""

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.finance import (
    AGING_D1_30,
    AGING_D31_60,
    AGING_D61_90,
    AGING_D90_PLUS,
    AGING_NOT_DUE,
    aging_bucket,
    create_collection,
    create_receivable,
)
from apps.core.models import AuditEvent, PublicationMode, Receivable
from apps.finance import services
from tests.factories import FeeTypeFactory, PublicationCaseFactory


def parse_csv(resp):
    raw = resp.content
    assert raw.startswith(b"\xef\xbb\xbf"), "CSV phải có BOM UTF-8"
    return list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))


@pytest.fixture
def sample(editor_manage, customer_a):
    """Dữ liệu mẫu năm 2026 có điều chỉnh, đảo, hai loại phí và hai hình thức xuất bản."""
    fee_edit = FeeTypeFactory(name="Phí biên tập")
    fee_pub = FeeTypeFactory(name="Phí quản lý xuất bản")
    case_self = PublicationCaseFactory(owner=customer_a, title="Sách tự xuất bản")
    case_linked = PublicationCaseFactory(
        owner=customer_a,
        title="Sách liên kết",
        publication_mode=PublicationMode.LINKED,
        partner_name="Công ty ABC",
    )
    r1 = create_receivable(
        actor=editor_manage,
        case=case_self,
        fee_type=fee_edit,
        amount=10_000_000,
        invoice_date=date(2026, 1, 15),
    )
    r2 = create_receivable(
        actor=editor_manage,
        case=case_linked,
        fee_type=fee_pub,
        amount=4_000_000,
        invoice_date=date(2026, 2, 10),
    )
    r_old = create_receivable(
        actor=editor_manage,
        case=case_self,
        fee_type=fee_pub,
        amount=2_000_000,
        invoice_date=date(2025, 12, 20),
    )
    create_receivable(
        actor=editor_manage,
        case=case_self,
        fee_type=fee_edit,
        amount=-1_000_000,
        invoice_date=date(2026, 3, 5),
        is_adjustment=True,
        adjusts=r1,
        note="Giảm giá",
    )
    create_collection(
        actor=editor_manage, receivable=r1, paid_date=date(2026, 2, 1), amount=3_000_000
    )
    c_bad = create_collection(
        actor=editor_manage, receivable=r2, paid_date=date(2026, 3, 1), amount=1_000_000
    )
    create_collection(
        actor=editor_manage,
        receivable=r2,
        paid_date=date(2026, 3, 2),
        amount=-c_bad.amount,
        is_adjustment=True,
        note=f"[Đảo khoản thu #{c_bad.pk}] nhầm",
    )
    create_collection(
        actor=editor_manage, receivable=r_old, paid_date=date(2025, 12, 25), amount=500_000
    )
    return {"fee_edit": fee_edit, "fee_pub": fee_pub, "r1": r1, "r2": r2, "r_old": r_old}


@pytest.mark.django_db
def test_overview_period_figures(sample):
    data = services.build_overview(date(2026, 1, 1), date(2026, 12, 31))
    assert data.total_receivable == Decimal("13000000")  # 10tr + 4tr - 1tr điều chỉnh
    assert data.total_collected == Decimal("3000000")  # 3tr + 1tr - 1tr đảo
    # Còn nợ cuối kỳ: (10-1-3) + 4 + (2-0.5) = 11,5tr
    assert data.outstanding_at_end == Decimal("11500000")
    months = {m["month"].month: m for m in data.months}
    assert len(data.months) == 12
    assert months[1]["receivable"] == Decimal("10000000")
    assert months[2]["receivable"] == Decimal("4000000")
    assert months[3]["receivable"] == Decimal("-1000000")
    assert months[2]["collected"] == Decimal("3000000")
    assert months[3]["collected"] == Decimal("0")
    fees = {f["name"]: f for f in data.fee_types}
    assert fees["Phí biên tập"]["receivable"] == Decimal("9000000")
    assert fees["Phí quản lý xuất bản"]["receivable"] == Decimal("4000000")
    assert fees["Phí biên tập"]["collected"] == Decimal("3000000")


@pytest.mark.django_db
def test_overview_filters_and_end_balance(sample):
    data = services.build_overview(date(2025, 12, 1), date(2025, 12, 31))
    assert data.total_receivable == Decimal("2000000")
    assert data.total_collected == Decimal("500000")
    assert data.outstanding_at_end == Decimal("1500000")

    data = services.build_overview(
        date(2026, 1, 1), date(2026, 12, 31), publication_mode=PublicationMode.LINKED
    )
    assert data.total_receivable == Decimal("4000000")
    assert data.total_collected == Decimal("0")

    data = services.build_overview(date(2026, 1, 1), date(2026, 2, 28), fee_type=sample["fee_edit"])
    assert data.total_receivable == Decimal("10000000")
    assert data.outstanding_at_end == Decimal("7000000")


@pytest.mark.django_db
def test_overview_uses_created_date_when_no_invoice_date(editor_manage, customer_a):
    fee = FeeTypeFactory()
    case = PublicationCaseFactory(owner=customer_a)
    create_receivable(actor=editor_manage, case=case, fee_type=fee, amount=700_000)
    today = timezone.localdate()
    data = services.build_overview(today, today)
    assert data.total_receivable == Decimal("700000")


@pytest.mark.django_db
def test_overview_page_and_csv(client, editor_view, sample):
    client.force_login(editor_view)
    resp = client.get(
        reverse("finance:overview"), {"date_from": "2026-01-01", "date_to": "2026-12-31"}
    )
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "13.000.000 đ" in body
    assert "11.500.000 đ" in body

    resp = client.get(
        reverse("finance:overview"),
        {"date_from": "2026-01-01", "date_to": "2026-12-31", "export": "csv"},
    )
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    assert "attachment" in resp["Content-Disposition"]
    rows = parse_csv(resp)
    assert rows[0] == ["Nhóm", "Mục", "Phải thu (VNĐ)", "Đã thu (VNĐ)"]
    assert ["Tháng", "01/2026", "10000000", "0"] in rows
    assert ["Loại phí", "Phí biên tập", "9000000", "3000000"] in rows
    assert rows[-2][0] == "Tổng kỳ" and rows[-2][2:] == ["13000000", "3000000"]
    assert rows[-1][0] == "Còn nợ cuối kỳ" and rows[-1][2] == "11500000"
    ev = AuditEvent.objects.get(action="finance.export")
    assert ev.actor == editor_view
    assert ev.data["report"] == "overview"


@pytest.mark.django_db
def test_overview_default_period_and_invalid_range(client, editor_view):
    client.force_login(editor_view)
    year = timezone.localdate().year
    resp = client.get(reverse("finance:overview"))
    assert resp.status_code == 200
    assert f"01/01/{year} – 31/12/{year}" in resp.content.decode()
    resp = client.get(
        reverse("finance:overview"), {"date_from": "2026-05-01", "date_to": "2026-01-01"}
    )
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "phải trước hoặc bằng" in body
    assert f"01/01/{year} – 31/12/{year}" in body
    # Lọc chỉ có loại phí -> kỳ mặc định năm hiện tại
    fee = FeeTypeFactory()
    resp = client.get(reverse("finance:overview"), {"fee_type": fee.pk})
    assert f"01/01/{year} – 31/12/{year}" in resp.content.decode()


def _rec(actor, case, fee, amount, due):
    return create_receivable(actor=actor, case=case, fee_type=fee, amount=amount, due_date=due)


@pytest.mark.django_db
def test_debt_aging_buckets_and_paid_hidden(client, editor_view, editor_manage, customer_a):
    today = timezone.localdate()
    fee = FeeTypeFactory(name="Phí biên tập")
    case = PublicationCaseFactory(owner=customer_a, title="Sách công nợ")
    recs = {
        AGING_NOT_DUE: _rec(editor_manage, case, fee, 100_000, today + timedelta(days=5)),
        AGING_D1_30: _rec(editor_manage, case, fee, 200_000, today - timedelta(days=30)),
        AGING_D31_60: _rec(editor_manage, case, fee, 300_000, today - timedelta(days=31)),
        AGING_D61_90: _rec(editor_manage, case, fee, 400_000, today - timedelta(days=90)),
        AGING_D90_PLUS: _rec(editor_manage, case, fee, 500_000, today - timedelta(days=91)),
    }
    no_due = create_receivable(actor=editor_manage, case=case, fee_type=fee, amount=50_000)
    paid = _rec(editor_manage, case, fee, 600_000, today - timedelta(days=100))
    create_collection(actor=editor_manage, receivable=paid, paid_date=today, amount=600_000)
    partial = _rec(editor_manage, case, fee, 1_000_000, today - timedelta(days=10))
    create_collection(actor=editor_manage, receivable=partial, paid_date=today, amount=250_000)

    lines = services.debt_lines(today=today)
    by_pk = {line.receivable.pk: line for line in lines}
    assert paid.pk not in by_pk
    for bucket, rec in recs.items():
        assert by_pk[rec.pk].bucket == bucket == aging_bucket(rec, today)
    assert by_pk[no_due.pk].bucket == AGING_NOT_DUE
    assert by_pk[partial.pk].outstanding == Decimal("750000")
    summary = {row["key"]: row for row in services.aging_summary(lines)}
    assert summary[AGING_NOT_DUE]["count"] == 2
    assert summary[AGING_D1_30]["amount"] == Decimal("950000")
    assert summary[AGING_D90_PLUS]["amount"] == Decimal("500000")

    client.force_login(editor_view)
    resp = client.get(reverse("finance:debt"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "600.000 đ" not in body
    assert "750.000 đ" in body
    assert "Trên 90 ngày" in body

    resp = client.get(reverse("finance:debt"), {"bucket": AGING_D31_60})
    assert [line.receivable.pk for line in resp.context["lines"]] == [recs[AGING_D31_60].pk]
    # Bảng tổng theo nhóm vẫn tính trên toàn bộ danh sách (không bị lọc nhóm)
    assert sum(r["count"] for r in resp.context["summary"]) == 7


@pytest.mark.django_db
def test_debt_adjusted_to_zero_hidden(editor_manage, customer_a):
    fee = FeeTypeFactory()
    case = PublicationCaseFactory(owner=customer_a)
    rec = create_receivable(actor=editor_manage, case=case, fee_type=fee, amount=300_000)
    create_receivable(
        actor=editor_manage,
        case=case,
        fee_type=fee,
        amount=-300_000,
        is_adjustment=True,
        adjusts=rec,
        note="Miễn phí",
    )
    assert services.debt_lines(today=timezone.localdate()) == []


@pytest.mark.django_db
def test_debt_filters_search_pagination_and_csv(client, editor_view, editor_manage, customer_a):
    fee_a = FeeTypeFactory(name="Phí A")
    fee_b = FeeTypeFactory(name="Phí B")
    target = PublicationCaseFactory(owner=customer_a, title="Quản trị chiến lược")
    create_receivable(
        actor=editor_manage,
        case=target,
        fee_type=fee_b,
        amount=900_000,
        payer_name="Trường Đại học X",
        due_date=date(2026, 1, 1),
    )
    for i in range(30):
        case = PublicationCaseFactory(owner=customer_a, title=f"Sách số {i}")
        create_receivable(actor=editor_manage, case=case, fee_type=fee_a, amount=100_000 + i)

    client.force_login(editor_view)
    url = reverse("finance:debt")
    resp = client.get(url)
    assert len(resp.context["lines"]) == 25
    assert resp.context["page_obj"].paginator.count == 31
    resp = client.get(url, {"page": 2, "fee_type": fee_a.pk})
    assert len(resp.context["lines"]) == 5
    assert "fee_type=" in resp.context["querystring"]
    assert "page" not in resp.context["querystring"]

    assert client.get(url, {"fee_type": fee_b.pk}).context["page_obj"].paginator.count == 1
    assert client.get(url, {"payer": "đại học x"}).context["page_obj"].paginator.count == 1
    assert client.get(url, {"q": "chiến lược"}).context["page_obj"].paginator.count == 1
    assert client.get(url, {"q": target.temp_code}).context["page_obj"].paginator.count == 1

    resp = client.get(url, {"q": "chiến lược"}, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    assert "<html" not in resp.content.decode()
    assert "Quản trị chiến lược" in resp.content.decode()

    resp = client.get(url, {"q": "chiến lược", "export": "csv"})
    rows = parse_csv(resp)
    assert rows[0] == services.DEBT_CSV_HEADER
    assert len(rows) == 2
    assert rows[1] == [
        target.display_code,
        "Quản trị chiến lược",
        "Trường Đại học X",
        "Phí B",
        "900000",
        "0",
        "900000",
        "01/01/2026",
        str(services.AGING_LABELS[aging_bucket(Receivable.objects.get(case=target))]),
    ]
    ev = AuditEvent.objects.get(action="finance.export")
    assert ev.data["report"] == "debt"
    assert ev.data["rows"] == 1


@pytest.mark.django_db
def test_case_page_totals(client, editor_view, sample):
    client.force_login(editor_view)
    case = sample["r1"].case
    resp = client.get(reverse("finance:case", args=[case.pk]))
    assert resp.status_code == 200
    totals = resp.context["finance"]["totals"]
    # r1: 10tr - 1tr, thu 3tr; r_old: 2tr, thu 0,5tr
    assert totals["receivable"] == Decimal("11000000")
    assert totals["collected"] == Decimal("3500000")
    assert totals["outstanding"] == Decimal("7500000")
    body = resp.content.decode()
    assert "Giảm giá" in body
    assert "7.500.000 đ" in body

    linked = sample["r2"].case
    resp = client.get(reverse("finance:case", args=[linked.pk]))
    assert resp.context["finance"]["totals"]["collected"] == Decimal("0")
    item = resp.context["finance"]["items"][0]
    reversed_ids = {c.pk for c in item["collections"] if c.already_reversed}
    assert len(reversed_ids) == 1


@pytest.mark.django_db
def test_case_page_empty(client, editor_view):
    client.force_login(editor_view)
    case = PublicationCaseFactory()
    body = client.get(reverse("finance:case", args=[case.pk])).content.decode()
    assert "chưa có khoản phải thu" in body
