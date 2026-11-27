"""Views của cổng khách hàng (M2).

Mọi view kế thừa CustomerRequiredMixin (+ CaseAccessMixin khi gắn với một hồ sơ);
đổi trạng thái chỉ qua apps.core.workflow.change_status.
"""

from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.core.audit import log_event
from apps.core.mixins import CaseAccessMixin, CustomerRequiredMixin
from apps.core.models import (
    CaseNote,
    CaseStatus,
    DocumentType,
    NoteVisibility,
    PublicationMode,
    SupplementStatus,
)
from apps.core.permissions import (
    can_download,
    can_edit_case_info,
    can_upload,
    can_view_note,
    cases_visible_to,
)
from apps.core.workflow import WorkflowError, allowed_transitions, change_status
from apps.customer.forms import (
    CASE_FIELDS,
    CONTRIBUTOR_FIELDS,
    CaseInfoForm,
    CaseNoteForm,
    ContributorForm,
    ProfileForm,
)
from apps.customer.labels import customer_status_choices

# Các loại tài liệu khách thấy trên trang chi tiết (mục 2.3.3); FORM_1 chỉ khi Liên kết.
CUSTOMER_DOC_TYPES = [
    DocumentType.MANUSCRIPT,
    DocumentType.FORM_1,
    DocumentType.FORM_2,
    DocumentType.FORM_3,
    DocumentType.OTHER,
]


def _snapshot(obj, fields: list[str]) -> dict:
    """Ảnh chụp giá trị các trường để ghi AuditEvent (before/after)."""
    data = {}
    for name in fields:
        field = obj._meta.get_field(name)
        value = getattr(obj, field.attname)
        data[name] = value if value is None or isinstance(value, bool | int) else str(value)
    return data


# Ghi chú chuyển trạng thái được hiện cho khách (khớp M3 và email M4).
CUSTOMER_VISIBLE_NOTE_STATUSES = (
    CaseStatus.NEED_SUPPLEMENT,
    CaseStatus.REVISION_REQUIRED,
    CaseStatus.REJECTED,
)


def public_forms_url() -> str:
    """Link trang công khai "Tải biểu mẫu" (M6)."""
    return reverse("public_site:forms")


def submit_checklist(case) -> list[dict]:
    """Danh sách điều kiện nộp, khớp với điều kiện DRAFT→SUBMITTED của change_status."""
    doc_types = set(case.documents.values_list("doc_type", flat=True))
    items = [
        {"label": _("Bản thảo"), "ok": DocumentType.MANUSCRIPT in doc_types},
        {"label": _("Mẫu 2"), "ok": DocumentType.FORM_2 in doc_types},
        {"label": _("Mẫu 3"), "ok": DocumentType.FORM_3 in doc_types},
    ]
    if case.publication_mode == PublicationMode.LINKED:
        items.append(
            {"label": _("Mẫu 1 (xuất bản liên kết)"), "ok": DocumentType.FORM_1 in doc_types}
        )
        items.append(
            {"label": _("Tên đơn vị liên kết"), "ok": bool((case.partner_name or "").strip())}
        )
    items.append({"label": _("Ít nhất 01 tác giả"), "ok": case.contributors.exists()})
    return items


# ---------------------------------------------------------------------------
# 2.1 Hồ sơ của tôi
# ---------------------------------------------------------------------------


class CustomerHomeView(CustomerRequiredMixin, ListView):
    template_name = "customer/home.html"
    context_object_name = "cases"
    paginate_by = 20

    def get_queryset(self):
        qs = cases_visible_to(self.request.user).order_by("-updated_at")
        status = self.request.GET.get("status", "")
        if status in CaseStatus.values:
            qs = qs.filter(status=status)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(temp_code__icontains=q)
                | Q(nxb_code__icontains=q)
                | Q(isbn__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "status_choices": customer_status_choices(),
                "current_status": self.request.GET.get("status", ""),
                "q": self.request.GET.get("q", "").strip(),
            }
        )
        return ctx


