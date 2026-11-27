"""Test M1 – GoogleDriveStorage trên bản giả lập Drive (không gọi Drive thật trong CI)."""

import hashlib
import io
import json

import pytest
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.core.models import AuditEvent, Document, DocumentType
from apps.core.storage import (
    CHUNK_SIZE,
    begin_document_upload,
    complete_document_upload,
    get_storage,
    upload_chunk,
)
from apps.documents_drive import client as client_module
from apps.documents_drive import storage as storage_module
from apps.documents_drive.client import DriveApiError, DriveClient, with_all_drives
from apps.documents_drive.management.commands.drive_check import Command as DriveCheckCommand
from apps.documents_drive.storage import GoogleDriveStorage
from tests.drive_fake import FakeDrive
from tests.factories import DocumentFactory, PublicationCaseFactory

DRIVE_ID = "drive123"


@pytest.fixture
def fake():
    return FakeDrive(DRIVE_ID)


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def make_storage(fake, sleeps):
    """Mỗi lần gọi tạo một GoogleDriveStorage mới (như mỗi HTTP request gọi get_storage())."""

    def _make(**kwargs):
        client = DriveClient(http=fake, sleep=sleeps.append)
        return GoogleDriveStorage(client=client, drive_id=DRIVE_ID, **kwargs)

    return _make


@pytest.fixture
def gdrive_settings(settings, fake, sleeps, monkeypatch):
    """Bật FILE_STORAGE_BACKEND=gdrive, DriveClient mặc định trỏ tới bản giả lập."""
    settings.FILE_STORAGE_BACKEND = "gdrive"
    settings.GDRIVE_SHARED_DRIVE_ID = DRIVE_ID
    monkeypatch.setattr(
        storage_module, "DriveClient", lambda: DriveClient(http=fake, sleep=sleeps.append)
    )
    return settings


def _assert_all_drives(fake):
    assert fake.requests
    for req in fake.requests:
        assert req.query.get("supportsAllDrives") == "true", req.uri
        if req.method == "GET" and req.uri.split("?")[0].endswith("/drive/v3/files"):
            assert req.query.get("includeItemsFromAllDrives") == "true"
            assert req.query.get("corpora") == "drive"
            assert req.query.get("driveId") == DRIVE_ID


# ---------------------------------------------------------------------------
# Upload chia phần qua service M0
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_three_part_upload_content_range_file_id_and_sha256(customer_a, fake, make_storage):
    case = PublicationCaseFactory(owner=customer_a)
    tail = 1234
    total = 2 * CHUNK_SIZE + tail
    parts = [b"\x01" * CHUNK_SIZE, b"\x02" * CHUNK_SIZE, b"\x03" * tail]
    expected_sha = hashlib.sha256(b"".join(parts)).hexdigest()

    session = begin_document_upload(
        user=customer_a,
        case=case,
        doc_type=DocumentType.MANUSCRIPT,
        filename="Bản thảo cuối.pdf",
        total_size=total,
        mime_type="application/pdf",
        storage=make_storage(),
    )
    assert session.backend_ref.startswith("https://www.googleapis.com/upload/drive/v3/files")
    assert "upload_id=" in session.backend_ref

    offset = 0
    for part in parts:
        # Mỗi phần dùng một instance mới: tổng dung lượng lấy lại từ UploadSession trong DB
        upload_chunk(
            user=customer_a, session=session, offset=offset, data=part, storage=make_storage()
        )
        offset += len(part)

    doc = complete_document_upload(user=customer_a, session=session, storage=make_storage())

    ranges = [r.headers["content-range"] for r in fake.upload_requests()]
    assert ranges == [
        f"bytes 0-{CHUNK_SIZE - 1}/{total}",
        f"bytes {CHUNK_SIZE}-{2 * CHUNK_SIZE - 1}/{total}",
        f"bytes {2 * CHUNK_SIZE}-{total - 1}/{total}",
    ]
    drive_file = fake.files[doc.storage_ref]
    assert drive_file["content"] == b"".join(parts)
    assert doc.sha256 == expected_sha
    assert doc.size_bytes == total
    assert doc.mime_type == "application/pdf"
    assert drive_file["name"] == "v1_B_n_th_o_cu_i.pdf"
    assert fake.path_of(doc.storage_ref) == (
        f"Portal/cases/{case.pk}/MANUSCRIPT/v1_B_n_th_o_cu_i.pdf"
    )
    doc_type_folder = fake.files[drive_file["parents"][0]]
    assert doc_type_folder["appProperties"]["portal_case_id"] == str(case.pk)
    assert doc_type_folder["appProperties"]["portal_doc_type"] == "MANUSCRIPT"
    _assert_all_drives(fake)


