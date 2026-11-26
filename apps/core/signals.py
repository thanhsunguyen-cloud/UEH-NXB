"""Tín hiệu Django dùng chung giữa M0 và các module sau (M4 lắng nghe để gửi email)."""

from django.dispatch import Signal

# Tham số gửi kèm: case, from_status, to_status, actor, note
case_status_changed = Signal()
