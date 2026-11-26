"""Nhóm test 4: Upload chia phần 8 MiB (file 70 MiB), SHA-256, version, stream download 40 MiB & chặn xóa Document."""

import hashlib

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import StreamingHttpResponse
from django.urls import reverse

from apps.core.models import Document, DocumentType
from apps.core.storage import (
    CHUNK_SIZE,
    LocalFileStorage,
    begin_document_upload,
    complete_document_upload,
    upload_chunk,
)
from tests.factories import DocumentFactory, PublicationCaseFactory


@pytest.mark.django_db
def test_chunked_upload_70_mib_and_sha256_and_streaming_download(
    tmp_path,
    settings,
    client,
    customer_a,
):
    settings.MEDIA_ROOT = tmp_path
    storage = LocalFileStorage(media_root=tmp_path)
    case = PublicationCaseFactory(owner=customer_a)

    # Tạo luồng 70 MiB gồm 9 phần (8 phần 8 MiB + 1 phần 6 MiB), không giữ 2 bản sao lớn cùng lúc
    total_size = 70 * 1024 * 1024
    session = begin_document_upload(
        user=customer_a,
        case=case,
        doc_type=DocumentType.MANUSCRIPT,
        filename="ban_thao_70mb.pdf",
        total_size=total_size,
        mime_type="application/pdf",
        storage=storage,
    )

    expected_hasher = hashlib.sha256()
    offset = 0
    chunk_idx = 0
    while offset < total_size:
        size = min(CHUNK_SIZE, total_size - offset)
        assert size <= CHUNK_SIZE
        chunk = bytes([chunk_idx % 251]) * size
        expected_hasher.update(chunk)
        upload_chunk(user=customer_a, session=session, offset=offset, data=chunk, storage=storage)
        offset += size
        chunk_idx += 1

    assert chunk_idx == 9
    doc_v1 = complete_document_upload(user=customer_a, session=session, storage=storage)
    assert doc_v1.version == 1
    assert doc_v1.is_current is True
    assert doc_v1.size_bytes == total_size
    assert doc_v1.sha256 == expected_hasher.hexdigest()

    # Tải xuống dạng StreamingHttpResponse không đặt Content-Length cố định (S4)
    client.force_login(customer_a)
    response = client.get(reverse("core:document_download", args=[doc_v1.pk]))
    assert response.status_code == 200
    assert isinstance(response, StreamingHttpResponse)
    assert "Content-Length" not in response

    # Tải phiên bản v2 -> v1 giữ nguyên, is_current chuyển False
    v2_data = b"%PDF-1.7 version 2 content"
    s2 = begin_document_upload(
        user=customer_a,
        case=case,
        doc_type=DocumentType.MANUSCRIPT,
        filename="ban_thao_v2.pdf",
        total_size=len(v2_data),
        storage=storage,
    )
    upload_chunk(user=customer_a, session=s2, offset=0, data=v2_data, storage=storage)
    doc_v2 = complete_document_upload(user=customer_a, session=s2, storage=storage)

    doc_v1.refresh_from_db()
    assert doc_v1.is_current is False
    assert doc_v2.version == 2
    assert doc_v2.is_current is True
    assert Document.objects.filter(case=case, doc_type=DocumentType.MANUSCRIPT).count() == 2


@pytest.mark.django_db
def test_streaming_download_40_mib_omits_content_length_header(
    tmp_path,
    settings,
    client,
    customer_a,
):
    """Kiểm tra S4: tệp 40 MiB (> 32 MiB Cloud Run) tải về dạng chunked, không có header Content-Length."""
    settings.MEDIA_ROOT = tmp_path
    case = PublicationCaseFactory(owner=customer_a)
    storage_ref = f"cases/{case.pk}/v1_40mb.pdf"
    target_path = tmp_path / storage_ref
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(b"%PDF-1.7 sample stream payload")

    doc_40mb = DocumentFactory(
        case=case,
        doc_type=DocumentType.MANUSCRIPT,
        size_bytes=40 * 1024 * 1024,
        storage_ref=storage_ref,
        uploaded_by=customer_a,
    )

    client.force_login(customer_a)
    response = client.get(reverse("core:document_download", args=[doc_40mb.pk]))
    assert response.status_code == 200
    assert isinstance(response, StreamingHttpResponse)
    assert "Content-Length" not in response
    assert b"".join(response.streaming_content) == b"%PDF-1.7 sample stream payload"


