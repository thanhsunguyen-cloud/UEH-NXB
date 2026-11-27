"""M8 – Ghi nhận: thêm khoản phải thu, ghi nhận thu, điều chỉnh, đảo khoản thu, thu vượt."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.finance import create_collection, create_receivable, outstanding
from apps.core.models import AuditEvent, Collection, FeeType, PublicationMode, Receivable
from apps.finance.templatetags.finance_tags import finance_action_label, format_vnd
from tests.factories import FeeTypeFactory, PublicationCaseFactory, UserFactory


@pytest.fixture
def case(customer_a):
    return PublicationCaseFactory(owner=customer_a, title="Kinh tế vĩ mô")


@pytest.fixture
def fee(db):
    return FeeTypeFactory(name="Phí biên tập")


@pytest.fixture
def rec(editor_manage, case, fee):
    return create_receivable(
        actor=editor_manage,
        case=case,
        fee_type=fee,
        amount=3_500_000,
        due_date=date(2026, 12, 31),
    )


@pytest.fixture
def manager(client, editor_manage):
    client.force_login(editor_manage)
    return client


def test_format_vnd():
    assert format_vnd(3500000) == "3.500.000 đ"
    assert format_vnd(Decimal("-500000")) == "-500.000 đ"
    assert format_vnd(0) == "0 đ"
    assert format_vnd(None) == ""
    assert format_vnd("abc") == ""
    assert finance_action_label("finance.export") == "Xuất CSV"
    assert finance_action_label("other") == "other"


@pytest.mark.django_db
def test_add_receivable_defaults_and_audit(manager, case, fee):
    url = reverse("finance:receivable_create", args=[case.pk])
    resp = manager.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Khách hàng A" in body  # người phải trả mặc định = người đại diện
    FeeType.objects.create(name="Phí ngừng dùng", is_active=False)
    assert "Phí ngừng dùng" not in manager.get(url).content.decode()

    resp = manager.post(
        url,
        {
            "fee_type": fee.pk,
            "amount": "3500000",
            "description": "Phí biên tập bản thảo",
            "payer_name": "",
            "contract_number": "HĐ-01",
            "invoice_number": "CT-01",
            "invoice_date": "2026-03-01",
            "due_date": "2026-04-01",
            "note": "",
        },
    )
    assert resp.status_code == 302
    assert resp["Location"] == reverse("finance:case", args=[case.pk])
    rec = Receivable.objects.get(case=case)
    assert rec.amount == Decimal("3500000")
    assert rec.payer_name == "Khách hàng A"
    assert rec.invoice_date == date(2026, 3, 1)
    assert outstanding(rec) == Decimal("3500000")
    assert AuditEvent.objects.filter(
        action="finance.receivable_create", object_id=str(rec.pk)
    ).exists()
    page = manager.get(reverse("finance:case", args=[case.pk])).content.decode()
    assert "3.500.000 đ" in page
    assert f"/noi-bo/ho-so/{case.pk}/" in page


@pytest.mark.django_db
def test_add_receivable_linked_payer_default(manager, customer_a):
    case = PublicationCaseFactory(
        owner=customer_a, publication_mode=PublicationMode.LINKED, partner_name="Công ty Sách ABC"
    )
    body = manager.get(reverse("finance:receivable_create", args=[case.pk])).content.decode()
    assert "Công ty Sách ABC" in body


@pytest.mark.django_db
@pytest.mark.parametrize("amount", ["0", "-5", "1.5", "abc", ""])
def test_add_receivable_rejects_invalid_amount(manager, case, fee, amount):
    resp = manager.post(
        reverse("finance:receivable_create", args=[case.pk]),
        {"fee_type": fee.pk, "amount": amount},
    )
    assert resp.status_code == 400
    assert not Receivable.objects.exists()


@pytest.mark.django_db
def test_record_collection_and_outstanding(manager, rec):
    url = reverse("finance:collection_create", args=[rec.pk])
    assert manager.get(url).status_code == 200
    resp = manager.post(
        url,
        {
            "paid_date": "2026-05-02",
            "amount": "1500000",
            "method": "TRANSFER",
            "reference": "UNC-123",
            "note": "",
        },
    )
    assert resp.status_code == 302
    col = Collection.objects.get(receivable=rec)
    assert col.reference == "UNC-123"
    assert outstanding(rec) == Decimal("2000000")
    assert AuditEvent.objects.filter(
        action="finance.collection_create", object_id=str(col.pk)
    ).exists()


@pytest.mark.django_db
def test_collection_date_cannot_be_future(manager, rec):
    future = timezone.localdate() + timedelta(days=1)
    resp = manager.post(
        reverse("finance:collection_create", args=[rec.pk]),
        {"paid_date": future.isoformat(), "amount": "100", "method": "CASH"},
    )
    assert resp.status_code == 400
    assert "tương lai" in resp.content.decode()
    assert not Collection.objects.exists()


@pytest.mark.django_db
def test_overpayment_blocked_without_confirmation(manager, rec):
    url = reverse("finance:collection_create", args=[rec.pk])
    data = {"paid_date": "2026-05-02", "amount": "4000000", "method": "CASH", "note": ""}
    resp = manager.post(url, data)
    assert resp.status_code == 400
    assert "overpayment-warning" in resp.content.decode()
    assert not Collection.objects.exists()

    # Tích xác nhận nhưng thiếu ghi chú -> vẫn chặn
    resp = manager.post(url, {**data, "confirm_overpayment": "on"})
    assert resp.status_code == 400
    assert not Collection.objects.exists()

    # Ghi chú nhưng không tích -> chặn
    resp = manager.post(url, {**data, "note": "Khách chuyển dư"})
    assert resp.status_code == 400
    assert not Collection.objects.exists()

    resp = manager.post(url, {**data, "confirm_overpayment": "on", "note": "Khách chuyển dư"})
    assert resp.status_code == 302
    assert outstanding(rec) == Decimal("-500000")
    assert AuditEvent.objects.filter(action="finance.collection_create").count() == 1


@pytest.mark.django_db
def test_adjustment_requires_note_and_updates_outstanding(manager, rec):
    url = reverse("finance:receivable_adjust", args=[rec.pk])
    assert manager.get(url).status_code == 200
    resp = manager.post(url, {"amount": "-500000", "note": "  "})
    assert resp.status_code == 400
    assert "bắt buộc ghi chú" in resp.content.decode()
    assert Receivable.objects.count() == 1

    resp = manager.post(url, {"amount": "0", "note": "Lý do"})
    assert resp.status_code == 400
    resp = manager.post(url, {"amount": "-9000000", "note": "Giảm quá mức"})
    assert resp.status_code == 400
    assert Receivable.objects.count() == 1

    resp = manager.post(url, {"amount": "-500000", "note": "Giảm giá theo phụ lục HĐ"})
    assert resp.status_code == 302
    adj = Receivable.objects.get(is_adjustment=True)
    assert adj.adjusts == rec
    assert adj.fee_type == rec.fee_type
    assert adj.note == "Giảm giá theo phụ lục HĐ"
    assert outstanding(rec) == Decimal("3000000")
    assert AuditEvent.objects.filter(
        action="finance.receivable_adjust", object_id=str(adj.pk)
    ).exists()
    # Không cho điều chỉnh tiếp chính bút toán điều chỉnh
    assert manager.get(reverse("finance:receivable_adjust", args=[adj.pk])).status_code == 404
    page = manager.get(reverse("finance:case", args=[rec.case.pk])).content.decode()
    assert "Giảm giá theo phụ lục HĐ" in page
    assert "3.000.000 đ" in page


@pytest.mark.django_db
def test_reverse_collection_requires_note(manager, rec, editor_manage):
    col = create_collection(
        actor=editor_manage, receivable=rec, paid_date=date(2026, 5, 1), amount=1_000_000
    )
    url = reverse("finance:collection_reverse", args=[col.pk])
    assert manager.get(url).status_code == 200
    resp = manager.post(url, {"paid_date": "2026-05-03", "note": ""})
    assert resp.status_code == 400
    assert Collection.objects.count() == 1
    future = (timezone.localdate() + timedelta(days=2)).isoformat()
    assert manager.post(url, {"paid_date": future, "note": "x"}).status_code == 400

    resp = manager.post(url, {"paid_date": "2026-05-03", "note": "Nhầm hồ sơ"})
    assert resp.status_code == 302
    reversal = Collection.objects.get(is_adjustment=True)
    assert reversal.amount == Decimal("-1000000")
    assert reversal.note.startswith(f"[Đảo khoản thu #{col.pk}]")
    assert outstanding(rec) == Decimal("3500000")
    assert AuditEvent.objects.filter(
        action="finance.collection_adjust", object_id=str(reversal.pk)
    ).exists()

    # Không đảo lần hai, không đảo chính bút toán đảo
    resp = manager.get(url)
    assert resp.status_code == 302
    resp = manager.post(url, {"paid_date": "2026-05-04", "note": "lần 2"})
    assert resp.status_code == 302
    assert Collection.objects.count() == 2
    assert manager.get(reverse("finance:collection_reverse", args=[reversal.pk])).status_code == 404
    page = manager.get(reverse("finance:case", args=[rec.case.pk])).content.decode()
    assert "Đã đảo" in page


@pytest.mark.django_db
def test_service_validation_error_shown(manager, rec, monkeypatch):
    from django.core.exceptions import ValidationError

    from apps.finance import views

    def boom(**kwargs):
        raise ValidationError("Lỗi kiểm tra từ M0")

    monkeypatch.setattr(views, "create_receivable", boom)
    monkeypatch.setattr(views, "create_collection", boom)
    resp = manager.post(
        reverse("finance:receivable_create", args=[rec.case.pk]),
        {"fee_type": rec.fee_type.pk, "amount": "10"},
    )
    assert resp.status_code == 400
    assert "Lỗi kiểm tra từ M0" in resp.content.decode()
    resp = manager.post(
        reverse("finance:collection_create", args=[rec.pk]),
        {"paid_date": "2026-05-02", "amount": "10", "method": "CASH"},
    )
    assert resp.status_code == 400
    assert "Lỗi kiểm tra từ M0" in resp.content.decode()


@pytest.mark.django_db
def test_manage_page_search_and_recent_events(manager, rec, editor_manage, customer_a):
    other = PublicationCaseFactory(owner=UserFactory(), title="Kinh tế lượng")
    url = reverse("finance:manage")
    resp = manager.get(url)
    assert resp.status_code == 200
    assert "Thêm khoản phải thu" in resp.content.decode()  # nhãn thao tác gần nhất

    # Một kết quả -> chuyển thẳng tới trang tài chính hồ sơ
    resp = manager.get(url, {"q": rec.case.temp_code})
    assert resp.status_code == 302
    assert resp["Location"] == reverse("finance:case", args=[rec.case.pk])

    # Nhiều kết quả -> danh sách
    resp = manager.get(url, {"q": "Kinh tế"})
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "search-results" in body
    assert rec.case.display_code in body and other.display_code in body

    resp = manager.get(url, {"q": "không có sách này"})
    assert "Không tìm thấy hồ sơ" in resp.content.decode()


@pytest.mark.django_db
def test_manage_search_by_isbn(manager, customer_a):
    case = PublicationCaseFactory(owner=customer_a, isbn="9786043288759")
    resp = manager.get(reverse("finance:manage"), {"q": "978-604-328-875-9"})
    assert resp.status_code == 302
    assert resp["Location"] == reverse("finance:case", args=[case.pk])


@pytest.mark.django_db
def test_recent_events_limited_to_20(manager, rec, editor_manage):
    for i in range(25):
        create_collection(
            actor=editor_manage, receivable=rec, paid_date=date(2026, 1, 1), amount=1 + i
        )
    body = manager.get(reverse("finance:manage")).content.decode()
    assert body.count("Ghi nhận đã thu") == 20
