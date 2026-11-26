"""View M7 — Cổng quản trị hệ thống (chỉ ADMIN, không xem nội dung hồ sơ).

Mọi view kế thừa AdminRequiredMixin: CUSTOMER/EDITOR nhận 404, chưa đăng nhập -> trang đăng nhập.
"""

from __future__ import annotations

import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.encoding import escape_uri_path
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import FormView, ListView

from apps.accounts.models import User
from apps.administration import services
from apps.administration.forms import (
    AuditFilterForm,
    FormTemplateCreateForm,
    StaffCreateForm,
    UserFilterForm,
    UserUpdateForm,
    catalog_form_class,
)
from apps.core.mixins import AdminRequiredMixin
from apps.core.models import AuditEvent, FormTemplate
from apps.core.storage import get_storage


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _add_errors(form, exc: ValidationError) -> None:
    for message in exc.messages:
        form.add_error(None, message)


class HtmxPartialMixin:
    """Trả về phần bảng kết quả khi yêu cầu đến từ HTMX (lọc / tìm / phân trang)."""

    partial_template_name: str = ""

    def get_template_names(self):
        if _is_htmx(self.request) and self.partial_template_name:
            return [self.partial_template_name]
        return super().get_template_names()


# ---------------------------------------------------------------------------
# 2.1 Người dùng
# ---------------------------------------------------------------------------


class UserListView(AdminRequiredMixin, HtmxPartialMixin, ListView):
    template_name = "administration/users.html"
    partial_template_name = "administration/_user_table.html"
    paginate_by = 20
    context_object_name = "users"

    def get_queryset(self):
        self.filter_form = UserFilterForm(self.request.GET or None)
        qs = User.objects.order_by("role", "email")
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("q"):
                qs = qs.filter(Q(full_name__icontains=data["q"]) | Q(email__icontains=data["q"]))
            if data.get("role"):
                qs = qs.filter(role=data["role"])
            if data.get("status") == "active":
                qs = qs.filter(is_active=True)
            elif data.get("status") == "locked":
                qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = self.filter_form
        return ctx


class StaffCreateView(AdminRequiredMixin, FormView):
    template_name = "administration/user_create.html"
    form_class = StaffCreateForm

    def form_valid(self, form):
        try:
            user = services.create_staff_user(
                actor=self.request.user, request=self.request, **form.cleaned_data
            )
        except ValidationError as exc:
            _add_errors(form, exc)
            return self.form_invalid(form)
        messages.success(self.request, _("Đã tạo tài khoản %(email)s.") % {"email": user.email})
        return redirect("administration:home")