@pytest.mark.django_db
def test_document_cannot_be_deleted_individually_or_in_bulk(customer_a):
    """Kiểm tra S5: chặn cả doc.delete() và Document.objects.filter(...).delete()."""
    case = PublicationCaseFactory(owner=customer_a)
    doc = DocumentFactory(case=case, uploaded_by=customer_a)

    with pytest.raises(PermissionDenied):
        doc.delete()
    with pytest.raises(PermissionDenied):
        Document.objects.filter(pk=doc.pk).delete()
    assert Document.objects.filter(pk=doc.pk).exists()


@pytest.mark.django_db
def test_upload_rejects_bad_offset_extension_size_and_unauthorized(
    tmp_path,
    settings,
    customer_a,
    customer_b,
):
    settings.MEDIA_ROOT = tmp_path
    storage = LocalFileStorage(media_root=tmp_path)
    case = PublicationCaseFactory(owner=customer_a)

    # Sai định dạng
    with pytest.raises(ValidationError):
        begin_document_upload(
            user=customer_a,
            case=case,
            doc_type=DocumentType.MANUSCRIPT,
            filename="virus.exe",
            total_size=1024,
            storage=storage,
        )

    # Quá dung lượng tối đa
    with pytest.raises(ValidationError):
        begin_document_upload(
            user=customer_a,
            case=case,
            doc_type=DocumentType.MANUSCRIPT,
            filename="huge.pdf",
            total_size=250 * 1024 * 1024,
            storage=storage,
        )

    # Người không có quyền không gửi được phần nào
    with pytest.raises(PermissionDenied):
        begin_document_upload(
            user=customer_b,
            case=case,
            doc_type=DocumentType.MANUSCRIPT,
            filename="steal.pdf",
            total_size=100,
            storage=storage,
        )

    # Sai offset và thiếu phần khi complete
    session = begin_document_upload(
        user=customer_a,
        case=case,
        doc_type=DocumentType.MANUSCRIPT,
        filename="ok.pdf",
        total_size=20,
        storage=storage,
    )
    with pytest.raises(ValidationError):
        upload_chunk(user=customer_a, session=session, offset=5, data=b"12345", storage=storage)

    upload_chunk(user=customer_a, session=session, offset=0, data=b"1234567890", storage=storage)
    with pytest.raises(ValidationError):
        complete_document_upload(user=customer_a, session=session, storage=storage)


# ---------------------------------------------------------------------------
# CR-001: save_library_file() và get_storage()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("category", ["form_templates", "public_media"])
def test_save_library_file_stores_under_library_category(tmp_path, category):
    import io

    storage = LocalFileStorage(media_root=tmp_path)
    payload = b"%PDF-1.7 bieu mau" * 1000
    stored = storage.save_library_file(
        category, "Mẫu 1.pdf", io.BytesIO(payload), len(payload), "application/pdf"
    )

    assert stored.storage_ref.startswith(f"library/{category}/")
    name = stored.storage_ref.rsplit("/", 1)[1]
    prefix, safe_name = name.split("_", 1)
    assert len(prefix) == 32 and int(prefix, 16) >= 0
    assert safe_name == "M_u_1.pdf"
    assert stored.size == len(payload)
    assert stored.mime == "application/pdf"
    assert stored.sha256 == hashlib.sha256(payload).hexdigest()
    assert storage.exists(stored.storage_ref)
    assert b"".join(storage.open_stream(stored.storage_ref)) == payload


def test_save_library_file_two_uploads_same_name_do_not_overwrite(tmp_path):
    import io

    storage = LocalFileStorage(media_root=tmp_path)
    a = storage.save_library_file("public_media", "bia.png", io.BytesIO(b"A"), 1, "image/png")
    b = storage.save_library_file("public_media", "bia.png", io.BytesIO(b"B"), 1, "image/png")
    assert a.storage_ref != b.storage_ref
    assert b"".join(storage.open_stream(a.storage_ref)) == b"A"


