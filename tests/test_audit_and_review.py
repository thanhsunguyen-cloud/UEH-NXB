"""Nhóm test 5 & 6: AuditEvent & StatusHistory bất biến (cả instance lẫn bulk) và ManuscriptReview cross-case."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.core.audit import log_event
from apps.core.models import (
    AuditEvent,
    CaseStatus,
    DocumentType,
    ManuscriptReview,
    ReviewResult,
    StatusHistory,
)
from tests.factories import DocumentFactory, PublicationCaseFactory


@pytest.mark.django_db
def test_audit_event_cannot_be_updated_or_deleted_individually_or_in_bulk(editor_none):
    event = log_event(
        actor=editor_none,
        action="test.action",
        object_type="System",
        object_id="1",
        data={"k": "v"},
    )
    event.action = "tampered.action"
    with pytest.raises(PermissionDenied):
        event.save()
    with pytest.raises(PermissionDenied):
        event.delete()
    with pytest.raises(PermissionDenied):
        AuditEvent.objects.filter(pk=event.pk).delete()
    with pytest.raises(PermissionDenied):
        AuditEvent.objects.filter(pk=event.pk).update(action="tampered.bulk")

    event.refresh_from_db()
    assert event.action == "test.action"


@pytest.mark.django_db
def test_status_history_cannot_be_updated_or_deleted_individually_or_in_bulk(
    customer_a,
    editor_none,
):
    case = PublicationCaseFactory(owner=customer_a)
    history = StatusHistory.objects.create(
        case=case,
        from_status=CaseStatus.DRAFT,
        to_status=CaseStatus.SUBMITTED,
        actor=customer_a,
        note="Nộp lần 1",
    )
    history.note = "Sửa lén"
    with pytest.raises(PermissionDenied):
        history.save()
    with pytest.raises(PermissionDenied):
        history.delete()
    with pytest.raises(PermissionDenied):
        StatusHistory.objects.filter(pk=history.pk).delete()
    with pytest.raises(PermissionDenied):
        StatusHistory.objects.filter(pk=history.pk).update(note="Sửa hàng loạt")

    history.refresh_from_db()
    assert history.note == "Nộp lần 1"


@pytest.mark.django_db
def test_manuscript_review_rejects_documents_from_other_case(customer_a, customer_b, editor_none):
    case_a = PublicationCaseFactory(owner=customer_a)
    case_b = PublicationCaseFactory(owner=customer_b)

    ms_a = DocumentFactory(case=case_a, doc_type=DocumentType.MANUSCRIPT)
    f4_a = DocumentFactory(case=case_a, doc_type=DocumentType.FORM_4, uploaded_by=editor_none)
    ms_b = DocumentFactory(case=case_b, doc_type=DocumentType.MANUSCRIPT)
    f4_b = DocumentFactory(case=case_b, doc_type=DocumentType.FORM_4, uploaded_by=editor_none)

    # Bản thảo thuộc hồ sơ khác -> từ chối
    with pytest.raises(ValidationError):
        ManuscriptReview.objects.create(
            case=case_a,
            manuscript=ms_b,
            form4=f4_a,
            result=ReviewResult.APPROVED,
            confirmed_by=editor_none,
        )

    # Mẫu 4 thuộc hồ sơ khác -> từ chối
    with pytest.raises(ValidationError):
        ManuscriptReview.objects.create(
            case=case_a,
            manuscript=ms_a,
            form4=f4_b,
            result=ReviewResult.APPROVED,
            confirmed_by=editor_none,
        )