@pytest.mark.django_db
def test_second_version_reuses_folders_and_names_v2(customer_a, fake, make_storage):
    case = PublicationCaseFactory(owner=customer_a)
    storage = make_storage()
    docs = []
    for content in (b"ban 1", b"ban 2"):
        s = begin_document_upload(
            user=customer_a,
            case=case,
            doc_type=DocumentType.MANUSCRIPT,
            filename="bt.pdf",
            total_size=len(content),
            storage=make_storage(),
        )
        upload_chunk(user=customer_a, session=s, offset=0, data=content, storage=storage)
        docs.append(complete_document_upload(user=customer_a, session=s, storage=storage))

    assert [fake.files[d.storage_ref]["name"] for d in docs] == ["v1_bt.pdf", "v2_bt.pdf"]
    # Portal, cases, <case>, MANUSCRIPT: chỉ tạo một lần, không tạo trùng
    assert len(fake.folders()) == 4


@pytest.mark.django_db
def test_sha256_computed_by_streaming_when_drive_does_not_return_it(customer_a, make_storage):
    fake_no_sha = FakeDrive(DRIVE_ID, return_sha256=False)
    storage = GoogleDriveStorage(
        client=DriveClient(http=fake_no_sha, sleep=lambda s: None), drive_id=DRIVE_ID
    )
    case = PublicationCaseFactory(owner=customer_a)
    content = b"z" * (5 * 1024 * 1024)
    s = begin_document_upload(
        user=customer_a,
        case=case,
        doc_type=DocumentType.OTHER,
        filename="a.pdf",
        total_size=len(content),
        storage=storage,
    )
    upload_chunk(user=customer_a, session=s, offset=0, data=content, storage=storage)
    doc = complete_document_upload(user=customer_a, session=s, storage=storage)
    assert doc.sha256 == hashlib.sha256(content).hexdigest()
    media_gets = [r for r in fake_no_sha.requests if "alt=media" in r.uri]
    assert len(media_gets) == 2  # 4 MiB + 1 MiB, không nạp cả file một lần


@pytest.mark.django_db
def test_append_chunk_validations(customer_a, make_storage):
    case = PublicationCaseFactory(owner=customer_a)
    storage = make_storage()
    url = storage.start_upload(case, DocumentType.MANUSCRIPT, "a.pdf", 1024 * 1024, "")

    with pytest.raises(ValidationError):  # vượt tổng dung lượng
        storage.append_chunk(url, 0, b"x" * (1024 * 1024 + 1))
    with pytest.raises(ValidationError):  # phần giữa không phải bội số 256 KiB
        storage.append_chunk(url, 0, b"x" * 1000)
    with pytest.raises(ValidationError):  # phiên chưa đủ dữ liệu
        storage.finish_upload(url)
    with pytest.raises(ValidationError):  # phiên không tồn tại trong DB
        make_storage().append_chunk("https://www.googleapis.com/upload/x?upload_id=nope", 0, b"x")


@pytest.mark.django_db
def test_start_upload_without_location_header_raises(customer_a, fake, make_storage):
    case = PublicationCaseFactory(owner=customer_a)
    original = fake._upload

    def no_location(method, query, headers, body, uri):
        resp, content = original(method, query, headers, body, uri)
        resp.pop("location", None)
        return resp, content

    fake._upload = no_location
    with pytest.raises(DriveApiError):
        make_storage().start_upload(case, DocumentType.MANUSCRIPT, "a.pdf", 10, "")


# ---------------------------------------------------------------------------
# Thử lại khi lỗi tạm thời
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_retry_on_503_then_success(customer_a, fake, make_storage, sleeps):
    case = PublicationCaseFactory(owner=customer_a)
    fake.fail_next(2, 503, method="GET")  # files.list lỗi 2 lần rồi thành công
    storage = make_storage()
    url = storage.start_upload(case, DocumentType.MANUSCRIPT, "a.pdf", 3, "application/pdf")
    assert sleeps == [1.0, 2.0]

    fake.fail_next(1, 503, method="PUT")  # phần dữ liệu lỗi 1 lần
    assert storage.append_chunk(url, 0, b"abc") == 3
    assert sleeps == [1.0, 2.0, 1.0]
    stored = storage.finish_upload(url)
    assert fake.files[stored.storage_ref]["content"] == b"abc"


