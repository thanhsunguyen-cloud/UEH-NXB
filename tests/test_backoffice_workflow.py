"""Test M3 — Quy trình hồ sơ qua giao diện BTV (chuyển trạng thái, Mẫu 4, yêu cầu bổ sung)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.core.models import (
    AuditEvent,
    CaseStatus,
    DocumentType,
    ManuscriptReview,
    PublicationMode,
    ReviewResult,
    StatusHistory,
    SupplementRequest,
    SupplementStatus,
)
from tests.factories import ContributorFactory, DocumentFactory, EditorFactory
from tests.test_backoffice_views import VALID_ISBN, detail_url, info_data, make_case, messages_of


@pytest.fixture
def editor(db):
    return EditorFactory(email="btv.quytrinh@ueh.edu.vn", full_name="BTV Quy trình")


@pytest.fixture
def editor_client(client, editor):
    client.force_login(editor)
    return client


def transition(client, case, to_status, note=""):
    return client.post(
        reverse("backoffice:case_transition", args=[case.pk]),
        {"to_status": to_status, "note": note},
        follow=True,
    )


def add_doc(case, doc_type, editor, version=1):
    return DocumentFactory(case=case, doc_type=doc_type, version=version, uploaded_by=editor)


def review(client, case, manuscript, form4, result=ReviewResult.APPROVED, confirm=True):
    data = {
        "manuscript": manuscript.pk if manuscript else "",
        "form4": form4.pk if form4 else "",
        "result": result,
        "note": "Đã đối chiếu",
    }
    if confirm:
        data["confirm"] = "on"
    return client.post(reverse("backoffice:case_review", args=[case.pk]), data, follow=True)


def assert_blocked(response, case, status, *fragments):
    case.refresh_from_db()
    assert case.status == status
    text = " ".join(messages_of(response))
    assert "Chưa đủ điều kiện chuyển trạng thái" in text
    for fragment in fragments:
        assert fragment in text


@pytest.mark.django_db
def test_full_linked_workflow_submitted_to_archived(editor_client, editor):
    case = make_case(
        publication_mode=PublicationMode.LINKED,
        partner_name="Công ty Đối tác Z",
        title="Sách liên kết trọn quy trình",
    )
    ContributorFactory(case=case, full_name="Tác giả Liên Kết")

    # SUBMITTED -> ACCEPTED (cấp mã NXB)
    response = transition(editor_client, case, CaseStatus.ACCEPTED)
    case.refresh_from_db()
    assert case.status == CaseStatus.ACCEPTED
    assert case.nxb_code
    assert any("Đã tiếp nhận" in m for m in messages_of(response))

    # ACCEPTED -> EDITING: thiếu BTV phụ trách
    response = transition(editor_client, case, CaseStatus.EDITING)
    assert_blocked(response, case, CaseStatus.ACCEPTED, "Biên tập viên phụ trách chính")
    editor_client.post(
        reverse("backoffice:case_assign_editor", args=[case.pk]), {"primary_editor": editor.pk}
    )
    transition(editor_client, case, CaseStatus.EDITING)
    case.refresh_from_db()
    assert case.status == CaseStatus.EDITING

    # EDITING -> REVIEW_APPROVED: thiếu kết quả duyệt
    response = transition(editor_client, case, CaseStatus.REVIEW_APPROVED)
    assert_blocked(response, case, CaseStatus.EDITING, "ManuscriptReview")
    manuscript = add_doc(case, DocumentType.MANUSCRIPT, editor)
    form4 = add_doc(case, DocumentType.FORM_4, editor)
    response = review(editor_client, case, manuscript, form4, ReviewResult.APPROVED)
    assert ManuscriptReview.objects.filter(case=case, result=ReviewResult.APPROVED).count() == 1
    assert any("Duyệt – đồng ý xuất bản" in m for m in messages_of(response))
    suggested = [t for t in response.context["transitions"] if t["suggested"]]
    assert [t["to_status"] for t in suggested] == [CaseStatus.REVIEW_APPROVED]
    transition(editor_client, case, CaseStatus.REVIEW_APPROVED)
    case.refresh_from_db()
    assert case.status == CaseStatus.REVIEW_APPROVED

    # REVIEW_APPROVED -> REGISTERED: thiếu ISBN, số/ngày XNĐK, Mẫu 5
    response = transition(editor_client, case, CaseStatus.REGISTERED)
    assert_blocked(
        response, case, CaseStatus.REVIEW_APPROVED, "ISBN", "registration_number", "FORM_5"
    )
    editor_client.post(
        reverse("backoffice:case_update", args=[case.pk]),
        info_data(
            case,
            isbn=VALID_ISBN,
            registration_number="123-2026/CXBIPH",
            registration_date="2026-11-20",
        ),
    )
    add_doc(case, DocumentType.FORM_5, editor)
    transition(editor_client, case, CaseStatus.REGISTERED)
    case.refresh_from_db()
    assert case.status == CaseStatus.REGISTERED

    # REGISTERED -> DECISION_ISSUED: thiếu QĐXB, Mẫu 6, Mẫu 7, số hợp đồng
    response = transition(editor_client, case, CaseStatus.DECISION_ISSUED)
    assert_blocked(
        response, case, CaseStatus.REGISTERED, "decision_number", "FORM_6", "FORM_7", "contract"
    )
    editor_client.post(
        reverse("backoffice:case_update", args=[case.pk]),
        info_data(
            case,
            decision_number="45/QĐ-NXBKT",
            decision_date="2026-11-22",
            contract_number="HĐ-01/2026",
            contract_date="2026-11-21",
        ),
    )
    add_doc(case, DocumentType.FORM_6, editor)
    add_doc(case, DocumentType.FORM_7, editor)
    transition(editor_client, case, CaseStatus.DECISION_ISSUED)
    case.refresh_from_db()
    assert case.status == CaseStatus.DECISION_ISSUED

    # DECISION_ISSUED -> DEPOSITED: thiếu Mẫu 9, ngày lưu chiểu
    response = transition(editor_client, case, CaseStatus.DEPOSITED)
    assert_blocked(response, case, CaseStatus.DECISION_ISSUED, "FORM_9", "deposit_date")
    editor_client.post(
        reverse("backoffice:case_update", args=[case.pk]),
        info_data(case, deposit_date="2026-11-25"),
    )
    add_doc(case, DocumentType.FORM_9, editor)
    transition(editor_client, case, CaseStatus.DEPOSITED)
    case.refresh_from_db()
    assert case.status == CaseStatus.DEPOSITED

    transition(editor_client, case, CaseStatus.COMPLETED, note="Hoàn tất hồ sơ")
    case.refresh_from_db()
    assert case.status == CaseStatus.COMPLETED

    # Không cho phép bước không có trong bảng chuyển trạng thái
    response = transition(editor_client, case, CaseStatus.EDITING)
    case.refresh_from_db()
    assert case.status == CaseStatus.COMPLETED
    assert any("Không thể chuyển trạng thái" in m for m in messages_of(response))

    response = transition(editor_client, case, CaseStatus.ARCHIVED)
    case.refresh_from_db()
    assert case.status == CaseStatus.ARCHIVED

    history = list(StatusHistory.objects.filter(case=case).order_by("at", "id"))
    assert [h.to_status for h in history] == [
        CaseStatus.ACCEPTED,
        CaseStatus.EDITING,
        CaseStatus.REVIEW_APPROVED,
        CaseStatus.REGISTERED,
        CaseStatus.DECISION_ISSUED,
        CaseStatus.DEPOSITED,
        CaseStatus.COMPLETED,
        CaseStatus.ARCHIVED,
    ]
    assert AuditEvent.objects.filter(case=case, action="case.status_change").count() == 8
    assert AuditEvent.objects.filter(case=case, action="case.manuscript_review").count() == 1
    assert AuditEvent.objects.filter(case=case, action="case.assign_editor").count() == 1
    assert AuditEvent.objects.filter(case=case, action="case.update").count() == 3

    # Dòng thời gian hiển thị ghi chú
    content = editor_client.get(detail_url(case, "workflow")).content.decode()
    assert "Hoàn tất hồ sơ" in content
    assert "Lưu trữ" in content


@pytest.mark.django_db
def test_transition_buttons_have_vietnamese_labels_and_missing_list(editor_client):
    case = make_case()
    response = editor_client.get(detail_url(case, "workflow"))
    labels = {t["to_status"]: t["label"] for t in response.context["transitions"]}
    assert labels == {
        CaseStatus.NEED_SUPPLEMENT: "Yêu cầu bổ sung",
        CaseStatus.ACCEPTED: "Tiếp nhận",
    }
    content = response.content.decode()
    assert "Nội dung yêu cầu bổ sung" in content

    accepted = make_case(status=CaseStatus.ACCEPTED)
    response = editor_client.get(detail_url(accepted, "workflow"))
    (option,) = response.context["transitions"]
    assert option["label"] == "Bắt đầu biên tập"
    assert option["missing"] == ["Biên tập viên phụ trách chính (primary_editor)"]
    assert "Còn thiếu" in response.content.decode()


@pytest.mark.django_db
def test_revision_and_rejection_paths(editor_client, editor):
    case = make_case(status=CaseStatus.EDITING, primary_editor=editor)
    ms1 = add_doc(case, DocumentType.MANUSCRIPT, editor, version=1)
    f4 = add_doc(case, DocumentType.FORM_4, editor)
    review(editor_client, case, ms1, f4, ReviewResult.REVISION_REQUIRED)
    transition(editor_client, case, CaseStatus.REVISION_REQUIRED, note="Sửa chương 2")
    case.refresh_from_db()
    assert case.status == CaseStatus.REVISION_REQUIRED

    response = editor_client.get(detail_url(case, "workflow"))
    assert [t["label"] for t in response.context["transitions"]] == ["Tiếp tục biên tập"]

    response = transition(editor_client, case, CaseStatus.EDITING)
    assert_blocked(response, case, CaseStatus.REVISION_REQUIRED, "phiên bản mới hơn")
    add_doc(case, DocumentType.MANUSCRIPT, editor, version=2)
    transition(editor_client, case, CaseStatus.EDITING)
    case.refresh_from_db()
    assert case.status == CaseStatus.EDITING

    ms2 = case.documents.get(doc_type=DocumentType.MANUSCRIPT, version=2)
    review(editor_client, case, ms2, f4, ReviewResult.REJECTED)
    transition(editor_client, case, CaseStatus.REJECTED)
    case.refresh_from_db()
    assert case.status == CaseStatus.REJECTED
    transition(editor_client, case, CaseStatus.ARCHIVED)
    case.refresh_from_db()
    assert case.status == CaseStatus.ARCHIVED


# ---------------------------------------------------------------------------
# Xác nhận Mẫu 4 "đúng hồ sơ"
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_review_rejects_documents_of_other_case(editor_client, editor):
    case = make_case(status=CaseStatus.EDITING, primary_editor=editor)
    other = make_case(status=CaseStatus.EDITING)
    own_ms = add_doc(case, DocumentType.MANUSCRIPT, editor)
    own_f4 = add_doc(case, DocumentType.FORM_4, editor)
    other_ms = add_doc(other, DocumentType.MANUSCRIPT, editor)
    other_f4 = add_doc(other, DocumentType.FORM_4, editor)

    response = review(editor_client, case, other_ms, own_f4)
    assert response.status_code == 200
    assert "Bản thảo không thuộc hồ sơ này." in response.content.decode()

    response = review(editor_client, case, own_ms, other_f4)
    assert "Mẫu 4 không thuộc hồ sơ này." in response.content.decode()

    # Sai loại tài liệu (Mẫu 4 chọn vào ô bản thảo) cũng bị từ chối.
    response = review(editor_client, case, own_f4, own_ms)
    content = response.content.decode()
    assert "Bản thảo không thuộc hồ sơ này." in content
    assert "Mẫu 4 không thuộc hồ sơ này." in content

    assert not ManuscriptReview.objects.exists()
    assert not AuditEvent.objects.filter(action="case.manuscript_review").exists()


@pytest.mark.django_db
def test_review_requires_confirmation_checkbox(editor_client, editor):
    case = make_case(status=CaseStatus.EDITING, primary_editor=editor)
    ms = add_doc(case, DocumentType.MANUSCRIPT, editor)
    f4 = add_doc(case, DocumentType.FORM_4, editor)
    response = review(editor_client, case, ms, f4, confirm=False)
    assert response.status_code == 200
    assert "Bắt buộc tích ô xác nhận Mẫu 4 đúng hồ sơ." in response.content.decode()
    assert not ManuscriptReview.objects.exists()

    response = review(editor_client, case, ms, f4, confirm=True)
    rec = ManuscriptReview.objects.get()
    assert rec.manuscript == ms and rec.form4 == f4 and rec.confirmed_by == editor
    content = editor_client.get(detail_url(case, "workflow")).content.decode()
    assert "Đồng ý xuất bản" in content


@pytest.mark.django_db
def test_review_only_when_editing(editor_client, editor):
    case = make_case(status=CaseStatus.ACCEPTED)
    ms = add_doc(case, DocumentType.MANUSCRIPT, editor)
    f4 = add_doc(case, DocumentType.FORM_4, editor)
    response = review(editor_client, case, ms, f4)
    assert any("Đang biên tập" in m for m in messages_of(response))
    assert not ManuscriptReview.objects.exists()
    assert 'id="review-form"' not in editor_client.get(detail_url(case)).content.decode()


# ---------------------------------------------------------------------------
# Yêu cầu bổ sung
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_need_supplement_creates_open_request(editor_client, editor):
    case = make_case()
    response = transition(editor_client, case, CaseStatus.NEED_SUPPLEMENT, note="   ")
    case.refresh_from_db()
    assert case.status == CaseStatus.SUBMITTED
    assert "Bắt buộc nhập nội dung yêu cầu bổ sung." in messages_of(response)
    assert not SupplementRequest.objects.exists()

    response = transition(
        editor_client, case, CaseStatus.NEED_SUPPLEMENT, note="Bổ sung Mẫu 3 có chữ ký"
    )
    case.refresh_from_db()
    assert case.status == CaseStatus.NEED_SUPPLEMENT
    sr = SupplementRequest.objects.get(case=case)
    assert sr.status == SupplementStatus.OPEN
    assert sr.message == "Bổ sung Mẫu 3 có chữ ký"
    assert sr.requested_by == editor
    history = StatusHistory.objects.get(case=case)
    assert history.note == "Bổ sung Mẫu 3 có chữ ký"
    assert AuditEvent.objects.filter(case=case, action="supplement.create").count() == 1
    assert AuditEvent.objects.filter(case=case, action="case.status_change").count() == 1


@pytest.mark.django_db
def test_need_supplement_rolls_back_on_workflow_error(editor_client):
    # Hồ sơ ACCEPTED không thể chuyển sang NEED_SUPPLEMENT: không được tạo yêu cầu.
    case = make_case(status=CaseStatus.ACCEPTED)
    response = transition(editor_client, case, CaseStatus.NEED_SUPPLEMENT, note="Thiếu")
    assert any("Không thể chuyển trạng thái" in m for m in messages_of(response))
    assert not SupplementRequest.objects.exists()


@pytest.mark.django_db
def test_transition_invalid_status_value(editor_client):
    case = make_case()
    response = transition(editor_client, case, "KHONG_HOP_LE")
    assert response.status_code == 200
    case.refresh_from_db()
    assert case.status == CaseStatus.SUBMITTED
    assert messages_of(response)


@pytest.mark.django_db
def test_transition_note_warns_when_sent_to_customer():
    from apps.backoffice.services import transition_options
    from apps.core.models import CaseStatus
    from tests.factories import PublicationCaseFactory, UserFactory

    editor = UserFactory(role="EDITOR")
    case = PublicationCaseFactory(status=CaseStatus.SUBMITTED)
    opts = {o["to_status"]: o for o in transition_options(editor, case)}
    assert opts[CaseStatus.NEED_SUPPLEMENT]["to_customer"] is True
    assert opts[CaseStatus.ACCEPTED]["to_customer"] is False
