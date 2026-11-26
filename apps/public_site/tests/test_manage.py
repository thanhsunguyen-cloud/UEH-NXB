"""Test màn hình quản lý tin tức / sách mới (EDITOR)."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.public_site.models import FeaturedBook, NewsPost
from apps.public_site.services import COVER_MAX_BYTES
from apps.public_site.tests.helpers import (
    JPEG_BYTES,
    PNG_BYTES,
    WEBP_BYTES,
    image_upload,
    make_book,
    make_news,
)

pytestmark = pytest.mark.django_db

MANAGE_GET_URLS = [
    ("public_site:news_manage", False),
    ("public_site:news_create", False),
    ("public_site:news_update", True),
    ("public_site:book_manage", False),
    ("public_site:book_create", False),
    ("public_site:book_update", True),
]
PUBLISH_URLS = ["public_site:news_publish", "public_site:book_publish"]


def _manage_urls(editor):
    news = make_news(editor)
    book = make_book(editor)
    urls = []
    for name, needs_pk in MANAGE_GET_URLS:
        pk = (book if name.startswith("public_site:book") else news).pk
        urls.append(reverse(name, args=[pk]) if needs_pk else reverse(name))
    return urls, news, book


@pytest.mark.parametrize("role_fixture", ["customer", "admin_user"])
def test_manage_pages_404_for_customer_and_admin(client, request, editor, role_fixture):
    user = request.getfixturevalue(role_fixture)
    client.force_login(user)
    urls, news, book = _manage_urls(editor)
    for url in urls:
        assert client.get(url).status_code == 404, url
    for name, obj in zip(PUBLISH_URLS, (news, book), strict=True):
        response = client.post(reverse(name, args=[obj.pk]), {"action": "unpublish"})
        assert response.status_code == 404
    news.refresh_from_db()
    assert news.is_published


def test_manage_pages_redirect_anonymous_to_login(client, editor):
    urls, _, _ = _manage_urls(editor)
    for url in urls:
        response = client.get(url)
        assert response.status_code == 302
        assert reverse("accounts:login") in response["Location"]


def test_manage_pages_ok_for_editor(editor_client, editor):
    urls, _, _ = _manage_urls(editor)
    for url in urls:
        assert editor_client.get(url).status_code == 200, url
    html = editor_client.get(reverse("public_site:news_manage")).content.decode()
    assert "Tin tức &amp; sách mới" in html
    assert reverse("public_site:book_manage") in html


def test_no_delete_route():
    from apps.public_site import urls

    assert not [p for p in urls.urlpatterns if "xoa" in str(p.pattern)]


# --- Tin tức ---------------------------------------------------------------


def test_editor_creates_news_with_cover(editor_client, editor, fake_storage):
    response = editor_client.post(
        reverse("public_site:news_create"),
        {
            "title": "Đại hội đồng Biên tập năm 2026",
            "summary": "Tóm tắt",
            "body": "Nội dung",
            "cover": image_upload("bia.png"),
        },
    )
    assert response.status_code == 302
    post = NewsPost.objects.get()
    assert post.slug == "dai-hoi-dong-bien-tap-nam-2026"
    assert post.created_by == editor
    assert not post.is_published and post.published_at is None
    assert post.cover_mime == "image/png"
    assert post.cover_storage_ref.startswith("library/public_media/")
    assert fake_storage.saved == [("public_media", "bia.png", len(PNG_BYTES), "image/png")]
    event = AuditEvent.objects.get(action="public.news_create")
    assert event.actor == editor and event.object_id == str(post.pk)


def test_news_slug_unique_and_not_reserved(editor_client, editor):
    make_news(editor, slug="quan-ly-2")
    for title in ("Quản lý", "Quản lý"):
        editor_client.post(
            reverse("public_site:news_create"),
            {"title": title, "summary": "s", "body": "b"},
        )
    slugs = set(NewsPost.objects.values_list("slug", flat=True))
    assert "quan-ly" not in slugs
    assert {"quan-ly-2", "quan-ly-3", "quan-ly-4"} == slugs


def test_editor_updates_news_keeps_slug_and_logs(editor_client, editor):
    post = make_news(editor, title="Cũ", slug="cu")
    response = editor_client.post(
        reverse("public_site:news_update", args=[post.pk]),
        {"title": "Mới", "summary": "s", "body": "b"},
    )
    assert response.status_code == 302
    post.refresh_from_db()
    assert post.title == "Mới" and post.slug == "cu"
    event = AuditEvent.objects.get(action="public.news_update")
    assert event.data["before"]["title"] == "Cũ"
    assert event.data["after"]["title"] == "Mới"


def test_publish_and_unpublish_news(editor_client, editor):
    post = make_news(editor, published=False)
    url = reverse("public_site:news_publish", args=[post.pk])

    assert editor_client.post(url, {"action": "publish"}).status_code == 302
    post.refresh_from_db()
    first_published_at = post.published_at
    assert post.is_published and first_published_at is not None
    assert AuditEvent.objects.filter(action="public.news_publish").count() == 1

    editor_client.post(url, {"action": "unpublish"})
    post.refresh_from_db()
    assert not post.is_published
    assert AuditEvent.objects.filter(action="public.news_unpublish").count() == 1

    editor_client.post(url, {"action": "publish"})
    post.refresh_from_db()
    assert post.published_at == first_published_at  # giữ ngày đăng lần đầu

    assert editor_client.post(url, {"action": "delete"}).status_code == 404
    assert editor_client.get(url).status_code == 405


# --- Sách mới --------------------------------------------------------------


def test_editor_creates_and_publishes_book(editor_client, editor, fake_storage):
    response = editor_client.post(
        reverse("public_site:book_create"),
        {
            "title": "Kinh tế học",
            "authors": "Nguyễn Văn A",
            "isbn": "978-604-300-001-6",
            "year": 2026,
            "description": "Giới thiệu",
            "sort_order": 1,
            "cover": image_upload("bia.webp", WEBP_BYTES, "image/webp"),
        },
    )
    assert response.status_code == 302
    book = FeaturedBook.objects.get()
    assert book.isbn == "9786043000016"
    assert book.cover_mime == "image/webp"
    assert book.created_by == editor
    assert AuditEvent.objects.filter(action="public.book_create").exists()

    editor_client.post(reverse("public_site:book_publish", args=[book.pk]), {"action": "publish"})
    book.refresh_from_db()
    assert book.is_published
    assert AuditEvent.objects.filter(action="public.book_publish").exists()


def test_book_update_replaces_cover(editor_client, editor, fake_storage):
    book = make_book(
        editor, cover_storage_ref="library/public_media/old.png", cover_mime="image/png"
    )
    response = editor_client.post(
        reverse("public_site:book_update", args=[book.pk]),
        {
            "title": book.title,
            "authors": book.authors,
            "isbn": "",
            "year": 2025,
            "description": "",
            "sort_order": 0,
            "cover": image_upload("moi.jpg", JPEG_BYTES, "image/jpeg"),
        },
    )
    assert response.status_code == 302
    book.refresh_from_db()
    assert book.cover_mime == "image/jpeg"
    assert book.cover_storage_ref != "library/public_media/old.png"
    event = AuditEvent.objects.get(action="public.book_update")
    assert event.data["before"]["year"] == "2026"
    assert event.data["after"]["year"] == "2025"


@pytest.mark.parametrize(
    "isbn,year",
    [("123", 2026), ("9786043000017", 2026), ("0306406152", 2026), ("", 1800)],
)
def test_book_invalid_isbn_or_year(editor_client, isbn, year):
    response = editor_client.post(
        reverse("public_site:book_create"),
        {"title": "T", "authors": "A", "isbn": isbn, "year": year, "sort_order": 0},
    )
    assert response.status_code == 200
    assert response.context["form"].errors
    assert not FeaturedBook.objects.exists()


# --- Ảnh bìa không hợp lệ --------------------------------------------------


@pytest.mark.parametrize(
    "upload",
    [
        image_upload("bia.gif", b"GIF89a" + b"\x00" * 20, "image/gif"),
        image_upload("bia.svg", b"<svg><script>alert(1)</script></svg>", "image/svg+xml"),
        image_upload("bia.png", b"<html>khong phai anh</html>", "image/png"),
        image_upload("bia.jpg", PNG_BYTES, "image/jpeg"),  # nội dung PNG, đuôi .jpg
        image_upload("bia.png", b"", "image/png"),
        image_upload("bia.png", PNG_BYTES + b"\x00" * COVER_MAX_BYTES, "image/png"),
    ],
    ids=["gif", "svg", "fake-png", "mismatch", "empty", "too-large"],
)
def test_invalid_cover_rejected(editor_client, fake_storage, upload):
    response = editor_client.post(
        reverse("public_site:news_create"),
        {"title": "Tin", "summary": "s", "body": "b", "cover": upload},
    )
    assert response.status_code == 200
    assert "cover" in response.context["form"].errors
    assert not NewsPost.objects.exists()
    assert fake_storage.saved == []


def test_cover_exactly_2mb_accepted(editor_client, fake_storage):
    content = PNG_BYTES + b"\x00" * (COVER_MAX_BYTES - len(PNG_BYTES))
    response = editor_client.post(
        reverse("public_site:news_create"),
        {"title": "Tin", "summary": "s", "body": "b", "cover": image_upload("a.png", content)},
    )
    assert response.status_code == 302
    assert NewsPost.objects.get().cover_storage_ref


def test_cover_error_when_storage_lacks_library_support(editor_client, media_root, monkeypatch):
    """Kho lưu trữ chưa có save_library_file (trước CR-001) -> báo lỗi thân thiện, không lưu."""

    class StorageWithoutLibrary:
        pass

    monkeypatch.setattr("apps.public_site.services.get_storage", StorageWithoutLibrary)
    response = editor_client.post(
        reverse("public_site:news_create"),
        {"title": "Tin", "summary": "s", "body": "b", "cover": image_upload()},
    )
    assert response.status_code == 200
    assert "cover" in response.context["form"].errors
    assert not NewsPost.objects.exists()


def test_published_cover_served_after_upload(editor_client, fake_storage):
    editor_client.post(
        reverse("public_site:book_create"),
        {"title": "T", "authors": "A", "year": 2026, "sort_order": 0, "cover": image_upload()},
    )
    book = FeaturedBook.objects.get()
    image_url = reverse("public_site:image", args=["sach-moi", book.pk])
    anonymous = Client()
    assert anonymous.get(image_url).status_code == 404
    editor_client.post(reverse("public_site:book_publish", args=[book.pk]), {"action": "publish"})
    response = anonymous.get(image_url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == PNG_BYTES
