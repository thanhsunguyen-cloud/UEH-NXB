"""Bộ nhận tín hiệu case_status_changed của M0."""

import logging

from apps.notifications.emails import notify_status_change

logger = logging.getLogger(__name__)


def on_case_status_changed(
    sender, case, from_status, to_status, actor=None, note="", **kwargs
) -> None:
    """Gửi email theo trạng thái mới; không bao giờ để lỗi làm hỏng thao tác đổi trạng thái."""
    try:
        notify_status_change(
            case=case,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            note=note or "",
        )
    except Exception:  # noqa: BLE001 – gửi email không được làm hỏng nghiệp vụ
        logger.exception("M4: lỗi ngoài dự kiến khi xử lý thông báo hồ sơ %s", case.pk)
