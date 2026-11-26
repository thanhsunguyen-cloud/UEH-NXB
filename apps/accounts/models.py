"""Mô hình người dùng tùy biến (AUTH_USER_MODEL = 'accounts.User') — mục 5.1."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserRole(models.TextChoices):
    CUSTOMER = "CUSTOMER", _("Khách hàng (Tác giả / Đối tác)")
    EDITOR = "EDITOR", _("Biên tập viên")
    ADMIN = "ADMIN", _("Quản trị viên")


class FinanceAccess(models.TextChoices):
    NONE = "NONE", _("Không có quyền")
    VIEW = "VIEW", _("Chỉ xem")
    MANAGE = "MANAGE", _("Quản lý tài chính")


class UserManager(BaseUserManager):
    """Trình quản lý User sử dụng email làm định danh duy nhất."""

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> User:
        if not email:
            raise ValueError(_("Địa chỉ email là bắt buộc."))
        email = self.normalize_email(email).lower()
        extra_fields.setdefault("role", UserRole.CUSTOMER)
        extra_fields.setdefault("finance_access", FinanceAccess.NONE)
        user = self.model(email=email, **extra_fields)
        if password and extra_fields.get("role") == UserRole.CUSTOMER:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> User:
        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("finance_access", FinanceAccess.NONE)
        return self.create_user(email=email, password=None, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Tài khoản người dùng Portal (đăng nhập bằng email, không dùng username)."""

    email = models.EmailField(_("Email"), unique=True)
    full_name = models.CharField(_("Họ và tên"), max_length=200)
    phone = models.CharField(_("Số điện thoại"), max_length=20, blank=True)
    role = models.CharField(
        _("Vai trò"),
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.CUSTOMER,
        db_index=True,
    )
    organization = models.CharField(_("Đơn vị / Đối tác"), max_length=255, blank=True)
    finance_access = models.CharField(
        _("Quyền tài chính"),
        max_length=20,
        choices=FinanceAccess.choices,
        default=FinanceAccess.NONE,
    )
    is_active = models.BooleanField(_("Đang hoạt động"), default=True)
    is_staff = models.BooleanField(_("Quyền truy cập Django Admin"), default=False)
    created_at = models.DateTimeField(_("Ngày tạo"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Ngày cập nhật"), auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = _("Người dùng")
        verbose_name_plural = _("Người dùng")
        ordering = ["email"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.email})" if self.full_name else self.email

    @property
    def is_customer(self) -> bool:
        return self.role == UserRole.CUSTOMER

    @property
    def is_editor(self) -> bool:
        return self.role == UserRole.EDITOR

    @property
    def is_admin_role(self) -> bool:
        return self.role == UserRole.ADMIN

    def save(self, *args, **kwargs) -> None:
        self.email = self.email.strip().lower()
        # Chỉ ADMIN mới được vào /django-admin/ (mục 10)
        self.is_staff = self.role == UserRole.ADMIN
        # Quyền tài chính chỉ có ý nghĩa với EDITOR (mục 5.1)
        if self.role != UserRole.EDITOR:
            self.finance_access = FinanceAccess.NONE
        super().save(*args, **kwargs)
