"""Nhật ký thao tác hệ thống (AuditEvent — chỉ ghi thêm, mục 5.12)."""

from __future__ import annotations

from typing import Any


def get_client_ip(request) -> str | None:
    """Trích xuất địa chỉ IP khách hàng từ request (hỗ trợ X-Forwarded-For trên Cloud Run)."""
    if request is None:
        return None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_event(
    *,
    action: str,
    object_type: str,
    object_id: str,
    actor=None,
    case=None,
    data: dict[str, Any] | None = None,
    ip_address: str | None = None,
    request=None,
):
    """Ghi một bản ghi AuditEvent mới (chỉ ghi thêm).

    Các module M1–M8 luôn gọi hàm này để đảm bảo định dạng nhất quán.
    """
    from apps.core.models import AuditEvent

    resolved_ip = ip_address or get_client_ip(request)
    resolved_actor = (
        actor if (actor is not None and getattr(actor, "is_authenticated", True)) else None
    )
    return AuditEvent.objects.create(
        actor=resolved_actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        case=case,
        data=data or {},
        ip_address=resolved_ip,
    )
