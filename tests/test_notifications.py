"""Test gói M4 – thông báo email khi hồ sơ đổi trạng thái (dùng mail.outbox của Django)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse

from apps.core.finance import create_receivable
from apps.core.models import (
    AuditEvent,
    CaseNote,
    CaseStatus,
    DocumentType,
    NoteVisibility,
    ReviewResult,
)
from apps.core.signals import case_status_changed
from apps.core.workflow import change_status, record_manuscript_review
from apps.notifications import conf
from apps.notifications.emails import (
    EMAIL_RULES,
    FRIENDLY_STATUS_LABELS,
    SUBJECT_PREFIX,
    notify_status_change,
)
from apps.notifications.receivers import on_case_status_changed
from tests.factories import (
    ContributorFactory,
    DocumentFactory,
    EditorFactory,
    FeeTypeFactory,
    PublicationCaseFactory,
    UserFactory,
)

BASE_URL = "https://portal.example.vn"
TECH_CODES = [status.value for status in CaseStatus]


@pytest.fixture(autouse=True)
def _portal_base_url(monkeypatch):
    monkeypatch.setenv("PORTAL_BASE_URL", BASE_URL + "/")


@pytest.fixture
def run(django_capture_on_commit_callbacks):
    """Gọi change_status thật của M0 và chạy các callback on_commit (nơi M0 phát tín hiệu)."""

    def _run(case, to_status, actor, note=""):
        with django_capture_on_commit_callbacks(execute=True):
            change_status(case, to_status, actor=actor, note=note)
        return case

    return _run


def _customer_url(case) -> str:
    return BASE_URL + reverse("customer:case_detail", kwargs={"case_id": case.pk})


def _backoffice_url(case) -> str:
    return BASE_URL + reverse("backoffice:case_detail", kwargs={"case_id": case.pk})


def _submittable(case):
    ContributorFactory(case=case)
    for doc_type in (DocumentType.MANUSCRIPT, DocumentType.FORM_2, DocumentType.FORM_3):
        DocumentFactory(case=case, doc_type=doc_type, version=1)


def _editing_with_review(customer, editor, result):
    case = PublicationCaseFactory(owner=customer, status=CaseStatus.EDITING, primary_editor=editor)
    ms = DocumentFactory(case=case, doc_type=DocumentType.MANUSCRIPT, version=1)
    form4 = DocumentFactory(case=case, doc_type=DocumentType.FORM_4, version=1)
    record_manuscript_review(
        case=case, manuscript=ms, form4=form4, result=result, confirmed_by=editor
    )
    return case


def _bodies(message) -> list[str]:
    return [message.body] + [content for content, _mime in message.alternatives]


def _assert_customer_email(message, case, customer, subject_text):
    assert message.to == [customer.email]
    assert message.subject == f"{SUBJECT_PREFIX} {case.display_code} – {subject_text}"
    assert message.from_email == "nxbkt@ueh.edu.vn"
    assert len(message.alternatives) == 1 and message.alternatives[0][1] == "text/html"
    for body in _bodies(message):
        assert _customer_url(case) in body
        assert case.title in body
        assert "Đây là email tự động, vui lòng không trả lời." in body
        assert "[CẦN NXB CUNG CẤP]" in body
        for code in TECH_CODES:
            assert code not in body
    for code in TECH_CODES:
        assert code not in message.subject


# ---------------------------------------------------------------------------
# Từng dòng bảng mục 3 – qua change_status thật
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_submitted_goes_to_primary_editor(run, customer_a, editor_none):
    other_editor = EditorFactory()
    case = PublicationCaseFactory(owner=customer_a, primary_editor=editor_none)
    _submittable(case)

    run(case, CaseStatus.SUBMITTED, customer_a)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == [editor_none.email]
    assert other_editor.email not in message.to
    assert message.subject == f"{SUBJECT_PREFIX} {case.temp_code} – Có hồ sơ cần xem xét"
    for body in _bodies(message):
        assert _backoffice_url(case) in body
        assert case.title in body
        assert customer_a.full_name in body
        assert "Có hồ sơ mới" in body


@pytest.mark.django_db
def test_submitted_without_primary_editor_goes_to_all_active_editors(run, customer_a):
    editor_1 = EditorFactory(email="btv1@ueh.edu.vn")
    editor_2 = EditorFactory(email="btv2@ueh.edu.vn")
    EditorFactory(email="btv_khoa@ueh.edu.vn", is_active=False)
    UserFactory(email="khach_khac@example.com")
    case = PublicationCaseFactory(owner=customer_a)
    _submittable(case)

    run(case, CaseStatus.SUBMITTED, customer_a)

    recipients = sorted(m.to[0] for m in mail.outbox)
    assert recipients == [editor_1.email, editor_2.email]
    assert all(_backoffice_url(case) in m.body for m in mail.outbox)


@pytest.mark.django_db
def test_submitted_falls_back_when_primary_editor_locked(run, customer_a):
    locked = EditorFactory(is_active=False)
    active = EditorFactory()
    case = PublicationCaseFactory(owner=customer_a, primary_editor=locked)
    _submittable(case)

    run(case, CaseStatus.SUBMITTED, customer_a)

    assert [m.to for m in mail.outbox] == [[active.email]]


@pytest.mark.django_db
def test_resubmission_after_supplement(run, customer_a, editor_none):
    case = PublicationCaseFactory(
        owner=customer_a, status=CaseStatus.NEED_SUPPLEMENT, primary_editor=editor_none
    )
    _submittable(case)

    run(case, CaseStatus.SUBMITTED, customer_a)

    assert len(mail.outbox) == 1
    assert "đã bổ sung và nộp lại" in mail.outbox[0].body


@pytest.mark.django_db
def test_need_supplement(run, customer_a, editor_none):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.SUBMITTED)
    run(case, CaseStatus.NEED_SUPPLEMENT, editor_none, note="Bổ sung Mẫu 2 có chữ ký")

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    _assert_customer_email(message, case, customer_a, "NXB yêu cầu bổ sung hồ sơ")
    for body in _bodies(message):
        assert "Bổ sung Mẫu 2 có chữ ký" in body
        assert FRIENDLY_STATUS_LABELS[CaseStatus.NEED_SUPPLEMENT] in body


@pytest.mark.django_db
def test_accepted_contains_nxb_code(run, customer_a, editor_none):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.SUBMITTED)
    run(case, CaseStatus.ACCEPTED, editor_none)

    case.refresh_from_db()
    assert case.nxb_code
    message = mail.outbox[0]
    assert len(mail.outbox) == 1
    _assert_customer_email(message, case, customer_a, "Hồ sơ đã được tiếp nhận")
    assert case.nxb_code in message.subject
    for body in _bodies(message):
        assert f"Mã NXB: {case.nxb_code}" in body


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("result", "to_status", "subject", "with_note"),
    [
        (
            ReviewResult.REVISION_REQUIRED,
            CaseStatus.REVISION_REQUIRED,
            "Cần chỉnh sửa bản thảo",
            True,
        ),
        (ReviewResult.APPROVED, CaseStatus.REVIEW_APPROVED, "Bản thảo đã được duyệt", False),
        (ReviewResult.REJECTED, CaseStatus.REJECTED, "Hồ sơ không được chấp nhận", True),
    ],
)
def test_review_outcomes(run, customer_a, editor_none, result, to_status, subject, with_note):
    case = _editing_with_review(customer_a, editor_none, result)
    note = "Ghi chú gửi khách hàng về bản thảo"
    run(case, to_status, editor_none, note=note)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    _assert_customer_email(message, case, customer_a, subject)
    for body in _bodies(message):
        assert (note in body) is with_note


@pytest.mark.django_db
def test_rejected_without_note(run, customer_a, editor_none):
    case = _editing_with_review(customer_a, editor_none, ReviewResult.REJECTED)
    run(case, CaseStatus.REJECTED, editor_none)

    assert len(mail.outbox) == 1
    assert "Lý do:" not in mail.outbox[0].body


@pytest.mark.django_db
def test_registered_contains_isbn(run, customer_a, editor_none):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.REVIEW_APPROVED)
    case.isbn = "978-604-346-001-8"
    case.registration_number = "123/CXBIPH"
    case.registration_date = date(2026, 6, 1)
    case.save()
    DocumentFactory(case=case, doc_type=DocumentType.FORM_5, version=1)

    run(case, CaseStatus.REGISTERED, editor_none)

    case.refresh_from_db()
    message = mail.outbox[0]
    assert len(mail.outbox) == 1
    _assert_customer_email(message, case, customer_a, "Đã đăng ký xuất bản")
    assert "9786043460018" in message.subject
    for body in _bodies(message):
        assert "ISBN: 9786043460018" in body


@pytest.mark.django_db
def test_decision_issued(run, customer_a, editor_none):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.REGISTERED)
    case.decision_number = "45/QĐ-NXBKT"
    case.decision_date = date(2026, 7, 1)
    case.save()
    DocumentFactory(case=case, doc_type=DocumentType.FORM_6, version=1)

    run(case, CaseStatus.DECISION_ISSUED, editor_none)

    assert len(mail.outbox) == 1
    _assert_customer_email(mail.outbox[0], case, customer_a, "Đã có quyết định xuất bản")


@pytest.mark.django_db
def test_completed(run, customer_a, editor_none):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.DEPOSITED)
    run(case, CaseStatus.COMPLETED, editor_none)

    assert len(mail.outbox) == 1
    _assert_customer_email(mail.outbox[0], case, customer_a, "Hồ sơ hoàn tất")


# ---------------------------------------------------------------------------
# Trạng thái không gửi
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_editing_sends_nothing(run, customer_a, editor_none):
    case = PublicationCaseFactory(
        owner=customer_a, status=CaseStatus.ACCEPTED, primary_editor=editor_none
    )
    run(case, CaseStatus.EDITING, editor_none)
    assert mail.outbox == []


@pytest.mark.django_db
def test_deposited_sends_nothing(run, customer_a, editor_none):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.DECISION_ISSUED)
    case.deposit_date = date(2026, 8, 1)
    case.save()
    DocumentFactory(case=case, doc_type=DocumentType.FORM_9, version=1)
    run(case, CaseStatus.DEPOSITED, editor_none)
    assert mail.outbox == []


@pytest.mark.django_db
def test_archived_sends_nothing(run, customer_a, editor_none):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.COMPLETED)
    run(case, CaseStatus.ARCHIVED, editor_none)
    assert mail.outbox == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "to_status",
    [CaseStatus.EDITING, CaseStatus.DEPOSITED, CaseStatus.ARCHIVED, CaseStatus.DRAFT],
)
def test_non_notified_statuses_direct(customer_a, editor_none, to_status):
    case = PublicationCaseFactory(owner=customer_a)
    assert to_status not in EMAIL_RULES
    sent = notify_status_change(
        case=case, from_status=CaseStatus.DRAFT, to_status=to_status, actor=editor_none
    )
    assert sent == 0
    assert mail.outbox == []


# ---------------------------------------------------------------------------
# Lọc người nhận
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_not_sent_to_actor(run, editor_none):
    # Người thao tác cũng là BTV phụ trách chính -> không tự gửi cho mình
    customer = UserFactory()
    case = PublicationCaseFactory(owner=customer, primary_editor=editor_none)
    sent = notify_status_change(
        case=case, from_status=CaseStatus.DRAFT, to_status=CaseStatus.SUBMITTED, actor=editor_none
    )
    assert sent == 0
    assert mail.outbox == []


@pytest.mark.django_db
def test_actor_excluded_from_all_editors(customer_a):
    actor = EditorFactory()
    other = EditorFactory()
    case = PublicationCaseFactory(owner=customer_a)
    notify_status_change(
        case=case, from_status=CaseStatus.DRAFT, to_status=CaseStatus.SUBMITTED, actor=actor
    )
    assert [m.to for m in mail.outbox] == [[other.email]]


@pytest.mark.django_db
def test_customer_actor_not_emailed(customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    sent = notify_status_change(
        case=case, from_status=CaseStatus.EDITING, to_status=CaseStatus.COMPLETED, actor=customer_a
    )
    assert sent == 0
    assert mail.outbox == []


@pytest.mark.django_db
def test_locked_owner_not_emailed(run, editor_none):
    owner = UserFactory(is_active=False)
    case = PublicationCaseFactory(owner=owner, status=CaseStatus.DEPOSITED)
    run(case, CaseStatus.COMPLETED, editor_none)
    assert mail.outbox == []
    assert not AuditEvent.objects.filter(action__startswith="email.").exists()


@pytest.mark.django_db
def test_owner_without_email_not_emailed(editor_none):
    owner = UserFactory(email="")
    case = PublicationCaseFactory(owner=owner)
    sent = notify_status_change(
        case=case,
        from_status=CaseStatus.DEPOSITED,
        to_status=CaseStatus.COMPLETED,
        actor=editor_none,
    )
    assert sent == 0
    assert mail.outbox == []


@pytest.mark.django_db
def test_editors_without_email_skipped(customer_a):
    EditorFactory(email="")
    good = EditorFactory()
    case = PublicationCaseFactory(owner=customer_a)
    notify_status_change(
        case=case, from_status=CaseStatus.DRAFT, to_status=CaseStatus.SUBMITTED, actor=customer_a
    )
    assert [m.to for m in mail.outbox] == [[good.email]]


# ---------------------------------------------------------------------------
# Bảo mật nội dung
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_customer_email_hides_internal_notes_and_money(run, customer_a, editor_manage):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.SUBMITTED)
    CaseNote.objects.create(
        case=case,
        author=editor_manage,
        body="GHI CHÚ NỘI BỘ: khách nợ phí cũ",
        visibility=NoteVisibility.INTERNAL,
    )
    create_receivable(
        actor=editor_manage,
        case=case,
        fee_type=FeeTypeFactory(),
        amount=Decimal("7350000"),
    )

    run(case, CaseStatus.NEED_SUPPLEMENT, editor_manage, note="Bổ sung mục lục")

    message = mail.outbox[0]
    for text in [message.subject, *_bodies(message)]:
        assert "GHI CHÚ NỘI BỘ" not in text
        for money in ("7350000", "7.350.000", "7,350,000", "7350"):
            assert money not in text
        assert "đồng" not in text.lower() and "VNĐ" not in text
        for code in TECH_CODES:
            assert code not in text


@pytest.mark.django_db
def test_html_body_escapes_note(run, customer_a, editor_none):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.SUBMITTED)
    run(case, CaseStatus.NEED_SUPPLEMENT, editor_none, note="<script>x</script> & Mẫu 2")
    message = mail.outbox[0]
    html = message.alternatives[0][0]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    # Bản văn bản thuần giữ nguyên ký tự
    assert "<script>x</script> & Mẫu 2" in message.body


# ---------------------------------------------------------------------------
# Độ tin cậy và nhật ký
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sent_event_logged_without_content(run, customer_a, editor_none):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.DEPOSITED)
    run(case, CaseStatus.COMPLETED, editor_none)

    event = AuditEvent.objects.get(action="email.sent")
    assert event.case_id == case.pk
    assert event.object_id == str(case.pk)
    assert event.data == {
        "email_type": "completed",
        "recipient": customer_a.email,
        "case_code": case.display_code,
    }


@pytest.mark.django_db
def test_backend_failure_does_not_break_change_status(run, settings, customer_a, editor_none):
    settings.EMAIL_BACKEND = "tests.test_notifications.BrokenEmailBackend"
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.DEPOSITED)

    run(case, CaseStatus.COMPLETED, editor_none)

    case.refresh_from_db()
    assert case.status == CaseStatus.COMPLETED
    assert AuditEvent.objects.filter(action="case.status_change", case=case).exists()
    event = AuditEvent.objects.get(action="email.failed")
    assert event.data["email_type"] == "completed"
    assert event.data["recipient"] == customer_a.email
    assert event.data["error"].startswith("ConnectionRefusedError")
    assert len(event.data["error"]) <= 200
    assert not AuditEvent.objects.filter(action="email.sent").exists()


@pytest.mark.django_db
def test_failed_audit_log_is_swallowed(monkeypatch, settings, customer_a, editor_none):
    settings.EMAIL_BACKEND = "tests.test_notifications.BrokenEmailBackend"

    def broken_log_event(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("apps.notifications.emails.log_event", broken_log_event)
    case = PublicationCaseFactory(owner=customer_a)
    sent = notify_status_change(
        case=case,
        from_status=CaseStatus.DEPOSITED,
        to_status=CaseStatus.COMPLETED,
        actor=editor_none,
    )
    assert sent == 0


@pytest.mark.django_db
def test_receiver_swallows_unexpected_errors(monkeypatch, customer_a, editor_none):
    def boom(**kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("apps.notifications.receivers.notify_status_change", boom)
    case = PublicationCaseFactory(owner=customer_a)
    # Không ném lỗi ra ngoài
    on_case_status_changed(
        sender=None,
        case=case,
        from_status=CaseStatus.DEPOSITED,
        to_status=CaseStatus.COMPLETED,
        actor=editor_none,
        note=None,
    )


@pytest.mark.django_db
def test_receiver_connected_to_signal(customer_a, editor_none):
    case = PublicationCaseFactory(owner=customer_a)
    case_status_changed.send(
        sender=None,
        case=case,
        from_status=CaseStatus.DEPOSITED,
        to_status=CaseStatus.COMPLETED,
        actor=editor_none,
        note="",
    )
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_deleted_case_sends_nothing(customer_a, editor_none):
    case = PublicationCaseFactory.build(owner=customer_a)
    sent = notify_status_change(
        case=case,
        from_status=CaseStatus.DEPOSITED,
        to_status=CaseStatus.COMPLETED,
        actor=editor_none,
    )
    assert sent == 0


def test_portal_base_url_default(monkeypatch):
    monkeypatch.delenv("PORTAL_BASE_URL", raising=False)
    assert conf.get_portal_base_url() == "http://localhost:8000"
    monkeypatch.setenv("PORTAL_BASE_URL", "  ")
    assert conf.get_portal_base_url() == "http://localhost:8000"
    monkeypatch.setenv("PORTAL_BASE_URL", "https://a.vn/")
    assert conf.get_portal_base_url() == "https://a.vn"


class BrokenEmailBackend:
    """Backend email giả lập máy chủ SMTP không kết nối được."""

    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, messages):
        raise ConnectionRefusedError("SMTP server unavailable " + "x" * 500)
