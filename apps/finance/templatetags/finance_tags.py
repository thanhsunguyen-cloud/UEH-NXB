"""Bộ lọc hiển thị tiền VNĐ cho M8: 3500000 -> "3.500.000 đ"."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def format_vnd(value) -> str:
    """Định dạng số tiền nguyên theo kiểu Việt Nam, ví dụ "3.500.000 đ"."""
    try:
        number = int(Decimal(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    sign = "-" if number < 0 else ""
    return f"{sign}{abs(number):,}".replace(",", ".") + " đ"


@register.filter
def vnd(value) -> str:
    return format_vnd(value)


ACTION_LABELS = {
    "finance.receivable_create": "Thêm khoản phải thu",
    "finance.receivable_adjust": "Điều chỉnh khoản phải thu",
    "finance.collection_create": "Ghi nhận đã thu",
    "finance.collection_adjust": "Đảo khoản thu",
    "finance.export": "Xuất CSV",
}


@register.filter
def finance_action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)
