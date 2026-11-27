"""View M5 — Tra cứu, thống kê danh mục xuất bản, nhập Excel dữ liệu cũ.

Chỉ EDITOR (EditorRequiredMixin / PublicationStatsMixin); CUSTOMER và ADMIN nhận 404.
"""

from __future__ import annotations

from django.contrib import messages
from django.core import signing
from django.core.paginator import Paginator
from django.http import FileResponse, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View

from apps.core.audit import log_event
from apps.core.mixins import EditorRequiredMixin, PublicationStatsMixin
from apps.core.permissions import cases_visible_to

from . import importer, services
from .forms import CatalogStatsForm, ImportConfirmForm, ImportUploadForm, SearchForm
from .models import ImportBatch

PAGE_SIZE = 25
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
IMPORT_SALT = "reports.import"
IMPORT_MAX_AGE = 60 * 60  # 1 giờ giữa bước kiểm tra và xác nhận


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


# ---------------------------------------------------------------------------
# 2.1 Tra cứu
# ---------------------------------------------------------------------------


class ReportsSearchView(EditorRequiredMixin, View):
    template_name = "reports/search.html"
    partial_template_name = "reports/_search_results.html"

    def get(self, request):
        form = SearchForm(request.GET or None)
        data = form.cleaned_data if form.is_valid() else {}
        cases = services.search_cases(cases_visible_to(request.user), data)
        page_obj = Paginator(cases, PAGE_SIZE).get_page(request.GET.get("page"))
        imported = services.imported_case_ids()
        rows = [
            {
                "case": case,
                "authors": services.authors_text(case),
                "is_imported": str(case.pk) in imported,
            }
            for case in page_obj.object_list
        ]
        ctx = {"form": form, "page_obj": page_obj, "rows": rows}
        template = self.partial_template_name if _is_htmx(request) else self.template_name
        return render(request, template, ctx)


# ---------------------------------------------------------------------------
# 2.2 Thống kê danh mục xuất bản
# ---------------------------------------------------------------------------


def _stats_context(request):
    params = request.GET.copy()
    params.pop("page", None)
    form = CatalogStatsForm(params or None)
    data = form.cleaned_data if form.is_valid() else {}
    default_from, default_to = services.default_period(timezone.localdate())
    date_from = data.get("date_from") or default_from
    date_to = data.get("date_to") or default_to
    if date_from > date_to:
        date_from, date_to = default_from, default_to
    group = data.get("group") or services.GROUP_MONTH
    data = {**data, "date_from": date_from, "date_to": date_to}
    qs = services.catalog_queryset(cases_visible_to(request.user), data)
    summary = services.catalog_summary(qs, group, date_from, date_to)
    return form, data, qs, summary, group, params


class ReportsCatalogStatsView(PublicationStatsMixin, View):
    template_name = "reports/catalog_stats.html"

    def get(self, request):
        form, data, qs, summary, group, params = _stats_context(request)
        page_obj = Paginator(services.catalog_rows(qs), PAGE_SIZE).get_page(request.GET.get("page"))
        rows = [{"case": c, "authors": services.authors_text(c)} for c in page_obj.object_list]
        ctx = {
            "form": form,
            "summary": summary,
            "group": group,
            "date_from": data["date_from"],
            "date_to": data["date_to"],
            "page_obj": page_obj,
            "rows": rows,
            "export_query": params.urlencode(),
        }
        return render(request, self.template_name, ctx)