@pytest.mark.django_db
def test_chunk_retry_resumes_from_drive_received_offset(customer_a, fake, make_storage):
    case = PublicationCaseFactory(owner=customer_a)
    storage = make_storage()
    total = CHUNK_SIZE + 10
    url = storage.start_upload(case, DocumentType.MANUSCRIPT, "a.pdf", total, "")
    storage.append_chunk(url, 0, b"a" * CHUNK_SIZE)
    fake.fail_next(1, 500, method="PUT", path_contains="upload_id")
    assert storage.append_chunk(url, CHUNK_SIZE, b"b" * 10) == total
    status_queries = [
        r for r in fake.requests if r.headers.get("content-range", "").startswith("bytes */")
    ]
    assert status_queries  # đã hỏi Drive nhận tới đâu trước khi gửi lại
    stored = storage.finish_upload(url)
    assert stored.size == total


@pytest.mark.django_db
def test_chunk_retry_when_drive_already_received_data(customer_a, fake, make_storage):
    """Drive đã nhận phần dữ liệu nhưng phản hồi bị lỗi: không gửi lại, không trùng dữ liệu."""
    case = PublicationCaseFactory(owner=customer_a)
    storage = make_storage()
    url = storage.start_upload(case, DocumentType.MANUSCRIPT, "a.pdf", CHUNK_SIZE * 2, "")
    original = fake._upload
    state = {"dropped": False}

    def drop_response_once(method, query, headers, body, uri):
        resp, content = original(method, query, headers, body, uri)
        if method == "PUT" and body and not state["dropped"]:
            state["dropped"] = True
            raise ConnectionResetError("connection reset")
        return resp, content

    fake._upload = drop_response_once
    assert storage.append_chunk(url, 0, b"a" * CHUNK_SIZE) == CHUNK_SIZE
    assert storage.append_chunk(url, CHUNK_SIZE, b"b" * CHUNK_SIZE) == 2 * CHUNK_SIZE
    stored = storage.finish_upload(url)
    assert fake.files[stored.storage_ref]["content"] == b"a" * CHUNK_SIZE + b"b" * CHUNK_SIZE


@pytest.mark.django_db
def test_chunk_upload_stops_after_5_attempts(customer_a, fake, make_storage, sleeps):
    case = PublicationCaseFactory(owner=customer_a)
    storage = make_storage()
    url = storage.start_upload(case, DocumentType.MANUSCRIPT, "a.pdf", 3, "")
    before = len(fake.upload_requests())
    # Mọi PUT gửi dữ liệu đều lỗi 503; các lần hỏi trạng thái vẫn trả 308
    original = fake._upload

    def fail_data_puts(method, query, headers, body, uri):
        if method == "PUT" and body:
            from tests.drive_fake import _error

            return _error(503)
        return original(method, query, headers, body, uri)

    fake._upload = fail_data_puts
    with pytest.raises(DriveApiError) as exc_info:
        storage.append_chunk(url, 0, b"abc")
    assert len(fake.upload_requests()) - before == 5
    assert "thử lại" in str(exc_info.value.messages[0])


def test_execute_stops_after_5_attempts_with_vietnamese_message(fake, sleeps):
    client = DriveClient(http=fake, sleep=sleeps.append)
    fake.fail_next(10, 503)
    with pytest.raises(DriveApiError) as exc_info:
        client.execute(client.files.get(fileId="abc", supportsAllDrives=True))
    assert len(fake.requests) == 5
    assert sleeps == [1.0, 2.0, 4.0, 8.0]
    message = exc_info.value.messages[0]
    assert "Kho lưu trữ tạm thời không phản hồi" in message
    assert "503" not in message and "googleapis" not in message


def test_send_stops_after_5_attempts(fake, sleeps):
    client = DriveClient(http=fake, sleep=sleeps.append)
    fake.fail_next(10, 502)
    with pytest.raises(DriveApiError) as exc_info:
        client.send("https://www.googleapis.com/drive/v3/files/abc?alt=media")
    assert exc_info.value.status == 502
    assert len(fake.requests) == 5


