"""Bộ lọc hiển thị cho bản demo."""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def vnd(value) -> str:
    """Định dạng số tiền kiểu Việt Nam: 25000000 -> "25.000.000"."""
    try:
        number = int(Decimal(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    return f"{number:,}".replace(",", ".")
