"""View bản demo M2/M3 – chỉ hiển thị dữ liệu giả, không đọc/ghi database.

Mọi view kế thừa DemoEnabledMixin: trả 404 trừ khi DEBUG=True hoặc DEMO_ENABLED=True.
"""

from __future__ import annotations

import os
from collections import OrderedDict

from django.conf import settings
from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from apps.core.models import CaseStatus, PublicationMode
from apps.demo import fake_data

TRUE_VALUES = {"1", "true", "yes", "on"}


def demo_enabled() -> bool:
    """Demo chỉ mở khi DEBUG=True hoặc biến môi trường DEMO_ENABLED=True."""
    if settings.DEBUG:
        return True
    return os.environ.get("DEMO_ENABLED", "").strip().lower() in TRUE_VALUES


def get_fake_case(slug: str) -> dict:
    case = fake_data.CASES_BY_SLUG.get(slug)
    if case is None:
        raise Http404("Không tìm thấy hồ sơ demo.")
    return case


class DemoEnabledMixin:
    """Chặn toàn bộ /demo/ (404) khi demo không được bật."""

    def dispatch(self, request, *args, **kwargs):
        if not demo_enabled():
            raise Http404("Không tìm thấy trang yêu cầu.")
        return super().dispatch(request, *args, **kwargs)


class DemoPageView(DemoEnabledMixin, TemplateView):
    """Trang demo chung: thêm tên màn hình và vai trò vào context."""

    screen_title = ""
    role = ""  # "customer" | "editor" | ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["screen_title"] = self.screen_title
        ctx["demo_role"] = self.role
        ctx["demo_customer_name"] = fake_data.DEMO_CUSTOMER_NAME
        return ctx


SCREENS = [
    {
        "role": _("Khách hàng (người đại diện)"),
        "items": [
            ("demo:customer_cases", None, _("1. Hồ sơ của tôi"), _("Danh sách hồ sơ, nhãn trạng thái màu và việc cần làm.")),
            ("demo:customer_create", None, _("2. Tạo hồ sơ – 4 bước"), _("Thông tin tác phẩm, tác giả, tải tài liệu, xem lại và nộp.")),
            ("demo:customer_case_detail", "hs-03", _("3. Chi tiết hồ sơ (khách hàng)"), _("Dòng thời gian, yêu cầu bổ sung, ghi chú NXB, tài liệu và phiên bản.")),
        ],
    },
    {
        "role": _("Biên tập viên"),
        "items": [
            ("demo:editor_cases", None, _("4. Danh sách hồ sơ"), _("Tìm theo ISBN/mã NXB/tên sách/tác giả; lọc trạng thái, hình thức, BTV.")),
            ("demo:editor_queue", None, _("5. Hồ sơ cần xử lý"), _("Hồ sơ nhóm theo việc cần làm: mới nộp, khách đã bổ sung, chờ đăng ký…")),
            ("demo:editor_case_detail", "hs-08", _("6. Chi tiết hồ sơ – 6 tab"), _("Tổng quan, Tác giả, Tài liệu, Quy trình, Ghi chú, Tài chính.")),
            ("demo:editor_case_detail", "hs-05?tab=quy-trinh&mau_4=1", _("7. Hộp thoại xác nhận Mẫu 4"), _("Xác nhận Mẫu 4 \"đúng hồ sơ\": mã, tên sách, phiên bản bản thảo, kết quả.")),
            ("demo:stats_catalog", None, _("8. Thống kê – Danh mục xuất bản"), _("Bộ lọc kỳ, bảng danh sách và biểu đồ cột số đầu sách theo tháng.")),
            ("demo:stats_debt", None, _("9. Thống kê – Công nợ"), _("Bảng khoản còn nợ và tổng theo nhóm tuổi nợ.")),
        ],
    },
]  # fmt: skip


def _screen_url(name: str, arg: str | None) -> str:
    if not arg:
        return reverse(name)
    slug, _sep, query = arg.partition("?")
    url = reverse(name, kwargs={"slug": slug})
    return f"{url}?{query}" if query else url