def test_rate_limit_429_and_403_rate_limit_are_retried(fake, sleeps):
    client = DriveClient(http=fake, sleep=sleeps.append)
    fake.fail_next(1, 429, reason="rateLimitExceeded")
    fake.fail_next(1, 403, reason="userRateLimitExceeded")
    result = client.execute(client.files.get(fileId=DRIVE_ID, supportsAllDrives=True))
    assert result["id"] == DRIVE_ID
    assert len(fake.requests) == 3


@pytest.mark.parametrize(
    ("status", "reason", "expected"),
    [
        (403, "insufficientFilePermissions", "không có quyền truy cập"),
        (404, "notFound", "Không tìm thấy tệp"),
        (400, "badRequest", "Không xử lý được yêu cầu"),
    ],
)
def test_permission_and_not_found_errors_are_not_retried(fake, sleeps, status, reason, expected):
    client = DriveClient(http=fake, sleep=sleeps.append)
    fake.fail_next(1, status, reason=reason)
    with pytest.raises(ValidationError) as exc_info:
        client.execute(client.files.get(fileId="abc", supportsAllDrives=True))
    assert len(fake.requests) == 1
    assert sleeps == []
    assert isinstance(exc_info.value, DriveApiError)
    assert expected in exc_info.value.messages[0]


def test_transport_errors_are_retried(sleeps):
    class FlakyHttp(FakeDrive):
        calls = 0

        def request(self, uri, method="GET", *args, **kwargs):
            FlakyHttp.calls += 1
            if FlakyHttp.calls <= 2:
                raise TimeoutError("timed out")
            return super().request(uri, method, *args, **kwargs)

    client = DriveClient(http=FlakyHttp(DRIVE_ID), sleep=sleeps.append)
    assert client.execute(client.files.get(fileId=DRIVE_ID, supportsAllDrives=True))["id"]
    resp, _ = client.send(f"https://www.googleapis.com/drive/v3/files/{DRIVE_ID}")
    assert int(resp.status) == 200

    class DeadHttp:
        def request(self, *args, **kwargs):
            raise ConnectionRefusedError("refused")

    dead = DriveClient(http=DeadHttp(), sleep=sleeps.append)
    with pytest.raises(DriveApiError):
        dead.execute(dead.files.get(fileId="x", supportsAllDrives=True))
    with pytest.raises(DriveApiError):
        dead.send("https://www.googleapis.com/drive/v3/files/x")


def test_with_all_drives_adds_parameter_once():
    assert with_all_drives("https://x/y") == "https://x/y?supportsAllDrives=true"
    assert with_all_drives("https://x/y?a=1") == "https://x/y?a=1&supportsAllDrives=true"
    url = "https://x/y?supportsAllDrives=true&upload_id=1"
    assert with_all_drives(url) == url


# ---------------------------------------------------------------------------
# exists() / open_stream() / abort_upload()
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_exists_true_for_live_file(fake, make_storage):
    file_id = fake.add_file(b"x")
    assert make_storage().exists(file_id) is True
    assert not AuditEvent.objects.filter(action="document.missing").exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        (lambda fake: fake.add_file(b"x", trashed=True), "trashed"),
        (lambda fake: fake.add_file(b"x", driveId="other-drive"), "outside_shared_drive"),
        (lambda fake: "deletedFileId123", "not_found"),
        (lambda fake: "../../etc/passwd", "invalid_ref"),
    ],
)
def test_exists_false_for_trashed_moved_deleted_and_logs_missing(fake, make_storage, setup, reason):
    ref = setup(fake)
    assert make_storage().exists(ref) is False
    event = AuditEvent.objects.get(action="document.missing")
    assert event.data["reason"] == reason
    assert event.data["storage_ref"] == ref


@pytest.mark.django_db
def test_exists_false_when_forbidden(fake, make_storage):
    file_id = fake.add_file(b"x")
    fake.fail_next(1, 403, reason="insufficientFilePermissions")
    assert make_storage().exists(file_id) is False
    assert AuditEvent.objects.get(action="document.missing").data["reason"] == "forbidden"


