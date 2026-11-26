#!/usr/bin/env python
"""Điểm khởi chạy lệnh quản trị Django cho UEH Publishing Portal V2."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Không thể nạp Django. Hãy kiểm tra môi trường ảo và các gói phụ thuộc."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