class IndexView(DemoPageView):
    template_name = "demo/index.html"
    screen_title = _("Danh sách màn hình demo")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["screens"] = [
            {
                "role": group["role"],
                "items": [
                    {"url": _screen_url(name, arg), "title": title, "description": desc}
                    for name, arg, title, desc in group["items"]
                ],
            }
            for group in SCREENS
        ]
        return ctx


# ---------------------------------------------------------------------------
# Khách hàng
# ---------------------------------------------------------------------------


class CustomerCaseListView(DemoPageView):
    template_name = "demo/customer_cases.html"
    screen_title = _("Hồ sơ của tôi")
    role = "customer"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cases"] = [c for c in fake_data.CASES if c["mine"]]
        return ctx


CREATE_STEPS = [
    (1, _("Thông tin tác phẩm")),
    (2, _("Tác giả")),
    (3, _("Tải tài liệu")),
    (4, _("Xem lại và nộp")),
]


class CustomerCaseCreateView(DemoPageView):
    template_name = "demo/customer_create.html"
    screen_title = _("Tạo hồ sơ mới")
    role = "customer"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            step = int(self.request.GET.get("buoc", "1"))
        except ValueError:
            step = 1
        step = min(max(step, 1), len(CREATE_STEPS))
        mode = self.request.GET.get("hinh_thuc", PublicationMode.SELF)
        if mode not in PublicationMode.values:
            mode = PublicationMode.SELF
        linked = mode == PublicationMode.LINKED
        uploads = [
            ("MANUSCRIPT", _("Bản thảo"), _("Tệp Word hoặc PDF, có thể lớn (tải chia phần).")),
        ]
        if linked:
            uploads.append(("FORM_1", _("Mẫu 1"), _("Chỉ bắt buộc với hình thức liên kết.")))
        uploads += [
            ("FORM_2", _("Mẫu 2"), _("Có chữ ký của tất cả tác giả.")),
            ("FORM_3", _("Mẫu 3"), ""),
        ]
        missing = [_("Chưa tải Mẫu 3")]
        if linked:
            missing.insert(0, _("Chưa nhập tên đơn vị liên kết"))
            missing.insert(1, _("Chưa tải Mẫu 1"))
        ctx.update(
            step=step,
            steps=CREATE_STEPS,
            mode=mode,
            linked=linked,
            modes=PublicationMode.choices,
            uploads=uploads,
            missing=missing,
            prev_step=step - 1,
            next_step=step + 1 if step < len(CREATE_STEPS) else None,
        )
        return ctx


class CustomerCaseDetailView(DemoPageView):
    template_name = "demo/customer_case_detail.html"
    screen_title = _("Chi tiết hồ sơ")
    role = "customer"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        case = get_fake_case(kwargs["slug"])
        if not case["mine"]:
            # Như CaseAccessMixin thật: hồ sơ của người khác -> 404.
            raise Http404("Không tìm thấy hồ sơ demo.")
        ctx["case"] = case
        return ctx


# ---------------------------------------------------------------------------
# Biên tập viên
# ---------------------------------------------------------------------------


def _filter_cases(params) -> list[dict]:
    q = params.get("q", "").strip().lower()
    status = params.get("trang_thai", "")
    mode = params.get("hinh_thuc", "")
    editor = params.get("btv", "")
    editor_name = fake_data.EDITORS.get(editor, "")
    result = []
    for case in fake_data.CASES:
        haystack = " ".join(
            [case["isbn"], case["nxb_code"], case["temp_code"], case["title"], case["author_names"]]
        ).lower()
        if q and q not in haystack:
            continue
        if status and case["status"] != status:
            continue
        if mode and case["mode"] != mode:
            continue
        if editor == "chua-phan-cong" and case["editor"]:
            continue
        if editor_name and case["editor"] != editor_name:
            continue
        result.append(case)
    return result


