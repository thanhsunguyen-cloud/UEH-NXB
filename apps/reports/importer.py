"""Nhập danh mục xuất bản các năm trước từ file Excel (.xlsx) theo mẫu chuẩn (M5 mục 2.3).

Hai bước:
1. ``parse_workbook`` + ``validate_rows``: chỉ đọc, KHÔNG ghi database.
2. ``import_rows``: nhập các dòng hợp lệ trong một ``transaction.atomic()``.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from apps.accounts.models import User, UserRole
from apps.core.audit import log_event
from apps.core.codes import normalize_isbn
from apps.core.models import (
    CaseNote,
    CaseStatus,
    Category,
    Contributor,
    ContributorRole,
    Field,
    NoteVisibility,
    PublicationCase,
    PublicationMode,
    StatusHistory,
)

from .models import ImportBatch

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000

SYSTEM_OWNER_EMAIL = "du-lieu-cu@portal.invalid"
SYSTEM_OWNER_NAME = "Dữ liệu nhập từ Excel"

# (khóa nội bộ, tiêu đề cột trong file mẫu, bắt buộc)
COLUMNS: list[tuple[str, str, bool]] = [
    ("title", "Tên xuất bản phẩm", True),
    ("authors", "Tác giả", True),
    ("category", "Thể loại", False),
    ("field", "Lĩnh vực", False),
    ("language", "Ngôn ngữ", False),
    ("mode", "Hình thức", False),
    ("partner_name", "Đơn vị liên kết", False),
    ("isbn", "ISBN", False),
    ("registration_number", "Số XNĐK", False),
    ("registration_date", "Ngày XNĐK", False),
    ("decision_number", "Số QĐXB", False),
    ("decision_date", "Ngày QĐXB", True),
    ("deposit_date", "Ngày nộp lưu chiểu", False),
    ("page_count", "Số trang", False),
    ("book_size", "Khổ", False),
    ("edition_number", "Lần xuất bản", False),
    ("note", "Ghi chú", False),
]

DATE_KEYS = ("registration_date", "decision_date", "deposit_date")
MAX_LENGTHS = {
    "title": 500,
    "language": 50,
    "partner_name": 255,
    "registration_number": 100,
    "decision_number": 100,
    "book_size": 50,
}
CHIEF_EDITOR_MARK = re.compile(r"\(\s*chủ\s*biên\s*\)", re.IGNORECASE)
MODE_VALUES = {
    "tự xuất bản": PublicationMode.SELF,
    "liên kết": PublicationMode.LINKED,
}


class ImportFileError(Exception):
    """Lỗi cả file (không đọc được, thiếu cột bắt buộc, quá nhiều dòng...)."""


def header_titles() -> list[str]:
    return [f"{title}*" if required else title for _key, title, required in COLUMNS]


def _norm_header(value) -> str:
    text = str(value or "").replace("*", "")
    return re.sub(r"\s+", " ", text).strip().lower()


# ---------------------------------------------------------------------------
# File mẫu
# ---------------------------------------------------------------------------


def build_template_workbook() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = _("Danh mục")
    ws.append(header_titles())
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for idx, width in enumerate(
        [40, 35, 18, 18, 14, 16, 25, 18, 16, 14, 16, 14, 18, 10, 10, 12, 30]
    ):
        ws.column_dimensions[ws.cell(row=1, column=idx + 1).column_letter].width = width

    guide = wb.create_sheet(_("Hướng dẫn"))
    for line in (
        _("Dấu * là cột bắt buộc. Nhập dữ liệu từ dòng 2 của sheet đầu tiên."),
        _("Tác giả: nhiều người cách nhau dấu ;  Chủ biên ghi “(Chủ biên)” sau tên."),
        _("Ngày: kiểu ngày của Excel hoặc chuỗi dd/mm/yyyy."),
        _("Hình thức: Tự xuất bản hoặc Liên kết (để trống = Tự xuất bản)."),
        _("Thể loại, Lĩnh vực: ghi đúng tên trong danh mục của Portal."),
        _("Chỉ nhận file .xlsx – file .xls cũ hãy Lưu thành .xlsx trước khi nhập."),
        _("Tối đa 5.000 dòng, dung lượng tối đa 10 MB."),
    ):
        guide.append([line])
    guide.column_dimensions["A"].width = 90

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Bước 1: đọc file
# ---------------------------------------------------------------------------


def _cell_to_text(value) -> str:
    """Chuyển giá trị ô về chuỗi; ngày -> dd/mm/yyyy, số nguyên không có phần .0."""
    if value is None:
        return ""
    if isinstance(value, datetime | date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_workbook(uploaded_file) -> list[dict]:
    """Đọc sheet đầu tiên, trả về danh sách dòng ``{"row": số dòng, "values": {khóa: chuỗi}}``.

    Chỉ đọc giá trị ô (``data_only=True``), bỏ dòng trống. Lỗi cả file -> ImportFileError.
    """
    from openpyxl import load_workbook

    name = getattr(uploaded_file, "name", "") or ""
    if not name.lower().endswith(".xlsx"):
        raise ImportFileError(_("Chỉ nhận file .xlsx. Hãy Lưu thành .xlsx trước khi nhập."))
    if getattr(uploaded_file, "size", 0) > MAX_FILE_BYTES:
        raise ImportFileError(_("File vượt quá 10 MB."))
    try:
        wb = load_workbook(uploaded_file, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - mọi lỗi đọc file đều báo chung
        raise ImportFileError(
            _("Không đọc được file Excel. Hãy Lưu thành .xlsx trước khi nhập.")
        ) from exc

    try:
        ws = wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        if header is None:
            raise ImportFileError(_("File không có dòng tiêu đề."))
        positions: dict[str, int] = {}
        wanted = {_norm_header(title): key for key, title, _req in COLUMNS}
        for idx, value in enumerate(header):
            key = wanted.get(_norm_header(value))
            if key and key not in positions:
                positions[key] = idx
        missing = [title for key, title, req in COLUMNS if req and key not in positions]
        if missing:
            raise ImportFileError(_("Thiếu cột bắt buộc: %(cols)s.") % {"cols": ", ".join(missing)})

        rows: list[dict] = []
        for row_number, raw in enumerate(rows_iter, start=2):
            values = {
                key: _cell_to_text(raw[idx]) if idx < len(raw) else ""
                for key, idx in positions.items()
            }
            if not any(values.values()):
                continue
            rows.append({"row": row_number, "values": values})
            if len(rows) > MAX_ROWS:
                raise ImportFileError(
                    _("File có hơn %(n)s dòng dữ liệu. Hãy tách thành nhiều file.")
                    % {"n": f"{MAX_ROWS:,}".replace(",", ".")}
                )
    finally:
        wb.close()
    return rows


# ---------------------------------------------------------------------------
# Kiểm tra từng dòng
# ---------------------------------------------------------------------------


@dataclass
class RowResult:
    row: int
    values: dict
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cleaned: dict = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def parse_date(text: str) -> date:
    text = (text or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(text)


def parse_authors(text: str) -> list[tuple[str, str]]:
    """Tách cột Tác giả thành [(họ tên, vai trò)], giữ đúng thứ tự."""
    result = []
    for part in (text or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if CHIEF_EDITOR_MARK.search(part):
            name = CHIEF_EDITOR_MARK.sub("", part).strip()
            role = ContributorRole.CHIEF_EDITOR
        else:
            name, role = part, ContributorRole.AUTHOR
        if name:
            result.append((name, role))
    return result


def _label(key: str) -> str:
    return next(title for k, title, _req in COLUMNS if k == key)


def validate_rows(rows: list[dict]) -> list[RowResult]:
    """Kiểm tra từng dòng, KHÔNG ghi database. Trả về kết quả kèm dữ liệu đã chuẩn hóa."""
    categories = {c.name.strip().lower(): c.pk for c in Category.objects.all()}
    fields = {f.name.strip().lower(): f.pk for f in Field.objects.all()}

    isbns_in_file: dict[str, int] = {}
    pending: list[tuple[RowResult, str]] = []
    results: list[RowResult] = []

    for item in rows:
        values = item["values"]
        res = RowResult(row=item["row"], values=values)
        v = {key: (values.get(key) or "").strip() for key, _t, _r in COLUMNS}
        c: dict = {}

        for key, title, required in COLUMNS:
            if required and not v[key]:
                res.errors.append(_("Thiếu “%(col)s”.") % {"col": title})
        for key, limit in MAX_LENGTHS.items():
            if len(v[key]) > limit:
                res.errors.append(
                    _("“%(col)s” dài quá %(n)s ký tự.") % {"col": _label(key), "n": limit}
                )

        c["title"] = v["title"]
        authors = parse_authors(v["authors"])
        if v["authors"] and not authors:
            res.errors.append(_("Cột “Tác giả” không có tên hợp lệ."))
        if any(len(name) > 200 for name, _role in authors):
            res.errors.append(_("Tên tác giả dài quá 200 ký tự."))
        c["authors"] = authors

        for key in DATE_KEYS:
            c[key] = None
            if v[key]:
                try:
                    c[key] = parse_date(v[key])
                except ValueError:
                    res.errors.append(
                        _("“%(col)s” sai định dạng ngày (cần dd/mm/yyyy): %(val)s")
                        % {"col": _label(key), "val": v[key]}
                    )

        mode_text = v["mode"].lower()
        c["publication_mode"] = PublicationMode.SELF
        if mode_text:
            if mode_text in MODE_VALUES:
                c["publication_mode"] = MODE_VALUES[mode_text]
            else:
                res.errors.append(
                    _("“Hình thức” chỉ nhận “Tự xuất bản” hoặc “Liên kết”: %(val)s")
                    % {"val": v["mode"]}
                )
        c["partner_name"] = v["partner_name"]
        if c["publication_mode"] == PublicationMode.LINKED and not v["partner_name"]:
            res.errors.append(_("Hình thức Liên kết bắt buộc có “Đơn vị liên kết”."))

        c["isbn"] = None
        if v["isbn"]:
            try:
                c["isbn"] = normalize_isbn(v["isbn"])
            except ValidationError as exc:
                res.errors.append(
                    _("ISBN sai (%(val)s): %(msg)s")
                    % {"val": v["isbn"], "msg": " ".join(exc.messages)}
                )
            else:
                if c["isbn"] in isbns_in_file:
                    res.errors.append(
                        _("ISBN %(isbn)s trùng với dòng %(row)s trong file.")
                        % {"isbn": c["isbn"], "row": isbns_in_file[c["isbn"]]}
                    )
                else:
                    isbns_in_file[c["isbn"]] = res.row
                    pending.append((res, c["isbn"]))

        for key in ("page_count", "edition_number"):
            c[key] = None
            if v[key]:
                if re.fullmatch(r"\d{1,6}", v[key]) and int(v[key]) > 0:
                    c[key] = int(v[key])
                else:
                    res.errors.append(
                        _("“%(col)s” phải là số nguyên dương: %(val)s")
                        % {"col": _label(key), "val": v[key]}
                    )
        if c["edition_number"] is not None and c["edition_number"] > 32767:
            res.errors.append(_("“Lần xuất bản” quá lớn."))

        c["category_id"] = None
        if v["category"]:
            c["category_id"] = categories.get(v["category"].lower())
            if c["category_id"] is None:
                res.warnings.append(
                    _("Thể loại “%(val)s” không có trong danh mục – để trống.")
                    % {"val": v["category"]}
                )
        c["field_id"] = None
        if v["field"]:
            c["field_id"] = fields.get(v["field"].lower())
            if c["field_id"] is None:
                res.warnings.append(
                    _("Lĩnh vực “%(val)s” không có trong danh mục – để trống.")
                    % {"val": v["field"]}
                )

        c["language"] = v["language"] or "Tiếng Việt"
        c["registration_number"] = v["registration_number"]
        c["decision_number"] = v["decision_number"]
        c["book_size"] = v["book_size"]
        c["note"] = v["note"]
        res.cleaned = c
        results.append(res)

    if pending:
        existing = set(
            PublicationCase.objects.filter(isbn__in=[isbn for _r, isbn in pending]).values_list(
                "isbn", flat=True
            )
        )
        for res, isbn in pending:
            if isbn in existing:
                res.errors.append(_("ISBN %(isbn)s đã có trong hệ thống.") % {"isbn": isbn})
    return results


# ---------------------------------------------------------------------------
# Bước 2: nhập
# ---------------------------------------------------------------------------


def get_system_owner() -> User:
    """Tài khoản hệ thống "Dữ liệu nhập từ Excel" (CUSTOMER, không đăng nhập được)."""
    owner = User.objects.filter(email=SYSTEM_OWNER_EMAIL).first()
    if owner is None:
        owner = User.objects.create_user(
            email=SYSTEM_OWNER_EMAIL,
            password=None,
            full_name=SYSTEM_OWNER_NAME,
            role=UserRole.CUSTOMER,
            is_active=False,
        )
    return owner


def import_rows(*, rows: list[dict], filename: str, actor, request=None) -> ImportBatch | None:
    """Kiểm tra lại và nhập các dòng hợp lệ trong một giao dịch. Không có dòng hợp lệ -> None."""
    with transaction.atomic():
        results = validate_rows(rows)
        valid = [r for r in results if r.is_valid]
        if not valid:
            return None
        owner = get_system_owner()
        batch = ImportBatch.objects.create(
            created_by=actor,
            original_filename=filename[:255],
            total_rows=len(results),
            imported_rows=len(valid),
            error_rows=len(results) - len(valid),
        )
        note = _("Nhập từ Excel – lô #%(id)s") % {"id": batch.pk}
        case_ids: list[str] = []
        for res in valid:
            c = res.cleaned
            status = CaseStatus.COMPLETED if c["deposit_date"] else CaseStatus.DECISION_ISSUED
            edition = c["edition_number"] or 1
            # Bản ghi mới: được gán trạng thái khi tạo (gói M5 mục 2.3), không dùng change_status.
            case = PublicationCase.objects.create(
                owner=owner,
                status=status,
                title=c["title"],
                category_id=c["category_id"],
                field_id=c["field_id"],
                language=c["language"],
                edition_number=edition,
                is_reprint=edition > 1,
                publication_mode=c["publication_mode"],
                partner_name=c["partner_name"],
                isbn=c["isbn"],
                registration_number=c["registration_number"],
                registration_date=c["registration_date"],
                decision_number=c["decision_number"],
                decision_date=c["decision_date"],
                deposit_date=c["deposit_date"],
                page_count=c["page_count"],
                book_size=c["book_size"],
            )
            Contributor.objects.bulk_create(
                Contributor(case=case, full_name=name, role=role, order=idx)
                for idx, (name, role) in enumerate(c["authors"], start=1)
            )
            StatusHistory.objects.create(
                case=case,
                from_status=CaseStatus.DRAFT,
                to_status=status,
                actor=actor,
                note=note,
            )
            if c["note"]:
                CaseNote.objects.create(
                    case=case, author=actor, body=c["note"], visibility=NoteVisibility.INTERNAL
                )
            log_event(
                actor=actor,
                action="case.import",
                object_type="PublicationCase",
                object_id=str(case.pk),
                case=case,
                data={"batch_id": batch.pk, "row": res.row, "status": status},
                request=request,
            )
            case_ids.append(str(case.pk))

        batch.case_ids = case_ids
        batch.save(update_fields=["case_ids"])
        log_event(
            actor=actor,
            action="import.batch",
            object_type="ImportBatch",
            object_id=str(batch.pk),
            data={
                "filename": batch.original_filename,
                "total_rows": batch.total_rows,
                "imported_rows": batch.imported_rows,
                "error_rows": batch.error_rows,
            },
            request=request,
        )
    return batch
