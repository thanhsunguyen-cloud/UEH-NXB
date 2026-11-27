"""Truy vấn tra cứu, thống kê danh mục xuất bản và xuất Excel của M5.

Không đổi trạng thái hồ sơ, không có số tiền.
"""

from __future__ import annotations

import re
import tempfile
from collections import OrderedDict
from datetime import date

from django.db.models import Count, F, Prefetch, Q, QuerySet
from django.db.models.functions import Coalesce, TruncMonth, TruncQuarter, TruncYear
from django.utils.translation import gettext as _

from apps.core.models import (
    CaseStatus,
    Contributor,
    ContributorRole,
    PublicationCase,
    PublicationMode,
)

from .models import ImportBatch

SOURCE_PORTAL = "PORTAL"
SOURCE_EXCEL = "EXCEL"

GROUP_MONTH = "month"
GROUP_QUARTER = "quarter"
GROUP_YEAR = "year"

TRUNC_FUNCS = {GROUP_MONTH: TruncMonth, GROUP_QUARTER: TruncQuarter, GROUP_YEAR: TruncYear}

CATALOG_COLUMNS = [
    "STT",
    "Tên xuất bản phẩm",
    "Tác giả",
    "Thể loại",
    "Lĩnh vực",
    "Hình thức",
    "Đơn vị liên kết",
    "ISBN",
    "Số XNĐK",
    "Ngày XNĐK",
    "Số QĐXB",
    "Ngày QĐXB",
    "Ngày nộp lưu chiểu",
    "Số trang",
    "Khổ",
]


def imported_case_ids() -> set[str]:
    """Tập UUID (chuỗi) của mọi hồ sơ tạo từ các lô nhập Excel."""
    ids: set[str] = set()
    for case_ids in ImportBatch.objects.values_list("case_ids", flat=True):
        ids.update(str(x) for x in case_ids or [])
    return ids


def with_stat_date(qs: QuerySet[PublicationCase]) -> QuerySet[PublicationCase]:
    """Gắn ngày tính thống kê: decision_date, nếu trống thì registration_date."""
    return qs.annotate(stat_date=Coalesce("decision_date", "registration_date"))


def with_contributors(qs: QuerySet[PublicationCase]) -> QuerySet[PublicationCase]:
    return qs.select_related("category", "field").prefetch_related(
        Prefetch("contributors", queryset=Contributor.objects.order_by("order", "id"))
    )


def authors_text(case: PublicationCase) -> str:
    """Nối tên tác giả theo thứ tự; chủ biên ghi kèm "(Chủ biên)"."""
    parts = []
    for c in case.contributors.all():
        if c.role == ContributorRole.CHIEF_EDITOR:
            parts.append(f"{c.full_name} ({_('Chủ biên')})")
        else:
            parts.append(c.full_name)
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# 2.1 Tra cứu
# ---------------------------------------------------------------------------


def search_cases(cases: QuerySet[PublicationCase], data: dict) -> QuerySet[PublicationCase]:
    """Lọc hồ sơ theo SearchForm.cleaned_data. Mặc định không hiện hồ sơ Nháp."""
    qs = with_stat_date(cases)

    status = data.get("status") or ""
    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.exclude(status=CaseStatus.DRAFT)

    if data.get("year"):
        qs = qs.filter(stat_date__year=data["year"])
    if data.get("category"):
        qs = qs.filter(category=data["category"])
    if data.get("field"):
        qs = qs.filter(field=data["field"])
    if data.get("mode"):
        qs = qs.filter(publication_mode=data["mode"])

    source = data.get("source") or ""
    if source:
        ids = imported_case_ids()
        qs = qs.filter(pk__in=ids) if source == SOURCE_EXCEL else qs.exclude(pk__in=ids)

    q = (data.get("q") or "").strip()
    if q:
        compact = re.sub(r"[\s-]+", "", q)
        cond = (
            Q(nxb_code__icontains=q)
            | Q(temp_code__icontains=q)
            | Q(registration_number__icontains=q)
            | Q(decision_number__icontains=q)
            | Q(title__icontains=q)
            | Q(contributors__full_name__icontains=q)
        )
        if compact:
            cond |= Q(isbn__icontains=compact)
        qs = qs.filter(pk__in=cases.filter(cond).values("pk"))

    return with_contributors(qs).order_by(F("stat_date").desc(nulls_last=True), "-created_at")


# ---------------------------------------------------------------------------
# 2.2 Thống kê danh mục xuất bản
# ---------------------------------------------------------------------------


def default_period(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    return date(today.year, 1, 1), date(today.year, 12, 31)


def catalog_queryset(cases: QuerySet[PublicationCase], data: dict) -> QuerySet[PublicationCase]:
    """Hồ sơ có ngày tính thống kê trong khoảng [date_from, date_to] và đúng bộ lọc."""
    date_from, date_to = default_period()
    date_from = data.get("date_from") or date_from
    date_to = data.get("date_to") or date_to
    qs = with_stat_date(cases).filter(
        stat_date__isnull=False, stat_date__gte=date_from, stat_date__lte=date_to
    )
    if data.get("category"):
        qs = qs.filter(category=data["category"])
    if data.get("field"):
        qs = qs.filter(field=data["field"])
    if data.get("mode"):
        qs = qs.filter(publication_mode=data["mode"])
    return qs


def _period_start(d: date, group: str) -> date:
    if group == GROUP_YEAR:
        return date(d.year, 1, 1)
    if group == GROUP_QUARTER:
        return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)
    return date(d.year, d.month, 1)


