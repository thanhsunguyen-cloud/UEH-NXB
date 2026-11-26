"""Test trang công khai M6 (khách chưa đăng nhập)."""

from __future__ import annotations

import datetime

import pytest
from django.urls import reverse

from apps.core.models import FormTemplate
from apps.public_site.tests.helpers import PNG_BYTES, make_book, make_news
from tests.factories import PublicationCaseFactory

pytestmark = pytest.mark.django_db

STATIC_PAGES = [
    "public_site:home",
    "public_site:about",
    "public_site:process",
    "public_site:forms",
    "public_site:news_list",
    "public_site:books",
    "public_site:contact",
]


@pytest.mark.parametrize("url_name", STATIC_PAGES)
def test_public_pages_ok_for_anonymous(client, url_name):
    response = client.get(reverse(url_name))
    assert response.status_code == 200
    html = response.content.decode()
    assert "<title>" in html
    assert '<meta name="description" content="' in html
    assert "Nhà xuất bản Kinh tế TP. Hồ Chí Minh" in html


def test_titles_and_descriptions_are_unique(client):
    titles, descriptions = set(), set()
    for url_name in STATIC_PAGES:
        ctx = client.get(reverse(url_name)).context
        titles.add(str(ctx["page_title"]))
        descriptions.add(str(ctx["meta_description"]))
    assert len(titles) == len(STATIC_PAGES)
    assert len(descriptions) == len(STATIC_PAGES)


def test_public_pages_show_official_nxb_content_without_placeholders(client):
    """Nội dung lấy từ phiếu NXB ngày 26/11/2026; không còn chỗ trống, không công bố điện thoại."""
    for url_name in STATIC_PAGES:
        html = client.get(reverse(url_name)).content.decode()
        assert "[CẦN NXB CUNG CẤP" not in html
        assert "Điện thoại" not in html
    contact = client.get(reverse("public_site:contact")).content.decode()
    assert "279 Nguyễn Tri Phương" in contact
    assert "nxbkt@ueh.edu.vn" in contact
    about = client.get(reverse("public_site:about")).content.decode()
    assert "444/GP-BTTTT" in about
    head = client.get(reverse("public_site:home")).content.decode().split("</head>")[0]
    assert '<meta name="description"' in head


def test_public_pages_do_not_show_case_data(client):
    case = PublicationCaseFactory(title="Hồ sơ bí mật của khách hàng")
    for url_name in STATIC_PAGES:
        html = client.get(reverse(url_name)).content.decode()
        assert case.title not in html
        assert case.temp_code not in html


def test_home_shows_three_news_and_four_books(client, editor):
    for i in range(5):
        make_news(editor, title=f"Tin công khai {i}")
    make_news(editor, published=False, title="Tin nháp ẩn")
    for i in range(6):
        make_book(editor, title=f"Sách công khai {i}", sort_order=i)
    make_book(editor, published=False, title="Sách nháp ẩn")

    response = client.get(reverse("public_site:home"))
    assert len(response.context["latest_news"]) == 3
    assert len(response.context["latest_books"]) == 4
    html = response.content.decode()
    assert "Tin nháp ẩn" not in html
    assert "Sách nháp ẩn" not in html
    assert reverse("customer:case_create") in response.context["submit_url"]
    assert reverse("public_site:process") in html
    assert reverse("public_site:forms") in html


def test_news_list_paginates_by_10_and_hides_drafts(client, editor):
    for _ in range(12):
        make_news(editor)
    make_news(editor, published=False, title="Bản nháp")
    response = client.get(reverse("public_site:news_list"))
    assert len(response.context["posts"]) == 10
    assert response.context["is_paginated"]
    page2 = client.get(reverse("public_site:news_list") + "?page=2")
    assert len(page2.context["posts"]) == 2
    assert "Bản nháp" not in response.content.decode() + page2.content.decode()


def test_news_detail_published_and_unpublished(client, editor):
    post = make_news(editor, summary="Tóm tắt riêng của tin")
    draft = make_news(editor, published=False)
    response = client.get(reverse("public_site:news_detail", args=[post.slug]))
    assert response.status_code == 200
    assert response.context["meta_description"] == "Tóm tắt riêng của tin"
    assert client.get(reverse("public_site:news_detail", args=[draft.slug])).status_code == 404


def test_books_page_only_published(client, editor):
    make_book(editor, title="Sách đã đăng", isbn="9786043000016")
    make_book(editor, published=False, title="Sách chưa đăng")
    html = client.get(reverse("public_site:books")).content.decode()
    assert "Sách đã đăng" in html
    assert "9786043000016" in html
    assert "Sách chưa đăng" not in html


