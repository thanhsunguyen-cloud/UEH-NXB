"""Điểm kiểm tra phân quyền duy nhất của toàn bộ hệ thống (mục 6).

Mọi view của mọi module M1–M8 bắt buộc gọi các hàm này hoặc kế thừa mixin từ
apps/core/mixins.py; tuyệt đối không tự viết điều kiện quyền rời rạc.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.models import FinanceAccess, UserRole
from apps.core.models import (
    CaseNote,
    CaseStatus,
    Document,
    DocumentType,
    NoteVisibility,
    PublicationCase,
)

CUSTOMER_EDITABLE_STATUSES = {
    CaseStatus.DRAFT,
    CaseStatus.NEED_SUPPLEMENT,
}

CUSTOMER_UPLOADABLE_STATUSES = {
    CaseStatus.DRAFT,
    CaseStatus.NEED_SUPPLEMENT,
    CaseStatus.REVISION_REQUIRED,
}

CUSTOMER_UPLOADABLE_DOC_TYPES = {
    DocumentType.MANUSCRIPT,
    DocumentType.FORM_1,
    DocumentType.FORM_2,
    DocumentType.FORM_3,
    DocumentType.OTHER,
}

EDITOR_READONLY_STATUSES = {
    CaseStatus.COMPLETED,
    CaseStatus.ARCHIVED,
}


def _is_active_authenticated(user) -> bool:
    return bool(
        user and getattr(user, "is_authenticated", False) and getattr(user, "is_active", False)
    )


def cases_visible_to(user) -> QuerySet[PublicationCase]:
    """Trả về QuerySet hồ sơ mà người dùng có quyền nhìn thấy.

    - CUSTOMER: chỉ hồ sơ có owner = user.
    - EDITOR: tất cả hồ sơ.
    - ADMIN hoặc chưa đăng nhập: QuerySet rỗng (ADMIN không xem nội dung hồ sơ).
    """
    if not _is_active_authenticated(user):
        return PublicationCase.objects.none()
    if user.role == UserRole.EDITOR:
        return PublicationCase.objects.all()
    if user.role == UserRole.CUSTOMER:
        return PublicationCase.objects.filter(owner=user)
    return PublicationCase.objects.none()


def can_view_case(user, case: PublicationCase) -> bool:
    """Kiểm tra quyền xem chi tiết hồ sơ."""
    if not _is_active_authenticated(user) or case is None:
        return False
    if user.role == UserRole.EDITOR:
        return True
    if user.role == UserRole.CUSTOMER:
        return case.owner_id == user.pk
    return False


def can_edit_case_info(user, case: PublicationCase) -> bool:
    """Kiểm tra quyền sửa thông tin hồ sơ.

    - CUSTOMER: chủ hồ sơ khi trạng thái DRAFT hoặc NEED_SUPPLEMENT.
    - EDITOR: mọi hồ sơ trừ COMPLETED / ARCHIVED.
    - ADMIN: không.
    """
    if not _is_active_authenticated(user) or case is None:
        return False
    if user.role == UserRole.EDITOR:
        return case.status not in EDITOR_READONLY_STATUSES
    if user.role == UserRole.CUSTOMER:
        return case.owner_id == user.pk and case.status in CUSTOMER_EDITABLE_STATUSES
    return False


def can_upload(user, case: PublicationCase, doc_type: str) -> bool:
    """Kiểm tra quyền tải tài liệu lên hồ sơ theo loại tài liệu và trạng thái."""
    if not _is_active_authenticated(user) or case is None:
        return False
    if doc_type not in DocumentType.values:
        return False
    if user.role == UserRole.EDITOR:
        return True
    if user.role == UserRole.CUSTOMER:
        return (
            case.owner_id == user.pk
            and doc_type in CUSTOMER_UPLOADABLE_DOC_TYPES
            and case.status in CUSTOMER_UPLOADABLE_STATUSES
        )
    return False


def can_download(user, document: Document) -> bool:
    """Kiểm tra quyền tải xuống tài liệu.

    - CUSTOMER: chủ hồ sơ, KHÔNG được tải FORM_4.
    - EDITOR: có.
    - ADMIN: không.
    """
    if not _is_active_authenticated(user) or document is None:
        return False
    if user.role == UserRole.EDITOR:
        return True
    if user.role == UserRole.CUSTOMER:
        return document.case.owner_id == user.pk and document.doc_type != DocumentType.FORM_4
    return False


def can_view_note(user, note: CaseNote) -> bool:
    """Kiểm tra quyền đọc ghi chú trên hồ sơ.

    - CUSTOMER: chỉ ghi chú có visibility = CUSTOMER của hồ sơ mình.
    - EDITOR: tất cả ghi chú.
    - ADMIN: không.
    """
    if not _is_active_authenticated(user) or note is None:
        return False
    if user.role == UserRole.EDITOR:
        return True
    if user.role == UserRole.CUSTOMER:
        return note.case.owner_id == user.pk and note.visibility == NoteVisibility.CUSTOMER
    return False


def can_change_status(user, case: PublicationCase, to_status: str) -> bool:
    """Kiểm tra quyền đổi trạng thái theo bảng chuyển trạng thái mục 7.2."""
    from apps.core.workflow import TRANSITIONS

    if not _is_active_authenticated(user) or case is None:
        return False
    if user.role == UserRole.ADMIN:
        return False

    rule = TRANSITIONS.get((case.status, to_status))
    if rule is None:
        return False
    if rule.actor_role == UserRole.CUSTOMER:
        return user.role == UserRole.CUSTOMER and case.owner_id == user.pk
    if rule.actor_role == UserRole.EDITOR:
        return user.role == UserRole.EDITOR
    return False


def can_manage_system(user) -> bool:
    """Chỉ ADMIN có quyền quản trị hệ thống (người dùng, danh mục, biểu mẫu, nhật ký)."""
    return _is_active_authenticated(user) and user.role == UserRole.ADMIN


def can_view_publication_stats(user) -> bool:
    """Chỉ EDITOR có quyền xem thống kê danh mục xuất bản."""
    return _is_active_authenticated(user) and user.role == UserRole.EDITOR


def can_view_finance(user) -> bool:
    """Chỉ EDITOR có finance_access là VIEW hoặc MANAGE được xem tài chính và công nợ."""
    return (
        _is_active_authenticated(user)
        and user.role == UserRole.EDITOR
        and user.finance_access in (FinanceAccess.VIEW, FinanceAccess.MANAGE)
    )


def can_manage_finance(user) -> bool:
    """Chỉ EDITOR có finance_access là MANAGE được ghi nhận/điều chỉnh khoản phải thu, đã thu."""
    return (
        _is_active_authenticated(user)
        and user.role == UserRole.EDITOR
        and user.finance_access == FinanceAccess.MANAGE
    )
