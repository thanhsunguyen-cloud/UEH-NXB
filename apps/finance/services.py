"""Nghiệp vụ hiển thị của M8: tổng hợp số liệu tài chính, công nợ và xuất CSV.

Mọi số dư từng khoản đều tính bằng hàm của M0 (`apps.core.finance`). Phần tổng hợp
theo kỳ cộng thẳng các bản ghi `Receivable`/`Collection` (bút toán điều chỉnh là các
bản ghi có số tiền âm/dương), nên tổng luôn khớp với `effective_receivable_amount`
và `total_collected` của M0.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import DateField, Q, QuerySet, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.finance import (
    AGING_D1_30,
    AGING_D31_60,
    AGING_D61_90,
    AGING_D90_PLUS,
    AGING_NOT_DUE,
    RECEIVABLE_STATUS_LABELS,
    aging_bucket,
    effective_receivable_amount,
    outstanding,
    receivable_status,
    total_collected,
)
from apps.core.models import Collection, PublicationCase, Receivable

ZERO = Decimal("0")

AGING_LABELS = {
    AGING_NOT_DUE: _("Chưa đến hạn"),
    AGING_D1_30: _("1–30 ngày"),
    AGING_D31_60: _("31–60 ngày"),
    AGING_D61_90: _("61–90 ngày"),
    AGING_D90_PLUS: _("Trên 90 ngày"),
}
AGING_ORDER = list(AGING_LABELS)

# Tiền tố ghi chú của bút toán đảo, dùng để biết khoản thu nào đã được đảo.
REVERSAL_TAG = "[Đảo khoản thu #{pk}]"


def format_amount_plain(value) -> str:
    """Số tiền dạng số nguyên thuần cho CSV (Excel tự nhận là số)."""
    return str(int(Decimal(value or 0)))


# ---------------------------------------------------------------------------
# Tổng quan theo kỳ
# ---------------------------------------------------------------------------


def receivables_with_date() -> QuerySet[Receivable]:
    """Receivable kèm `record_date` = ngày chứng từ, nếu trống thì ngày tạo (giờ VN)."""
    return Receivable.objects.annotate(
        record_date=Coalesce(
            "invoice_date",
            TruncDate("created_at", tzinfo=timezone.get_current_timezone()),
            output_field=DateField(),
        )
    )


def _apply_dimension_filters(rec_qs, col_qs, fee_type=None, publication_mode=""):
    if fee_type is not None:
        rec_qs = rec_qs.filter(fee_type=fee_type)
        col_qs = col_qs.filter(receivable__fee_type=fee_type)
    if publication_mode:
        rec_qs = rec_qs.filter(case__publication_mode=publication_mode)
        col_qs = col_qs.filter(receivable__case__publication_mode=publication_mode)
    return rec_qs, col_qs


def _sum(qs) -> Decimal:
    return qs.aggregate(total=Sum("amount"))["total"] or ZERO


def _month_starts(date_from: date, date_to: date) -> list[date]:
    months = []
    current = date(date_from.year, date_from.month, 1)
    while current <= date_to:
        months.append(current)
        current = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
    return months


@dataclass
class OverviewData:
    date_from: date
    date_to: date
    total_receivable: Decimal = ZERO
    total_collected: Decimal = ZERO
    outstanding_at_end: Decimal = ZERO
    months: list[dict] = field(default_factory=list)
    fee_types: list[dict] = field(default_factory=list)


def build_overview(
    date_from: date, date_to: date, fee_type=None, publication_mode: str = ""
) -> OverviewData:
    """Số liệu trang tổng quan cho kỳ [date_from, date_to]."""
    rec_all, col_all = _apply_dimension_filters(
        receivables_with_date(), Collection.objects.all(), fee_type, publication_mode
    )
    rec_period = rec_all.filter(record_date__gte=date_from, record_date__lte=date_to)
    col_period = col_all.filter(paid_date__gte=date_from, paid_date__lte=date_to)

    data = OverviewData(date_from=date_from, date_to=date_to)
    data.total_receivable = _sum(rec_period)
    data.total_collected = _sum(col_period)
    data.outstanding_at_end = _sum(rec_all.filter(record_date__lte=date_to)) - _sum(
        col_all.filter(paid_date__lte=date_to)
    )

    by_month: dict[date, dict] = {
        m: {"month": m, "receivable": ZERO, "collected": ZERO}
        for m in _month_starts(date_from, date_to)
    }
    for record_date, amount in rec_period.values_list("record_date", "amount"):
        by_month[date(record_date.year, record_date.month, 1)]["receivable"] += amount
    for paid_date, amount in col_period.values_list("paid_date", "amount"):
        by_month[date(paid_date.year, paid_date.month, 1)]["collected"] += amount
    data.months = list(by_month.values())

    by_fee: dict[int, dict] = {}
    for fee_id, fee_name, amount in rec_period.values_list(
        "fee_type_id", "fee_type__name", "amount"
    ):
        row = by_fee.setdefault(fee_id, {"name": fee_name, "receivable": ZERO, "collected": ZERO})
        row["receivable"] += amount
    for fee_id, fee_name, amount in col_period.values_list(
        "receivable__fee_type_id", "receivable__fee_type__name", "amount"
    ):
        row = by_fee.setdefault(fee_id, {"name": fee_name, "receivable": ZERO, "collected": ZERO})
        row["collected"] += amount
    data.fee_types = sorted(by_fee.values(), key=lambda r: r["name"])
    return data


def overview_csv_rows(data: OverviewData) -> list[list[str]]:
    rows = [["Nhóm", "Mục", "Phải thu (VNĐ)", "Đã thu (VNĐ)"]]
    for m in data.months:
        rows.append(
            [
                "Tháng",
                m["month"].strftime("%m/%Y"),
                format_amount_plain(m["receivable"]),
                format_amount_plain(m["collected"]),
            ]
        )
    for f in data.fee_types:
        rows.append(
            [
                "Loại phí",
                f["name"],
                format_amount_plain(f["receivable"]),
                format_amount_plain(f["collected"]),
            ]
        )
    rows.append(
        [
            "Tổng kỳ",
            f"{data.date_from:%d/%m/%Y} - {data.date_to:%d/%m/%Y}",
            format_amount_plain(data.total_receivable),
            format_amount_plain(data.total_collected),
        ]
    )
    rows.append(
        [
            "Còn nợ cuối kỳ",
            f"{data.date_to:%d/%m/%Y}",
            format_amount_plain(data.outstanding_at_end),
            "",
        ]
    )
    return rows


# ---------------------------------------------------------------------------
# Công nợ
# ---------------------------------------------------------------------------


@dataclass
class ReceivableLine:
    """Một khoản phải thu gốc kèm số liệu tính bằng hàm M0."""

    receivable: Receivable
    effective: Decimal
    collected: Decimal
    outstanding: Decimal
    status: str
    bucket: str

    @property
    def status_label(self):
        return RECEIVABLE_STATUS_LABELS.get(self.status, self.status)

    @property
    def bucket_label(self):
        return AGING_LABELS.get(self.bucket, self.bucket)


def make_line(rec: Receivable, today: date) -> ReceivableLine:
    return ReceivableLine(
        receivable=rec,
        effective=effective_receivable_amount(rec),
        collected=total_collected(rec),
        outstanding=outstanding(rec),
        status=receivable_status(rec, today),
        bucket=aging_bucket(rec, today),
    )


def base_receivables() -> QuerySet[Receivable]:
    """Khoản phải thu gốc (không phải bút toán điều chỉnh của khoản khác)."""
    return Receivable.objects.filter(adjusts__isnull=True).select_related(
        "case", "fee_type", "case__owner"
    )


def search_cases_q(term: str) -> Q:
    """Điều kiện tìm hồ sơ theo mã hiển thị (ISBN, mã NXB, mã tạm) hoặc tên sách."""
    term = term.strip()
    compact = term.replace("-", "").replace(" ", "")
    return (
        Q(isbn__icontains=compact)
        | Q(nxb_code__icontains=term)
        | Q(temp_code__icontains=term)
        | Q(title__icontains=term)
    )


def debt_lines(*, today: date, fee_type=None, payer: str = "", q: str = "") -> list[ReceivableLine]:
    """Danh sách khoản còn nợ (outstanding > 0), sắp theo hạn thanh toán."""
    qs = base_receivables()
    if fee_type is not None:
        qs = qs.filter(fee_type=fee_type)
    if payer.strip():
        qs = qs.filter(payer_name__icontains=payer.strip())
    if q.strip():
        case_ids = PublicationCase.objects.filter(search_cases_q(q)).values("pk")
        qs = qs.filter(case_id__in=case_ids)
    lines = [make_line(rec, today) for rec in qs]
    lines = [line for line in lines if line.outstanding > ZERO]
    lines.sort(
        key=lambda line: (
            line.receivable.due_date is None,
            line.receivable.due_date or date.max,
            line.receivable.pk,
        )
    )
    return lines


def aging_summary(lines: list[ReceivableLine]) -> list[dict]:
    summary = {
        key: {"key": key, "label": AGING_LABELS[key], "count": 0, "amount": ZERO}
        for key in AGING_ORDER
    }
    for line in lines:
        summary[line.bucket]["count"] += 1
        summary[line.bucket]["amount"] += line.outstanding
    return list(summary.values())


DEBT_CSV_HEADER = [
    "Mã hồ sơ",
    "Tên sách",
    "Đơn vị / Tác giả phải trả",
    "Loại phí",
    "Phải thu (VNĐ)",
    "Đã thu (VNĐ)",
    "Còn nợ (VNĐ)",
    "Hạn thanh toán",
    "Nhóm tuổi nợ",
]


def debt_csv_rows(lines: list[ReceivableLine]) -> list[list[str]]:
    rows = [list(DEBT_CSV_HEADER)]
    for line in lines:
        rec = line.receivable
        rows.append(
            [
                rec.case.display_code,
                rec.case.title,
                rec.payer_name,
                rec.fee_type.name,
                format_amount_plain(line.effective),
                format_amount_plain(line.collected),
                format_amount_plain(line.outstanding),
                rec.due_date.strftime("%d/%m/%Y") if rec.due_date else "",
                str(line.bucket_label),
            ]
        )
    return rows


def render_csv(rows: list[list[str]]) -> bytes:
    """CSV UTF-8 có BOM để Excel mở đúng tiếng Việt."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    return ("﻿" + buffer.getvalue()).encode("utf-8")


