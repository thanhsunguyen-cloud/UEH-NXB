"""View M8 — Tài chính và công nợ phí dịch vụ xuất bản.

- Xem: `FinanceViewMixin` (EDITOR có finance_access VIEW/MANAGE).
- Ghi nhận/điều chỉnh: `FinanceManageMixin` (EDITOR có MANAGE).
- Người khác nhận 404. Không có URL xóa; sửa sai bằng bút toán điều chỉnh/đảo.
"""

from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.views import View

from apps.core.audit import log_event
from apps.core.finance import create_collection, create_receivable, effective_receivable_amount
from apps.core.mixins import FinanceManageMixin, FinanceViewMixin
from apps.core.models import AuditEvent, Collection, Receivable
from apps.core.permissions import can_manage_finance, cases_visible_to

from . import services
from .forms import (
    AdjustmentForm,
    CaseSearchForm,
    CollectionForm,
    DebtFilterForm,
    OverviewFilterForm,
    ReceivableForm,
    ReversalForm,
)

DEBT_PAGE_SIZE = 25
RECENT_EVENTS = 20


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _querystring_without_page(request) -> str:
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("export", None)
    return params.urlencode()


def _csv_response(request, rows, filename: str, report: str, filters: dict) -> HttpResponse:
    log_event(
        actor=request.user,
        action="finance.export",
        object_type="FinanceReport",
        object_id=report,
        data={"report": report, "filters": filters, "rows": len(rows) - 1},
        request=request,
    )
    response = HttpResponse(services.render_csv(rows), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _validation_messages(exc: ValidationError) -> list[str]:
    return [str(m) for m in exc.messages]


# ---------------------------------------------------------------------------
# 2.1 Tổng quan
# ---------------------------------------------------------------------------


class FinanceOverviewView(FinanceViewMixin, View):
    template_name = "finance/overview.html"

    def get(self, request):
        form = OverviewFilterForm(request.GET or None)
        if form.is_bound and form.is_valid():
            filters = form.cleaned_data
        else:
            today = timezone.localdate()
            filters = {
                "date_from": date(today.year, 1, 1),
                "date_to": date(today.year, 12, 31),
                "fee_type": None,
                "publication_mode": "",
            }
            if not form.is_bound:
                form = OverviewFilterForm(
                    initial={"date_from": filters["date_from"], "date_to": filters["date_to"]}
                )
        data = services.build_overview(
            filters["date_from"],
            filters["date_to"],
            fee_type=filters["fee_type"],
            publication_mode=filters["publication_mode"],
        )
        if request.GET.get("export") == "csv":
            return _csv_response(
                request,
                services.overview_csv_rows(data),
                f"tong-quan-tai-chinh-{data.date_from:%Y%m%d}-{data.date_to:%Y%m%d}.csv",
                "overview",
                {
                    "date_from": data.date_from.isoformat(),
                    "date_to": data.date_to.isoformat(),
                    "fee_type": filters["fee_type"].pk if filters["fee_type"] else None,
                    "publication_mode": filters["publication_mode"],
                },
            )
        ctx = {
            "form": form,
            "data": data,
            "querystring": _querystring_without_page(request),
            "can_manage": can_manage_finance(request.user),
        }
        return render(request, self.template_name, ctx)


# ---------------------------------------------------------------------------
# 2.2 Công nợ
# ---------------------------------------------------------------------------


class FinanceDebtView(FinanceViewMixin, View):
    template_name = "finance/debt.html"
    partial_template_name = "finance/_debt_results.html"

    def get(self, request):
        form = DebtFilterForm(request.GET or None)
        filters = form.cleaned_data if form.is_valid() else {}
        today = timezone.localdate()
        lines = services.debt_lines(
            today=today,
            fee_type=filters.get("fee_type"),
            payer=filters.get("payer", ""),
            q=filters.get("q", ""),
        )
        summary = services.aging_summary(lines)
        bucket = filters.get("bucket", "")
        if bucket:
            lines = [line for line in lines if line.bucket == bucket]
        if request.GET.get("export") == "csv":
            return _csv_response(
                request,
                services.debt_csv_rows(lines),
                f"cong-no-{today:%Y%m%d}.csv",
                "debt",
                {
                    "q": filters.get("q", ""),
                    "bucket": bucket,
                    "fee_type": filters["fee_type"].pk if filters.get("fee_type") else None,
                    "payer": filters.get("payer", ""),
                },
            )
        page_obj = Paginator(lines, DEBT_PAGE_SIZE).get_page(request.GET.get("page"))
        ctx = {
            "form": form,
            "page_obj": page_obj,
            "lines": page_obj.object_list,
            "summary": summary,
            "summary_total": sum((row["amount"] for row in summary), services.ZERO),
            "today": today,
            "querystring": _querystring_without_page(request),
            "can_manage": can_manage_finance(request.user),
        }
        template = self.partial_template_name if _is_htmx(request) else self.template_name
        return render(request, template, ctx)


# ---------------------------------------------------------------------------
# 2.3 Tài chính một hồ sơ
# ---------------------------------------------------------------------------


class FinanceCaseView(FinanceViewMixin, View):
    template_name = "finance/case.html"

    def get(self, request, case_id):
        case = get_object_or_404(cases_visible_to(request.user).select_related("owner"), pk=case_id)
        ctx = {
            "case": case,
            "finance": services.case_finance(case, timezone.localdate()),
            "can_manage": can_manage_finance(request.user),
            "backoffice_url": f"/noi-bo/ho-so/{case.pk}/",
        }
        return render(request, self.template_name, ctx)


class ManageFormView(FinanceManageMixin, View):
    """Khung chung cho các trang form ghi nhận (GET hiện form, POST lưu)."""

    template_name = "finance/entry_form.html"
    page_title = ""
    submit_label = _lazy("Lưu")

    def case_url(self, case):
        return reverse("finance:case", args=[case.pk])

    def render_form(self, form, case, status=200, **extra):
        ctx = {
            "form": form,
            "case": case,
            "page_title": self.page_title,
            "submit_label": self.submit_label,
            "back_url": self.case_url(case),
            **extra,
        }
        return render(self.request, self.template_name, ctx, status=status)

    def get_receivable(self, pk):
        return get_object_or_404(
            Receivable.objects.select_related("case", "case__owner", "fee_type"),
            pk=pk,
            adjusts__isnull=True,
            case__in=cases_visible_to(self.request.user),
        )


class ReceivableCreateView(ManageFormView):
    page_title = _lazy("Thêm khoản phải thu")

    def get_case(self, case_id):
        return get_object_or_404(
            cases_visible_to(self.request.user).select_related("owner"), pk=case_id
        )

    def get(self, request, case_id):
        case = self.get_case(case_id)
        form = ReceivableForm(
            initial={
                "payer_name": services.default_payer_name(case),
                "contract_number": case.contract_number,
            }
        )
        return self.render_form(form, case)

    def post(self, request, case_id):
        case = self.get_case(case_id)
        form = ReceivableForm(request.POST)
        if not form.is_valid():
            return self.render_form(form, case, status=400)
        data = form.cleaned_data
        try:
            create_receivable(
                actor=request.user,
                case=case,
                fee_type=data["fee_type"],
                amount=data["amount"],
                payer_name=data["payer_name"].strip() or services.default_payer_name(case),
                description=data["description"],
                contract_number=data["contract_number"],
                invoice_number=data["invoice_number"],
                invoice_date=data["invoice_date"],
                due_date=data["due_date"],
                note=data["note"],
                request=request,
            )
        except ValidationError as exc:
            for msg in _validation_messages(exc):
                form.add_error(None, msg)
            return self.render_form(form, case, status=400)
        messages.success(request, _("Đã thêm khoản phải thu."))
        return redirect(self.case_url(case))


class CollectionCreateView(ManageFormView):
    page_title = _lazy("Ghi nhận đã thu")

    def get(self, request, pk):
        rec = self.get_receivable(pk)
        form = CollectionForm(receivable=rec, initial={"paid_date": timezone.localdate()})
        return self.render_form(form, rec.case, receivable=rec, line=self._line(rec))

    def _line(self, rec):
        return services.make_line(rec, timezone.localdate())

    def post(self, request, pk):
        rec = self.get_receivable(pk)
        form = CollectionForm(request.POST, receivable=rec)
        if not form.is_valid():
            return self.render_form(
                form, rec.case, status=400, receivable=rec, line=self._line(rec)
            )
        data = form.cleaned_data
        try:
            create_collection(
                actor=request.user,
                receivable=rec,
                paid_date=data["paid_date"],
                amount=data["amount"],
                method=data["method"],
                reference=data["reference"],
                note=data["note"],
                confirm_overpayment=data["confirm_overpayment"],
                request=request,
            )
        except ValidationError as exc:
            for msg in _validation_messages(exc):
                form.add_error(None, msg)
            return self.render_form(
                form, rec.case, status=400, receivable=rec, line=self._line(rec)
            )
        messages.success(request, _("Đã ghi nhận khoản thu."))
        return redirect(self.case_url(rec.case))


class ReceivableAdjustView(ManageFormView):
    page_title = _lazy("Điều chỉnh khoản phải thu")

    def _form(self, rec, data=None):
        return AdjustmentForm(data, effective_amount=effective_receivable_amount(rec))

    def get(self, request, pk):
        rec = self.get_receivable(pk)
        return self.render_form(
            self._form(rec),
            rec.case,
            receivable=rec,
            line=services.make_line(rec, timezone.localdate()),
        )

    def post(self, request, pk):
        rec = self.get_receivable(pk)
        form = self._form(rec, request.POST)
        if not form.is_valid():
            return self.render_form(
                form,
                rec.case,
                status=400,
                receivable=rec,
                line=services.make_line(rec, timezone.localdate()),
            )
        create_receivable(
            actor=request.user,
            case=rec.case,
            fee_type=rec.fee_type,
            amount=form.cleaned_data["amount"],
            payer_name=rec.payer_name,
            description=_("Điều chỉnh khoản #%(pk)s") % {"pk": rec.pk},
            contract_number=rec.contract_number,
            is_adjustment=True,
            adjusts=rec,
            note=form.cleaned_data["note"],
            request=request,
        )
        messages.success(request, _("Đã tạo bút toán điều chỉnh."))
        return redirect(self.case_url(rec.case))


class CollectionReverseView(ManageFormView):
    page_title = _lazy("Đảo khoản thu")
    submit_label = _lazy("Đảo khoản thu")

    def get_collection(self, pk):
        col = get_object_or_404(
            Collection.objects.select_related(
                "receivable", "receivable__case", "receivable__case__owner"
            ),
            pk=pk,
            is_adjustment=False,
            receivable__case__in=cases_visible_to(self.request.user),
        )
        return col

    def _is_reversed(self, col) -> bool:
        return col.pk in services.reversed_collection_ids(col.receivable.case)

    def get(self, request, pk):
        col = self.get_collection(pk)
        if self._is_reversed(col):
            messages.error(request, _("Khoản thu này đã được đảo."))
            return redirect(self.case_url(col.receivable.case))
        form = ReversalForm(initial={"paid_date": timezone.localdate()})
        return self.render_form(form, col.receivable.case, collection=col)

    def post(self, request, pk):
        col = self.get_collection(pk)
        case = col.receivable.case
        if self._is_reversed(col):
            messages.error(request, _("Khoản thu này đã được đảo."))
            return redirect(self.case_url(case))
        form = ReversalForm(request.POST)
        if not form.is_valid():
            return self.render_form(form, case, status=400, collection=col)
        create_collection(
            actor=request.user,
            receivable=col.receivable,
            paid_date=form.cleaned_data["paid_date"],
            amount=-col.amount,
            method=col.method,
            reference=col.reference,
            is_adjustment=True,
            note=f"{services.REVERSAL_TAG.format(pk=col.pk)} {form.cleaned_data['note']}",
            request=request,
        )
        messages.success(request, _("Đã đảo khoản thu."))
        return redirect(self.case_url(case))


# ---------------------------------------------------------------------------
# 2.4 Ghi nhận
# ---------------------------------------------------------------------------


class FinanceManageView(FinanceManageMixin, View):
    template_name = "finance/manage.html"

    def get(self, request):
        form = CaseSearchForm(request.GET or None)
        results = None
        term = form.cleaned_data.get("q", "").strip() if form.is_valid() else ""
        if term:
            matches = list(
                cases_visible_to(request.user)
                .filter(services.search_cases_q(term))
                .select_related("owner")
                .order_by("-created_at")[:21]
            )
            if len(matches) == 1:
                return redirect(reverse("finance:case", args=[matches[0].pk]))
            results = matches[:20]
            if not results:
                messages.info(request, _("Không tìm thấy hồ sơ phù hợp."))
        events = (
            AuditEvent.objects.filter(action__startswith="finance.")
            .select_related("actor", "case")
            .order_by("-at", "-id")[:RECENT_EVENTS]
        )
        ctx = {
            "form": form,
            "results": results,
            "events": events,
            "term": term,
            "can_manage": True,
        }
        return render(request, self.template_name, ctx)