@pytest.mark.django_db
def test_exists_raises_on_persistent_server_error(fake, make_storage):
    file_id = fake.add_file(b"x")
    fake.fail_next(5, 500)
    with pytest.raises(DriveApiError):
        make_storage().exists(file_id)


def test_open_stream_reads_in_blocks(fake, make_storage):
    content = bytes(range(256)) * (9 * 1024 * 4)  # 9 MiB
    file_id = fake.add_file(content)
    blocks = list(make_storage().open_stream(file_id))
    assert [len(b) for b in blocks] == [4 * 1024 * 1024, 4 * 1024 * 1024, 1024 * 1024]
    assert b"".join(blocks) == content
    assert all("Range" in r.headers or "range" in r.headers for r in fake.requests)


def test_open_stream_empty_and_full_responses(fake, make_storage):
    empty = fake.add_file(b"")
    assert list(make_storage().open_stream(empty)) == []

    original = fake._media
    fake._media = lambda file_id, headers: original(file_id, {})  # server bỏ qua Range → 200
    full = fake.add_file(b"hello")
    assert list(make_storage().open_stream(full)) == [b"hello"]

    with pytest.raises(DriveApiError):
        list(make_storage().open_stream("bad/ref"))


@pytest.mark.django_db
def test_abort_upload_cancels_resumable_session(customer_a, fake, make_storage):
    case = PublicationCaseFactory(owner=customer_a)
    url = make_storage().start_upload(case, DocumentType.MANUSCRIPT, "a.pdf", 10, "")
    make_storage().abort_upload(url)
    assert fake.sessions == {}
    assert any(r.method == "DELETE" and r.uri == url for r in fake.requests)
    # Hủy lần nữa (phiên đã mất) không gây lỗi
    make_storage().abort_upload(url)


@pytest.mark.django_db
def test_abort_upload_deletes_orphan_file_after_last_chunk(customer_a, fake, make_storage):
    case = PublicationCaseFactory(owner=customer_a)
    session = begin_document_upload(
        user=customer_a,
        case=case,
        doc_type=DocumentType.MANUSCRIPT,
        filename="a.pdf",
        total_size=3,
        storage=make_storage(),
    )
    upload_chunk(user=customer_a, session=session, offset=0, data=b"abc", storage=make_storage())
    file_ids = [f["id"] for f in fake.files.values() if f.get("content") == b"abc"]
    assert len(file_ids) == 1
    make_storage().abort_upload(session.backend_ref)
    assert file_ids[0] not in fake.files


@pytest.mark.django_db
def test_cleanup_uploads_command_aborts_drive_sessions(
    customer_a, fake, gdrive_settings, make_storage
):
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.models import UploadSession, UploadSessionStatus

    case = PublicationCaseFactory(owner=customer_a)
    session = begin_document_upload(
        user=customer_a,
        case=case,
        doc_type=DocumentType.MANUSCRIPT,
        filename="a.pdf",
        total_size=10,
        storage=make_storage(),
    )
    UploadSession.objects.filter(pk=session.pk).update(
        expires_at=timezone.now() - timedelta(hours=1)
    )
    call_command("cleanup_uploads", stdout=io.StringIO())
    session.refresh_from_db()
    assert session.status == UploadSessionStatus.ABORTED
    assert fake.sessions == {}


def test_delete_file_falls_back_to_trash_when_forbidden(fake, make_storage):
    file_id = fake.add_file(b"x")
    fake.fail_next(1, 403, method="DELETE", reason="insufficientFilePermissions")
    make_storage().delete_file(file_id)
    assert fake.files[file_id]["trashed"] is True

    fake.fail_next(1, 400, method="DELETE")
    with pytest.raises(DriveApiError):
        make_storage().delete_file(file_id)


# ---------------------------------------------------------------------------
# save_library_file lên Drive
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("category", ["form_templates", "public_media"])
def test_save_library_file_on_drive(fake, make_storage, category):
    payload = b"bieu mau" * 1000
    stored = make_storage().save_library_file(
        category, "../Mẫu 1.docx", io.BytesIO(payload), len(payload), "application/msword"
    )
    drive_file = fake.files[stored.storage_ref]
    assert drive_file["content"] == payload
    assert stored.sha256 == hashlib.sha256(payload).hexdigest()
    assert stored.size == len(payload)
    assert stored.mime == "application/msword"
    path = fake.path_of(stored.storage_ref)
    assert path.startswith(f"Portal/library/{category}/")
    prefix, safe = path.rsplit("/", 1)[1].split("_", 1)
    assert len(prefix) == 32
    assert safe == "M_u_1.docx"
    folder = fake.files[drive_file["parents"][0]]
    assert folder["appProperties"]["portal_library_category"] == category
    _assert_all_drives(fake)