# ---------------------------------------------------------------------------
# 2.2 Tạo hồ sơ / sửa thông tin chung
# ---------------------------------------------------------------------------


class CustomerNewCaseView(CustomerRequiredMixin, TemplateView):
    template_name = "customer/case_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("form", CaseInfoForm())
        ctx["page_title"] = _("Tạo hồ sơ mới")
        return ctx

    def post(self, request, *args, **kwargs):
        form = CaseInfoForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        with transaction.atomic():
            case = form.save(commit=False)
            case.owner = request.user
            case.save()
            log_event(
                actor=request.user,
                action="case.create",
                object_type="PublicationCase",
                object_id=str(case.pk),
                case=case,
                data={"after": _snapshot(case, CASE_FIELDS)},
                request=request,
            )
        messages.success(
            request, _("Đã tạo hồ sơ nháp. Vui lòng thêm tác giả và tải tài liệu để nộp.")
        )
        return redirect("customer:case_detail", case_id=case.pk)


class CaseEditGuardMixin:
    """Chặn thao tác sửa khi can_edit_case_info() trả False (hồ sơ không còn ở trạng thái cho sửa)."""

    def check_editable(self):
        if not can_edit_case_info(self.request.user, self.case):
            messages.error(
                self.request,
                _("Hồ sơ ở trạng thái hiện tại không cho phép sửa thông tin."),
            )
            return redirect("customer:case_detail", case_id=self.case.pk)
        return None


class CustomerCaseEditView(CustomerRequiredMixin, CaseAccessMixin, CaseEditGuardMixin, View):
    template_name = "customer/case_form.html"

    def _render(self, form):
        return render(
            self.request,
            self.template_name,
            {"form": form, "case": self.case, "page_title": _("Sửa thông tin hồ sơ")},
        )

    def get(self, request, *args, **kwargs):
        blocked = self.check_editable()
        if blocked:
            return blocked
        return self._render(CaseInfoForm(instance=self.case))

    def post(self, request, *args, **kwargs):
        blocked = self.check_editable()
        if blocked:
            return blocked
        before = _snapshot(self.case, CASE_FIELDS)
        form = CaseInfoForm(request.POST, instance=self.case)
        if not form.is_valid():
            return self._render(form)
        with transaction.atomic():
            case = form.save()
            log_event(
                actor=request.user,
                action="case.update",
                object_type="PublicationCase",
                object_id=str(case.pk),
                case=case,
                data={"before": before, "after": _snapshot(case, CASE_FIELDS)},
                request=request,
            )
        messages.success(request, _("Đã cập nhật thông tin hồ sơ."))
        return redirect("customer:case_detail", case_id=case.pk)


# ---------------------------------------------------------------------------
# 2.3 Chi tiết hồ sơ
# ---------------------------------------------------------------------------


