"""Backend xác thực mật khẩu: chỉ cho phép CUSTOMER, chặn hoàn toàn EDITOR và ADMIN."""

from allauth.account.auth_backends import AuthenticationBackend as AllauthAuthenticationBackend
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from apps.accounts.models import UserRole

User = get_user_model()

STAFF_ROLES = (UserRole.EDITOR, UserRole.ADMIN)


class CustomerPasswordBackend(ModelBackend):
    """Từ chối mọi đăng nhập bằng mật khẩu đối với tài khoản EDITOR và ADMIN (mục 5.1).

    Khi phát hiện email thuộc tài khoản nhân sự (EDITOR/ADMIN), backend ném PermissionDenied
    để Django dừng ngay toàn bộ chuỗi AUTHENTICATION_BACKENDS và trả None thay vì rơi xuống
    backend kế tiếp.
    """

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        login_email = (email or username or "").strip().lower()
        if not login_email or not password:
            return None
        try:
            user = User.objects.get(email__iexact=login_email)
        except User.DoesNotExist:
            return None
        if user.role in STAFF_ROLES:
            raise PermissionDenied("Tài khoản nhân sự chỉ được đăng nhập bằng Google @ueh.edu.vn.")
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None


class PortalAllauthBackend(AllauthAuthenticationBackend):
    """Lớp con allauth chặn xác thực mật khẩu đối với EDITOR và ADMIN (phòng thủ nhiều lớp).

    Đăng nhập Google OAuth của nhân sự vẫn hoạt động bình thường vì luồng social login
    gọi perform_login() sau khi xác thực OAuth, không đi qua xác thực mật khẩu.
    """

    def authenticate(self, request, **credentials):
        login_email = (
            (credentials.get("email") or credentials.get("username") or "").strip().lower()
        )
        password = credentials.get("password")
        if login_email and password:
            existing = User.objects.filter(email__iexact=login_email).first()
            if existing and existing.role in STAFF_ROLES:
                raise PermissionDenied(
                    "Tài khoản nhân sự chỉ được đăng nhập bằng Google @ueh.edu.vn."
                )
        return super().authenticate(request, **credentials)
