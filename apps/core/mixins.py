"""Các Mixin phân quyền dùng chung cho mọi view của M1–M8 (mục 6).

Quy tắc bắt buộc:
- Mọi view phải kế thừa các mixin này, không tự viết điều kiện quyền.
- Không có quyền xem hồ sơ hoặc tài chính -> trả 404 (không trả 403 để tránh lộ dữ liệu tồn tại).
"""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.accounts.models import UserRole
from apps.core.permissions import (
    can_manage_finance,
    can_manage_system,
    can_view_finance,
    can_view_publication_stats,
    cases_visible_to,
)


class CustomerRequiredMixin(LoginRequiredMixin):
    """Chỉ cho phép người dùng đã đăng nhập với vai trò CUSTOMER."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != UserRole.CUSTOMER or not request.user.is_active:
            raise Http404("Không tìm thấy trang yêu cầu.")
        return super().dispatch(request, *args, **kwargs)


class EditorRequiredMixin(LoginRequiredMixin):
    """Chỉ cho phép người dùng đã đăng nhập với vai trò EDITOR."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != UserRole.EDITOR or not request.user.is_active:
            raise Http404("Không tìm thấy trang yêu cầu.")
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(LoginRequiredMixin):
    """Chỉ cho phép người dùng đã đăng nhập với vai trò ADMIN."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not can_manage_system(request.user):
            raise Http404("Không tìm thấy trang yêu cầu.")
        return super().dispatch(request, *args, **kwargs)


class CaseAccessMixin(LoginRequiredMixin):
    """Lấy hồ sơ theo UUID thông qua cases_visible_to(); không có quyền -> 404."""

    case_url_kwarg: str = "case_id"

    def get_case(self):
        if not hasattr(self, "_cached_case"):
            case_id = self.kwargs.get(self.case_url_kwarg) or self.kwargs.get("pk")
            self._cached_case = get_object_or_404(cases_visible_to(self.request.user), pk=case_id)
        return self._cached_case

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.case = self.get_case()
        return super().dispatch(request, *args, **kwargs)


class FinanceViewMixin(LoginRequiredMixin):
    """Chỉ cho phép EDITOR có quyền xem tài chính (VIEW hoặc MANAGE); ngược lại -> 404."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not can_view_finance(request.user):
            raise Http404("Không tìm thấy trang yêu cầu.")
        return super().dispatch(request, *args, **kwargs)


class FinanceManageMixin(LoginRequiredMixin):
    """Chỉ cho phép EDITOR có quyền quản lý tài chính (MANAGE); ngược lại -> 404."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not can_manage_finance(request.user):
            raise Http404("Không tìm thấy trang yêu cầu.")
        return super().dispatch(request, *args, **kwargs)


class PublicationStatsMixin(LoginRequiredMixin):
    """Chỉ cho phép EDITOR xem thống kê danh mục xuất bản; ngược lại -> 404."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not can_view_publication_stats(request.user):
            raise Http404("Không tìm thấy trang yêu cầu.")
        return super().dispatch(request, *args, **kwargs)
