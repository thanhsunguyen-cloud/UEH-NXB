"""Nghiệp vụ của M6: kiểm tra và lưu ảnh bìa, sinh slug, chọn biểu mẫu đang áp dụng."""

from __future__ import annotations

import re
from pathlib import Path

from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.models import FormTemplate
from apps.core.storage import StoredFile, get_storage

COVER_CATEGORY = "public_media"
COVER_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
COVER_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# Slug không được trùng với đường dẫn quản lý /tin-tuc/quan-ly/
RESERVED_SLUGS = {"quan-ly"}


def _sniff_image_mime(head: bytes) -> str | None:
    """Nhận diện ảnh theo chữ ký nhị phân (không tin phần mở rộng hay MIME trình duyệt gửi)."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_cover(uploaded_file) -> str:
    """Kiểm tra ảnh bìa: .jpg/.png/.webp, ≤ 2 MB, nội dung đúng định dạng. Trả về MIME chuẩn."""
    ext = Path(uploaded_file.name or "").suffix.lower()
    expected_mime = COVER_TYPES.get(ext)
    if expected_mime is None:
        raise ValidationError(_("Ảnh bìa chỉ nhận tệp .jpg, .png hoặc .webp."))
    if uploaded_file.size > COVER_MAX_BYTES:
        raise ValidationError(_("Ảnh bìa không được vượt quá 2 MB."))
    if uploaded_file.size == 0:
        raise ValidationError(_("Tệp ảnh bìa rỗng."))
    uploaded_file.seek(0)
    head = uploaded_file.read(16)
    uploaded_file.seek(0)
    if _sniff_image_mime(head) != expected_mime:
        raise ValidationError(_("Nội dung tệp không phải ảnh hợp lệ đúng với phần mở rộng."))
    return expected_mime


def save_cover(uploaded_file, mime_type: str) -> StoredFile:
    """Lưu ảnh bìa vào kho thư viện `public_media` qua `save_library_file` (CR-001)."""
    storage = get_storage()
    save_library_file = getattr(storage, "save_library_file", None)
    if save_library_file is None:
        # Kho lưu trữ hiện tại chưa có save_library_file (CR-001 chưa gộp).
        raise ValidationError(_("Chức năng lưu ảnh bìa chưa sẵn sàng. Vui lòng thử lại sau."))
    uploaded_file.seek(0)
    return save_library_file(
        COVER_CATEGORY,
        uploaded_file.name,
        uploaded_file,
        uploaded_file.size,
        mime_type,
    )


def unique_news_slug(title: str, model, exclude_pk: int | None = None) -> str:
    """Sinh slug tiếng Việt không dấu, duy nhất, không trùng đường dẫn dành riêng."""
    base = slugify(re.sub("[đĐ]", "d", title or ""))[:240] or "tin"
    candidate = base
    counter = 2
    qs = model.objects.all()
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    while candidate in RESERVED_SLUGS or qs.filter(slug=candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def active_form_templates() -> list[FormTemplate]:
    """Mỗi `code` một bản: bản đang áp dụng có ngày hiệu lực mới nhất."""
    latest: dict[str, FormTemplate] = {}
    qs = FormTemplate.objects.filter(is_active=True).order_by("code", "-effective_from", "-id")
    for template in qs:
        latest.setdefault(template.code, template)
    return list(latest.values())
