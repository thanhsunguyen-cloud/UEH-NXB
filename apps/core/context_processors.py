"""Context processor cung cấp cờ phân quyền và menu theo vai trò cho templates/base.html."""

from apps.core.permissions import (
    can_manage_finance,
    can_manage_system,
    can_view_finance,
    can_view_publication_stats,
)


def portal_navigation(request):
    """Đưa các quyền điều hướng chuẩn vào mọi template (không viết logic quyền rời trong template)."""
    user = getattr(request, "user", None)
    return {
        "nav_can_manage_system": can_manage_system(user),
        "nav_can_view_publication_stats": can_view_publication_stats(user),
        "nav_can_view_finance": can_view_finance(user),
        "nav_can_manage_finance": can_manage_finance(user),
    }
