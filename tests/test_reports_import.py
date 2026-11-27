"""Test M5 — Nhập danh mục xuất bản cũ từ Excel."""

from __future__ import annotations

import datetime
import io
import re

import pytest
from django.contrib.auth import authenticate
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from apps.accounts.models import User, UserRole
from apps.core.models import (
    AuditEvent,
    CaseNote,
    CaseStatus,
    Contributor,
    ContributorRole,
    PublicationCase,
    PublicationMode,
    StatusHistory,
)
from apps.reports import importer
from apps.reports.models import ImportBatch
from tests.factories import CategoryFactory, FieldFactory, PublicationCaseFactory

HEADER = importer.header_titles()
ISBN_OK = "978-604-300-000-9"
ISBN_OK_2 = "9780306406157"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def make_row(**kw):
    base = {
        "Tên xuất bản phẩm*": "Sách hư cấu",
        "Tác giả*": "Nguyễn Hư Cấu",
        "Ngày QĐXB*": datetime.datetime(2019, 6, 1),
    }
    base.update(kw)
    return [base.get(h) for h in HEADER]


def make_xlsx(rows, header=HEADER, name="danh-muc.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=XLSX)


@pytest.fixture
def cat_field(db):
    return CategoryFactory(name="Giáo trình"), FieldFactory(name="Kinh tế học")


def _db_counts():
    return (
        PublicationCase.objects.count(),
        Contributor.objects.count(),
        StatusHistory.objects.count(),
        AuditEvent.objects.count(),
        ImportBatch.objects.count(),
        User.objects.count(),
        CaseNote.objects.count(),
    )


def _check(client, upload):
    resp = client.post(reverse("reports:import"), {"file": upload})
    assert resp.status_code == 200
    return resp


def _confirm(client, resp):
    payload = resp.context["confirm_form"].initial["payload"]
    return client.post(reverse("reports:import"), {"payload": payload})


def sample_rows():
    return [
        make_row(
            **{
                "Tên xuất bản phẩm*": "Giáo trình kinh tế vi mô hư cấu",
                "Tác giả*": "Lê Văn A (Chủ biên); Trần Thị B ; Phạm C",
                "Thể loại": "giáo trình",
                "Lĩnh vực": "KINH TẾ HỌC",
                "Hình thức": "Liên kết",
                "Đơn vị liên kết": "Công ty Sách Tưởng Tượng",
                "ISBN": ISBN_OK,
                "Số XNĐK": "1234-2019/CXBIPH/1-11/KT",
                "Ngày XNĐK": "15/04/2019",
                "Số QĐXB": "45/QĐ-NXBKT",
                "Ngày QĐXB*": datetime.datetime(2019, 6, 1),
                "Ngày nộp lưu chiểu": "20/07/2019",
                "Số trang": 320,
                "Khổ": "16x24",
                "Lần xuất bản": 2,
                "Ghi chú": "Dữ liệu thử",
            }
        ),
        make_row(
            **{
                "Tên xuất bản phẩm*": "Sách chưa lưu chiểu",
                "Thể loại": "Không có thể loại này",
                "ISBN": ISBN_OK_2,
            }
        ),
        [None] * len(HEADER),  # dòng trống bị bỏ qua
        make_row(**{"ISBN": "978-604-300-000-1"}),  # sai số kiểm tra
        make_row(**{"Tên xuất bản phẩm*": None, "Ngày QĐXB*": "31/02/2019"}),
        make_row(**{"ISBN": "9786043000009"}),  # trùng ISBN dòng 2 trong file
        make_row(**{"Hình thức": "Hợp tác", "Số trang": "abc"}),
    ]


def test_template_download_has_exact_header(client, editor_none):
    client.force_login(editor_none)
    resp = client.get(reverse("reports:import_template"))
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    header = [c.value for c in wb.worksheets[0][1]]
    assert header == [
        "Tên xuất bản phẩm*",
        "Tác giả*",
        "Thể loại",
        "Lĩnh vực",
        "Ngôn ngữ",
        "Hình thức",
        "Đơn vị liên kết",
        "ISBN",
        "Số XNĐK",
        "Ngày XNĐK",
        "Số QĐXB",
        "Ngày QĐXB*",
        "Ngày nộp lưu chiểu",
        "Số trang",
        "Khổ",
        "Lần xuất bản",
        "Ghi chú",
    ]
    assert wb.worksheets[0].max_row == 1


def test_check_step_writes_nothing(client, editor_none, cat_field):
    client.force_login(editor_none)
    before = _db_counts()
    resp = _check(client, make_xlsx(sample_rows()))
    assert _db_counts() == before
    assert resp.context["total"] == 6
    assert resp.context["valid_count"] == 2
    assert resp.context["error_count"] == 4
    results = {r.row: r for r in resp.context["results"]}
    assert set(results) == {2, 3, 5, 6, 7, 8}  # dòng 4 trống bị bỏ
    assert results[2].is_valid and not results[2].warnings
    assert results[3].is_valid
    assert any("Không có thể loại này" in w for w in results[3].warnings)
    assert any("ISBN sai" in e for e in results[5].errors)
    errs6 = " ".join(results[6].errors)
    assert "Thiếu “Tên xuất bản phẩm”" in errs6
    assert "sai định dạng ngày" in errs6
    assert any("trùng với dòng 2" in e for e in results[7].errors)
    errs8 = " ".join(results[8].errors)
    assert "Hình thức" in errs8 and "Số trang" in errs8


def test_confirm_creates_cases(client, editor_none, cat_field):
    cat, fld = cat_field
    client.force_login(editor_none)
    resp = _check(client, make_xlsx(sample_rows(), name="cu-2019.xlsx"))
    resp = _confirm(client, resp)
    assert resp.status_code == 302
    assert resp["Location"] == reverse("reports:import_history")

    batch = ImportBatch.objects.get()
    assert batch.created_by == editor_none
    assert batch.original_filename == "cu-2019.xlsx"
    assert (batch.total_rows, batch.imported_rows, batch.error_rows) == (6, 2, 4)
    assert len(batch.case_ids) == 2

    owner = User.objects.get(email="du-lieu-cu@portal.invalid")
    assert owner.role == UserRole.CUSTOMER
    assert owner.is_active is False
    assert owner.full_name == "Dữ liệu nhập từ Excel"
    assert not owner.has_usable_password()

    a = PublicationCase.objects.get(isbn="9786043000009")
    assert str(a.pk) in batch.case_ids
    assert a.owner == owner
    assert a.status == CaseStatus.COMPLETED
    assert a.nxb_code is None
    assert a.category == cat and a.field == fld
    assert a.publication_mode == PublicationMode.LINKED
    assert a.partner_name == "Công ty Sách Tưởng Tượng"
    assert a.registration_date == datetime.date(2019, 4, 15)
    assert a.decision_date == datetime.date(2019, 6, 1)
    assert a.deposit_date == datetime.date(2019, 7, 20)
    assert a.page_count == 320 and a.book_size == "16x24"
    assert a.edition_number == 2 and a.is_reprint
    assert a.decision_number == "45/QĐ-NXBKT"
    contributors = list(a.contributors.order_by("order"))
    assert [(c.full_name, c.role, c.order) for c in contributors] == [
        ("Lê Văn A", ContributorRole.CHIEF_EDITOR, 1),
        ("Trần Thị B", ContributorRole.AUTHOR, 2),
        ("Phạm C", ContributorRole.AUTHOR, 3),
    ]
    history = StatusHistory.objects.get(case=a)
    assert history.from_status == CaseStatus.DRAFT
    assert history.to_status == CaseStatus.COMPLETED
    assert history.actor == editor_none
    assert history.note == f"Nhập từ Excel – lô #{batch.pk}"
    assert CaseNote.objects.get(case=a).body == "Dữ liệu thử"

    b = PublicationCase.objects.get(isbn=ISBN_OK_2)
    assert b.status == CaseStatus.DECISION_ISSUED
    assert b.category is None
    assert b.publication_mode == PublicationMode.SELF
    assert b.language == "Tiếng Việt"
    assert StatusHistory.objects.get(case=b).to_status == CaseStatus.DECISION_ISSUED

    assert AuditEvent.objects.filter(action="case.import").count() == 2
    assert AuditEvent.objects.filter(action="case.import", case=a).exists()
    batch_ev = AuditEvent.objects.get(action="import.batch")
    assert batch_ev.object_id == str(batch.pk)
    assert batch_ev.actor == editor_none

    # Lịch sử nhập hiển thị lô
    page = client.get(reverse("reports:import_history")).content.decode()
    assert "cu-2019.xlsx" in page


def test_system_account_cannot_login(client, editor_none, cat_field):
    client.force_login(editor_none)
    _confirm(client, _check(client, make_xlsx(sample_rows())))
    client.logout()
    assert authenticate(email="du-lieu-cu@portal.invalid", password="") is None
    assert not client.login(email="du-lieu-cu@portal.invalid", password="bat-ky")
    client.post(reverse("accounts:login"), {"email": "du-lieu-cu@portal.invalid", "password": "x"})
    assert "_auth_user_id" not in client.session


def test_reimport_same_file_reports_duplicate_isbn(client, editor_none, cat_field):
    client.force_login(editor_none)
    rows = sample_rows()
    _confirm(client, _check(client, make_xlsx(rows)))
    resp = _check(client, make_xlsx(rows))
    results = {r.row: r for r in resp.context["results"]}
    assert any("đã có trong hệ thống" in e for e in results[2].errors)
    assert any("đã có trong hệ thống" in e for e in results[3].errors)
    assert resp.context["valid_count"] == 0
    assert "confirm_form" in resp.context
    assert b"Kh\xc3\xb4ng c\xc3\xb3 d\xc3\xb2ng h\xe1\xbb\xa3p l\xe1\xbb\x87" in resp.content


def test_existing_isbn_in_portal_reported(client, editor_none, db):
    PublicationCaseFactory(isbn=ISBN_OK_2)
    client.force_login(editor_none)
    resp = _check(client, make_xlsx([make_row(ISBN=ISBN_OK_2)]))
    assert "đã có trong hệ thống" in " ".join(resp.context["results"][0].errors)


def test_confirm_revalidates(client, editor_none, db):
    """ISBN bị tạo ở nơi khác giữa hai bước -> dòng đó không được nhập."""
    client.force_login(editor_none)
    resp = _check(client, make_xlsx([make_row(ISBN=ISBN_OK_2)]))
    PublicationCaseFactory(isbn=ISBN_OK_2)
    resp = _confirm(client, resp)
    assert resp["Location"] == reverse("reports:import")
    assert not ImportBatch.objects.exists()


def test_confirm_bad_or_foreign_payload(client, editor_none, db):
    client.force_login(editor_none)
    resp = client.post(reverse("reports:import"), {"payload": "giả-mạo"})
    assert resp.status_code == 302 and resp["Location"] == reverse("reports:import")
    # Payload của BTV khác
    from tests.factories import EditorFactory

    other = EditorFactory()
    client.force_login(other)
    check = _check(client, make_xlsx([make_row()]))
    client.force_login(editor_none)
    resp = _confirm(client, check)
    assert resp["Location"] == reverse("reports:import")
    assert not PublicationCase.objects.exists()


def test_rejects_non_xlsx_and_garbage(client, editor_none, db):
    client.force_login(editor_none)
    resp = _check(client, SimpleUploadedFile("cu.xls", b"abc"))
    assert "Lưu thành .xlsx" in resp.content.decode()
    resp = _check(client, SimpleUploadedFile("hong.xlsx", b"khong phai excel"))
    assert "Không đọc được file Excel" in resp.content.decode()


def test_missing_required_columns(client, editor_none, db):
    client.force_login(editor_none)
    resp = _check(client, make_xlsx([["x"]], header=["Tên xuất bản phẩm", "ISBN"]))
    content = resp.content.decode()
    assert "Thiếu cột bắt buộc" in content
    assert "Tác giả" in content and "Ngày QĐXB" in content


def test_header_match_is_lenient_and_formulas_not_run(client, editor_none, db):
    client.force_login(editor_none)
    header = ["  tên xuất bản phẩm ", "TÁC GIẢ", "Ngày QĐXB", "Số trang"]
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    ws.append(["Sách công thức", "Tác giả X", "01/02/2018", "=10*20"])
    buf = io.BytesIO()
    wb.save(buf)
    resp = _check(client, SimpleUploadedFile("f.xlsx", buf.getvalue()))
    r = resp.context["results"][0]
    # data_only=True: ô công thức chưa có giá trị tính sẵn -> trống, không chạy công thức
    assert r.is_valid
    assert r.cleaned["page_count"] is None


def test_too_many_rows(client, editor_none, db, monkeypatch):
    monkeypatch.setattr(importer, "MAX_ROWS", 3)
    client.force_login(editor_none)
    resp = _check(client, make_xlsx([make_row() for _ in range(5)]))
    assert "hơn 3 dòng" in resp.content.decode()


def test_file_too_large(client, editor_none, db, monkeypatch):
    client.force_login(editor_none)
    monkeypatch.setattr("apps.reports.forms.MAX_FILE_BYTES", 10)
    resp = _check(client, make_xlsx([make_row()]))
    assert "10 MB" in resp.content.decode()


def test_parse_helpers():
    assert importer.parse_authors(" A (chủ biên) ;; B;") == [
        ("A", ContributorRole.CHIEF_EDITOR),
        ("B", ContributorRole.AUTHOR),
    ]
    assert importer.parse_date("05/03/2020") == datetime.date(2020, 3, 5)
    with pytest.raises(ValueError):
        importer.parse_date("2020/13/01")
    assert importer._cell_to_text(12.0) == "12"
    assert importer._cell_to_text(datetime.date(2020, 1, 2)) == "02/01/2020"
    assert re.match(r"^Tên", importer.header_titles()[0])


def test_parse_workbook_direct_errors(db):
    with pytest.raises(importer.ImportFileError):
        importer.parse_workbook(SimpleUploadedFile("a.xls", b""))
    big = SimpleUploadedFile("a.xlsx", b"x")
    big.size = importer.MAX_FILE_BYTES + 1
    with pytest.raises(importer.ImportFileError):
        importer.parse_workbook(big)


def test_validation_edge_cases(db):
    rows = [
        {"row": 2, "values": {"title": "x" * 501, "authors": ";", "decision_date": "01/01/2020"}},
        {
            "row": 3,
            "values": {
                "title": "T",
                "authors": "A",
                "decision_date": "01/01/2020",
                "isbn": "0306406152",
                "mode": "liên kết",
                "edition_number": "40000",
                "field": "Không có",
            },
        },
    ]
    r1, r2 = importer.validate_rows(rows)
    assert any("dài quá 500" in e for e in r1.errors)
    assert any("không có tên hợp lệ" in e for e in r1.errors)
    errs = " ".join(r2.errors)
    assert "ISBN-13" in errs
    assert "Đơn vị liên kết" in errs
    assert "quá lớn" in errs
    assert any("Lĩnh vực" in w for w in r2.warnings)


def test_import_rows_none_when_no_valid(db, editor_none):
    assert importer.import_rows(rows=[], filename="x.xlsx", actor=editor_none) is None


def test_system_owner_reused(db):
    a = importer.get_system_owner()
    assert importer.get_system_owner() == a


def test_batch_cannot_be_deleted(db, editor_none):
    from django.core.exceptions import PermissionDenied

    batch = ImportBatch.objects.create(created_by=editor_none, original_filename="a.xlsx")
    with pytest.raises(PermissionDenied):
        batch.delete()
    assert str(batch).startswith("Lô #")