class CustomerCaseDetailView(CustomerRequiredMixin, CaseAccessMixin, TemplateView):
    template_name = "customer/case_detail.html"

    def _document_groups(self, user, case):
        types = [
            t
            for t in CUSTOMER_DOC_TYPES
            if t != DocumentType.FORM_1 or case.publication_mode == PublicationMode.LINKED
        ]
        docs = list(case.documents.filter(doc_type__in=types).order_by("doc_type", "-version"))
        # Ô tải trong bảng tài liệu dành cho DRAFT/NEED_SUPPLEMENT; khi REVISION_REQUIRED
        # khách chỉ nộp bản thảo mới ở khối riêng (mục 2.3.6).
        table_upload_open = case.status != CaseStatus.REVISION_REQUIRED
        groups = []
        for doc_type in types:
            versions = [d for d in docs if d.doc_type == doc_type and can_download(user, d)]
            current = next((d for d in versions if d.is_current), None)
            groups.append(
                {
                    "doc_type": doc_type,
                    "label": str(DocumentType(doc_type).label),
                    "upload_label": _("Tải lên %(label)s")
                    % {"label": DocumentType(doc_type).label},
                    "current": current,
                    "history": [d for d in versions if d is not current],
                    "can_upload": table_upload_open and can_upload(user, case, doc_type),
                }
            )
        return groups

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        case = self.case
        editable = can_edit_case_info(user, case)
        notes = [
            n
            for n in case.notes.select_related("author").order_by("created_at", "id")
            if can_view_note(user, n)
        ]
        timeline = []
        for h in case.status_history.order_by("at", "id"):
            timeline.append(
                {
                    "at": h.at,
                    "to_status": h.to_status,
                    "note": h.note if h.to_status in CUSTOMER_VISIBLE_NOTE_STATUSES else "",
                }
            )
        ctx.update(
            {
                "case": case,
                "page_title": _("Hồ sơ %(code)s") % {"code": case.display_code},
                "can_edit": editable,
                "contributors": case.contributors.all(),
                "document_groups": self._document_groups(user, case),
                "show_checklist": case.status in (CaseStatus.DRAFT, CaseStatus.NEED_SUPPLEMENT),
                "checklist": submit_checklist(case),
                "can_submit": CaseStatus.SUBMITTED in allowed_transitions(user, case),
                "open_supplements": case.supplement_requests.filter(
                    status=SupplementStatus.OPEN
                ).order_by("created_at"),
                "show_revision_upload": case.status == CaseStatus.REVISION_REQUIRED
                and can_upload(user, case, DocumentType.MANUSCRIPT),
                "notes": notes,
                "note_form": kwargs.get("note_form") or CaseNoteForm(),
                "timeline": timeline,
                "public_forms_url": public_forms_url(),
            }
        )
        return ctx


class CustomerCaseSubmitView(CustomerRequiredMixin, CaseAccessMixin, View):
    """Nộp hồ sơ (DRAFT/NEED_SUPPLEMENT → SUBMITTED) qua change_status."""

    def post(self, request, *args, **kwargs):
        case = self.case
        from_status = case.status
        note = request.POST.get("note", "").strip()
        try:
            with transaction.atomic():
                change_status(
                    case, CaseStatus.SUBMITTED, actor=request.user, note=note, request=request
                )
                if from_status == CaseStatus.NEED_SUPPLEMENT:
                    open_requests = case.supplement_requests.filter(status=SupplementStatus.OPEN)
                    resolved_ids = list(open_requests.values_list("id", flat=True))
                    open_requests.update(
                        status=SupplementStatus.RESOLVED, resolved_at=timezone.now()
                    )
                    log_event(
                        actor=request.user,
                        action="case.supplement_resolved",
                        object_type="PublicationCase",
                        object_id=str(case.pk),
                        case=case,
                        data={"supplement_request_ids": resolved_ids},
                        request=request,
                    )
        except WorkflowError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("Đã nộp hồ sơ. NXB sẽ xem xét và phản hồi."))
        return redirect("customer:case_detail", case_id=case.pk)


class CustomerNoteAddView(CustomerRequiredMixin, CaseAccessMixin, View):
    """Khách gửi ghi chú trao đổi với NXB (luôn visibility=CUSTOMER)."""

    def post(self, request, *args, **kwargs):
        case = self.case
        form = CaseNoteForm(request.POST)
        if not form.is_valid():
            view = CustomerCaseDetailView()
            view.setup(request, *args, **kwargs)
            view.case = case
            return view.render_to_response(view.get_context_data(note_form=form))
        with transaction.atomic():
            note = CaseNote.objects.create(
                case=case,
                author=request.user,
                body=form.cleaned_data["body"],
                visibility=NoteVisibility.CUSTOMER,
            )
            log_event(
                actor=request.user,
                action="case.note_add",
                object_type="CaseNote",
                object_id=str(note.pk),
                case=case,
                data={"visibility": NoteVisibility.CUSTOMER},
                request=request,
            )
        messages.success(request, _("Đã gửi trao đổi tới NXB."))
        return HttpResponseRedirect(
            reverse("customer:case_detail", kwargs={"case_id": case.pk}) + "#trao-doi"
        )


