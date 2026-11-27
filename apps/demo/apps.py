"""Cấu hình app demo (bản demo M2/M3, dữ liệu giả, không có model)."""

from django.apps import AppConfig


class DemoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.demo"
    verbose_name = "Bản demo M2/M3"
