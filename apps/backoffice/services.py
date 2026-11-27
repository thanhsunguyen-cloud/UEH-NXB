"""Truy vấn và nghiệp vụ phụ trợ của M3 (không tạo model, không đổi trạng thái trực tiếp)."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Exists, F, Max, OuterRef, Q, QuerySet, Subquery
from django.utils.translation import gettext_lazy as _

from apps.core.models import (
    CaseStatus,
    Document,
    DocumentType,
    ManuscriptReview,
    PublicationCase,
    StatusHistory,
    SupplementRequest,
    SupplementStatus,
)
from apps.core.workflow import TRANSITIONS, allowed_transitions

from .forms import UNASSIGNED

# Nhãn nút chuyển trạng thái cho BTV (gói M3 mục 2.4), khóa theo (từ, sang).
TRANSITION_LABELS: dict[tuple[str, str], str] = {
    (CaseStatus.SUBMITTED, CaseStatus.ACCEPTED): _("Tiếp nhận"),
    (CaseStatus.SUBMITTED, CaseStatus.NEED_SUPPLEMENT): _("Yêu cầu bổ sung"),
    (CaseStatus.ACCEPTED, CaseStatus.EDITING): _("Bắt đầu biên tập"),
    (CaseStatus.EDITING, CaseStatus.REVIEW_APPROVED): _("Duyệt – đồng ý xuất bản"),
    (CaseStatus.EDITING, CaseStatus.REVISION_REQUIRED): _("Trả tác giả chỉnh sửa"),
    (CaseStatus.EDITING, CaseStatus.REJECTED): _("Từ chối"),
    (CaseStatus.REVISION_REQUIRED, CaseStatus.EDITING): _("Tiếp tục biên tập"),
    (CaseStatus.REVIEW_APPROVED, CaseStatus.REGISTERED): _("Đã đăng ký xuất bản"),
    (CaseStatus.REGISTERED, CaseStatus.DECISION_ISSUED): _("Đã có quyết định xuất bản"),
    (CaseStatus.DECISION_ISSUED, CaseStatus.DEPOSITED): _("Đã nộp lưu chiểu"),
    (CaseStatus.DEPOSITED, CaseStatus.COMPLETED): _("Hoàn tất"),
    (CaseStatus.COMPLETED, CaseStatus.ARCHIVED): _("Lưu trữ"),
    (CaseStatus.REJECTED, CaseStatus.ARCHIVED): _("Lưu trữ"),
}

# Kết quả duyệt Mẫu 4 -> trạng thái đích được gợi ý.
REVIEW_SUGGESTION = {
    "APPROVED": CaseStatus.REVIEW_APPROVED,
    "REVISION_REQUIRED": CaseStatus.REVISION_REQUIRED,
    "REJECTED": CaseStatus.REJECTED,
}


def transition_label(from_status: str, to_status: str) -> str:
    label = TRANSITION_LABELS.get((from_status, to_status))
    return str(label) if label else str(CaseStatus(to_status).label)


# Ghi chú khi chuyển sang các trạng thái này được gửi cho khách (Portal + email M4).
CUSTOMER_VISIBLE_NOTE_STATUSES = (
    CaseStatus.NEED_SUPPLEMENT,
    CaseStatus.REVISION_REQUIRED,
    CaseStatus.REJECTED,
)


def transition_options(user, case: PublicationCase) -> list[dict]:
    """Danh sách nút chuyển trạng thái kèm các điều kiện còn thiếu (gọi validator của M0)."""
    options = []
    latest = case.reviews.order_by("-confirmed_at", "-id").first()
    suggested = REVIEW_SUGGESTION.get(latest.result) if latest else None
    for to_status in allowed_transitions(user, case):
        rule = TRANSITIONS[(case.status, to_status)]
        missing = [] if to_status == CaseStatus.NEED_SUPPLEMENT else rule.validator(case, "")
        options.append(
            {
                "to_status": to_status,
                "label": transition_label(case.status, to_status),
                "missing": missing,
                "needs_message": to_status == CaseStatus.NEED_SUPPLEMENT,
                "to_customer": to_status in CUSTOMER_VISIBLE_NOTE_STATUSES,
                "suggested": case.status == CaseStatus.EDITING and to_status == suggested,
                "danger": to_status in (CaseStatus.REJECTED, CaseStatus.NEED_SUPPLEMENT),
            }
        )
    return options


# ---------------------------------------------------------------------------
# Danh sách & tìm kiếm
# ---------------------------------------------------------------------------


def base_case_queryset(cases: QuerySet[PublicationCase]) -> QuerySet[PublicationCase]:
    return cases.select_related("owner", "primary_editor", "category")


def filter_cases(cases: QuerySet[PublicationCase], data: dict, user) -> QuerySet[PublicationCase]:
    """Lọc danh sách hồ sơ theo form CaseFilterForm đã hợp lệ (cleaned_data)."""
    qs = base_case_queryset(cases)

    status = data.get("status") or ""
    if status:
        qs = qs.filter(status=status)
    else:
        # Không hiện hồ sơ Nháp của khách trừ khi lọc "Nháp" tường minh.
        qs = qs.exclude(status=CaseStatus.DRAFT)

    if data.get("mode"):
        qs = qs.filter(publication_mode=data["mode"])
    if data.get("category"):
        qs = qs.filter(category=data["category"])

    editor = data.get("editor") or ""
    if editor == UNASSIGNED:
        qs = qs.filter(primary_editor__isnull=True)
    elif editor:
        qs = qs.filter(primary_editor_id=editor)

    if data.get("mine"):
        qs = qs.filter(primary_editor=user)

    q = (data.get("q") or "").strip()
    if q:
        compact = re.sub(r"[\s-]+", "", q)
        cond = (
            Q(nxb_code__icontains=q)
            | Q(temp_code__icontains=q)
            | Q(title__icontains=q)
            | Q(owner__email__icontains=q)
            | Q(contributors__full_name__icontains=q)
        )
        if compact:
            cond |= Q(isbn__icontains=compact)
        matched = cases.filter(cond).values("pk")
        qs = qs.filter(pk__in=matched)

    return qs.order_by("-updated_at")


# ---------------------------------------------------------------------------
# Hồ sơ cần xử lý
# ---------------------------------------------------------------------------


def _annotate_queue(qs: QuerySet[PublicationCase]) -> QuerySet[PublicationCase]:
    latest_supplement = SupplementRequest.objects.filter(case=OuterRef("pk")).order_by(
        "-created_at", "-id"
    )
    latest_review = ManuscriptReview.objects.filter(case=OuterRef("pk")).order_by(
        "-confirmed_at", "-id"
    )
    max_manuscript = (
        Document.objects.filter(case=OuterRef("pk"), doc_type=DocumentType.MANUSCRIPT)
        .values("case")
        .annotate(v=Max("version"))
        .values("v")
    )
    return qs.annotate(
        latest_supplement_status=Subquery(latest_supplement.values("status")[:1]),
        had_need_supplement=Exists(
            StatusHistory.objects.filter(case=OuterRef("pk"), to_status=CaseStatus.NEED_SUPPLEMENT)
        ),
        reviewed_version=Subquery(latest_review.values("manuscript__version")[:1]),
        max_manuscript_version=Subquery(max_manuscript[:1]),
    )


QUEUE_PREVIEW = 10


def queue_groups(cases: QuerySet[PublicationCase]) -> list[dict]:
    """Các nhóm việc của trang 'Hồ sơ cần xử lý' (gói M3 mục 2.2)."""
    qs = _annotate_queue(base_case_queryset(cases))
    resupplied = Q(
        status=CaseStatus.SUBMITTED,
        had_need_supplement=True,
        latest_supplement_status=SupplementStatus.RESOLVED,
    )
    definitions = [
        (
            "new",
            _("Mới nộp – chờ tiếp nhận"),
            qs.filter(status=CaseStatus.SUBMITTED).exclude(resupplied),
            CaseStatus.SUBMITTED,
        ),
        ("resupplied", _("Khách đã bổ sung"), qs.filter(resupplied), CaseStatus.SUBMITTED),
        (
            "accepted",
            _("Đã tiếp nhận – chưa giao BTV hoặc chưa bắt đầu biên tập"),
            qs.filter(status=CaseStatus.ACCEPTED),
            CaseStatus.ACCEPTED,
        ),
        (
            "revised",
            _("Khách đã nộp bản thảo sửa"),
            qs.filter(
                status=CaseStatus.REVISION_REQUIRED,
                max_manuscript_version__gt=F("reviewed_version"),
            ),
            CaseStatus.REVISION_REQUIRED,
        ),
        (
            "approved",
            _("Chờ đăng ký xuất bản"),
            qs.filter(status=CaseStatus.REVIEW_APPROVED),
            CaseStatus.REVIEW_APPROVED,
        ),
        (
            "registered",
            _("Chờ quyết định xuất bản"),
            qs.filter(status=CaseStatus.REGISTERED),
            CaseStatus.REGISTERED,
        ),
        (
            "decision",
            _("Chờ nộp lưu chiểu"),
            qs.filter(status=CaseStatus.DECISION_ISSUED),
            CaseStatus.DECISION_ISSUED,
        ),
    ]
    groups = []
    for key, title, group_qs, status in definitions:
        ordered = group_qs.order_by("updated_at")
        groups.append(
            {
                "key": key,
                "title": title,
                "count": ordered.count(),
                "items": list(ordered[:QUEUE_PREVIEW]),
                "status": status,
            }
        )
    return groups


# ---------------------------------------------------------------------------
# Nhật ký: chuyển giá trị sang dạng JSON được
# ---------------------------------------------------------------------------


def jsonable(value):
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "pk"):
        return value.pk
    return str(value)


def snapshot(instance, fields) -> dict:
    return {name: jsonable(getattr(instance, name)) for name in fields}