# ---------------------------------------------------------------------------
# Tài chính một hồ sơ
# ---------------------------------------------------------------------------


def case_finance(case: PublicationCase, today: date) -> dict:
    """Khoản phải thu của hồ sơ, mỗi khoản kèm bút toán điều chỉnh và các lần thu."""
    reversed_ids = reversed_collection_ids(case)
    items = []
    for rec in base_receivables().filter(case=case).order_by("created_at", "id"):
        line = make_line(rec, today)
        collections = list(rec.collections.select_related("created_by").order_by("paid_date", "id"))
        for col in collections:
            col.already_reversed = col.pk in reversed_ids
        items.append(
            {
                "line": line,
                "adjustments": list(
                    rec.adjustments.select_related("created_by").order_by("created_at", "id")
                ),
                "collections": collections,
            }
        )
    totals = {
        "receivable": sum((i["line"].effective for i in items), ZERO),
        "collected": sum((i["line"].collected for i in items), ZERO),
        "outstanding": sum((i["line"].outstanding for i in items), ZERO),
    }
    return {"items": items, "totals": totals}


def reversed_collection_ids(case: PublicationCase) -> set[int]:
    """Mã các khoản thu đã có bút toán đảo (nhận diện qua tiền tố ghi chú)."""
    ids = set()
    notes = Collection.objects.filter(
        receivable__case=case, is_adjustment=True, note__startswith="[Đảo khoản thu #"
    ).values_list("note", flat=True)
    for note in notes:
        head = note.split("]", 1)[0].removeprefix("[Đảo khoản thu #")
        if head.isdigit():
            ids.add(int(head))
    return ids


def default_payer_name(case: PublicationCase) -> str:
    return case.partner_name or case.owner.full_name or case.owner.email
