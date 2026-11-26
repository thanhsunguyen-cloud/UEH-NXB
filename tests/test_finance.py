"""Nhóm test 8: Phân quyền tài chính, không xóa Receivable/Collection, tính công nợ & tuổi nợ."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.core.finance import (
    AGING_D1_30,
    AGING_D31_60,
    AGING_D61_90,
    AGING_D90_PLUS,
    AGING_NOT_DUE,
    STATUS_OVERDUE,
    STATUS_PAID,
    STATUS_PARTIAL,
    STATUS_UNPAID,
    aging_bucket,
    create_collection,
    create_receivable,
    outstanding,
    receivable_status,
)
from apps.core.models import Collection, Receivable
from tests.factories import FeeTypeFactory, PublicationCaseFactory


@pytest.mark.django_db
def test_finance_permissions_404_and_view_cannot_create(
    client,
    editor_none,
    editor_view,
    editor_manage,
    customer_a,
):
    case = PublicationCaseFactory(owner=customer_a)
    fee = FeeTypeFactory(name="Phí quản lý xuất bản")

    # Editor finance_access = NONE -> gọi URL tài chính trả 404
    client.force_login(editor_none)
    assert client.get(reverse("finance:overview")).status_code == 404
    assert client.get(reverse("finance:debt")).status_code == 404

    # Customer -> gọi URL tài chính trả 404
    client.force_login(customer_a)
    assert client.get(reverse("finance:overview")).status_code == 404

    # Editor VIEW -> xem được nhưng không tạo được khoản phải thu / đã thu
    client.force_login(editor_view)
    assert client.get(reverse("finance:overview")).status_code == 200
    assert client.get(reverse("finance:manage")).status_code == 404
    with pytest.raises(PermissionDenied):
        create_receivable(actor=editor_view, case=case, fee_type=fee, amount=Decimal("5000000"))

    # Editor MANAGE -> tạo thành công và không xóa được (cả từng bản ghi lẫn hàng loạt)
    rec = create_receivable(actor=editor_manage, case=case, fee_type=fee, amount=Decimal("5000000"))
    col = create_collection(
        actor=editor_manage,
        receivable=rec,
        paid_date=date(2026, 6, 1),
        amount=Decimal("2000000"),
    )
    with pytest.raises(PermissionDenied):
        rec.delete()
    with pytest.raises(PermissionDenied):
        Receivable.objects.filter(pk=rec.pk).delete()
    with pytest.raises(PermissionDenied):
        col.delete()
    with pytest.raises(PermissionDenied):
        Collection.objects.filter(pk=col.pk).delete()
    assert Receivable.objects.filter(pk=rec.pk).exists()
    assert Collection.objects.filter(pk=col.pk).exists()


@pytest.mark.django_db
def test_outstanding_status_aging_and_adjustments(editor_manage, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    fee = FeeTypeFactory(name="Phí biên tập")
    today = date(2026, 11, 25)

    # 1. Chưa thu, chưa đến hạn
    r_unpaid = create_receivable(
        actor=editor_manage,
        case=case,
        fee_type=fee,
        amount=Decimal("10000000"),
        due_date=today + timedelta(days=10),
    )
    assert outstanding(r_unpaid) == Decimal("10000000")
    assert receivable_status(r_unpaid, today) == STATUS_UNPAID
    assert aging_bucket(r_unpaid, today) == AGING_NOT_DUE

    # 2. Thu một phần
    create_collection(
        actor=editor_manage, receivable=r_unpaid, paid_date=today, amount=Decimal("4000000")
    )
    assert outstanding(r_unpaid) == Decimal("6000000")
    assert receivable_status(r_unpaid, today) == STATUS_PARTIAL

    # 3. Thu vượt mức không có ghi chú/xác nhận -> bị từ chối
    with pytest.raises(ValidationError):
        create_collection(
            actor=editor_manage, receivable=r_unpaid, paid_date=today, amount=Decimal("7000000")
        )

    # 4. Bút toán điều chỉnh giảm 2.000.000 và thu nốt 4.000.000 -> PAID
    create_receivable(
        actor=editor_manage,
        case=case,
        fee_type=fee,
        amount=Decimal("-2000000"),
        is_adjustment=True,
        adjusts=r_unpaid,
        note="Điều chỉnh giảm theo phụ lục hợp đồng",
    )
    assert outstanding(r_unpaid) == Decimal("4000000")
    create_collection(
        actor=editor_manage, receivable=r_unpaid, paid_date=today, amount=Decimal("4000000")
    )
    assert outstanding(r_unpaid) == Decimal("0")
    assert receivable_status(r_unpaid, today) == STATUS_PAID
    assert aging_bucket(r_unpaid, today) == AGING_NOT_DUE

    # 5. Các mốc quá hạn 15 / 45 / 75 / 120 ngày
    cases_aging = [
        (15, AGING_D1_30),
        (45, AGING_D31_60),
        (75, AGING_D61_90),
        (120, AGING_D90_PLUS),
    ]
    for days_past, expected_bucket in cases_aging:
        rec = create_receivable(
            actor=editor_manage,
            case=case,
            fee_type=fee,
            amount=Decimal("3000000"),
            due_date=today - timedelta(days=days_past),
        )
        assert receivable_status(rec, today) == STATUS_OVERDUE
        assert aging_bucket(rec, today) == expected_bucket
