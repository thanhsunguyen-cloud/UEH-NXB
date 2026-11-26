"""Test HTTP cho các view upload chia phần / tải xuống dạng stream của M0 (gói M1, mục 3.3)."""

import hashlib
import json

import pytest
from django.http import StreamingHttpResponse
from django.urls import reverse

from apps.core.models import (
    AuditEvent,
    CaseStatus,
    Document,
    DocumentType,
    UploadSession,
    UploadSessionStatus,
)
from apps.core.storage import CHUNK_SIZE
from tests.factories import DocumentFactory, PublicationCaseFactory


@pytest.fixture
def local_media(settings, tmp_path):
    settings.FILE_STORAGE_BACKEND = "local"
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def _begin(client, case, *, doc_type=DocumentType.MANUSCRIPT, filename="ban_thao.pdf", size=10):
    return client.post(
        reverse("core:upload_begin"),
        data=json.dumps(
            {
                "case_id": str(case.pk),
                "doc_type": doc_type,
                "filename": filename,
                "total_size": size,
                "mime_type": "application/pdf",
            }
        ),
        content_type="application/json",
    )


def _chunk(client, session_id, offset, data):
    return client.post(
        reverse("core:upload_chunk", args=[session_id]),
        data=data,
        content_type="application/octet-stream",
        headers={"X-Upload-Offset": str(offset)},
    )


def _complete(client, session_id, body=None):
    return client.post(
        reverse("core:upload_complete", args=[session_id]),
        data=json.dumps(body) if body is not None else "",
        content_type="application/json",
    )


@pytest.mark.django_db
def test_full_http_upload_flow_and_streaming_download(client, customer_a, local_media):
    case = PublicationCaseFactory(owner=customer_a)
    payload = b"A" * CHUNK_SIZE + b"B" * 1234
    client.force_login(customer_a)

    res = _begin(client, case, size=len(payload))
    assert res.status_code == 201
    body = res.json()
    assert body["chunk_size"] == CHUNK_SIZE
    session_id = body["session_id"]

    res = _chunk(client, session_id, 0, payload[:CHUNK_SIZE])
    assert res.status_code == 200
    assert res.json() == {"received_bytes": CHUNK_SIZE, "total_size": len(payload)}
    res = _chunk(client, session_id, CHUNK_SIZE, payload[CHUNK_SIZE:])
    assert res.json()["received_bytes"] == len(payload)

    res = _complete(client, session_id, {"note": "Bản thảo lần 1"})
    assert res.status_code == 201
    data = res.json()
    assert data["version"] == 1
    assert data["sha256"] == hashlib.sha256(payload).hexdigest()
    assert data["size_bytes"] == len(payload)

    doc = Document.objects.get(pk=data["document_id"])
    assert doc.note == "Bản thảo lần 1"
    assert data["download_url"] == reverse("core:document_download", args=[doc.pk])
    assert UploadSession.objects.get(pk=session_id).status == UploadSessionStatus.DONE

    res = client.get(data["download_url"])
    assert res.status_code == 200
    assert isinstance(res, StreamingHttpResponse)
    assert "Content-Length" not in res
    assert res["Content-Disposition"] == "attachment; filename*=UTF-8''ban_thao.pdf"
    assert b"".join(res.streaming_content) == payload
    assert AuditEvent.objects.filter(action="document.download", object_id=str(doc.pk)).exists()


@pytest.mark.django_db
def test_complete_without_body_and_with_invalid_json_note(client, customer_a, local_media):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)
    for body in ("", "{khong-phai-json"):
        session_id = _begin(client, case, size=3).json()["session_id"]
        _chunk(client, session_id, 0, b"abc")
        res = client.post(
            reverse("core:upload_complete", args=[session_id]),
            data=body,
            content_type="application/json",
        )
        assert res.status_code == 201
        assert Document.objects.get(pk=res.json()["document_id"]).note == ""


@pytest.mark.django_db
def test_anonymous_user_is_redirected_to_login(client, customer_a, local_media):
    case = PublicationCaseFactory(owner=customer_a)
    doc = DocumentFactory(case=case)
    for res in (
        _begin(client, case),
        client.get(reverse("core:document_download", args=[doc.pk])),
    ):
        assert res.status_code == 302
        assert "/tai-khoan/dang-nhap/" in res["Location"]


