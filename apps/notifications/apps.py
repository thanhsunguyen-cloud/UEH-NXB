"""Cấu hình app notifications (M4 – thông báo email)."""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    verbose_name = "Thông báo email"

    def ready(self) -> None:
        from apps.core.signals import case_status_changed
        from apps.notifications.receivers import on_case_status_changed

        case_status_changed.connect(
            on_case_status_changed,
            dispatch_uid="apps.notifications.on_case_status_changed",
        )