@pytest.mark.django_db
def test_save_library_file_multi_chunk(fake, make_storage, settings):
    settings.MAX_LIBRARY_FILE_MB = 10
    payload = b"m" * (CHUNK_SIZE + 100)
    stored = make_storage().save_library_file(
        "public_media", "bia.png", io.BytesIO(payload), len(payload), ""
    )
    assert fake.files[stored.storage_ref]["content"] == payload
    assert stored.mime == "application/octet-stream"
    assert len(fake.upload_requests()) == 2


@pytest.mark.django_db
def test_save_library_file_rejections(fake, make_storage, settings):
    settings.MAX_LIBRARY_FILE_MB = 1
    storage = make_storage()
    with pytest.raises(ValidationError):
        storage.save_library_file("cases", "a.pdf", io.BytesIO(b"abc"), 3, "")
    big = 1024 * 1024 + 1
    with pytest.raises(ValidationError):
        storage.save_library_file("form_templates", "a.pdf", io.BytesIO(b"x" * big), big, "")
    assert fake.requests == []  # bị chặn trước khi gọi Drive

    # Dữ liệu thực lớn hơn khai báo → hủy phiên, không để lại file
    with pytest.raises(ValidationError):
        storage.save_library_file("form_templates", "a.pdf", io.BytesIO(b"x" * big), 10, "")
    # Dữ liệu thực ít hơn khai báo
    with pytest.raises(ValidationError):
        storage.save_library_file("form_templates", "a.pdf", io.BytesIO(b"x" * 5), 10, "")
    assert fake.sessions == {}
    assert not [f for f in fake.files.values() if "content" in f]


def test_sha256_mismatch_is_rejected(fake, make_storage):
    original = fake._public
    fake._public = lambda f: (
        {**original(f), "sha256Checksum": "0" * 64} if "content" in f else original(f)
    )
    with pytest.raises(ValidationError):
        make_storage().save_library_file("public_media", "a.png", io.BytesIO(b"abc"), 3, "")


# ---------------------------------------------------------------------------
# Tích hợp với get_storage() và view tải xuống của M0
# ---------------------------------------------------------------------------


def test_get_storage_returns_google_drive_storage(gdrive_settings):
    assert isinstance(get_storage(), GoogleDriveStorage)


def test_missing_shared_drive_id_is_improperly_configured(settings):
    settings.GDRIVE_SHARED_DRIVE_ID = ""
    with pytest.raises(ImproperlyConfigured):
        GoogleDriveStorage(client=object())


@pytest.mark.django_db
def test_http_upload_and_download_with_gdrive_backend(client, customer_a, fake, gdrive_settings):
    case = PublicationCaseFactory(owner=customer_a)
    payload = b"P" * CHUNK_SIZE + b"Q" * 77
    client.force_login(customer_a)
    res = client.post(
        reverse("core:upload_begin"),
        data=json.dumps(
            {
                "case_id": str(case.pk),
                "doc_type": DocumentType.MANUSCRIPT,
                "filename": "bt.pdf",
                "total_size": len(payload),
                "mime_type": "application/pdf",
            }
        ),
        content_type="application/json",
    )
    session_id = res.json()["session_id"]
    for offset in (0, CHUNK_SIZE):
        res = client.post(
            reverse("core:upload_chunk", args=[session_id]),
            data=payload[offset : offset + CHUNK_SIZE],
            content_type="application/octet-stream",
            headers={"X-Upload-Offset": str(offset)},
        )
        assert res.status_code == 200
    res = client.post(reverse("core:upload_complete", args=[session_id]))
    assert res.status_code == 201
    doc = Document.objects.get(pk=res.json()["document_id"])
    assert doc.storage_backend == "gdrive"
    assert doc.storage_ref in fake.files

    res = client.get(reverse("core:document_download", args=[doc.pk]))
    assert res.status_code == 200
    assert "Content-Length" not in res
    assert b"".join(res.streaming_content) == payload
    _assert_all_drives(fake)


