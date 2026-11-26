"""Dữ liệu mẫu cho test M6."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.public_site.models import FeaturedBook, NewsPost

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP_BYTES = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64


def image_upload(name="bia.png", content=PNG_BYTES, content_type="image/png"):
    return SimpleUploadedFile(name, content, content_type=content_type)


def make_news(user, *, published=True, slug=None, **kwargs) -> NewsPost:
    count = NewsPost.objects.count() + 1
    defaults = {
        "title": f"Tin số {count}",
        "slug": slug or f"tin-so-{count}",
        "summary": "Tóm tắt",
        "body": "Nội dung",
        "is_published": published,
        "published_at": timezone.now() if published else None,
        "created_by": user,
    }
    defaults.update(kwargs)
    return NewsPost.objects.create(**defaults)


def make_book(user, *, published=True, **kwargs) -> FeaturedBook:
    count = FeaturedBook.objects.count() + 1
    defaults = {
        "title": f"Sách số {count}",
        "authors": "Tác giả A",
        "year": 2026,
        "is_published": published,
        "created_by": user,
    }
    defaults.update(kwargs)
    return FeaturedBook.objects.create(**defaults)
