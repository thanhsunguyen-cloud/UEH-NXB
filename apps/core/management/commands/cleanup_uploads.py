"""Lệnh hủy các phiên tải tệp chia phần quá hạn 24 giờ và dọn tệp tạm (mục 9)."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import UploadSession, UploadSessionStatus
from apps.core.storage import get_storage


class Command(BaseCommand):
    help = "Hủy các UploadSession mở quá 24 giờ và xóa tệp tạm tương ứng."

    def handle(self, *args, **options):
        now = timezone.now()
        expired = UploadSession.objects.filter(
            status=UploadSessionStatus.OPEN,
            expires_at__lt=now,
        )
        storage = get_storage()
        count = 0
        for session in expired:
            if session.backend_ref:
                storage.abort_upload(session.backend_ref)
            session.status = UploadSessionStatus.ABORTED
            session.save(update_fields=["status", "updated_at"])
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Đã hủy và dọn {count} phiên tải tệp quá hạn."))
