"""Nhãn trạng thái và việc cần làm hiển thị cho khách hàng (gói M2, mục 3)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.models import CaseStatus

CUSTOMER_STATUS_LABELS = {
    CaseStatus.DRAFT: _("Đang soạn hồ sơ"),
    CaseStatus.SUBMITTED: _("Đã nộp – chờ NXB tiếp nhận"),
    CaseStatus.NEED_SUPPLEMENT: _("Cần bổ sung"),
    CaseStatus.ACCEPTED: _("NXB đã tiếp nhận"),
    CaseStatus.EDITING: _("NXB đang biên tập"),
    CaseStatus.REVISION_REQUIRED: _("Cần chỉnh sửa bản thảo"),
    CaseStatus.REVIEW_APPROVED: _("Bản thảo đã được duyệt"),
    CaseStatus.REJECTED: _("Không được chấp thuận xuất bản"),
    CaseStatus.REGISTERED: _("Đã đăng ký xuất bản"),
    CaseStatus.DECISION_ISSUED: _("Đã có quyết định xuất bản"),
    CaseStatus.DEPOSITED: _("Đã nộp lưu chiểu"),
    CaseStatus.COMPLETED: _("Hoàn tất"),
    CaseStatus.ARCHIVED: _("Đã lưu trữ"),
}

# Màu nhãn Bootstrap (text-bg-*) theo trạng thái
CUSTOMER_STATUS_BADGES = {
    CaseStatus.DRAFT: "secondary",
    CaseStatus.SUBMITTED: "info",
    CaseStatus.NEED_SUPPLEMENT: "warning",
    CaseStatus.ACCEPTED: "primary",
    CaseStatus.EDITING: "primary",
    CaseStatus.REVISION_REQUIRED: "warning",
    CaseStatus.REVIEW_APPROVED: "success",
    CaseStatus.REJECTED: "danger",
    CaseStatus.REGISTERED: "success",
    CaseStatus.DECISION_ISSUED: "success",
    CaseStatus.DEPOSITED: "success",
    CaseStatus.COMPLETED: "dark",
    CaseStatus.ARCHIVED: "light",
}

# Cột "Việc cần làm" trên danh sách hồ sơ (mục 2.1)
CUSTOMER_TODO = {
    CaseStatus.DRAFT: _("Hoàn thiện và nộp hồ sơ"),
    CaseStatus.NEED_SUPPLEMENT: _("Bổ sung theo yêu cầu NXB"),
    CaseStatus.REVISION_REQUIRED: _("Nộp bản thảo đã chỉnh sửa"),
}


def customer_status_label(status: str) -> str:
    return str(CUSTOMER_STATUS_LABELS.get(status, status))


def customer_status_badge(status: str) -> str:
    return CUSTOMER_STATUS_BADGES.get(status, "secondary")


def customer_todo(status: str) -> str:
    todo = CUSTOMER_TODO.get(status)
    return str(todo) if todo else ""


def customer_status_choices() -> list[tuple[str, str]]:
    """Danh sách (mã, nhãn khách hàng) theo đúng thứ tự trạng thái chuẩn."""
    return [(value, customer_status_label(value)) for value in CaseStatus.values]