class EditorCaseListView(DemoPageView):
    template_name = "demo/editor_cases.html"
    screen_title = _("Danh sách hồ sơ")
    role = "editor"

    def get_template_names(self):
        headers = self.request.headers
        if headers.get("HX-Request") == "true" and not headers.get("HX-History-Restore-Request"):
            return ["demo/_editor_case_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET
        ctx.update(
            cases=_filter_cases(params),
            total=len(fake_data.CASES),
            q=params.get("q", ""),
            selected_status=params.get("trang_thai", ""),
            selected_mode=params.get("hinh_thuc", ""),
            selected_editor=params.get("btv", ""),
            statuses=CaseStatus.choices,
            modes=PublicationMode.choices,
            editors=list(fake_data.EDITORS.items()),
        )
        return ctx


class EditorQueueView(DemoPageView):
    template_name = "demo/editor_queue.html"
    screen_title = _("Hồ sơ cần xử lý")
    role = "editor"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["groups"] = [
            {
                "code": code,
                "title": title,
                "hint": hint,
                "cases": [c for c in fake_data.CASES if match(c)],
            }
            for code, title, hint, match in fake_data.QUEUE_GROUPS
        ]
        return ctx


EDITOR_TABS = ("tong-quan", "tac-gia", "tai-lieu", "quy-trinh", "ghi-chu", "tai-chinh")


class EditorCaseDetailView(DemoPageView):
    template_name = "demo/editor_case_detail.html"
    screen_title = _("Chi tiết hồ sơ (biên tập viên)")
    role = "editor"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        case = get_fake_case(kwargs["slug"])
        # Demo: giả lập quyền tài chính bằng tham số ?tai_chinh=0/1 (mặc định có quyền).
        can_finance = self.request.GET.get("tai_chinh", "1") != "0"
        tab = self.request.GET.get("tab", "tong-quan")
        if tab not in EDITOR_TABS or (tab == "tai-chinh" and not can_finance):
            tab = "tong-quan"
        ctx.update(
            case=case,
            can_view_finance=can_finance,
            review_results=fake_data.REVIEW_RESULT_CHOICES,
            open_form4=self.request.GET.get("mau_4") == "1",
            active_tab=tab,
        )
        return ctx


class StatsCatalogView(DemoPageView):
    template_name = "demo/stats_catalog.html"
    screen_title = _("Thống kê – Danh mục xuất bản")
    role = "editor"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        years = sorted({b["decision_date"].year for b in fake_data.PUBLISHED_BOOKS}, reverse=True)
        try:
            year = int(self.request.GET.get("nam", years[0]))
        except ValueError:
            year = years[0]
        if year not in years:
            year = years[0]
        quarter = self.request.GET.get("quy", "")
        months = list(range(1, 13))
        if quarter in {"1", "2", "3", "4"}:
            start = (int(quarter) - 1) * 3 + 1
            months = list(range(start, start + 3))
        else:
            quarter = ""
        books = sorted(
            (
                b
                for b in fake_data.PUBLISHED_BOOKS
                if b["decision_date"].year == year and b["decision_date"].month in months
            ),
            key=lambda b: b["decision_date"],
        )
        counts = OrderedDict((m, 0) for m in months)
        for book in books:
            counts[book["decision_date"].month] += 1
        peak = max(counts.values()) or 1
        chart = [
            {"month": m, "count": n, "height": round(n * 100 / peak)} for m, n in counts.items()
        ]
        ctx.update(
            years=years,
            year=year,
            quarter=quarter,
            books=books,
            chart=chart,
            peak=peak,
        )
        return ctx


class StatsDebtView(DemoPageView):
    template_name = "demo/stats_debt.html"
    screen_title = _("Thống kê – Công nợ")
    role = "editor"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = fake_data.debt_rows()
        selected = self.request.GET.get("nhom", "")
        buckets = []
        for code, label in fake_data.AGING_BUCKETS:
            items = [r for r in rows if r["bucket"] == code]
            buckets.append(
                {
                    "code": code,
                    "label": label,
                    "count": len(items),
                    "total": sum(r["outstanding"] for r in items),
                }
            )
        if selected in dict(fake_data.AGING_BUCKETS):
            rows = [r for r in rows if r["bucket"] == selected]
        else:
            selected = ""
        ctx.update(
            rows=rows,
            buckets=buckets,
            selected=selected,
            grand_total=sum(b["total"] for b in buckets),
            today=fake_data.DEMO_TODAY,
        )
        return ctx