# ---------------------------------------------------------------------------
# Tác giả (Contributor)
# ---------------------------------------------------------------------------


class ContributorFormView(CustomerRequiredMixin, CaseAccessMixin, CaseEditGuardMixin, View):
    template_name = "customer/contributor_form.html"

    def get_contributor(self):
        pk = self.kwargs.get("contributor_id")
        if pk is None:
            return None
        return get_object_or_404(self.case.contributors, pk=pk)

    def _render(self, form, contributor):
        return render(
            self.request,
            self.template_name,
            {
                "form": form,
                "case": self.case,
                "contributor": contributor,
                "page_title": _("Sửa tác giả") if contributor else _("Thêm tác giả"),
            },
        )

    def get(self, request, *args, **kwargs):
        contributor = self.get_contributor()
        blocked = self.check_editable()
        if blocked:
            return blocked
        if contributor is None:
            next_order = self.case.contributors.count() + 1
            form = ContributorForm(initial={"order": next_order})
        else:
            form = ContributorForm(instance=contributor)
        return self._render(form, contributor)

    def post(self, request, *args, **kwargs):
        contributor = self.get_contributor()
        blocked = self.check_editable()
        if blocked:
            return blocked
        before = _snapshot(contributor, CONTRIBUTOR_FIELDS) if contributor else None
        form = ContributorForm(request.POST, instance=contributor)
        if not form.is_valid():
            return self._render(form, contributor)
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.case = self.case
            obj.save()
            data = {"after": _snapshot(obj, CONTRIBUTOR_FIELDS)}
            if before is not None:
                data["before"] = before
            log_event(
                actor=request.user,
                action="case.contributor_update" if contributor else "case.contributor_add",
                object_type="Contributor",
                object_id=str(obj.pk),
                case=self.case,
                data=data,
                request=request,
            )
        messages.success(
            request, _("Đã cập nhật tác giả.") if contributor else _("Đã thêm tác giả.")
        )
        return HttpResponseRedirect(
            reverse("customer:case_detail", kwargs={"case_id": self.case.pk}) + "#tac-gia"
        )


class ContributorRemoveView(CustomerRequiredMixin, CaseAccessMixin, CaseEditGuardMixin, View):
    def post(self, request, *args, **kwargs):
        contributor = get_object_or_404(self.case.contributors, pk=kwargs["contributor_id"])
        blocked = self.check_editable()
        if blocked:
            return blocked
        with transaction.atomic():
            before = _snapshot(contributor, CONTRIBUTOR_FIELDS)
            contributor_pk = contributor.pk
            contributor.delete()
            log_event(
                actor=request.user,
                action="case.contributor_remove",
                object_type="Contributor",
                object_id=str(contributor_pk),
                case=self.case,
                data={"before": before},
                request=request,
            )
        messages.success(request, _("Đã xóa tác giả khỏi hồ sơ."))
        return HttpResponseRedirect(
            reverse("customer:case_detail", kwargs={"case_id": self.case.pk}) + "#tac-gia"
        )


# ---------------------------------------------------------------------------
# 2.5 Tài khoản
# ---------------------------------------------------------------------------


class CustomerProfileView(CustomerRequiredMixin, TemplateView):
    template_name = "customer/profile.html"
    profile_fields = ["full_name", "phone", "organization"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("form", ProfileForm(instance=self.request.user))
        ctx["page_title"] = _("Tài khoản")
        return ctx

    def post(self, request, *args, **kwargs):
        user = request.user
        before = _snapshot(user, self.profile_fields)
        form = ProfileForm(request.POST, instance=user)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        with transaction.atomic():
            form.save()
            log_event(
                actor=user,
                action="user.profile_update",
                object_type="User",
                object_id=str(user.pk),
                data={"before": before, "after": _snapshot(user, self.profile_fields)},
                request=request,
            )
        messages.success(request, _("Đã cập nhật thông tin tài khoản."))
        return redirect("customer:profile")
