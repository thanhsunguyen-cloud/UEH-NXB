"""Adapter django-allauth cho đăng nhập email/mật khẩu và Google OAuth (@ueh.edu.vn)."""

from __future__ import annotations

import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import UserRole

User = get_user_model()


def get_home_url_for_user(user) -> str:
    """Trả về trang chủ tương ứng với vai trò người dùng (mục 10)."""
    if not user or not user.is_authenticated:
        return "/tai-khoan/dang-nhap/"
    if user.role == UserRole.ADMIN:
        return "/quan-tri/"
    if user.role == UserRole.EDITOR:
        return "/noi-bo/"
    return "/khach-hang/"


logger = logging.getLogger(__name__)


def mark_email_verified(user, email: str) -> None:
    """Ghi nhận email của user là đã xác minh và là email chính."""
    from allauth.account.models import EmailAddress

    address, _created = EmailAddress.objects.get_or_create(
        user=user, email__iexact=email, defaults={"email": email}
    )
    changed = []
    if not address.verified:
        address.verified = True
        changed.append("verified")
    if not address.primary and not EmailAddress.objects.filter(user=user, primary=True).exists():
        address.primary = True
        changed.append("primary")
    if changed:
        address.save(update_fields=changed)


def _google_email_verified(sociallogin) -> bool:
    account = getattr(sociallogin, "account", None)
    data = getattr(account, "extra_data", None) or {}
    value = data.get("email_verified", data.get("verified_email"))
    return value is True or str(value).lower() == "true"


class PortalAccountAdapter(DefaultAccountAdapter):
    """Điều hướng sau đăng nhập theo vai trò và chặn nhân sự đăng nhập bằng mật khẩu."""

    def get_login_redirect_url(self, request):
        return get_home_url_for_user(request.user)

    def send_mail(self, template_prefix, email, context):
        """Lỗi máy chủ email không được làm hỏng thao tác đăng ký/đăng nhập (lỗi 500)."""
        try:
            return super().send_mail(template_prefix, email, context)
        except Exception:  # noqa: BLE001 - mọi lỗi SMTP
            logger.exception("Gửi email %s thất bại", template_prefix)
            from allauth.core import context as allauth_context

            request = getattr(allauth_context, "request", None)
            if request is not None:
                messages.warning(
                    request,
                    _(
                        "Hệ thống chưa gửi được email. Vui lòng thử lại sau hoặc liên hệ nxbkt@ueh.edu.vn."
                    ),
                )
            return None

    def authenticate(self, request, **credentials):
        email = (credentials.get("email") or "").strip().lower()
        if email:
            existing = User.objects.filter(email__iexact=email).first()
            if existing and existing.role in (UserRole.EDITOR, UserRole.ADMIN):
                return None
        return super().authenticate(request, **credentials)


class PortalSocialAccountAdapter(DefaultSocialAccountAdapter):
    def on_authentication_error(
        self, request, provider, error=None, exception=None, extra_context=None
    ):
        """Ghi lý do đăng nhập Google thất bại vào nhật ký (không chứa mật khẩu/khóa)."""
        logger.warning(
            "Đăng nhập %s thất bại: error=%s exception=%r",
            getattr(provider, "id", provider),
            error,
            exception,
        )
        return super().on_authentication_error(
            request, provider, error=error, exception=exception, extra_context=extra_context
        )

    """Kiểm soát đăng nhập Google theo quy tắc mục 5.1.

    - Người lạ có email @ueh.edu.vn đăng nhập Google KHÔNG tự động thành EDITOR mà là CUSTOMER.
    - Tài khoản đã có vai trò EDITOR/ADMIN bắt buộc phải có domain trùng STAFF_GOOGLE_DOMAIN.
    """

    def pre_social_login(self, request, sociallogin):
        email = (sociallogin.user.email or "").strip().lower()
        if not email:
            messages.error(request, _("Tài khoản Google không cung cấp địa chỉ email hợp lệ."))
            raise ImmediateHttpResponse(redirect("accounts:login"))

        domain = email.split("@")[-1]
        staff_domain = getattr(settings, "STAFF_GOOGLE_DOMAIN", "ueh.edu.vn").lower()
        existing_user = User.objects.filter(email__iexact=email).first()

        if existing_user:
            if not existing_user.is_active:
                messages.error(request, _("Tài khoản của bạn đã bị quản trị viên khóa."))
                raise ImmediateHttpResponse(redirect("accounts:login"))
            if existing_user.role in (UserRole.EDITOR, UserRole.ADMIN) and domain != staff_domain:
                messages.error(
                    request,
                    _("Tài khoản nhân sự chỉ được đăng nhập bằng Google domain @%(domain)s.")
                    % {"domain": staff_domain},
                )
                raise ImmediateHttpResponse(redirect("accounts:login"))
            if _google_email_verified(sociallogin):
                # Google đã xác minh email: đánh dấu đã xác minh để allauth không gửi email xác nhận.
                mark_email_verified(existing_user, email)
            sociallogin.connect(request, existing_user)

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.email = (data.get("email") or "").strip().lower()
        first = data.get("first_name") or ""
        last = data.get("last_name") or ""
        user.full_name = (data.get("name") or f"{last} {first}").strip() or user.email
        # Mọi tài khoản mới đăng nhập Google (kể cả @ueh.edu.vn) mặc định là CUSTOMER
        user.role = UserRole.CUSTOMER
        user.set_unusable_password()
        return user
