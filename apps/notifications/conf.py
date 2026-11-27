"""Cấu hình riêng của M4, đọc trực tiếp từ biến môi trường (không sửa portal/settings)."""

import os

DEFAULT_PORTAL_BASE_URL = "http://localhost:8000"


def get_portal_base_url() -> str:
    """Địa chỉ gốc của Portal dùng để ghép đường dẫn trong email (không có dấu / ở cuối)."""
    value = os.environ.get("PORTAL_BASE_URL", "").strip() or DEFAULT_PORTAL_BASE_URL
    return value.rstrip("/")
