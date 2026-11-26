"""Cấp mã hồ sơ tạm, mã NXB tuần tự không trùng và kiểm tra ISBN-13 (mục 8)."""

from __future__ import annotations

import re
import secrets
import string

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

TEMP_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_temp_code() -> str:
    """Sinh mã tạm dạng TMP-XXXXXXXX (8 ký tự ngẫu nhiên gồm chữ hoa và chữ số)."""
    suffix = "".join(secrets.choice(TEMP_CODE_ALPHABET) for _ in range(8))
    return f"TMP-{suffix}"


def _isbn13_check_digit(first_12: str) -> str:
    """Tính số kiểm tra ISBN-13 theo trọng số luân phiên 1 và 3."""
    total = sum(int(digit) * (1 if idx % 2 == 0 else 3) for idx, digit in enumerate(first_12))
    return str((10 - (total % 10)) % 10)


def normalize_isbn(value: str | None) -> str:
    """Chuẩn hóa ISBN về chuỗi 13 chữ số liền; từ chối ISBN-10 và định dạng sai.

    - Bỏ dấu gạch ngang và khoảng trắng.
    - ISBN-10 -> raise ValidationError("Vui lòng nhập ISBN-13").
    - Chỉ chấp nhận ISBN-13 gồm 13 chữ số, bắt đầu bằng 978 hoặc 979 và đúng số kiểm tra.
    """
    if value is None:
        return ""
    cleaned = re.sub(r"[\s-]+", "", str(value).strip()).upper()
    if not cleaned:
        return ""
    if len(cleaned) == 10 and re.fullmatch(r"\d{9}[\dX]", cleaned):
        raise ValidationError(_("Vui lòng nhập ISBN-13"))
    validate_isbn13(cleaned)
    return cleaned


def validate_isbn13(value: str | None) -> None:
    """Kiểm tra tính hợp lệ của chuỗi ISBN-13 (gắn làm validator cho trường PublicationCase.isbn)."""
    if not value:
        return
    cleaned = re.sub(r"[\s-]+", "", str(value).strip()).upper()
    if len(cleaned) == 10 and re.fullmatch(r"\d{9}[\dX]", cleaned):
        raise ValidationError(_("Vui lòng nhập ISBN-13"))
    if not re.fullmatch(r"\d{13}", cleaned):
        raise ValidationError(_("ISBN-13 phải gồm đúng 13 chữ số."))
    if not cleaned.startswith(("978", "979")):
        raise ValidationError(_("ISBN-13 phải bắt đầu bằng 978 hoặc 979."))
    expected = _isbn13_check_digit(cleaned[:12])
    if cleaned[12] != expected:
        raise ValidationError(_("Số kiểm tra của ISBN-13 không hợp lệ."))


def issue_nxb_code(case, prefix: str = "NXB", year: int | None = None) -> str:
    """Cấp mã NXB dạng NXB-{year}-{number:04d} an toàn khi gọi đồng thời.

    - Dùng CodeSequence với select_for_update() trong transaction.
    - Nếu hồ sơ đã có nxb_code thì giữ nguyên mã cũ, không cấp lại.
    """
    from apps.core.models import CodeSequence, PublicationCase

    with transaction.atomic():
        locked_case = PublicationCase.objects.select_for_update().get(pk=case.pk)
        if locked_case.nxb_code:
            case.nxb_code = locked_case.nxb_code
            return locked_case.nxb_code

        issue_year = year or (
            locked_case.accepted_at.year if locked_case.accepted_at else timezone.localdate().year
        )
        seq, _ = CodeSequence.objects.select_for_update().get_or_create(
            prefix=prefix,
            year=issue_year,
            defaults={"last_number": 0},
        )
        seq.last_number += 1
        seq.save(update_fields=["last_number", "updated_at"])

        code = f"{prefix}-{issue_year}-{seq.last_number:04d}"
        locked_case.nxb_code = code
        locked_case.save(update_fields=["nxb_code", "updated_at"])
        case.nxb_code = code
        return code
