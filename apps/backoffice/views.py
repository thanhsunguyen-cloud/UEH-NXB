"""View M3 — Tác nghiệp của biên tập viên (chỉ EDITOR; CUSTOMER/ADMIN nhận 404).

Mọi view kế thừa EditorRequiredMixin (+ CaseAccessMixin cho trang hồ sơ).
Đổi trạng thái chỉ qua apps.core.workflow.change_status().
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import TemplateView

from apps.core.audit import log_event
from apps.core.mixins import CaseAccessMixin, EditorRequiredMixin
from apps.core.models import (
    CaseStatus,
    DocumentType,
    SupplementRequest,
    SupplementStatus,
)
from apps.core.permissions import (
    can_edit_case_info,
    can_view_finance,
    can_view_note,
    cases_visible_to,
)
from apps.core.workflow import (
    WorkflowError,
    change_case_owner,
    change_status,
    record_manuscript_review,
)

from . import services
from .forms import (
    AssignEditorForm,
    CaseFilterForm,
    CaseInfoForm,
    CaseNoteForm,
    ChangeOwnerForm,
    ContributorForm,
    ManuscriptReviewForm,
    TransitionForm,
)

PAGE_SIZE = 25
TABS = ("overview", "contributors", "documents", "workflow", "notes")


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


# ---------------------------------------------------------------------------
# 2.1 Danh sách hồ sơ
# ---------------------------------------------------------------------------


class BackofficeHomeView(EditorRequiredMixin, View):
    template_name = "backoffice/home.html"
    partial_template_name = "backoffice/_case_table.html"

    def get(self, request):
        form = CaseFilterForm(request.GET or None)
        data = form.cleaned_data if form.is_valid() else {}
        cases = services.filter_cases(cases_visible_to(request.user), data, request.user)
        page_obj = Paginator(cases, PAGE_SIZE).get_page(request.GET.get("page"))
        ctx = {"filter_form": form, "page_obj": page_obj, "cases": page_obj.object_list}
        template = self.partial_template_name if _is_htmx(request) else self.template_name
        return render(request, template, ctx)


# ---------------------------------------------------------------------------
# 2.2 Hồ sơ cần xử lý
# ---------------------------------------------------------------------------


class BackofficeQueueView(EditorRequiredMixin, TemplateView):
    template_name = "backoffice/queue.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cases = cases_visible_to(self.request.user)
        mine = self.request.GET.get("mine") == "1"
        if mine:
            cases = cases.filter(primary_editor=self.request.user)
        ctx.update({"groups": services.queue_groups(cases), "mine": mine})
        return ctx


# ---------------------------------------------------------------------------
# 2.3 Chi tiết hồ sơ
# ---------------------------------------------------------------------------


class CaseViewBase(EditorRequiredMixin, CaseAccessMixin, View):
    """Khung chung: dựng ngữ cảnh 5 tab và hiển thị lại trang khi form có lỗi."""

    template_name = "backoffice/case_detail.html"

    def detail_url(self, tab: str = "overview") -> str:
        url = reverse("backoffice:case_detail", args=[self.case.pk])
        return f"{url}?tab={tab}" if tab != "overview" else url

    def redirect_tab(self, tab: str):
        return redirect(self.detail_url(tab))

    def build_context(self, tab: str = "overview", **forms) -> dict:
        case = self.case
        user = self.request.user
        editable = can_edit_case_info(user, case)
        documents = list(
            case.documents.select_related("uploaded_by").order_by(
                "doc_type", "form_code", "-version"
            )
        )
        doc_groups: dict[str, dict] = {}
        for doc in documents:
            group = doc_groups.setdefault(
                doc.doc_type, {"label": doc.get_doc_type_display(), "docs": []}
            )
            group["docs"].append(doc)
        notes = [
            n
            for n in case.notes.select_related("author").order_by("-created_at")
            if can_view_note(user, n)
        ]
        contributors = list(case.contributors.all())
        ctx = {
            "case": case,
            "tab": tab if tab in TABS else "overview",
            "can_edit": editable,
            "can_view_finance": can_view_finance(user),
            "finance_url": f"/tai-chinh/ho-so/{case.pk}/",
            "doc_groups": list(doc_groups.values()),
            "doc_type_choices": DocumentType.choices,
            "contributors": contributors,
            "contributor_forms": [
                (
                    c,
                    forms.get(f"contributor_{c.pk}")
                    or ContributorForm(instance=c, prefix=f"c{c.pk}"),
                )
                for c in contributors
            ],
            "transitions": services.transition_options(user, case),
            "reviews": case.reviews.select_related("manuscript", "form4", "confirmed_by"),
            "history": case.status_history.select_related("actor").order_by("-at", "-id"),
            "notes": notes,
            "supplements": case.supplement_requests.select_related("requested_by"),
            "is_editing": case.status == CaseStatus.EDITING,
            "info_form": forms.get("info_form") or CaseInfoForm(instance=case),
            "assign_form": forms.get("assign_form")
            or AssignEditorForm(initial={"primary_editor": case.primary_editor_id}),
            "owner_form": forms.get("owner_form") or ChangeOwnerForm(),
            "contributor_form": forms.get("contributor_form")
            or ContributorForm(initial={"order": len(contributors) + 1}, prefix="new"),
            "review_form": forms.get("review_form") or ManuscriptReviewForm(case=case),
            "transition_errors": forms.get("transition_errors") or {},
            "note_form": forms.get("note_form") or CaseNoteForm(),
        }
        return ctx

    def render_detail(self, tab: str = "overview", status: int = 200, **forms):
        return render(
            self.request, self.template_name, self.build_context(tab, **forms), status=status
        )

    def deny_readonly(self, tab: str):
        messages.error(
            self.request,
            _("Hồ sơ đã hoàn tất hoặc lưu trữ, không thể sửa thông tin."),
        )
        return self.redirect_tab(tab)


class BackofficeCaseDetailView(CaseViewBase):
    def get(self, request, case_id):
        return self.render_detail(request.GET.get("tab", "overview"))


class CaseUpdateView(CaseViewBase):
    def post(self, request, case_id):
        case = self.case
        if not can_edit_case_info(request.user, case):
            return self.deny_readonly("overview")
        fields = CaseInfoForm.Meta.fields
        before = services.snapshot(case, fields)
        form = CaseInfoForm(request.POST, instance=case)
        if not form.is_valid():
            # Hoàn nguyên đối tượng trong bộ nhớ để phần hiển thị không lẫn giá trị sai.
            case.refresh_from_db()
            return self.render_detail("overview", info_form=form)
        with transaction.atomic():
            form.save()
            after = services.snapshot(case, fields)
            changed = [f for f in fields if before[f] != after[f]]
            if changed:
                log_event(
                    actor=request.user,
                    action="case.update",
                    object_type="PublicationCase",
                    object_id=str(case.pk),
                    case=case,
                    data={
                        "before": {f: before[f] for f in changed},
                        "after": {f: after[f] for f in changed},
                    },
                    request=request,
                )
        messages.success(request, _("Đã lưu thông tin hồ sơ."))
        return self.redirect_tab("overview")


class CaseAssignEditorView(CaseViewBase):
    def post(self, request, case_id):
        case = self.case
        if not can_edit_case_info(request.user, case):
            return self.deny_readonly("overview")
        form = AssignEditorForm(request.POST)
        if not form.is_valid():
            return self.render_detail("overview", assign_form=form)
        new_editor = form.cleaned_data["primary_editor"]
        old_editor = case.primary_editor
        if (old_editor and old_editor.pk) != (new_editor and new_editor.pk):
            with transaction.atomic():
                case.primary_editor = new_editor
                case.save(update_fields=["primary_editor", "updated_at"])
                log_event(
                    actor=request.user,
                    action="case.assign_editor",
                    object_type="PublicationCase",
                    object_id=str(case.pk),
                    case=case,
                    data={
                        "before": {
                            "primary_editor_id": old_editor.pk if old_editor else None,
                            "primary_editor_email": old_editor.email if old_editor else None,
                        },
                        "after": {
                            "primary_editor_id": new_editor.pk if new_editor else None,
                            "primary_editor_email": new_editor.email if new_editor else None,
                        },
                    },
                    request=request,
                )
        messages.success(request, _("Đã cập nhật BTV phụ trách."))
        return self.redirect_tab("overview")


class CaseChangeOwnerView(CaseViewBase):
    def post(self, request, case_id):
        case = self.case
        if not can_edit_case_info(request.user, case):
            return self.deny_readonly("overview")
        form = ChangeOwnerForm(request.POST)
        if not form.is_valid():
            return self.render_detail("overview", owner_form=form)
        try:
            change_case_owner(
                case,
                form.new_owner,
                actor=request.user,
                note=form.cleaned_data["reason"],
                request=request,
            )
        except WorkflowError as exc:
            form.add_error(None, str(exc))
            case.refresh_from_db()
            return self.render_detail("overview", owner_form=form)
        messages.success(request, _("Đã đổi người đại diện hồ sơ."))
        return self.redirect_tab("overview")


# ---------------------------------------------------------------------------
# Tab Tác giả
# ---------------------------------------------------------------------------

CONTRIBUTOR_FIELDS = ContributorForm.Meta.fields


class ContributorCreateView(CaseViewBase):
    def post(self, request, case_id):
        case = self.case
        if not can_edit_case_info(request.user, case):
            return self.deny_readonly("contributors")
        form = ContributorForm(request.POST, prefix="new")
        if not form.is_valid():
            return self.render_detail("contributors", contributor_form=form)
        with transaction.atomic():
            contributor = form.save(commit=False)
            contributor.case = case
            contributor.save()
            log_event(
                actor=request.user,
                action="contributor.add",
                object_type="Contributor",
                object_id=str(contributor.pk),
                case=case,
                data={"after": services.snapshot(contributor, CONTRIBUTOR_FIELDS)},
                request=request,
            )
        messages.success(request, _("Đã thêm tác giả."))
        return self.redirect_tab("contributors")


class ContributorUpdateView(CaseViewBase):
    def post(self, request, case_id, pk):
        case = self.case
        contributor = get_object_or_404(case.contributors, pk=pk)
        if not can_edit_case_info(request.user, case):
            return self.deny_readonly("contributors")
        before = services.snapshot(contributor, CONTRIBUTOR_FIELDS)
        form = ContributorForm(request.POST, instance=contributor, prefix=f"c{contributor.pk}")
        if not form.is_valid():
            return self.render_detail("contributors", **{f"contributor_{contributor.pk}": form})
        with transaction.atomic():
            form.save()
            log_event(
                actor=request.user,
                action="contributor.update",
                object_type="Contributor",
                object_id=str(contributor.pk),
                case=case,
                data={
                    "before": before,
                    "after": services.snapshot(contributor, CONTRIBUTOR_FIELDS),
                },
                request=request,
            )
        messages.success(request, _("Đã cập nhật tác giả."))
        return self.redirect_tab("contributors")


class ContributorDeleteView(CaseViewBase):
    def post(self, request, case_id, pk):
        case = self.case
        contributor = get_object_or_404(case.contributors, pk=pk)
        if not can_edit_case_info(request.user, case):
            return self.deny_readonly("contributors")
        before = services.snapshot(contributor, CONTRIBUTOR_FIELDS)
        contributor_id = contributor.pk
        with transaction.atomic():
            contributor.delete()
            log_event(
                actor=request.user,
                action="contributor.delete",
                object_type="Contributor",
                object_id=str(contributor_id),
                case=case,
                data={"before": before},
                request=request,
            )
        messages.success(request, _("Đã xóa tác giả."))
        return self.redirect_tab("contributors")


# ---------------------------------------------------------------------------
# Tab Quy trình
# ---------------------------------------------------------------------------


class CaseTransitionView(CaseViewBase):
    def post(self, request, case_id):
        case = self.case
        form = TransitionForm(request.POST)
        if not form.is_valid():
            to_status = request.POST.get("to_status", "")
            errors = [e for errs in form.errors.values() for e in errs]
            for error in errors:
                messages.error(request, error)
            return self.render_detail("workflow", transition_errors={to_status: errors})
        to_status = form.cleaned_data["to_status"]
        note = form.cleaned_data["note"]
        try:
            with transaction.atomic():
                if to_status == CaseStatus.NEED_SUPPLEMENT and case.status == CaseStatus.SUBMITTED:
                    supplement = SupplementRequest.objects.create(
                        case=case,
                        requested_by=request.user,
                        message=note,
                        status=SupplementStatus.OPEN,
                    )
                    log_event(
                        actor=request.user,
                        action="supplement.create",
                        object_type="SupplementRequest",
                        object_id=str(supplement.pk),
                        case=case,
                        data={"message": note},
                        request=request,
                    )
                change_status(case, to_status, actor=request.user, note=note, request=request)
        except WorkflowError as exc:
            messages.error(request, str(exc))
            return self.redirect_tab("workflow")
        messages.success(
            request,
            _("Đã chuyển hồ sơ sang trạng thái “%(status)s”.")
            % {"status": case.get_status_display()},
        )
        return self.redirect_tab("workflow")


class CaseReviewView(CaseViewBase):
    def post(self, request, case_id):
        case = self.case
        if case.status != CaseStatus.EDITING:
            messages.error(
                request, _("Chỉ xác nhận duyệt Mẫu 4 khi hồ sơ đang ở trạng thái Đang biên tập.")
            )
            return self.redirect_tab("workflow")
        form = ManuscriptReviewForm(request.POST, case=case)
        if not form.is_valid():
            messages.error(request, _("Chưa xác nhận được kết quả duyệt. Vui lòng kiểm tra lại."))
            return self.render_detail("workflow", review_form=form)
        try:
            review = record_manuscript_review(
                case=case,
                manuscript=form.cleaned_data["manuscript"],
                form4=form.cleaned_data["form4"],
                result=form.cleaned_data["result"],
                confirmed_by=request.user,
                note=form.cleaned_data["note"],
                request=request,
            )
        except (ValidationError, WorkflowError) as exc:  # pragma: no cover - form đã chặn trước
            messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
            return self.render_detail("workflow", review_form=form)
        target = services.REVIEW_SUGGESTION[review.result]
        messages.success(
            request,
            _("Đã ghi nhận kết quả duyệt “%(result)s”. Bấm nút “%(label)s” để chuyển trạng thái.")
            % {
                "result": review.get_result_display(),
                "label": services.transition_label(case.status, target),
            },
        )
        return self.redirect_tab("workflow")


# ---------------------------------------------------------------------------
# Tab Ghi chú & trao đổi
# ---------------------------------------------------------------------------


class CaseNoteCreateView(CaseViewBase):
    def post(self, request, case_id):
        case = self.case
        form = CaseNoteForm(request.POST)
        if not form.is_valid():
            return self.render_detail("notes", note_form=form)
        with transaction.atomic():
            note = form.save(commit=False)
            note.case = case
            note.author = request.user
            note.save()
            log_event(
                actor=request.user,
                action="case.note_add",
                object_type="CaseNote",
                object_id=str(note.pk),
                case=case,
                data={"visibility": note.visibility},
                request=request,
            )
        messages.success(request, _("Đã thêm ghi chú."))
        return self.redirect_tab("notes")


class SupplementResolveView(CaseViewBase):
    def post(self, request, case_id, pk):
        case = self.case
        supplement = get_object_or_404(case.supplement_requests, pk=pk)
        if supplement.status == SupplementStatus.RESOLVED:
            messages.info(request, _("Yêu cầu bổ sung này đã được đánh dấu hoàn tất."))
            return self.redirect_tab("notes")
        with transaction.atomic():
            supplement.status = SupplementStatus.RESOLVED
            supplement.resolved_at = timezone.now()
            supplement.save(update_fields=["status", "resolved_at", "updated_at"])
            log_event(
                actor=request.user,
                action="supplement.resolve",
                object_type="SupplementRequest",
                object_id=str(supplement.pk),
                case=case,
                data={
                    "before": {"status": SupplementStatus.OPEN},
                    "after": {"status": SupplementStatus.RESOLVED},
                },
                request=request,
            )
        messages.success(request, _("Đã đánh dấu yêu cầu bổ sung là đã bổ sung."))
        return self.redirect_tab("notes")
