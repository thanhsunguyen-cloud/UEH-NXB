"""Nhóm test 2: Quy trình chuyển trạng thái bảng 7.2 theo từng dòng (parametrize), StatusHistory, AuditEvent."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import (
    AuditEvent,
    CaseStatus,
    DocumentType,
    PublicationMode,
    ReviewResult,
    StatusHistory,
)
from apps.core.workflow import (
    WorkflowError,
    allowed_transitions,
    change_status,
    record_manuscript_review,
)
from tests.factories import ContributorFactory, DocumentFactory, PublicationCaseFactory


def _prepare_submittable(case, linked: bool = False):
    ContributorFactory(case=case)
    DocumentFactory(case=case, doc_type=DocumentType.MANUSCRIPT, version=1)
    DocumentFactory(case=case, doc_type=DocumentType.FORM_2, version=1)
    DocumentFactory(case=case, doc_type=DocumentType.FORM_3, version=1)
    if linked:
        DocumentFactory(case=case, doc_type=DocumentType.FORM_1, version=1)


def _setup_row(row_id: str, customer, editor):
    """Tạo hồ sơ ở đúng trạng thái nguồn, trả về (case, actor, note, prepare_valid_fn, verify_fn)."""
    if row_id == "1_DRAFT_to_SUBMITTED_LINKED":
        case = PublicationCaseFactory(
            owner=customer,
            status=CaseStatus.DRAFT,
            publication_mode=PublicationMode.LINKED,
            partner_name="",
        )

        def prepare():
            case.partner_name = "Công ty Liên kết ABC"
            case.save()
            _prepare_submittable(case, linked=True)

        def verify():
            assert case.submitted_at is not None

        return case, customer, "", prepare, verify, True

    if row_id == "2_SUBMITTED_to_NEED_SUPPLEMENT":
        case = PublicationCaseFactory(owner=customer, status=CaseStatus.SUBMITTED)
        return case, editor, "Bổ sung mục lục chi tiết", None, None, True

    if row_id == "3_NEED_SUPPLEMENT_to_SUBMITTED":
        case = PublicationCaseFactory(owner=customer, status=CaseStatus.NEED_SUPPLEMENT)

        def prepare():
            _prepare_submittable(case, linked=False)

        return case, customer, "", prepare, None, True

    if row_id == "4_SUBMITTED_to_ACCEPTED":
        case = PublicationCaseFactory(owner=customer, status=CaseStatus.SUBMITTED)

        def verify():
            assert case.nxb_code and case.nxb_code.startswith("NXB-")
            assert case.accepted_at is not None

        return case, editor, "", None, verify, False

    if row_id == "5_ACCEPTED_to_EDITING":
        case = PublicationCaseFactory(owner=customer, status=CaseStatus.ACCEPTED)

        def prepare():
            case.primary_editor = editor
            case.save()

        return case, editor, "", prepare, None, True

    if row_id == "6_EDITING_to_REVIEW_APPROVED":
        case = PublicationCaseFactory(
            owner=customer,
            primary_editor=editor,
            status=CaseStatus.EDITING,
        )
        ms = DocumentFactory(case=case, doc_type=DocumentType.MANUSCRIPT, version=1)
        f4 = DocumentFactory(case=case, doc_type=DocumentType.FORM_4, version=1, uploaded_by=editor)

        def prepare():
            record_manuscript_review(
                case=case,
                manuscript=ms,
                form4=f4,
                result=ReviewResult.APPROVED,
                confirmed_by=editor,
            )

        return case, editor, "", prepare, None, True

    if row_id == "7_EDITING_to_REVISION_REQUIRED":
        case = PublicationCaseFactory(
            owner=customer,
            primary_editor=editor,
            status=CaseStatus.EDITING,
        )
        ms = DocumentFactory(case=case, doc_type=DocumentType.MANUSCRIPT, version=1)
        f4 = DocumentFactory(case=case, doc_type=DocumentType.FORM_4, version=1, uploaded_by=editor)

        def prepare():
            record_manuscript_review(
                case=case,
                manuscript=ms,
                form4=f4,
                result=ReviewResult.REVISION_REQUIRED,
                confirmed_by=editor,
                note="Sửa chương 2",
            )

        return case, editor, "", prepare, None, True

    if row_id == "8_EDITING_to_REJECTED":
        case = PublicationCaseFactory(
            owner=customer,
            primary_editor=editor,
            status=CaseStatus.EDITING,
        )
        ms = DocumentFactory(case=case, doc_type=DocumentType.MANUSCRIPT, version=1)
        f4 = DocumentFactory(case=case, doc_type=DocumentType.FORM_4, version=1, uploaded_by=editor)

        def prepare():
            record_manuscript_review(
                case=case,
                manuscript=ms,
                form4=f4,
                result=ReviewResult.REJECTED,
                confirmed_by=editor,
                note="Không phù hợp tôn chỉ xuất bản",
            )

        return case, editor, "", prepare, None, True

    if row_id == "9_REVISION_REQUIRED_to_EDITING":
        case = PublicationCaseFactory(
            owner=customer,
            primary_editor=editor,
            status=CaseStatus.REVISION_REQUIRED,
        )
        ms_v1 = DocumentFactory(case=case, doc_type=DocumentType.MANUSCRIPT, version=1)
        f4_v1 = DocumentFactory(
            case=case,
            doc_type=DocumentType.FORM_4,
            version=1,
            uploaded_by=editor,
        )
        record_manuscript_review(
            case=case,
            manuscript=ms_v1,
            form4=f4_v1,
            result=ReviewResult.REVISION_REQUIRED,
            confirmed_by=editor,
        )

        def prepare():
            DocumentFactory(
                case=case,
                doc_type=DocumentType.MANUSCRIPT,
                version=2,
                uploaded_by=customer,
            )

        return case, editor, "", prepare, None, True

    if row_id == "10_REVIEW_APPROVED_to_REGISTERED":
        case = PublicationCaseFactory(
            owner=customer,
            primary_editor=editor,
            status=CaseStatus.REVIEW_APPROVED,
        )

        def prepare():
            case.isbn = "978-604-346-001-8"
            case.registration_number = "123/CXBIPH"
            case.registration_date = date(2026, 6, 1)
            case.save()
            DocumentFactory(case=case, doc_type=DocumentType.FORM_5, version=1, uploaded_by=editor)

        return case, editor, "", prepare, None, True

    if row_id == "11_REGISTERED_to_DECISION_ISSUED_LINKED":
        case = PublicationCaseFactory(
            owner=customer,
            primary_editor=editor,
            status=CaseStatus.REGISTERED,
            publication_mode=PublicationMode.LINKED,
            partner_name="Đối tác Liên kết",
        )

        def prepare():
            case.decision_number = "10/QĐ-NXB"
            case.decision_date = date(2026, 6, 10)
            case.contract_number = "HDLK-01/2026"
            case.save()
            DocumentFactory(case=case, doc_type=DocumentType.FORM_6, version=1, uploaded_by=editor)
            DocumentFactory(case=case, doc_type=DocumentType.FORM_7, version=1, uploaded_by=editor)

        return case, editor, "", prepare, None, True

    if row_id == "12_DECISION_ISSUED_to_DEPOSITED":
        case = PublicationCaseFactory(
            owner=customer,
            primary_editor=editor,
            status=CaseStatus.DECISION_ISSUED,
        )

        def prepare():
            case.deposit_date = date(2026, 7, 1)
            case.save()
            DocumentFactory(case=case, doc_type=DocumentType.FORM_9, version=1, uploaded_by=editor)

        return case, editor, "", prepare, None, True

    if row_id == "13_DEPOSITED_to_COMPLETED":
        case = PublicationCaseFactory(
            owner=customer,
            primary_editor=editor,
            status=CaseStatus.DEPOSITED,
        )
        return case, editor, "", None, None, False

    if row_id == "14_COMPLETED_to_ARCHIVED":
        case = PublicationCaseFactory(
            owner=customer,
            primary_editor=editor,
            status=CaseStatus.COMPLETED,
        )
        return case, editor, "", None, None, False

    if row_id == "15_REJECTED_to_ARCHIVED":
        case = PublicationCaseFactory(
            owner=customer,
            primary_editor=editor,
            status=CaseStatus.REJECTED,
        )
        return case, editor, "", None, None, False

    raise AssertionError(f"Unknown row_id: {row_id}")


TABLE_7_2_ROWS = [
    ("1_DRAFT_to_SUBMITTED_LINKED", CaseStatus.SUBMITTED),
    ("2_SUBMITTED_to_NEED_SUPPLEMENT", CaseStatus.NEED_SUPPLEMENT),
    ("3_NEED_SUPPLEMENT_to_SUBMITTED", CaseStatus.SUBMITTED),
    ("4_SUBMITTED_to_ACCEPTED", CaseStatus.ACCEPTED),
    ("5_ACCEPTED_to_EDITING", CaseStatus.EDITING),
    ("6_EDITING_to_REVIEW_APPROVED", CaseStatus.REVIEW_APPROVED),
    ("7_EDITING_to_REVISION_REQUIRED", CaseStatus.REVISION_REQUIRED),
    ("8_EDITING_to_REJECTED", CaseStatus.REJECTED),
    ("9_REVISION_REQUIRED_to_EDITING", CaseStatus.EDITING),
    ("10_REVIEW_APPROVED_to_REGISTERED", CaseStatus.REGISTERED),
    ("11_REGISTERED_to_DECISION_ISSUED_LINKED", CaseStatus.DECISION_ISSUED),
    ("12_DECISION_ISSUED_to_DEPOSITED", CaseStatus.DEPOSITED),
    ("13_DEPOSITED_to_COMPLETED", CaseStatus.COMPLETED),
    ("14_COMPLETED_to_ARCHIVED", CaseStatus.ARCHIVED),
    ("15_REJECTED_to_ARCHIVED", CaseStatus.ARCHIVED),
]


@pytest.mark.django_db
def test_direct_status_assignment_is_blocked(customer_a):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.DRAFT)
    case.status = CaseStatus.SUBMITTED
    with pytest.raises(ValidationError):
        case.save()


@pytest.mark.django_db
def test_invalid_transition_and_wrong_actor_are_rejected(customer_a, editor_none):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.DRAFT)
    assert allowed_transitions(customer_a, case) == [CaseStatus.SUBMITTED]
    assert allowed_transitions(editor_none, case) == []

    with pytest.raises(WorkflowError):
        change_status(case, CaseStatus.COMPLETED, editor_none)

    with pytest.raises(WorkflowError):
        change_status(case, CaseStatus.SUBMITTED, editor_none)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("row_id", "to_status"), TABLE_7_2_ROWS, ids=[r[0] for r in TABLE_7_2_ROWS]
)
def test_table_7_2_transition_row(row_id, to_status, customer_a, editor_none):
    case, actor, note, prepare_fn, verify_fn, has_missing_case = _setup_row(
        row_id,
        customer_a,
        editor_none,
    )

    # 1. Thiếu điều kiện -> bắt buộc báo WorkflowError
    if has_missing_case:
        with pytest.raises(WorkflowError):
            change_status(case, to_status, actor, note="")

    # 2. Đủ điều kiện -> chuyển thành công, sinh đúng 1 StatusHistory và 1 AuditEvent
    if prepare_fn is not None:
        prepare_fn()

    from_status = case.status
    change_status(case, to_status, actor, note=note)
    assert case.status == to_status
    if verify_fn is not None:
        verify_fn()

    assert (
        StatusHistory.objects.filter(
            case=case,
            from_status=from_status,
            to_status=to_status,
        ).count()
        == 1
    )
    assert (
        AuditEvent.objects.filter(
            case=case,
            action="case.status_change",
        ).count()
        == 1
    )