def test_script_content_is_escaped(client, editor):
    payload = "<script>alert('xss')</script>"
    post = make_news(editor, title=payload, summary=payload, body=f"Đoạn 1\n\n{payload}")
    make_book(editor, title=payload, authors=payload, description=payload)
    for url in (
        reverse("public_site:news_detail", args=[post.slug]),
        reverse("public_site:news_list"),
        reverse("public_site:books"),
        reverse("public_site:home"),
    ):
        html = client.get(url).content.decode()
        assert payload not in html
        assert "&lt;script&gt;" in html


def test_news_body_plain_text_becomes_paragraphs(client, editor):
    post = make_news(editor, body="Đoạn một\n\nĐoạn hai")
    html = client.get(reverse("public_site:news_detail", args=[post.slug])).content.decode()
    assert "<p>Đoạn một</p>" in html
    assert "<p>Đoạn hai</p>" in html


# --- Biểu mẫu --------------------------------------------------------------


def _form_template(media_root, *, code="MAU_2", version="1", active=True, day=1, content=b"x"):
    ref = f"library/form_templates/{code}_{version}.docx"
    path = media_root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return FormTemplate.objects.create(
        code=code,
        name=f"Biểu mẫu {code}",
        version=version,
        effective_from=datetime.date(2026, 1, day),
        is_active=active,
        storage_ref=ref,
        original_filename=f"{code} v{version}.docx",
    )


def test_forms_page_lists_latest_active_per_code(client, media_root):
    old = _form_template(media_root, code="MAU_2", version="1", day=1)
    new = _form_template(media_root, code="MAU_2", version="2", day=5)
    inactive_newer = _form_template(media_root, code="MAU_2", version="3", day=9, active=False)
    other = _form_template(media_root, code="MAU_3", version="1")
    only_inactive = _form_template(media_root, code="MAU_9", version="1", active=False)

    listed = client.get(reverse("public_site:forms")).context["templates"]
    assert [t.pk for t in listed] == [new.pk, other.pk]
    assert old not in listed and inactive_newer not in listed and only_inactive not in listed


def test_form_download_active_only(client, media_root):
    active = _form_template(media_root, content=b"noi dung bieu mau")
    inactive = _form_template(media_root, code="MAU_3", active=False)

    response = client.get(reverse("public_site:form_download", args=[active.pk]))
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"noi dung bieu mau"
    assert "attachment;" in response["Content-Disposition"]
    assert "MAU_2%20v1.docx" in response["Content-Disposition"]

    assert client.get(reverse("public_site:form_download", args=[inactive.pk])).status_code == 404
    assert client.get(reverse("public_site:form_download", args=[99999])).status_code == 404


def test_form_download_missing_file_404(client, media_root):
    template = _form_template(media_root)
    (media_root / template.storage_ref).unlink()
    response = client.get(reverse("public_site:form_download", args=[template.pk]))
    assert response.status_code == 404


# --- Ảnh bìa ---------------------------------------------------------------


def _write_cover(media_root, name="cover.png"):
    ref = f"library/public_media/{name}"
    path = media_root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_BYTES)
    return ref


@pytest.mark.parametrize("kind,factory", [("tin-tuc", make_news), ("sach-moi", make_book)])
def test_image_only_for_published_items(client, editor, media_root, kind, factory):
    ref = _write_cover(media_root)
    published = factory(editor, cover_storage_ref=ref, cover_mime="image/png")
    draft = factory(editor, published=False, cover_storage_ref=ref, cover_mime="image/png")

    response = client.get(reverse("public_site:image", args=[kind, published.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert b"".join(response.streaming_content) == PNG_BYTES

    assert client.get(reverse("public_site:image", args=[kind, draft.pk])).status_code == 404


def test_image_404_cases(client, editor, media_root):
    no_cover = make_news(editor)
    missing = make_book(editor, cover_storage_ref="library/public_media/khong-co.png")
    assert (
        client.get(reverse("public_site:image", args=["tin-tuc", no_cover.pk])).status_code == 404
    )
    assert (
        client.get(reverse("public_site:image", args=["sach-moi", missing.pk])).status_code == 404
    )
    assert client.get(reverse("public_site:image", args=["ho-so", no_cover.pk])).status_code == 404


def test_cover_image_rendered_on_cards(client, editor, media_root):
    ref = _write_cover(media_root)
    post = make_news(editor, cover_storage_ref=ref, cover_mime="image/png")
    book = make_book(editor, cover_storage_ref=ref, cover_mime="image/png")
    html = client.get(reverse("public_site:home")).content.decode()
    assert reverse("public_site:image", args=["tin-tuc", post.pk]) in html
    assert reverse("public_site:image", args=["sach-moi", book.pk]) in html