def test_save_library_file_rejects_file_over_limit(tmp_path, settings):
    import io

    settings.MAX_LIBRARY_FILE_MB = 1
    storage = LocalFileStorage(media_root=tmp_path)
    too_big = 1024 * 1024 + 1
    with pytest.raises(ValidationError):
        storage.save_library_file(
            "form_templates", "lon.pdf", io.BytesIO(b"x" * too_big), too_big, "application/pdf"
        )
    # Khai báo sai dung lượng (nhỏ hơn thực tế) cũng bị chặn và không để lại file rác
    with pytest.raises(ValidationError):
        storage.save_library_file(
            "form_templates", "gian_lan.pdf", io.BytesIO(b"x" * too_big), 10, "application/pdf"
        )
    # Khai báo lớn hơn dữ liệu thực nhận
    with pytest.raises(ValidationError):
        storage.save_library_file(
            "form_templates", "thieu.pdf", io.BytesIO(b"x" * 5), 10, "application/pdf"
        )
    with pytest.raises(ValidationError):
        storage.save_library_file("form_templates", "rong.pdf", io.BytesIO(b""), 0, "")
    library_dir = tmp_path / "library" / "form_templates"
    assert not library_dir.exists() or list(library_dir.iterdir()) == []


def test_save_library_file_default_limit_is_10_mib(tmp_path, settings):
    import io

    del settings.MAX_LIBRARY_FILE_MB
    storage = LocalFileStorage(media_root=tmp_path)
    with pytest.raises(ValidationError):
        storage.save_library_file(
            "public_media", "a.png", io.BytesIO(b""), 10 * 1024 * 1024 + 1, "image/png"
        )


@pytest.mark.parametrize("category", ["cases", "../cases", "library", "", "FORM_TEMPLATES"])
def test_save_library_file_rejects_unknown_category(tmp_path, category):
    import io

    storage = LocalFileStorage(media_root=tmp_path)
    with pytest.raises(ValidationError):
        storage.save_library_file(category, "a.pdf", io.BytesIO(b"abc"), 3, "application/pdf")
    assert not (tmp_path / "library").exists()


@pytest.mark.parametrize(
    "dangerous",
    ["../../etc/passwd", "..\\..\\windows\\win.ini", "/abs/path/x.pdf", "....", "a b<>|?*.pdf"],
)
def test_save_library_file_sanitizes_dangerous_filename(tmp_path, dangerous):
    import io

    storage = LocalFileStorage(media_root=tmp_path)
    stored = storage.save_library_file(
        "form_templates", dangerous, io.BytesIO(b"abc"), 3, "application/pdf"
    )
    parts = stored.storage_ref.split("/")
    assert parts[:2] == ["library", "form_templates"]
    assert len(parts) == 3
    assert ".." not in parts[2].split("_", 1)[1].split("/")
    target = (tmp_path / stored.storage_ref).resolve()
    assert target.is_file()
    assert str(target).startswith(str((tmp_path / "library" / "form_templates").resolve()))


def test_get_storage_returns_local_backend(settings, tmp_path):
    from apps.core.storage import get_storage

    settings.FILE_STORAGE_BACKEND = "local"
    settings.MEDIA_ROOT = tmp_path
    assert isinstance(get_storage(), LocalFileStorage)


def test_get_storage_returns_gdrive_backend(settings, monkeypatch):
    """get_storage() import GoogleDriveStorage bên trong hàm khi FILE_STORAGE_BACKEND=gdrive."""
    import sys
    import types

    from apps.core.storage import get_storage

    class FakeGoogleDriveStorage:
        pass

    fake_module = types.ModuleType("apps.documents_drive.storage")
    fake_module.GoogleDriveStorage = FakeGoogleDriveStorage
    monkeypatch.setitem(sys.modules, "apps.documents_drive.storage", fake_module)

    settings.FILE_STORAGE_BACKEND = "gdrive"
    assert isinstance(get_storage(), FakeGoogleDriveStorage)


def test_get_storage_rejects_unknown_backend(settings):
    from apps.core.storage import get_storage

    settings.FILE_STORAGE_BACKEND = "s3"
    with pytest.raises(NotImplementedError):
        get_storage()


def test_library_settings_defaults():
    from django.conf import settings as dj_settings

    assert dj_settings.MAX_LIBRARY_FILE_MB == 10
    assert dj_settings.GDRIVE_SHARED_DRIVE_ID == ""
    assert dj_settings.GDRIVE_CREDENTIALS_FILE == ""
