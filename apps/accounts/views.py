"""Views đăng nhập, đăng xuất và điều hướng theo vai trò (M0)."""

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.accounts.adapters import get_home_url_for_user
from apps.accounts.models import User, UserRole
from apps.core.audit import log_event


def login_view(request):
    """Màn hình đăng nhập thống nhất: Google @ueh.edu.vn cho nhân sự, Email+Mật khẩu cho khách hàng."""
    if request.user.is_authenticated:
        return redirect(get_home_url_for_user(request.user))

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        existing = User.objects.filter(email__iexact=email).first()
        if existing and existing.role in (UserRole.EDITOR, UserRole.ADMIN):
            messages.error(
                request,
                _(
                    "Tài khoản nhân sự không được đăng nhập bằng mật khẩu. Vui lòng dùng Google @ueh.edu.vn."
                ),
            )
            return render(request, "accounts/login.html", {"email": email}, status=403)

        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            log_event(
                actor=user,
                action="auth.login",
                object_type="User",
                object_id=str(user.pk),
                data={"method": "password"},
                request=request,
            )
            return redirect(get_home_url_for_user(user))

        messages.error(request, _("Email hoặc mật khẩu không đúng, hoặc tài khoản đã bị khóa."))

    return render(request, "accounts/login.html")


@login_required
def role_redirect_view(request):
    """Chuyển hướng người dùng sau đăng nhập đến trang chủ tương ứng với vai trò."""
    return redirect(get_home_url_for_user(request.user))


@require_POST
def logout_view(request):
    """Đăng xuất an toàn bằng POST."""
    if request.user.is_authenticated:
        log_event(
            actor=request.user,
            action="auth.logout",
            object_type="User",
            object_id=str(request.user.pk),
            request=request,
        )
        logout(request)
    return redirect("accounts:login")
