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