class UserUpdateView(AdminRequiredMixin, FormView):
    template_name = "administration/user_update.html"
    form_class = UserUpdateForm

    @cached_property
    def target_user(self):
        return get_object_or_404(User, pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["target_user"] = self.target_user
        return kwargs

    def get_initial(self):
        return {
            "role": self.target_user.role,
            "finance_access": self.target_user.finance_access,
            "is_active": self.target_user.is_active,
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["target_user"] = self.target_user
        return ctx

    def form_valid(self, form):
        try:
            actions = services.update_user(
                actor=self.request.user,
                user=self.target_user,
                request=self.request,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            _add_errors(form, exc)
            return self.form_invalid(form)
        if actions:
            messages.success(
                self.request,
                _("Đã cập nhật tài khoản %(email)s.") % {"email": self.target_user.email},
            )
        else:
            messages.info(self.request, _("Không có thay đổi nào."))
        return redirect("administration:home")


# ---------------------------------------------------------------------------
# 2.2 Danh mục
# ---------------------------------------------------------------------------


def _catalog_kind(kind: str):
    if kind not in services.CATALOG_KINDS:
        raise Http404("Không tìm thấy danh mục.")
    return services.CATALOG_KINDS[kind]


class CatalogsView(AdminRequiredMixin, View):
    """3 tab Thể loại / Lĩnh vực / Loại phí; GET hiển thị, POST thêm mục mới."""

    template_name = "administration/catalogs.html"

    def _render(self, request, kind, form):
        model, _label = _catalog_kind(kind)
        tabs = [(key, label) for key, (_m, label) in services.CATALOG_KINDS.items()]
        return render(
            request,
            self.template_name,
            {
                "kind": kind,
                "tabs": tabs,
                "items": model.objects.order_by("sort_order", "name"),
                "form": form,
            },
        )

    def get(self, request):
        kind = request.GET.get("loai", "the-loai")
        model, _label = _catalog_kind(kind)
        return self._render(request, kind, catalog_form_class(model)(initial={"is_active": True}))

    def post(self, request):
        kind = request.POST.get("loai", "")
        model, _label = _catalog_kind(kind)
        form = catalog_form_class(model)(request.POST)
        if not form.is_valid():
            return self._render(request, kind, form)
        item = form.save()
        services.log_catalog_change(actor=request.user, item=item, before=None, request=request)
        messages.success(request, _("Đã thêm “%(name)s”.") % {"name": item.name})
        return HttpResponseRedirect(f"{reverse('administration:catalogs')}?loai={kind}")


class CatalogUpdateView(AdminRequiredMixin, View):
    template_name = "administration/catalog_update.html"

    def _get(self, kind, pk):
        model, label = _catalog_kind(kind)
        return get_object_or_404(model, pk=pk), label

    def _render(self, request, kind, item, label, form):
        return render(
            request,
            self.template_name,
            {"kind": kind, "item": item, "kind_label": label, "form": form},
        )

    def get(self, request, kind, pk):
        item, label = self._get(kind, pk)
        return self._render(
            request, kind, item, label, catalog_form_class(type(item))(instance=item)
        )

    def post(self, request, kind, pk):
        item, label = self._get(kind, pk)
        before = services.catalog_snapshot(item)
        form = catalog_form_class(type(item))(request.POST, instance=item)
        if not form.is_valid():
            return self._render(request, kind, item, label, form)
        item = form.save()
        if services.catalog_snapshot(item) != before:
            services.log_catalog_change(
                actor=request.user, item=item, before=before, request=request
            )
            messages.success(request, _("Đã cập nhật “%(name)s”.") % {"name": item.name})
        else:
            messages.info(request, _("Không có thay đổi nào."))
        return HttpResponseRedirect(f"{reverse('administration:catalogs')}?loai={kind}")


class CatalogToggleView(AdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, kind, pk):
        model, _label = _catalog_kind(kind)
        item = get_object_or_404(model, pk=pk)
        services.toggle_catalog_item(actor=request.user, item=item, request=request)
        state = _("bật") if item.is_active else _("tắt")
        messages.success(
            request, _("Đã %(state)s “%(name)s”.") % {"state": state, "name": item.name}
        )
        return HttpResponseRedirect(f"{reverse('administration:catalogs')}?loai={kind}")


# ---------------------------------------------------------------------------
# 2.3 Biểu mẫu tải về
# ---------------------------------------------------------------------------


class FormTemplateListView(AdminRequiredMixin, ListView):
    template_name = "administration/templates.html"
    context_object_name = "form_templates"

    def get_queryset(self):
        return FormTemplate.objects.order_by("code", "-effective_from", "-id")


class FormTemplateCreateView(AdminRequiredMixin, FormView):
    template_name = "administration/template_create.html"
    form_class = FormTemplateCreateForm

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["suggested_codes"] = services.SUGGESTED_FORM_CODES
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            template = services.create_form_template(
                actor=self.request.user,
                code=data["code"],
                name=data["name"],
                version=data["version"],
                effective_from=data["effective_from"],
                uploaded_file=data["file"],
                activate=data["activate"],
                request=self.request,
            )
        except ValidationError as exc:
            _add_errors(form, exc)
            return self.form_invalid(form)
        messages.success(
            self.request,
            _("Đã thêm %(code)s phiên bản %(version)s.")
            % {"code": template.code, "version": template.version},
        )
        return redirect("administration:templates")


class FormTemplateToggleView(AdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        template = get_object_or_404(FormTemplate, pk=pk)
        active = request.POST.get("active") == "1"
        services.set_form_template_active(
            actor=request.user, template=template, active=active, request=request
        )
        if active:
            msg = _("Đã áp dụng %(code)s phiên bản %(version)s; các phiên bản khác cùng mã đã tắt.")
        else:
            msg = _("Đã tắt áp dụng %(code)s phiên bản %(version)s.")
        messages.success(request, msg % {"code": template.code, "version": template.version})
        return redirect("administration:templates")


class FormTemplateDownloadView(AdminRequiredMixin, View):
    """Admin tải biểu mẫu để kiểm tra — trả về dạng stream, không lộ đường dẫn lưu trữ."""

    def get(self, request, pk):
        template = get_object_or_404(FormTemplate, pk=pk)
        storage = get_storage()
        if not storage.exists(template.storage_ref):
            raise Http404("Tệp lưu trữ không tồn tại.")
        response = StreamingHttpResponse(
            storage.open_stream(template.storage_ref),
            content_type=services.guess_mime_type(template.original_filename),
        )
        safe_name = escape_uri_path(template.original_filename)
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{safe_name}"
        return response


# ---------------------------------------------------------------------------
# 2.4 Nhật ký hệ thống
# ---------------------------------------------------------------------------

# Chỉ các nhóm này được hiện trường `data`; case.*, document.*, finance.* và mọi nhóm khác thì ẩn.
DATA_VISIBLE_PREFIXES = ("user.", "auth.", "catalog.", "form_template.")
FILTER_GROUP_PREFIXES = ("case.", "document.", "finance.", "user.", "auth.")


def audit_data_visible(action: str) -> bool:
    return (action or "").startswith(DATA_VISIBLE_PREFIXES)


class AuditLogListView(AdminRequiredMixin, HtmxPartialMixin, ListView):
    template_name = "administration/audit_logs.html"
    partial_template_name = "administration/_audit_table.html"
    paginate_by = 50
    context_object_name = "events"

    def get_queryset(self):
        self.filter_form = AuditFilterForm(self.request.GET or None)
        qs = AuditEvent.objects.select_related("actor", "case").order_by("-at", "-id")
        if not self.filter_form.is_valid():
            return qs if not self.filter_form.is_bound else qs.none()
        data = self.filter_form.cleaned_data
        if data.get("date_from"):
            qs = qs.filter(at__date__gte=data["date_from"])
        if data.get("date_to"):
            qs = qs.filter(at__date__lte=data["date_to"])
        if data.get("actor"):
            term = data["actor"]
            qs = qs.filter(Q(actor__email__icontains=term) | Q(actor__full_name__icontains=term))
        group = data.get("group")
        if group == "other":
            for prefix in FILTER_GROUP_PREFIXES:
                qs = qs.exclude(action__startswith=prefix)
        elif group:
            qs = qs.filter(action__startswith=group + ".")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = self.filter_form
        rows = []
        for event in ctx["events"]:
            rows.append(
                {
                    "at": event.at,
                    "actor": event.actor,
                    "action": event.action,
                    "object_type": event.object_type,
                    "object_id": event.object_id,
                    "case_code": event.case.display_code if event.case_id else "",
                    "ip_address": event.ip_address,
                    # Không bao giờ đưa `data` của nhóm hồ sơ/tài liệu/tài chính vào template.
                    "data_json": (
                        json.dumps(event.data, ensure_ascii=False, indent=1, default=str)
                        if audit_data_visible(event.action) and event.data
                        else ""
                    ),
                }
            )
        ctx["rows"] = rows
        return ctx
