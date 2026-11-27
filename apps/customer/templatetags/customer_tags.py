"""Bộ lọc template hiển thị trạng thái hồ sơ theo nhãn khách hàng."""

from django import template

from apps.customer import labels

register = template.Library()


@register.filter
def customer_status_label(status: str) -> str:
    return labels.customer_status_label(status)


@register.filter
def customer_status_badge(status: str) -> str:
    return labels.customer_status_badge(status)


@register.filter
def customer_todo(status: str) -> str:
    return labels.customer_todo(status)
