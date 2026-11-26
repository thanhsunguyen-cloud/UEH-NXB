"""Views của M6 — Trang công khai và màn hình quản lý tin tức/sách mới.

Trang công khai không hiển thị bất kỳ dữ liệu hồ sơ nào của khách hàng.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict
from django.http import Http404, HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import escape_uri_path
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.core.audit import log_event
from apps.core.mixins import EditorRequiredMixin
from apps.core.models import FormTemplate
from apps.core.storage import ALLOWED_EXTENSIONS, get_storage
from apps.public_site.forms import FeaturedBookForm, NewsPostForm
from apps.public_site.models import FeaturedBook, NewsPost
from apps.public_site.services import active_form_templates, save_cover, unique_news_slug

HOME_NEWS_COUNT = 3
HOME_BOOK_COUNT = 4


class PublicPageMixin:
    """Gắn tiêu đề và mô tả meta riêng cho từng trang công khai."""

    page_title = ""
    meta_description = ""

    def get_page_title(self):
        return self.page_title

    def get_meta_description(self):
        return self.meta_description

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = self.get_page_title()
        ctx["meta_description"] = self.get_meta_description()
        return ctx


def published_news():
    return NewsPost.objects.filter(is_published=True).order_by("-published_at", "-id")


def published_books():
    return FeaturedBook.objects.filter(is_published=True).order_by("sort_order", "-year", "-id")


# ---------------------------------------------------------------------------
# Trang công khai
# ---------------------------------------------------------------------------


class HomeView(PublicPageMixin, TemplateView):
    template_name = "public_site/home.html"
    page_title = _("Trang chủ")
    meta_description = _(
        "Cổng thông tin Nhà xuất bản Kinh tế TP. Hồ Chí Minh: nộp hồ sơ xuất bản, "
        "quy trình, biểu mẫu, tin tức và sách mới."
    )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["latest_news"] = published_news()[:HOME_NEWS_COUNT]
        ctx["latest_books"] = published_books()[:HOME_BOOK_COUNT]
        ctx["submit_url"] = reverse("accounts:login") + "?next=" + reverse("customer:case_create")
        return ctx


class AboutView(PublicPageMixin, TemplateView):
    template_name = "public_site/about.html"
    page_title = _("Giới thiệu")
    meta_description = _("Giới thiệu Nhà xuất bản Kinh tế TP. Hồ Chí Minh.")


class ProcessView(PublicPageMixin, TemplateView):
    template_name = "public_site/process.html"
    page_title = _("Quy trình xuất bản")
    meta_description = _(
        "Các bước từ nộp hồ sơ đến nộp lưu chiểu, giấy tờ cần nộp và yêu cầu bản thảo "
        "dành cho tác giả."
    )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["allowed_extensions"] = ", ".join(sorted(ALLOWED_EXTENSIONS))
        ctx["max_file_mb"] = int(getattr(settings, "MAX_FILE_MB", 200))
        return ctx


class FormsView(PublicPageMixin, TemplateView):
    template_name = "public_site/forms.html"
    page_title = _("Tải biểu mẫu")
    meta_description = _("Danh sách biểu mẫu đang áp dụng của Nhà xuất bản, tải về miễn phí.")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["templates"] = active_form_templates()
        return ctx


class FormDownloadView(View):
    """Tải biểu mẫu dạng stream; chỉ bản đang áp dụng (is_active=True), bản khác -> 404."""

    def get(self, request, pk: int):
        template = get_object_or_404(FormTemplate, pk=pk, is_active=True)
        storage = get_storage()
        if not template.storage_ref or not storage.exists(template.storage_ref):
            raise Http404("Tệp biểu mẫu không tồn tại.")
        response = StreamingHttpResponse(
            storage.open_stream(template.storage_ref),
            content_type="application/octet-stream",
        )
        filename = template.original_filename or Path(template.storage_ref).name
        response["Content-Disposition"] = (
            f"attachment; filename*=UTF-8''{escape_uri_path(filename)}"
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response


class NewsListView(PublicPageMixin, ListView):
    template_name = "public_site/news_list.html"
    context_object_name = "posts"
    paginate_by = 10
    page_title = _("Tin tức")
    meta_description = _("Tin tức và thông báo của Nhà xuất bản Kinh tế TP. Hồ Chí Minh.")

    def get_queryset(self):
        return published_news()


class NewsDetailView(PublicPageMixin, DetailView):
    template_name = "public_site/news_detail.html"
    context_object_name = "post"

    def get_queryset(self):
        return published_news()

    def get_page_title(self):
        return self.object.title

    def get_meta_description(self):
        return self.object.summary


class BooksView(PublicPageMixin, ListView):
    template_name = "public_site/books.html"
    context_object_name = "books"
    paginate_by = 12
    page_title = _("Sách mới")
    meta_description = _("Sách mới của Nhà xuất bản Kinh tế TP. Hồ Chí Minh.")

    def get_queryset(self):
        return published_books()


class ContactView(PublicPageMixin, TemplateView):
    template_name = "public_site/contact.html"
    page_title = _("Liên hệ")
    meta_description = _("Thông tin liên hệ Nhà xuất bản Kinh tế TP. Hồ Chí Minh.")


IMAGE_MODELS = {"tin-tuc": NewsPost, "sach-moi": FeaturedBook}


class CoverImageView(View):
    """Trả ảnh bìa dạng stream; chỉ của tin/sách đã đăng."""

    def get(self, request, kind: str, pk: int):
        model = IMAGE_MODELS.get(kind)
        if model is None:
            raise Http404("Không tìm thấy ảnh.")
        item = get_object_or_404(model, pk=pk, is_published=True)
        if not item.cover_storage_ref:
            raise Http404("Không có ảnh bìa.")
        storage = get_storage()
        if not storage.exists(item.cover_storage_ref):
            raise Http404("Tệp ảnh không tồn tại.")
        response = StreamingHttpResponse(
            storage.open_stream(item.cover_storage_ref),
            content_type=item.cover_mime or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "public, max-age=3600"
        return response


# ---------------------------------------------------------------------------
# Quản lý nội dung (EDITOR)
# ---------------------------------------------------------------------------


class ManageContextMixin:
    manage_section = ""  # "news" | "books" — để tô đậm tab quản lý

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["manage_section"] = self.manage_section
        return ctx


def _snapshot(obj, fields):
    data = model_to_dict(obj, fields=fields)
    return {key: (str(value) if value is not None else None) for key, value in data.items()}


class ContentFormMixin(EditorRequiredMixin, ManageContextMixin):
    """Lưu tin/sách kèm ảnh bìa và ghi AuditEvent."""

    audit_prefix = ""  # "news" | "book"
    audit_fields: list[str] = []
    list_url_name = ""

    def get_success_url(self):
        return reverse(self.list_url_name)

    def apply_cover(self, form, obj) -> bool:
        cover = form.cleaned_data.get("cover")
        if not cover:
            return True
        try:
            stored = save_cover(cover, form.cover_mime)
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error("cover", message)
            return False
        obj.cover_storage_ref = stored.storage_ref
        obj.cover_mime = form.cover_mime
        return True

    def prepare(self, obj):
        """Gán thêm giá trị trước khi lưu (slug, người tạo...)."""

    def form_valid(self, form):
        is_create = form.instance.pk is None
        before = {} if is_create else _snapshot(self.get_object(), self.audit_fields)
        obj = form.save(commit=False)
        if not self.apply_cover(form, obj):
            return self.form_invalid(form)
        self.prepare(obj)
        obj.save()
        self.object = obj
        action = "create" if is_create else "update"
        log_event(
            actor=self.request.user,
            action=f"public.{self.audit_prefix}_{action}",
            object_type=obj.__class__.__name__,
            object_id=str(obj.pk),
            data={"before": before, "after": _snapshot(obj, self.audit_fields)},
            request=self.request,
        )
        messages.success(self.request, _("Đã lưu nội dung."))
        return HttpResponseRedirect(self.get_success_url())


class PublishToggleView(EditorRequiredMixin, View):
    """Đăng / gỡ đăng (không có xóa). POST field `action` = publish | unpublish."""

    model = None
    audit_prefix = ""
    list_url_name = ""

    def on_publish(self, obj):
        """Hook cho model cần ghi thêm thời điểm đăng."""

    def post(self, request, pk: int):
        obj = get_object_or_404(self.model, pk=pk)
        action = request.POST.get("action")
        if action not in ("publish", "unpublish"):
            raise Http404("Thao tác không hợp lệ.")
        obj.is_published = action == "publish"
        if obj.is_published:
            self.on_publish(obj)
        obj.save()
        log_event(
            actor=request.user,
            action=f"public.{self.audit_prefix}_{action}",
            object_type=obj.__class__.__name__,
            object_id=str(obj.pk),
            data={"is_published": obj.is_published},
            request=request,
        )
        if obj.is_published:
            messages.success(request, _("Đã đăng nội dung."))
        else:
            messages.success(request, _("Đã gỡ đăng nội dung."))
        return HttpResponseRedirect(reverse(self.list_url_name))


# --- Tin tức ---------------------------------------------------------------

NEWS_AUDIT_FIELDS = ["title", "slug", "summary", "cover_storage_ref", "is_published"]


class NewsManageListView(EditorRequiredMixin, ManageContextMixin, ListView):
    template_name = "public_site/manage/news_list.html"
    context_object_name = "posts"
    paginate_by = 20
    manage_section = "news"

    def get_queryset(self):
        return NewsPost.objects.select_related("created_by").order_by("-created_at", "-id")


class NewsFormMixin(ContentFormMixin):
    model = NewsPost
    form_class = NewsPostForm
    template_name = "public_site/manage/form.html"
    manage_section = "news"
    audit_prefix = "news"
    audit_fields = NEWS_AUDIT_FIELDS
    list_url_name = "public_site:news_manage"


class NewsCreateView(NewsFormMixin, CreateView):
    extra_context = {"form_title": _("Thêm tin tức")}

    def prepare(self, obj):
        obj.created_by = self.request.user
        obj.slug = unique_news_slug(obj.title, NewsPost)


class NewsUpdateView(NewsFormMixin, UpdateView):
    extra_context = {"form_title": _("Sửa tin tức")}


class NewsPublishView(PublishToggleView):
    model = NewsPost
    audit_prefix = "news"
    list_url_name = "public_site:news_manage"

    def on_publish(self, obj):
        if obj.published_at is None:
            obj.published_at = timezone.now()


# --- Sách mới --------------------------------------------------------------

BOOK_AUDIT_FIELDS = [
    "title",
    "authors",
    "isbn",
    "year",
    "sort_order",
    "cover_storage_ref",
    "is_published",
]


class BookManageListView(EditorRequiredMixin, ManageContextMixin, ListView):
    template_name = "public_site/manage/book_list.html"
    context_object_name = "books"
    paginate_by = 20
    manage_section = "books"

    def get_queryset(self):
        return FeaturedBook.objects.select_related("created_by").order_by(
            "sort_order", "-year", "-id"
        )


class BookFormMixin(ContentFormMixin):
    model = FeaturedBook
    form_class = FeaturedBookForm
    template_name = "public_site/manage/form.html"
    manage_section = "books"
    audit_prefix = "book"
    audit_fields = BOOK_AUDIT_FIELDS
    list_url_name = "public_site:book_manage"


class BookCreateView(BookFormMixin, CreateView):
    extra_context = {"form_title": _("Thêm sách mới")}

    def prepare(self, obj):
        obj.created_by = self.request.user


class BookUpdateView(BookFormMixin, UpdateView):
    extra_context = {"form_title": _("Sửa sách mới")}


class BookPublishView(PublishToggleView):
    model = FeaturedBook
    audit_prefix = "book"
    list_url_name = "public_site:book_manage"
