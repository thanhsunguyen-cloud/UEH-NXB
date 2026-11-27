"""Quy tắc và hàm gửi email thông báo khi hồ sơ đổi trạng thái (Gói M4, mục 3–5).

- Chỉ đọc dữ liệu hồ sơ, không sửa luồng nghiệp vụ.
- Không đưa số liệu tài chính, không đưa ghi chú nội bộ (CaseNote INTERNAL) vào email.
- Mọi lỗi gửi được bắt lại và ghi AuditEvent ``email.failed``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

from apps.accounts.models import User, UserRole
from apps.core.audit import log_event
from apps.core.models import CaseStatus, PublicationCase
from apps.notifications.conf import get_portal_base_url

logger = logging.getLogger(__name__)

SUBJECT_PREFIX = "[NXB Kinh tế TP.HCM]"
AUDIENCE_CUSTOMER = "customer"
AUDIENCE_EDITOR = "editor"
MAX_ERROR_LENGTH = 200

# Nhãn trạng thái dễ hiểu cho người nhận email (không dùng mã kỹ thuật).
FRIENDLY_STATUS_LABELS: dict[str, str] = {
    CaseStatus.DRAFT: "Hồ sơ đang soạn",
    CaseStatus.SUBMITTED: "Đã nộp, chờ NXB xem xét",
    CaseStatus.NEED_SUPPLEMENT: "NXB yêu cầu bổ sung hồ sơ",
    CaseStatus.ACCEPTED: "NXB đã tiếp nhận hồ sơ",
    CaseStatus.EDITING: "NXB đang biên tập",
    CaseStatus.REVISION_REQUIRED: "Cần chỉnh sửa bản thảo",
    CaseStatus.REVIEW_APPROVED: "Bản thảo đã được duyệt",
    CaseStatus.REJECTED: "Hồ sơ không được chấp nhận",
    CaseStatus.REGISTERED: "Đã đăng ký xuất bản",
    CaseStatus.DECISION_ISSUED: "Đã có quyết định xuất bản",
    CaseStatus.DEPOSITED: "Đã nộp lưu chiểu",
    CaseStatus.COMPLETED: "Hồ sơ hoàn tất",
    CaseStatus.ARCHIVED: "Đã lưu trữ",
}


@dataclass(frozen=True)
class EmailRule:
    kind: str
    subject: str
    audience: str
    include_note: bool = False


# Bảng mục 3 của gói M4. Trạng thái không có trong bảng thì không gửi.
EMAIL_RULES: dict[str, EmailRule] = {
    CaseStatus.SUBMITTED: EmailRule("submitted", "Có hồ sơ cần xem xét", AUDIENCE_EDITOR),
    CaseStatus.NEED_SUPPLEMENT: EmailRule(
        "need_supplement", "NXB yêu cầu bổ sung hồ sơ", AUDIENCE_CUSTOMER, include_note=True
    ),
    CaseStatus.ACCEPTED: EmailRule("accepted", "Hồ sơ đã được tiếp nhận", AUDIENCE_CUSTOMER),
    CaseStatus.REVISION_REQUIRED: EmailRule(
        "revision_required", "Cần chỉnh sửa bản thảo", AUDIENCE_CUSTOMER, include_note=True
    ),
    CaseStatus.REVIEW_APPROVED: EmailRule(
        "review_approved", "Bản thảo đã được duyệt", AUDIENCE_CUSTOMER
    ),
    CaseStatus.REJECTED: EmailRule(
        "rejected", "Hồ sơ không được chấp nhận", AUDIENCE_CUSTOMER, include_note=True
    ),
    CaseStatus.REGISTERED: EmailRule("registered", "Đã đăng ký xuất bản", AUDIENCE_CUSTOMER),
    CaseStatus.DECISION_ISSUED: EmailRule(
        "decision_issued", "Đã có quyết định xuất bản", AUDIENCE_CUSTOMER
    ),
    CaseStatus.COMPLETED: EmailRule("completed", "Hồ sơ hoàn tất", AUDIENCE_CUSTOMER),
}


def friendly_status_label(status: str) -> str:
    return FRIENDLY_STATUS_LABELS.get(status, "")


def _can_receive(user, actor) -> bool:
    if user is None or not user.is_active or not (user.email or "").strip():
        return False
    return not (actor is not None and getattr(actor, "pk", None) == user.pk)


def _editor_recipients(case: PublicationCase, actor) -> list:
    """BTV phụ trách chính; nếu chưa có (hoặc bị khóa / không có email) thì mọi EDITOR hoạt động."""
    editor = case.primary_editor
    if editor is not None and editor.role == UserRole.EDITOR and _can_receive(editor, None):
        return [editor] if _can_receive(editor, actor) else []
    editors = User.objects.filter(role=UserRole.EDITOR, is_active=True).order_by("email")
    return [user for user in editors if _can_receive(user, actor)]


def get_recipients(case: PublicationCase, rule: EmailRule, actor) -> list:
    if rule.audience == AUDIENCE_EDITOR:
        return _editor_recipients(case, actor)
    owner = case.owner
    return [owner] if _can_receive(owner, actor) else []


def build_case_url(case: PublicationCase, audience: str) -> str:
    namespace = "backoffice" if audience == AUDIENCE_EDITOR else "customer"
    path = reverse(f"{namespace}:case_detail", kwargs={"case_id": case.pk})
    return f"{get_portal_base_url()}{path}"


def build_subject(case: PublicationCase, rule: EmailRule) -> str:
    return f"{SUBJECT_PREFIX} {case.display_code} – {rule.subject}"


def build_context(
    case: PublicationCase, rule: EmailRule, recipient, from_status: str, note: str
) -> dict:
    return {
        "case": case,
        "title": case.title,
        "display_code": case.display_code,
        "nxb_code": case.nxb_code or "",
        "isbn": case.isbn or "",
        "owner_name": case.owner.full_name or case.owner.email,
        "recipient_name": recipient.full_name or recipient.email,
        "status_label": friendly_status_label(case.status),
        "is_resubmission": from_status == CaseStatus.NEED_SUPPLEMENT,
        "note": (note or "").strip() if rule.include_note else "",
        "case_url": build_case_url(case, rule.audience),
    }


def _short_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]


def _log(action: str, case: PublicationCase, data: dict) -> None:
    try:
        log_event(
            action=action,
            object_type="PublicationCase",
            object_id=str(case.pk),
            case=case,
            data=data,
        )
    except Exception:  # noqa: BLE001 – nhật ký lỗi cũng không được làm hỏng nghiệp vụ
        logger.exception("M4: không ghi được nhật ký %s cho hồ sơ %s", action, case.pk)


def send_one(case: PublicationCase, rule: EmailRule, recipient, from_status: str, note: str):
    """Gửi 1 email cho 1 người nhận; trả về True nếu gửi thành công."""
    try:
        context = build_context(case, rule, recipient, from_status, note)
        text_body = render_to_string(f"notifications/{rule.kind}.txt", context)
        html_body = render_to_string(f"notifications/{rule.kind}.html", context)
        message = EmailMultiAlternatives(
            subject=build_subject(case, rule),
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient.email],
        )
        message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 – bắt mọi lỗi gửi (mục 5)
        logger.warning("M4: gửi email %s tới %s thất bại: %s", rule.kind, recipient.email, exc)
        _log(
            "email.failed",
            case,
            {"email_type": rule.kind, "recipient": recipient.email, "error": _short_error(exc)},
        )
        return False
    _log(
        "email.sent",
        case,
        {"email_type": rule.kind, "recipient": recipient.email, "case_code": case.display_code},
    )
    return True


def notify_status_change(*, case, from_status: str, to_status: str, actor=None, note: str = ""):
    """Gửi email theo bảng EMAIL_RULES; trả về số email gửi thành công."""
    rule = EMAIL_RULES.get(to_status)
    if rule is None:
        return 0
    # Đọc lại hồ sơ để có mã NXB/ISBN mới nhất (mã hiển thị trong tiêu đề)
    fresh_case = (
        PublicationCase.objects.select_related("owner", "primary_editor").filter(pk=case.pk).first()
    )
    if fresh_case is None:
        return 0
    sent = 0
    for recipient in get_recipients(fresh_case, rule, actor):
        if send_one(fresh_case, rule, recipient, from_status, note):
            sent += 1
    return sent
