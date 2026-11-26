"""Nghiệp vụ sổ theo dõi phí dịch vụ xuất bản: phải thu, đã thu, công nợ (mục 5.13, 5.14).

Lưu ý phạm vi:
- Chỉ theo dõi nhập tay các khoản phí dịch vụ xuất bản; không thay phần mềm kế toán.
- Tuyệt đối không xóa Receivable/Collection; sửa sai bằng bút toán điều chỉnh có ghi chú.
- Không có bất kỳ khoản phí nào về in ấn hoặc phát hành.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.audit import log_event
from apps.core.models import Collection, CollectionMethod, FeeType, PublicationCase, Receivable
from apps.core.permissions import can_manage_finance

STATUS_UNPAID = "UNPAID"
STATUS_PARTIAL = "PARTIAL"
STATUS_PAID = "PAID"
STATUS_OVERDUE = "OVERDUE"

RECEIVABLE_STATUS_LABELS = {
    STATUS_UNPAID: _("Chưa thu"),
    STATUS_PARTIAL: _("Thu một phần"),
    STATUS_PAID: _("Đã thu đủ"),
    STATUS_OVERDUE: _("Quá hạn"),
}

AGING_NOT_DUE = "NOT_DUE"
AGING_D1_30 = "D1_30"
AGING_D31_60 = "D31_60"
AGING_D61_90 = "D61_90"
AGING_D90_PLUS = "D90_PLUS"


def effective_receivable_amount(receivable: Receivable) -> Decimal:
    """Tổng số tiền phải thu sau khi cộng các bút toán điều chỉnh gắn với khoản này."""
    adj_total = receivable.adjustments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return Decimal(receivable.amount) + Decimal(adj_total)


def total_collected(receivable: Receivable) -> Decimal:
    """Tổng số tiền đã thu (đã bao gồm các bút toán đảo nếu có)."""
    total = receivable.collections.aggregate(total=Sum("amount"))["total"]
    return Decimal(total or 0)


def outstanding(receivable: Receivable) -> Decimal:
    """Số tiền còn phải thu: effective_amount(receivable) - tổng collections."""
    return effective_receivable_amount(receivable) - total_collected(receivable)


def receivable_status(receivable: Receivable, today: date | None = None) -> str:
    """Xác định trạng thái công nợ của khoản phải thu tại ngày today.

    Trả về một trong: UNPAID, PARTIAL, PAID, OVERDUE.
    """
    ref_date = today or timezone.localdate()
    rem = outstanding(receivable)
    if rem <= Decimal("0"):
        return STATUS_PAID
    if receivable.due_date is not None and ref_date > receivable.due_date:
        return STATUS_OVERDUE
    if total_collected(receivable) > Decimal("0"):
        return STATUS_PARTIAL
    return STATUS_UNPAID


def aging_bucket(receivable: Receivable, today: date | None = None) -> str:
    """Phân nhóm tuổi nợ quá hạn theo ngày due_date.

    Trả về: NOT_DUE, D1_30, D31_60, D61_90, D90_PLUS.
    """
    ref_date = today or timezone.localdate()
    if outstanding(receivable) <= Decimal("0") or receivable.due_date is None:
        return AGING_NOT_DUE
    overdue_days = (ref_date - receivable.due_date).days
    if overdue_days <= 0:
        return AGING_NOT_DUE
    if overdue_days <= 30:
        return AGING_D1_30
    if overdue_days <= 60:
        return AGING_D31_60
    if overdue_days <= 90:
        return AGING_D61_90
    return AGING_D90_PLUS


def create_receivable(
    *,
    actor,
    case: PublicationCase,
    fee_type: FeeType,
    amount: Decimal | int,
    payer_name: str = "",
    description: str = "",
    contract_number: str = "",
    invoice_number: str = "",
    invoice_date: date | None = None,
    due_date: date | None = None,
    is_adjustment: bool = False,
    adjusts: Receivable | None = None,
    note: str = "",
    request=None,
) -> Receivable:
    """Tạo khoản phải thu hoặc bút toán điều chỉnh và ghi AuditEvent."""
    if not can_manage_finance(actor):
        raise PermissionDenied(_("Bạn không có quyền quản lý tài chính."))

    decimal_amount = Decimal(amount)
    if adjusts is not None and adjusts.case_id != case.pk:
        raise ValidationError(_("Khoản bị điều chỉnh phải thuộc cùng hồ sơ."))

    with transaction.atomic():
        rec = Receivable.objects.create(
            case=case,
            fee_type=fee_type,
            description=description,
            amount=decimal_amount,
            payer_name=payer_name or case.partner_name or case.owner.full_name or case.owner.email,
            contract_number=contract_number,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            due_date=due_date,
            is_adjustment=is_adjustment,
            adjusts=adjusts,
            note=note,
            created_by=actor,
        )
        action = "finance.receivable_adjust" if is_adjustment else "finance.receivable_create"
        log_event(
            actor=actor,
            action=action,
            object_type="Receivable",
            object_id=str(rec.pk),
            case=case,
            data={
                "before": None,
                "after": {
                    "fee_type": fee_type.name,
                    "amount": str(rec.amount),
                    "payer_name": rec.payer_name,
                    "due_date": rec.due_date.isoformat() if rec.due_date else None,
                    "is_adjustment": rec.is_adjustment,
                    "adjusts_id": rec.adjusts_id,
                    "note": rec.note,
                },
            },
            request=request,
        )
    return rec


def create_collection(
    *,
    actor,
    receivable: Receivable,
    paid_date: date,
    amount: Decimal | int,
    method: str = CollectionMethod.TRANSFER,
    reference: str = "",
    is_adjustment: bool = False,
    note: str = "",
    confirm_overpayment: bool = False,
    request=None,
) -> Collection:
    """Ghi nhận khoản đã thu hoặc bút toán đảo, kiểm tra vượt mức phải thu và ghi AuditEvent."""
    if not can_manage_finance(actor):
        raise PermissionDenied(_("Bạn không có quyền quản lý tài chính."))

    decimal_amount = Decimal(amount)
    before_collected = total_collected(receivable)
    after_collected = before_collected + decimal_amount
    eff_amount = effective_receivable_amount(receivable)

    if not is_adjustment and after_collected > eff_amount:
        if not (confirm_overpayment and (note or "").strip()):
            raise ValidationError(
                _(
                    "Tổng số tiền đã thu (%(after)s VNĐ) vượt quá khoản phải thu (%(target)s VNĐ). "
                    "Bắt buộc có ghi chú và xác nhận của người dùng để ghi nhận thu vượt."
                )
                % {"after": f"{after_collected:,}", "target": f"{eff_amount:,}"}
            )

    with transaction.atomic():
        col = Collection.objects.create(
            receivable=receivable,
            paid_date=paid_date,
            amount=decimal_amount,
            method=method,
            reference=reference,
            is_adjustment=is_adjustment,
            note=note,
            created_by=actor,
        )
        action = "finance.collection_adjust" if is_adjustment else "finance.collection_create"
        log_event(
            actor=actor,
            action=action,
            object_type="Collection",
            object_id=str(col.pk),
            case=receivable.case,
            data={
                "before": {"total_collected": str(before_collected)},
                "after": {
                    "receivable_id": receivable.pk,
                    "amount": str(col.amount),
                    "paid_date": col.paid_date.isoformat(),
                    "method": col.method,
                    "is_adjustment": col.is_adjustment,
                    "total_collected": str(after_collected),
                    "note": col.note,
                },
            },
            request=request,
        )
    return col
