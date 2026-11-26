"""Lệnh khởi tạo tài khoản Quản trị viên từ biến môi trường BOOTSTRAP_ADMIN_EMAILS (tối đa 2 email)."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import FinanceAccess, User, UserRole
from apps.core.audit import log_event


class Command(BaseCommand):
    help = "Tạo tài khoản ADMIN từ biến môi trường BOOTSTRAP_ADMIN_EMAILS (tối đa 2 email)."

    def handle(self, *args, **options):
        emails = getattr(settings, "BOOTSTRAP_ADMIN_EMAILS", [])
        if not emails:
            raise CommandError("Chưa cấu hình biến môi trường BOOTSTRAP_ADMIN_EMAILS.")
        if len(emails) > 2:
            raise CommandError("BOOTSTRAP_ADMIN_EMAILS chỉ cho phép tối đa 2 email quản trị.")

        staff_domain = getattr(settings, "STAFF_GOOGLE_DOMAIN", "ueh.edu.vn").lower()
        for email in emails:
            if not email.endswith(f"@{staff_domain}"):
                raise CommandError(f"Email quản trị '{email}' phải thuộc domain @{staff_domain}.")
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "full_name": "Quản trị viên NXB UEH",
                    "role": UserRole.ADMIN,
                    "finance_access": FinanceAccess.NONE,
                    "is_active": True,
                },
            )
            if not created and user.role != UserRole.ADMIN:
                old_role = user.role
                user.role = UserRole.ADMIN
                user.set_unusable_password()
                user.save()
                log_event(
                    actor=None,
                    action="user.role_change",
                    object_type="User",
                    object_id=str(user.pk),
                    data={"before": {"role": old_role}, "after": {"role": UserRole.ADMIN}},
                )
            status_label = "Đã tạo mới" if created else "Đã tồn tại / cập nhật"
            self.stdout.write(self.style.SUCCESS(f"{status_label}: {email} (ADMIN)"))