def _next_period(d: date, group: str) -> date:
    step = {GROUP_YEAR: 12, GROUP_QUARTER: 3}.get(group, 1)
    month = d.month - 1 + step
    return date(d.year + month // 12, month % 12 + 1, 1)


def period_label(d: date, group: str) -> str:
    if group == GROUP_YEAR:
        return _("Năm %(y)s") % {"y": d.year}
    if group == GROUP_QUARTER:
        return _("Quý %(q)s/%(y)s") % {"q": (d.month - 1) // 3 + 1, "y": d.year}
    return _("Tháng %(m)02d/%(y)s") % {"m": d.month, "y": d.year}


def _normalize_date(value) -> date:
    return value.date() if hasattr(value, "date") and callable(value.date) else value


def count_by_period(qs, group: str, date_from: date, date_to: date) -> list[dict]:
    """Số đầu sách theo kỳ, liệt kê đủ mọi kỳ trong khoảng (kỳ trống = 0)."""
    trunc = TRUNC_FUNCS.get(group, TruncMonth)
    rows = (
        qs.annotate(period=trunc("stat_date"))
        .values("period")
        .annotate(n=Count("pk", distinct=True))
        .order_by("period")
    )
    counts = {_normalize_date(r["period"]): r["n"] for r in rows}
    result = []
    current = _period_start(date_from, group)
    end = _period_start(date_to, group)
    # Giới hạn an toàn: tối đa 600 kỳ (50 năm theo tháng)
    while current <= end and len(result) < 600:
        result.append(
            {"start": current, "label": period_label(current, group), "n": counts.get(current, 0)}
        )
        current = _next_period(current, group)
    peak = max((r["n"] for r in result), default=0)
    for r in result:
        r["pct"] = round(r["n"] * 100 / peak) if peak else 0
    return result


def _count_by(qs, field_name: str, empty_label: str) -> list[dict]:
    rows = qs.values(field_name).annotate(n=Count("pk", distinct=True)).order_by("-n", field_name)
    return [{"label": r[field_name] or empty_label, "n": r["n"]} for r in rows]


def catalog_summary(qs, group: str, date_from: date, date_to: date) -> dict:
    mode_labels = dict(PublicationMode.choices)
    by_mode = [
        {"label": str(mode_labels.get(r["label"], r["label"])), "n": r["n"]}
        for r in _count_by(qs, "publication_mode", "")
    ]
    return {
        "total": qs.values("pk").distinct().count(),
        "by_period": count_by_period(qs, group, date_from, date_to),
        "by_category": _count_by(qs, "category__name", _("(Chưa phân loại)")),
        "by_field": _count_by(qs, "field__name", _("(Chưa phân loại)")),
        "by_mode": by_mode,
    }


def catalog_rows(qs) -> QuerySet[PublicationCase]:
    return with_contributors(qs).order_by("stat_date", "title", "pk")


# ---------------------------------------------------------------------------
# Xuất Excel
# ---------------------------------------------------------------------------


def build_catalog_workbook(qs, summary: dict, filters: dict):
    """Tạo file .xlsx (sheet "Tổng hợp" và "Danh mục"), trả về file tạm đã tua về đầu."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font

    wb = Workbook(write_only=True)
    bold = Font(bold=True)

    def header(ws, values):
        cells = []
        for v in values:
            cell = WriteOnlyCell(ws, value=v)
            cell.font = bold
            cells.append(cell)
        ws.append(cells)

    ws = wb.create_sheet(_("Tổng hợp"))
    header(ws, [_("THỐNG KÊ DANH MỤC XUẤT BẢN")])
    for label, value in filters.items():
        ws.append([label, value])
    ws.append([_("Tổng số đầu sách"), summary["total"]])
    for title, key in (
        (_("Theo kỳ"), "by_period"),
        (_("Theo thể loại"), "by_category"),
        (_("Theo lĩnh vực"), "by_field"),
        (_("Theo hình thức"), "by_mode"),
    ):
        ws.append([])
        header(ws, [title, _("Số đầu sách")])
        for row in summary[key]:
            ws.append([row["label"], row["n"]])

    ws = wb.create_sheet(_("Danh mục"))
    header(ws, CATALOG_COLUMNS)

    def date_cell(value):
        cell = WriteOnlyCell(ws, value=value)
        if value:
            cell.number_format = "DD/MM/YYYY"
        return cell

    mode_labels = dict(PublicationMode.choices)
    for idx, case in enumerate(qs.iterator(chunk_size=500), start=1):
        ws.append(
            [
                idx,
                case.title,
                authors_text(case),
                case.category.name if case.category else "",
                case.field.name if case.field else "",
                str(mode_labels.get(case.publication_mode, case.publication_mode)),
                case.partner_name,
                case.isbn or "",
                case.registration_number,
                date_cell(case.registration_date),
                case.decision_number,
                date_cell(case.decision_date),
                date_cell(case.deposit_date),
                case.page_count,
                case.book_size,
            ]
        )

    tmp = tempfile.SpooledTemporaryFile(max_size=5 * 1024 * 1024)
    wb.save(tmp)
    tmp.seek(0)
    return tmp


def summary_filters_text(data: dict, date_from: date, date_to: date, group: str) -> dict:
    group_labels = {GROUP_MONTH: _("Tháng"), GROUP_QUARTER: _("Quý"), GROUP_YEAR: _("Năm")}
    out: OrderedDict[str, str] = OrderedDict()
    out[_("Từ ngày")] = date_from.strftime("%d/%m/%Y")
    out[_("Đến ngày")] = date_to.strftime("%d/%m/%Y")
    out[_("Nhóm theo")] = str(group_labels.get(group, group))
    if data.get("category"):
        out[_("Thể loại")] = str(data["category"])
    if data.get("field"):
        out[_("Lĩnh vực")] = str(data["field"])
    if data.get("mode"):
        out[_("Hình thức")] = str(dict(PublicationMode.choices)[data["mode"]])
    return out
