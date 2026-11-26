"""Lớp quy trình trạng thái hồ sơ xuất bản (mục 7).

- Bảng chuyển trạng thái khai báo dạng dữ liệu chuẩn hóa theo bảng 7.2.
- Hàm change_status() là điểm duy nhất được phép thay đổi PublicationCase.status.
- Tự động ghi đúng 1 StatusHistory + 1 AuditEvent trong cùng 1 transaction và phát
  tín hiệu case_status_changed cho M4.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import UserRole
from apps.core.audit import log_event
from apps.core.codes import issue_nxb_code, validate_isbn13
from apps.core.models import (
    CaseStatus,
    DocumentType,
    ManuscriptReview,
    PublicationCase,
    PublicationMode,
    ReviewResult,
    StatusHistory,
)
from apps.core.permissions import can_change_status
from apps.core.signals import case_status_changed


class WorkflowError(Exception):
    """Ngoại lệ quy trình khi thiếu điều kiện hoặc chuyển trạng thái không hợp lệ."""

    def __init__(self, message: str, missing: list[str] | None = None):
        self.missing = missing or []
        super().__init__(message)


@dataclass(frozen=True)
class TransitionRule:
    from_status: str
    to_status: str
    actor_role: str
    validator: Callable[[PublicationCase, str], list[str]]


def _has_doc(case: PublicationCase, doc_type: str) -> bool:
    return case.documents.filter(doc_type=doc_type).exists()


def _check_submit(case: PublicationCase, note: str) -> list[str]:
    missing: list[str] = []
    if not _has_doc(case, DocumentType.MANUSCRIPT):
        missing.append("Bản thảo (MANUSCRIPT)")
    if not _has_doc(case, DocumentType.FORM_2):
        missing.append("Mẫu 2 (FORM_2)")
    if not _has_doc(case, DocumentType.FORM_3):
        missing.append("Mẫu 3 (FORM_3)")
    if case.publication_mode == PublicationMode.LINKED:
        if not _has_doc(case, DocumentType.FORM_1):
            missing.append("Mẫu 1 (FORM_1) cho hình thức xuất bản liên kết")
        if not (case.partner_name or "").strip():
            missing.append("Tên đơn vị liên kết (partner_name)")
    if not case.contributors.exists():
        missing.append("Ít nhất 01 tác giả (Contributor)")
    return missing


def _check_need_supplement(case: PublicationCase, note: str) -> list[str]:
    if not (note or "").strip():
        return ["Ghi chú yêu cầu bổ sung (bắt buộc)"]
    return []


def _check_none(case: PublicationCase, note: str) -> list[str]:
    return []


def _check_editing_from_accepted(case: PublicationCase, note: str) -> list[str]:
    if not case.primary_editor_id:
        return ["Biên tập viên phụ trách chính (primary_editor)"]
    return []


def _make_review_checker(expected_result: str) -> Callable[[PublicationCase, str], list[str]]:
    def _check(case: PublicationCase, note: str) -> list[str]:
        latest = case.reviews.order_by("-confirmed_at", "-id").first()
        if latest is None or latest.result != expected_result:
            return [
                f"Kết quả duyệt bản thảo (ManuscriptReview) mới nhất có kết quả {expected_result}"
            ]
        return []

    return _check


def _check_revision_to_editing(case: PublicationCase, note: str) -> list[str]:
    latest_review = case.reviews.order_by("-confirmed_at", "-id").first()
    if latest_review is None:
        return ["Chưa có bản ghi duyệt bản thảo trước đó để đối chiếu phiên bản"]
    newer_exists = case.documents.filter(
        doc_type=DocumentType.MANUSCRIPT,
        version__gt=latest_review.manuscript.version,
    ).exists()
    if not newer_exists:
        return [
            f"Bản thảo phiên bản mới hơn phiên bản đã duyệt (v{latest_review.manuscript.version})"
        ]
    return []


def _check_registered(case: PublicationCase, note: str) -> list[str]:
    missing: list[str] = []
    if not (case.isbn or "").strip():
        missing.append("Mã ISBN-13 hợp lệ")
    else:
        try:
            validate_isbn13(case.isbn)
        except ValidationError as exc:
            missing.append(f"Mã ISBN-13 không hợp lệ ({'; '.join(exc.messages)})")
    if not (case.registration_number or "").strip():
        missing.append("Số xác nhận đăng ký xuất bản (registration_number)")
    if not case.registration_date:
        missing.append("Ngày xác nhận đăng ký xuất bản (registration_date)")
    if not _has_doc(case, DocumentType.FORM_5):
        missing.append("Mẫu 5 (FORM_5)")
    return missing


def _check_decision_issued(case: PublicationCase, note: str) -> list[str]:
    missing: list[str] = []
    if not (case.decision_number or "").strip():
        missing.append("Số quyết định xuất bản (decision_number)")
    if not case.decision_date:
        missing.append("Ngày quyết định xuất bản (decision_date)")
    if not _has_doc(case, DocumentType.FORM_6):
        missing.append("Mẫu 6 (FORM_6)")
    if case.publication_mode == PublicationMode.LINKED:
        if not _has_doc(case, DocumentType.FORM_7):
            missing.append("Mẫu 7 — Hợp đồng liên kết (FORM_7)")
        if not (case.contract_number or "").strip():
            missing.append("Số hợp đồng liên kết (contract_number)")
    return missing


def _check_deposited(case: PublicationCase, note: str) -> list[str]:
    missing: list[str] = []
    if not _has_doc(case, DocumentType.FORM_9):
        missing.append("Mẫu 9 — Nộp lưu chiểu (FORM_9)")
    if not case.deposit_date:
        missing.append("Ngày nộp lưu chiểu (deposit_date)")
    return missing


# Bảng chuyển trạng thái khai báo dạng dữ liệu theo đúng mục 7.2
TRANSITION_RULES: tuple[TransitionRule, ...] = (
    TransitionRule(CaseStatus.DRAFT, CaseStatus.SUBMITTED, UserRole.CUSTOMER, _check_submit),
    TransitionRule(
        CaseStatus.SUBMITTED, CaseStatus.NEED_SUPPLEMENT, UserRole.EDITOR, _check_need_supplement
    ),
    TransitionRule(
        CaseStatus.NEED_SUPPLEMENT, CaseStatus.SUBMITTED, UserRole.CUSTOMER, _check_submit
    ),
    TransitionRule(CaseStatus.SUBMITTED, CaseStatus.ACCEPTED, UserRole.EDITOR, _check_none),
    TransitionRule(
        CaseStatus.ACCEPTED, CaseStatus.EDITING, UserRole.EDITOR, _check_editing_from_accepted
    ),
    TransitionRule(
        CaseStatus.EDITING,
        CaseStatus.REVIEW_APPROVED,
        UserRole.EDITOR,
        _make_review_checker(ReviewResult.APPROVED),
    ),
    TransitionRule(
        CaseStatus.EDITING,
        CaseStatus.REVISION_REQUIRED,
        UserRole.EDITOR,
        _make_review_checker(ReviewResult.REVISION_REQUIRED),
    ),
    TransitionRule(
        CaseStatus.EDITING,
        CaseStatus.REJECTED,
        UserRole.EDITOR,
        _make_review_checker(ReviewResult.REJECTED),
    ),
    TransitionRule(
        CaseStatus.REVISION_REQUIRED,
        CaseStatus.EDITING,
        UserRole.EDITOR,
        _check_revision_to_editing,
    ),
    TransitionRule(
        CaseStatus.REVIEW_APPROVED, CaseStatus.REGISTERED, UserRole.EDITOR, _check_registered
    ),
    TransitionRule(
        CaseStatus.REGISTERED, CaseStatus.DECISION_ISSUED, UserRole.EDITOR, _check_decision_issued
    ),
    TransitionRule(
        CaseStatus.DECISION_ISSUED, CaseStatus.DEPOSITED, UserRole.EDITOR, _check_deposited
    ),
    TransitionRule(CaseStatus.DEPOSITED, CaseStatus.COMPLETED, UserRole.EDITOR, _check_none),
    TransitionRule(CaseStatus.COMPLETED, CaseStatus.ARCHIVED, UserRole.EDITOR, _check_none),
    TransitionRule(CaseStatus.REJECTED, CaseStatus.ARCHIVED, UserRole.EDITOR, _check_none),
)

TRANSITIONS: dict[tuple[str, str], TransitionRule] = {
    (rule.from_status, rule.to_status): rule for rule in TRANSITION_RULES
}


def allowed_transitions(user, case: PublicationCase) -> list[str]:
    """Trả về danh sách mã trạng thái đích mà người dùng có quyền chuyển từ trạng thái hiện tại."""
    result: list[str] = []
    for rule in TRANSITION_RULES:
        if rule.from_status == case.status and can_change_status(user, case, rule.to_status):
            result.append(rule.to_status)
    return result


def change_status(
    case: PublicationCase,
    to_status: str,
    actor,
    note: str = "",
    request=None,
) -> PublicationCase:
    """Kiểm tra quyền + điều kiện, đổi trạng thái, ghi StatusHistory và AuditEvent trong cùng một transaction.

    Sai điều kiện -> raise WorkflowError với thông báo tiếng Việt liệt kê điều kiện còn thiếu.
    """
    rule = TRANSITIONS.get((case.status, to_status))
    if rule is None:
        raise WorkflowError(
            f"Không thể chuyển trạng thái từ '{case.get_status_display()}' sang '{to_status}'."
        )

    if not can_change_status(actor, case, to_status):
        raise WorkflowError("Bạn không có quyền thực hiện thao tác chuyển trạng thái này.")

    missing = rule.validator(case, note)
    if missing:
        detail = "; ".join(missing)
        raise WorkflowError(
            f"Chưa đủ điều kiện chuyển trạng thái. Còn thiếu: {detail}.", missing=missing
        )

    from_status = case.status
    now = timezone.now()

    with transaction.atomic():
        locked_case = PublicationCase.objects.select_for_update().get(pk=case.pk)
        if locked_case.status != from_status:
            raise WorkflowError("Trạng thái hồ sơ đã thay đổi trước đó. Vui lòng tải lại trang.")

        update_fields = ["status", "updated_at"]
        locked_case._allow_status_mutation = True
        try:
            locked_case.status = to_status
            if to_status == CaseStatus.SUBMITTED:
                locked_case.submitted_at = now
                update_fields.append("submitted_at")
            elif to_status == CaseStatus.ACCEPTED:
                locked_case.accepted_at = now
                update_fields.append("accepted_at")
            locked_case.save(update_fields=update_fields)
        finally:
            locked_case._allow_status_mutation = False

        if to_status == CaseStatus.ACCEPTED and not locked_case.nxb_code:
            issue_nxb_code(locked_case)

        StatusHistory.objects.create(
            case=locked_case,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            note=note,
            at=now,
        )

        log_event(
            actor=actor,
            action="case.status_change",
            object_type="PublicationCase",
            object_id=str(locked_case.pk),
            case=locked_case,
            data={
                "before": {"status": from_status},
                "after": {"status": to_status, "nxb_code": locked_case.nxb_code},
                "note": note,
            },
            request=request,
        )

        transaction.on_commit(
            lambda: case_status_changed.send(
                sender=PublicationCase,
                case=locked_case,
                from_status=from_status,
                to_status=to_status,
                actor=actor,
                note=note,
            )
        )

    case.refresh_from_db()
    return case


def change_case_owner(
    case: PublicationCase, new_owner, actor, note: str = "", request=None
) -> PublicationCase:
    """Đổi người đại diện (owner) của hồ sơ — chỉ EDITOR thực hiện, bắt buộc ghi chú và AuditEvent (mục 5.3)."""
    if not actor or actor.role != UserRole.EDITOR:
        raise WorkflowError(_("Chỉ biên tập viên mới được đổi người đại diện hồ sơ."))
    if not new_owner or new_owner.role != UserRole.CUSTOMER:
        raise WorkflowError(_("Người đại diện mới phải là tài khoản khách hàng (CUSTOMER)."))
    if not (note or "").strip():
        raise WorkflowError(_("Bắt buộc nhập ghi chú lý do khi đổi người đại diện hồ sơ."))

    old_owner = case.owner
    with transaction.atomic():
        case.owner = new_owner
        case.save(update_fields=["owner", "updated_at"])
        log_event(
            actor=actor,
            action="case.owner_change",
            object_type="PublicationCase",
            object_id=str(case.pk),
            case=case,
            data={
                "before": {"owner_id": old_owner.pk, "owner_email": old_owner.email},
                "after": {"owner_id": new_owner.pk, "owner_email": new_owner.email},
                "note": note,
            },
            request=request,
        )
    return case


def record_manuscript_review(
    *,
    case: PublicationCase,
    manuscript,
    form4,
    result: str,
    confirmed_by,
    note: str = "",
    request=None,
) -> ManuscriptReview:
    """Tạo bản ghi kết quả duyệt bản thảo (ManuscriptReview) với đầy đủ kiểm tra ràng buộc (mục 5.6)."""
    if not confirmed_by or confirmed_by.role != UserRole.EDITOR:
        raise WorkflowError("Chỉ biên tập viên mới được xác nhận kết quả duyệt bản thảo.")
    if manuscript.case_id != case.pk or manuscript.doc_type != DocumentType.MANUSCRIPT:
        raise ValidationError("Bản thảo được duyệt phải thuộc đúng hồ sơ và có loại MANUSCRIPT.")
    if form4.case_id != case.pk or form4.doc_type != DocumentType.FORM_4:
        raise ValidationError("Mẫu 4 đã ký phải thuộc đúng hồ sơ và có loại FORM_4.")

    with transaction.atomic():
        review = ManuscriptReview.objects.create(
            case=case,
            manuscript=manuscript,
            form4=form4,
            result=result,
            confirmed_by=confirmed_by,
            note=note,
        )
        log_event(
            actor=confirmed_by,
            action="case.manuscript_review",
            object_type="ManuscriptReview",
            object_id=str(review.pk),
            case=case,
            data={
                "manuscript_id": manuscript.pk,
                "manuscript_version": manuscript.version,
                "form4_id": form4.pk,
                "result": result,
                "note": note,
            },
            request=request,
        )
    return review