@pytest.mark.django_db
def test_download_of_file_removed_from_drive_returns_404_and_logs_missing(
    client, customer_a, fake, gdrive_settings
):
    case = PublicationCaseFactory(owner=customer_a)
    file_id = fake.add_file(b"x", trashed=True)
    doc = DocumentFactory(case=case, storage_backend="gdrive", storage_ref=file_id)
    client.force_login(customer_a)
    res = client.get(reverse("core:document_download", args=[doc.pk]))
    assert res.status_code == 404
    event = AuditEvent.objects.get(action="document.missing")
    assert event.object_type == "Document"
    assert event.object_id == str(doc.pk)
    assert event.case_id == case.pk
    assert event.data["reason"] == "trashed"


@pytest.mark.django_db
def test_drive_error_during_complete_returns_vietnamese_400(
    client, customer_a, fake, gdrive_settings
):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)
    res = client.post(
        reverse("core:upload_begin"),
        data=json.dumps(
            {
                "case_id": str(case.pk),
                "doc_type": DocumentType.MANUSCRIPT,
                "filename": "bt.pdf",
                "total_size": 3,
            }
        ),
        content_type="application/json",
    )
    session_id = res.json()["session_id"]
    client.post(
        reverse("core:upload_chunk", args=[session_id]),
        data=b"abc",
        content_type="application/octet-stream",
        headers={"X-Upload-Offset": "0"},
    )
    fake.fail_next(1, 403, method="GET", reason="insufficientFilePermissions")
    res = client.post(reverse("core:upload_complete", args=[session_id]))
    assert res.status_code == 400
    assert "không có quyền truy cập" in res.json()["error"]
    assert "googleapis" not in res.json()["error"]
    assert not Document.objects.exists()


# ---------------------------------------------------------------------------
# Xác thực
# ---------------------------------------------------------------------------


def test_build_authorized_http_uses_credentials_file(settings, monkeypatch):
    from google.oauth2 import service_account

    calls = {}

    def fake_from_file(path, scopes):
        calls["path"], calls["scopes"] = path, scopes
        return object()

    monkeypatch.setattr(service_account.Credentials, "from_service_account_file", fake_from_file)
    settings.GDRIVE_CREDENTIALS_FILE = "/secrets/sa.json"
    http = client_module.build_authorized_http()
    assert calls == {
        "path": "/secrets/sa.json",
        "scopes": ["https://www.googleapis.com/auth/drive"],
    }
    assert http.http.timeout == client_module.HTTP_TIMEOUT_SECONDS


def test_build_authorized_http_uses_application_default_credentials(settings, monkeypatch):
    import google.auth

    calls = {}

    def fake_default(scopes):
        calls["scopes"] = scopes
        return object(), "project"

    monkeypatch.setattr(google.auth, "default", fake_default)
    settings.GDRIVE_CREDENTIALS_FILE = ""
    client_module.build_authorized_http()
    assert calls == {"scopes": ["https://www.googleapis.com/auth/drive"]}


def test_drive_client_builds_default_http(monkeypatch, fake):
    monkeypatch.setattr(client_module, "build_authorized_http", lambda: fake)
    client = DriveClient()
    assert client.execute(client.files.get(fileId=DRIVE_ID, supportsAllDrives=True))["id"]
    assert client.request_log[0][0] == "GET"


# ---------------------------------------------------------------------------
# Lệnh drive_check
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_drive_check_command_success(fake, make_storage):
    storage = make_storage()
    out = io.StringIO()
    call_command(DriveCheckCommand(storage=storage), stdout=out)
    output = out.getvalue()
    assert "Đọc được Shared Drive 'NXB Shared Drive'" in output
    assert "Portal/_healthcheck/" in output
    assert "sha256 khớp" in output
    assert "Xóa được file thử" in output
    assert "supportsAllDrives=true" in output
    assert "TẤT CẢ ĐẠT" in output
    assert "[LỖI]" not in output
    assert not [f for f in fake.files.values() if "content" in f]  # file thử đã xóa
    healthcheck = [f for f in fake.folders() if f["name"] == "_healthcheck"]
    assert fake.path_of(healthcheck[0]["id"]) == "Portal/_healthcheck"


