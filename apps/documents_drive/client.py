"""Lớp gọi Google Drive API v3 cho M1: xác thực, thử lại khi lỗi tạm thời, chuyển lỗi sang tiếng Việt.

- Xác thực bằng service account (file JSON tại GDRIVE_CREDENTIALS_FILE) hoặc
  Application Default Credentials khi biến này rỗng (tài khoản dịch vụ gắn vào Cloud Run).
- Lỗi 429/5xx (và 403 do vượt hạn mức): gọi tối đa MAX_ATTEMPTS = 5 lần (1 lần đầu + 4 lần
  thử lại) với thời gian chờ tăng dần.
- Lỗi quyền (403) / không tìm thấy (404) / lỗi khác: ném DriveApiError (một ValidationError)
  với thông báo tiếng Việt, không lộ thông tin kỹ thuật ra người dùng; chi tiết ghi vào log.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httplib2
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.translation import gettext_lazy as _
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
DRIVE_API_URL = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"

MAX_ATTEMPTS = 5
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 32.0
HTTP_TIMEOUT_SECONDS = 120

RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}
TRANSPORT_ERRORS = (OSError, httplib2.HttpLib2Error)

MESSAGE_FORBIDDEN = _(
    "Hệ thống không có quyền truy cập tệp trên kho lưu trữ. Vui lòng liên hệ NXB."
)
MESSAGE_NOT_FOUND = _("Không tìm thấy tệp trên kho lưu trữ.")
MESSAGE_UNAVAILABLE = _("Kho lưu trữ tạm thời không phản hồi. Vui lòng thử lại sau ít phút.")
MESSAGE_GENERIC = _("Không xử lý được yêu cầu với kho lưu trữ. Vui lòng thử lại hoặc liên hệ NXB.")


class DriveApiError(ValidationError):
    """Lỗi Drive đã được chuyển sang thông báo tiếng Việt; `status` giữ mã HTTP để xử lý nội bộ."""

    def __init__(self, status: int | None, detail: str = ""):
        self.status = status
        self.detail = detail
        if status == 403:
            message = MESSAGE_FORBIDDEN
        elif status in (404, 410):
            message = MESSAGE_NOT_FOUND
        elif status is None or status == 429 or status >= 500:
            message = MESSAGE_UNAVAILABLE
        else:
            message = MESSAGE_GENERIC
        super().__init__(message)


def _error_reasons(content: bytes | str | None) -> set[str]:
    try:
        payload = json.loads(content or b"{}")
        return {e.get("reason", "") for e in payload.get("error", {}).get("errors", [])}
    except (ValueError, AttributeError, TypeError):
        return set()


def is_retryable(status: int, content: bytes | str | None = None) -> bool:
    if status == 429 or status >= 500:
        return True
    return status == 403 and bool(_error_reasons(content) & RATE_LIMIT_REASONS)


def with_all_drives(uri: str) -> str:
    """Bảo đảm URI có supportsAllDrives=true (bắt buộc cho mọi lời gọi Drive API)."""
    parts = urlsplit(uri)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if any(k == "supportsAllDrives" for k, _v in query):
        return uri
    query.append(("supportsAllDrives", "true"))
    return urlunsplit(parts._replace(query=urlencode(query)))


def build_authorized_http():
    """Tạo httplib2.Http đã gắn thông tin xác thực service account / ADC."""
    import google.auth
    import google_auth_httplib2
    from google.oauth2 import service_account

    credentials_file = getattr(settings, "GDRIVE_CREDENTIALS_FILE", "")
    if credentials_file:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=DRIVE_SCOPES
        )
    else:
        credentials, _project = google.auth.default(scopes=DRIVE_SCOPES)
    return google_auth_httplib2.AuthorizedHttp(
        credentials, http=httplib2.Http(timeout=HTTP_TIMEOUT_SECONDS)
    )


class DriveClient:
    """Bao bọc googleapiclient (metadata) và httplib2 (resumable upload, tải nội dung).

    Tham số `http` cho phép test truyền bản giả lập thay cho Drive thật.
    Mọi URI đã gửi được ghi vào `request_log` để kiểm tra supportsAllDrives.
    """

    def __init__(
        self,
        http=None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = MAX_ATTEMPTS,
        base_delay: float = BASE_DELAY_SECONDS,
    ):
        from googleapiclient.discovery import build

        self.http = _LoggingHttp(http or build_authorized_http())
        self.sleep = sleep
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.service = build(
            "drive", "v3", http=self.http, cache_discovery=False, static_discovery=True
        )

    @property
    def request_log(self) -> list[tuple[str, str]]:
        return self.http.log

    @property
    def files(self):
        return self.service.files()

    def backoff(self, attempt: int) -> None:
        """Chờ tăng dần trước lần thử lại thứ `attempt` (1, 2, 4, 8... giây, tối đa 32 giây)."""
        self.sleep(min(self.base_delay * (2 ** (attempt - 1)), MAX_DELAY_SECONDS))

    def execute(self, request) -> dict:
        """Thực thi một request googleapiclient, thử lại khi lỗi tạm thời."""
        for attempt in range(1, self.max_attempts + 1):
            try:
                return request.execute(num_retries=0)
            except HttpError as exc:
                status = int(exc.resp.status)
                if is_retryable(status, exc.content) and attempt < self.max_attempts:
                    logger.warning("Drive API %s (lần %s), thử lại", status, attempt)
                    self.backoff(attempt)
                    continue
                logger.error("Drive API lỗi %s: %s", status, exc.content[:500])
                raise DriveApiError(status, str(exc.content[:500])) from exc
            except TRANSPORT_ERRORS as exc:
                if attempt < self.max_attempts:
                    logger.warning("Lỗi kết nối Drive (lần %s): %s, thử lại", attempt, exc)
                    self.backoff(attempt)
                    continue
                logger.error("Lỗi kết nối Drive: %s", exc)
                raise DriveApiError(None, str(exc)) from exc
        raise AssertionError("unreachable")  # pragma: no cover

    def send(
        self,
        uri: str,
        method: str = "GET",
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        ok: tuple[int, ...] = (200, 201),
        retry: bool = True,
    ):
        """Gửi request HTTP trực tiếp tới Drive, trả (resp, content) khi status thuộc `ok`.

        Nếu `retry=False` thì chỉ gửi một lần và trả về mọi phản hồi (kể cả lỗi) để
        người gọi tự xử lý (dùng cho resumable upload cần hỏi trạng thái trước khi gửi lại).
        """
        uri = with_all_drives(uri)
        attempts = self.max_attempts if retry else 1
        for attempt in range(1, attempts + 1):
            try:
                resp, content = self.http.request(
                    uri, method=method, body=body, headers=dict(headers or {})
                )
            except TRANSPORT_ERRORS as exc:
                if attempt < attempts:
                    logger.warning("Lỗi kết nối Drive (lần %s): %s, thử lại", attempt, exc)
                    self.backoff(attempt)
                    continue
                raise DriveApiError(None, str(exc)) from exc
            status = int(resp.status)
            if not retry or status in ok:
                return resp, content
            if is_retryable(status, content) and attempt < attempts:
                logger.warning("Drive %s %s (lần %s), thử lại", method, status, attempt)
                self.backoff(attempt)
                continue
            logger.error("Drive %s lỗi %s: %s", method, status, content[:500])
            raise DriveApiError(status, str(content[:500]))
        raise AssertionError("unreachable")  # pragma: no cover


class _LoggingHttp:
    """Bọc đối tượng http, ghi lại (method, uri) của mọi request đã gửi."""

    def __init__(self, http):
        self._http = http
        self.log: list[tuple[str, str]] = []

    def request(self, uri, method="GET", *args, **kwargs):
        self.log.append((method, uri))
        return self._http.request(uri, method, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._http, name)


def get_shared_drive_id() -> str:
    drive_id = getattr(settings, "GDRIVE_SHARED_DRIVE_ID", "")
    if not drive_id:
        raise ImproperlyConfigured(
            "Chưa cấu hình GDRIVE_SHARED_DRIVE_ID cho FILE_STORAGE_BACKEND=gdrive."
        )
    return drive_id