class ReportsCatalogExportView(PublicationStatsMixin, View):
    def get(self, request):
        form, data, qs, summary, group, params = _stats_context(request)
        filters = services.summary_filters_text(data, data["date_from"], data["date_to"], group)
        tmp = services.build_catalog_workbook(services.catalog_rows(qs), summary, filters)
        log_event(
            actor=request.user,
            action="report.export",
            object_type="Report",
            object_id="catalog_stats",
            data={
                "date_from": data["date_from"].isoformat(),
                "date_to": data["date_to"].isoformat(),
                "group": group,
                "category": data["category"].pk if data.get("category") else None,
                "field": data["field"].pk if data.get("field") else None,
                "mode": data.get("mode") or None,
                "total": summary["total"],
            },
            request=request,
        )
        filename = "danh-muc-xuat-ban_{}_{}.xlsx".format(
            data["date_from"].strftime("%Y%m%d"), data["date_to"].strftime("%Y%m%d")
        )
        return FileResponse(tmp, as_attachment=True, filename=filename, content_type=XLSX_MIME)


# ---------------------------------------------------------------------------
# 2.3 Nhập Excel dữ liệu cũ
# ---------------------------------------------------------------------------


class ImportTemplateDownloadView(PublicationStatsMixin, View):
    def get(self, request):
        response = HttpResponse(importer.build_template_workbook(), content_type=XLSX_MIME)
        response["Content-Disposition"] = 'attachment; filename="mau-nhap-danh-muc.xlsx"'
        return response


class ImportView(PublicationStatsMixin, View):
    """Bước 1 – kiểm tra (không ghi database) và Bước 2 – xác nhận nhập."""

    template_name = "reports/import.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ImportUploadForm()})

    def post(self, request):
        if "payload" in request.POST:
            return self._confirm(request)
        return self._check(request)

    def _check(self, request):
        form = ImportUploadForm(request.POST, request.FILES)
        ctx = {"form": form}
        if not form.is_valid():
            return render(request, self.template_name, ctx)
        uploaded = form.cleaned_data["file"]
        try:
            rows = importer.parse_workbook(uploaded)
        except importer.ImportFileError as exc:
            form.add_error("file", str(exc))
            return render(request, self.template_name, ctx)
        results = importer.validate_rows(rows)
        valid_count = sum(1 for r in results if r.is_valid)
        payload = signing.dumps(
            {"user": request.user.pk, "filename": uploaded.name, "rows": rows},
            salt=IMPORT_SALT,
            compress=True,
        )
        ctx.update(
            {
                "results": results,
                "filename": uploaded.name,
                "total": len(results),
                "valid_count": valid_count,
                "error_count": len(results) - valid_count,
                "confirm_form": ImportConfirmForm(initial={"payload": payload}),
                "columns": importer.COLUMNS,
            }
        )
        return render(request, self.template_name, ctx)

    def _confirm(self, request):
        form = ImportConfirmForm(request.POST)
        payload = None
        if form.is_valid():
            try:
                payload = signing.loads(
                    form.cleaned_data["payload"], salt=IMPORT_SALT, max_age=IMPORT_MAX_AGE
                )
            except signing.BadSignature:
                payload = None
        if not payload or payload.get("user") != request.user.pk:
            messages.error(
                request, _("Phiên kiểm tra đã hết hạn hoặc không hợp lệ. Vui lòng tải file lại.")
            )
            return redirect("reports:import")
        batch = importer.import_rows(
            rows=payload["rows"], filename=payload["filename"], actor=request.user, request=request
        )
        if batch is None:
            messages.error(request, _("Không có dòng hợp lệ để nhập."))
            return redirect("reports:import")
        messages.success(
            request,
            _("Đã nhập %(ok)s dòng (lô #%(id)s); %(err)s dòng lỗi không được nhập.")
            % {"ok": batch.imported_rows, "id": batch.pk, "err": batch.error_rows},
        )
        return redirect("reports:import_history")


class ImportHistoryView(PublicationStatsMixin, View):
    template_name = "reports/import_history.html"

    def get(self, request):
        batches = ImportBatch.objects.select_related("created_by").order_by("-created_at", "-id")
        page_obj = Paginator(batches, PAGE_SIZE).get_page(request.GET.get("page"))
        return render(
            request,
            self.template_name,
            {
                "page_obj": page_obj,
                "batches": page_obj.object_list,
                "is_paginated": page_obj.has_other_pages(),
            },
        )
