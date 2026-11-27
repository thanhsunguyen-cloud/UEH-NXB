"""M2 — Trang chi tiết hồ sơ: tài liệu, nộp hồ sơ, bổ sung, trao đổi, dòng thời gian."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.core.models import (
    AuditEvent,
    CaseNote,
    CaseStatus,
    DocumentType,
    NoteVisibility,
    PublicationMode,
    Receivable,
    StatusHistory,
    SupplementRequest,
    SupplementStatus,
)
from apps.core.workflow import change_status
from apps.customer.views import public_forms_url, submit_checklist
from tests.factories import (
    ContributorFactory,
    DocumentFactory,
    FeeTypeFactory,
    PublicationCaseFactory,
)

UPLOAD_MARK = 'data-doc-type="{}"'


def _complete_case(owner, **kwargs):
    case = PublicationCaseFactory(owner=owner, **kwargs)
    for doc_type in (DocumentType.MANUSCRIPT, DocumentType.FORM_2, DocumentType.FORM_3):
        DocumentFactory(case=case, doc_type=doc_type)
    ContributorFactory(case=case)
    return case


def _detail(client, case):
    response = client.get(reverse("customer:case_detail", args=[case.pk]))
    assert response.status_code == 200
    return response.content.decode()


# --- Nộp hồ sơ ----------------------------------------------------------


@pytest.mark.django_db
def test_submit_missing_conditions_lists_missing_and_keeps_status(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)
    response = client.post(reverse("customer:case_submit", args=[case.pk]), follow=True)
    html = response.content.decode()
    case.refresh_from_db()
    assert case.status == CaseStatus.DRAFT
    assert "Còn thiếu" in html
    assert "Bản thảo (MANUSCRIPT)" in html
    assert "Mẫu 2 (FORM_2)" in html
    assert "Ít nhất 01 tác giả" in html
    assert not StatusHistory.objects.filter(case=case).exists()


@pytest.mark.django_db
def test_submit_complete_case_goes_to_submitted(client, customer_a):
    case = _complete_case(customer_a)
    client.force_login(customer_a)
    response = client.post(
        reverse("customer:case_submit", args=[case.pk]), {"note": "Kính gửi NXB"}, follow=True
    )
    case.refresh_from_db()
    assert case.status == CaseStatus.SUBMITTED
    history = StatusHistory.objects.get(case=case)
    assert history.from_status == CaseStatus.DRAFT
    assert history.to_status == CaseStatus.SUBMITTED
    assert history.actor == customer_a
    html = response.content.decode()
    assert "Đã nộp hồ sơ" in html
    assert "Đã nộp – chờ NXB tiếp nhận" in html
    # Sau khi nộp: không còn nút nộp, không còn ô tải lên
    assert reverse("customer:case_submit", args=[case.pk]) not in html
    assert "ueh-chunked-upload" not in html


@pytest.mark.django_db
def test_submit_linked_case_requires_form1(client, customer_a):
    case = _complete_case(
        customer_a, publication_mode=PublicationMode.LINKED, partner_name="Công ty ABC"
    )
    client.force_login(customer_a)
    client.post(reverse("customer:case_submit", args=[case.pk]))
    case.refresh_from_db()
    assert case.status == CaseStatus.DRAFT
    DocumentFactory(case=case, doc_type=DocumentType.FORM_1)
    client.post(reverse("customer:case_submit", args=[case.pk]))
    case.refresh_from_db()
    assert case.status == CaseStatus.SUBMITTED


@pytest.mark.django_db
def test_checklist_matches_workflow(customer_a):
    case = PublicationCaseFactory(owner=customer_a, publication_mode=PublicationMode.LINKED)
    items = submit_checklist(case)
    assert len(items) == 6
    assert not any(i["ok"] for i in items)
    case = _complete_case(customer_a)
    assert all(i["ok"] for i in submit_checklist(case))


@pytest.mark.django_db
def test_checklist_and_submit_button_shown_in_draft(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)
    html = _detail(client, case)
    assert "Điều kiện nộp hồ sơ" in html
    assert "Còn thiếu" in html
    assert reverse("customer:case_submit", args=[case.pk]) in html


@pytest.mark.django_db
def test_resubmit_from_need_supplement_resolves_open_requests(client, customer_a, editor_none):
    case = _complete_case(customer_a)
    change_status(case, CaseStatus.SUBMITTED, actor=customer_a)
    change_status(case, CaseStatus.NEED_SUPPLEMENT, actor=editor_none, note="Bổ sung Mẫu 3 ký")
    req1 = SupplementRequest.objects.create(
        case=case, requested_by=editor_none, message="Bổ sung Mẫu 3 có chữ ký"
    )
    old = SupplementRequest.objects.create(
        case=case, requested_by=editor_none, message="Cũ", status=SupplementStatus.RESOLVED
    )
    client.force_login(customer_a)

    html = _detail(client, case)
    assert "NXB yêu cầu bổ sung hồ sơ" in html
    assert "Bổ sung Mẫu 3 có chữ ký" in html
    # Ghi chú của bước chuyển sang NEED_SUPPLEMENT được hiện trên dòng thời gian
    assert "Bổ sung Mẫu 3 ký" in html
    assert "Bổ sung theo yêu cầu NXB" in client.get(reverse("customer:home")).content.decode()

    client.post(reverse("customer:case_submit", args=[case.pk]))
    case.refresh_from_db()
    assert case.status == CaseStatus.SUBMITTED
    req1.refresh_from_db()
    assert req1.status == SupplementStatus.RESOLVED
    assert req1.resolved_at is not None
    old.refresh_from_db()
    assert old.resolved_at is None
    event = AuditEvent.objects.get(action="case.supplement_resolved", case=case)
    assert event.data["supplement_request_ids"] == [req1.pk]


@pytest.mark.django_db
def test_failed_resubmit_keeps_requests_open(client, customer_a, editor_none):
    case = _complete_case(customer_a)
    change_status(case, CaseStatus.SUBMITTED, actor=customer_a)
    change_status(case, CaseStatus.NEED_SUPPLEMENT, actor=editor_none, note="Thiếu")
    req = SupplementRequest.objects.create(case=case, requested_by=editor_none, message="x")
    case.contributors.all().delete()
    client.force_login(customer_a)
    client.post(reverse("customer:case_submit", args=[case.pk]))
    case.refresh_from_db()
    req.refresh_from_db()
    assert case.status == CaseStatus.NEED_SUPPLEMENT
    assert req.status == SupplementStatus.OPEN


@pytest.mark.django_db
def test_submit_not_allowed_from_editing(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.EDITING)
    client.force_login(customer_a)
    html = _detail(client, case)
    assert "Điều kiện nộp hồ sơ" not in html
    response = client.post(reverse("customer:case_submit", args=[case.pk]), follow=True)
    case.refresh_from_db()
    assert case.status == CaseStatus.EDITING
    assert "Không thể chuyển trạng thái" in response.content.decode()


# --- Nội dung bị ẩn -----------------------------------------------------


@pytest.mark.django_db
def test_detail_hides_internal_notes_form4_and_finance(client, customer_a, editor_manage):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.EDITING)
    CaseNote.objects.create(
        case=case,
        author=editor_manage,
        body="GHI-CHU-NOI-BO-BI-MAT",
        visibility=NoteVisibility.INTERNAL,
    )
    CaseNote.objects.create(
        case=case,
        author=editor_manage,
        body="Lời nhắn gửi khách",
        visibility=NoteVisibility.CUSTOMER,
    )
    DocumentFactory(
        case=case,
        doc_type=DocumentType.FORM_4,
        original_filename="phieu-duyet-mau4.pdf",
        uploaded_by=editor_manage,
    )
    DocumentFactory(
        case=case,
        doc_type=DocumentType.FORM_5,
        original_filename="mau5-noi-bo.pdf",
        uploaded_by=editor_manage,
    )
    Receivable.objects.create(
        case=case,
        fee_type=FeeTypeFactory(),
        amount=Decimal("98765432"),
        created_by=editor_manage,
    )
    client.force_login(customer_a)
    html = _detail(client, case)
    assert "Lời nhắn gửi khách" in html
    assert "GHI-CHU-NOI-BO-BI-MAT" not in html
    assert "phieu-duyet-mau4.pdf" not in html
    assert "Mẫu 4" not in html
    assert "mau5-noi-bo.pdf" not in html
    assert "98765432" not in html
    assert "98,765,432" not in html
    assert "98.765.432" not in html
    assert "VNĐ" not in html


@pytest.mark.django_db
def test_timeline_hides_internal_status_notes(client, customer_a, editor_none):
    case = _complete_case(customer_a)
    change_status(case, CaseStatus.SUBMITTED, actor=customer_a, note="nop")
    change_status(case, CaseStatus.ACCEPTED, actor=editor_none, note="NOI-BO-TIEP-NHAN")
    client.force_login(customer_a)
    html = _detail(client, case)
    assert "NXB đã tiếp nhận" in html
    assert "NOI-BO-TIEP-NHAN" not in html


# --- Tài liệu & ô tải lên -----------------------------------------------


@pytest.mark.django_db
def test_documents_current_and_history_with_download_links(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    v1 = DocumentFactory(
        case=case, version=1, is_current=False, original_filename="ban-thao-v1.pdf"
    )
    v2 = DocumentFactory(case=case, version=2, is_current=True, original_filename="ban-thao-v2.pdf")
    client.force_login(customer_a)
    html = _detail(client, case)
    assert reverse("core:document_download", args=[v1.pk]) in html
    assert reverse("core:document_download", args=[v2.pk]) in html
    assert "Lịch sử phiên bản (1)" in html
    assert public_forms_url() in html


@pytest.mark.django_db
def test_upload_widgets_in_draft_self(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)
    html = _detail(client, case)
    for doc_type in ("MANUSCRIPT", "FORM_2", "FORM_3", "OTHER"):
        assert UPLOAD_MARK.format(doc_type) in html
    assert UPLOAD_MARK.format("FORM_1") not in html
    assert "Mẫu 1" not in html
    assert UPLOAD_MARK.format("FORM_4") not in html


@pytest.mark.django_db
def test_upload_widgets_in_linked_need_supplement(client, customer_a):
    case = PublicationCaseFactory(
        owner=customer_a,
        status=CaseStatus.NEED_SUPPLEMENT,
        publication_mode=PublicationMode.LINKED,
        partner_name="Công ty ABC",
    )
    client.force_login(customer_a)
    html = _detail(client, case)
    for doc_type in ("MANUSCRIPT", "FORM_1", "FORM_2", "FORM_3", "OTHER"):
        assert UPLOAD_MARK.format(doc_type) in html


@pytest.mark.django_db
def test_revision_required_only_manuscript_upload(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.REVISION_REQUIRED)
    client.force_login(customer_a)
    html = _detail(client, case)
    assert "Sau khi tải bản mới, NXB sẽ tiếp tục biên tập" in html
    assert html.count("ueh-chunked-upload border") == 1
    assert UPLOAD_MARK.format("MANUSCRIPT") in html
    assert UPLOAD_MARK.format("FORM_2") not in html
    assert reverse("customer:case_submit", args=[case.pk]) not in html
    assert "Nộp bản thảo đã chỉnh sửa" in client.get(reverse("customer:home")).content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status", [CaseStatus.SUBMITTED, CaseStatus.ACCEPTED, CaseStatus.EDITING, CaseStatus.COMPLETED]
)
def test_no_upload_widget_in_locked_statuses(client, customer_a, status):
    case = PublicationCaseFactory(owner=customer_a, status=status)
    client.force_login(customer_a)
    html = _detail(client, case)
    assert "ueh-chunked-upload border" not in html


# --- Trao đổi -----------------------------------------------------------


@pytest.mark.django_db
def test_customer_adds_note(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.EDITING)
    client.force_login(customer_a)
    response = client.post(
        reverse("customer:note_add", args=[case.pk]),
        {"body": "Cho tôi hỏi tiến độ", "visibility": NoteVisibility.INTERNAL},
    )
    assert response.status_code == 302
    note = CaseNote.objects.get(case=case)
    assert note.visibility == NoteVisibility.CUSTOMER
    assert note.author == customer_a
    assert AuditEvent.objects.filter(action="case.note_add", case=case).exists()
    assert "Cho tôi hỏi tiến độ" in _detail(client, case)


@pytest.mark.django_db
def test_customer_empty_note_rejected(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)
    response = client.post(reverse("customer:note_add", args=[case.pk]), {"body": "   "})
    assert response.status_code == 200
    assert response.context["note_form"].errors
    assert not CaseNote.objects.exists()


def test_public_forms_url_fallback():
    assert public_forms_url().startswith("/")