@pytest.mark.django_db
def test_begin_rejects_invalid_json_and_bad_metadata(client, customer_a, local_media):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)

    res = client.post(reverse("core:upload_begin"), data="{oops", content_type="application/json")
    assert res.status_code == 400

    res = _begin(client, case, filename="virus.exe")
    assert res.status_code == 400
    assert "không được hỗ trợ" in res.json()["error"]

    res = client.post(
        reverse("core:upload_begin"),
        data=json.dumps(
            {
                "case_id": str(case.pk),
                "doc_type": DocumentType.MANUSCRIPT,
                "filename": "a.pdf",
                "total_size": "abc",
            }
        ),
        content_type="application/json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_begin_on_other_customers_case_returns_404(client, customer_a, customer_b, local_media):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_b)
    assert _begin(client, case).status_code == 404
    assert not UploadSession.objects.exists()


@pytest.mark.django_db
def test_admin_cannot_begin_upload_or_download(client, customer_a, admin_user, local_media):
    case = PublicationCaseFactory(owner=customer_a)
    doc = DocumentFactory(case=case)
    client.force_login(admin_user)
    assert _begin(client, case).status_code == 404
    assert client.get(reverse("core:document_download", args=[doc.pk])).status_code == 404


@pytest.mark.django_db
def test_begin_forbidden_doc_type_or_status_returns_403(client, customer_a, local_media):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)
    res = _begin(client, case, doc_type=DocumentType.FORM_4)
    assert res.status_code == 403

    locked = PublicationCaseFactory(owner=customer_a, status=CaseStatus.SUBMITTED)
    assert _begin(client, locked).status_code == 403


@pytest.mark.django_db
def test_chunk_errors_bad_offset_other_user_and_missing_session(
    client, customer_a, customer_b, local_media
):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)
    session_id = _begin(client, case, size=10).json()["session_id"]

    res = _chunk(client, session_id, 5, b"12345")
    assert res.status_code == 400
    assert "offset" in res.json()["error"]

    res = client.post(
        reverse("core:upload_chunk", args=[session_id]),
        data=b"12345",
        content_type="application/octet-stream",
        headers={"X-Upload-Offset": "khong-phai-so"},
    )
    assert res.status_code == 400

    # Offset qua query string khi không có header
    res = client.post(
        reverse("core:upload_chunk", args=[session_id]) + "?offset=0",
        data=b"12345",
        content_type="application/octet-stream",
    )
    assert res.status_code == 200
    assert res.json()["received_bytes"] == 5

    # Người khác không gửi được phần vào phiên của khách hàng A
    client.force_login(customer_b)
    res = _chunk(client, session_id, 5, b"67890")
    assert res.status_code == 403
    res = _complete(client, session_id)
    assert res.status_code == 403

    # Phiên không tồn tại
    res = _chunk(client, "00000000-0000-0000-0000-000000000000", 0, b"x")
    assert res.status_code == 404


@pytest.mark.django_db
def test_complete_incomplete_upload_returns_400(client, customer_a, local_media):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)
    session_id = _begin(client, case, size=10).json()["session_id"]
    _chunk(client, session_id, 0, b"12345")
    res = _complete(client, session_id)
    assert res.status_code == 400
    assert "chưa tải đủ" in res.json()["error"]
    assert not Document.objects.exists()


@pytest.mark.django_db
def test_download_permissions(client, customer_a, customer_b, editor_none, local_media):
    case = PublicationCaseFactory(owner=customer_a)
    storage_ref = f"cases/{case.pk}/MANUSCRIPT/v1_a.pdf"
    target = local_media / storage_ref
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF")
    doc = DocumentFactory(case=case, storage_ref=storage_ref)
    form4 = DocumentFactory(case=case, doc_type=DocumentType.FORM_4, storage_ref=storage_ref)
    url = reverse("core:document_download", args=[doc.pk])

    client.force_login(customer_b)
    assert client.get(url).status_code == 404

    client.force_login(customer_a)
    assert client.get(url).status_code == 200
    # Khách hàng không được tải Mẫu 4 (phiếu duyệt bản thảo)
    assert client.get(reverse("core:document_download", args=[form4.pk])).status_code == 404

    client.force_login(editor_none)
    assert client.get(url).status_code == 200
    assert client.get(reverse("core:document_download", args=[form4.pk])).status_code == 200

    assert client.get(reverse("core:document_download", args=[999999])).status_code == 404


@pytest.mark.django_db
def test_download_missing_file_returns_404(client, customer_a, local_media):
    case = PublicationCaseFactory(owner=customer_a)
    doc = DocumentFactory(case=case, storage_ref=f"cases/{case.pk}/MANUSCRIPT/v1_mat.pdf")
    client.force_login(customer_a)
    res = client.get(reverse("core:document_download", args=[doc.pk]))
    assert res.status_code == 404
    assert not AuditEvent.objects.filter(action="document.download").exists()