@pytest.mark.django_db
def test_drive_check_keep_file(fake, make_storage):
    out = io.StringIO()
    call_command(DriveCheckCommand(storage=make_storage()), "--keep-file", stdout=out)
    assert "Giữ lại file thử" in out.getvalue()
    assert [f for f in fake.files.values() if "content" in f]


@pytest.mark.django_db
def test_drive_check_command_reports_failure(fake, make_storage):
    fake.fail_next(1, 403, reason="insufficientFilePermissions")
    out = io.StringIO()
    with pytest.raises(CommandError):
        call_command(DriveCheckCommand(storage=make_storage()), stdout=out)
    assert "[LỖI]" in out.getvalue()
    assert "không có quyền truy cập" in out.getvalue()


@pytest.mark.django_db
def test_drive_check_detects_missing_supports_all_drives(fake, make_storage):
    storage = make_storage()
    storage.client.request_log.append(("GET", "https://www.googleapis.com/drive/v3/files/x"))
    out = io.StringIO()
    with pytest.raises(CommandError):
        call_command(DriveCheckCommand(storage=storage), stdout=out)
    assert "thiếu supportsAllDrives" in out.getvalue()


@pytest.mark.django_db
def test_drive_check_detects_wrong_content_and_wrong_drive(fake, make_storage):
    original = fake._public
    fake._public = lambda f: (
        {**original(f), "driveId": "other", "sha256Checksum": "0" * 64}
        if "content" in f
        else original(f)
    )
    storage = make_storage()
    storage._stored_file = lambda file_id, size, sha="", meta=None: type(
        "S", (), {"storage_ref": file_id, "sha256": "0" * 64}
    )()
    out = io.StringIO()
    with pytest.raises(CommandError):
        call_command(DriveCheckCommand(storage=storage), "--keep-file", stdout=out)
    output = out.getvalue()
    assert "SHA-256 của file thử không khớp" in output
    assert "không nằm trong Shared Drive" in output


def test_drive_check_without_configuration(settings):
    settings.GDRIVE_SHARED_DRIVE_ID = ""
    settings.FILE_STORAGE_BACKEND = "local"
    out = io.StringIO()
    with pytest.raises(CommandError):
        call_command("drive_check", stdout=out)
    output = out.getvalue()
    assert "chưa là 'gdrive'" in output
    assert "Không khởi tạo được kết nối Google Drive" in output


@pytest.mark.django_db
def test_chunk_partially_accepted_is_resent_from_drive_offset(customer_a, fake, make_storage):
    """Drive trả 308 nhưng mới nhận một phần (bội số 256 KiB): gửi tiếp phần còn lại."""
    case = PublicationCaseFactory(owner=customer_a)
    storage = make_storage()
    total = CHUNK_SIZE + 5
    url = storage.start_upload(case, DocumentType.MANUSCRIPT, "a.pdf", total, "")
    original = fake._upload
    state = {"partial": False}
    quarter = 256 * 1024

    def accept_partially(method, query, headers, body, uri):
        if method == "PUT" and body and not state["partial"]:
            state["partial"] = True
            headers = {**headers, "content-range": f"bytes 0-{quarter - 1}/{total}"}
            return original(method, query, headers, body[:quarter], uri)
        return original(method, query, headers, body, uri)

    fake._upload = accept_partially
    assert storage.append_chunk(url, 0, b"a" * CHUNK_SIZE) == CHUNK_SIZE
    ranges = [r.headers["content-range"] for r in fake.upload_requests()]
    assert ranges[-1] == f"bytes {quarter}-{CHUNK_SIZE - 1}/{total}"
    storage.append_chunk(url, CHUNK_SIZE, b"b" * 5)
    assert fake.files[storage.finish_upload(url).storage_ref]["content"] == (
        b"a" * CHUNK_SIZE + b"b" * 5
    )


@pytest.mark.django_db
def test_chunk_rejected_by_drive_is_not_retried(customer_a, fake, make_storage, sleeps):
    case = PublicationCaseFactory(owner=customer_a)
    storage = make_storage()
    url = storage.start_upload(case, DocumentType.MANUSCRIPT, "a.pdf", 3, "")
    fake.fail_next(1, 400, method="PUT")
    with pytest.raises(DriveApiError) as exc_info:
        storage.append_chunk(url, 0, b"abc")
    assert exc_info.value.status == 400
    assert sleeps == []
