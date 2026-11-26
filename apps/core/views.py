"""Views dùng chung của M0: tải tài liệu dạng stream và các endpoint upload chia phần."""

from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils.encoding import escape_uri_path
from django.views import View

from apps.core.audit import log_event
from apps.core.models import Document, UploadSession
from apps.core.permissions import can_download, cases_visible_to
from apps.core.storage import (
    CHUNK_SIZE,
    begin_document_upload,
    complete_document_upload,
    get_storage,
    upload_chunk,
)


class DocumentDownloadView(LoginRequiredMixin, View):
    """Tải xuống tài liệu qua StreamingHttpResponse sau khi kiểm tra can_download() (mục 9)."""

    def get(self, request, doc_id: int):
        document = get_object_or_404(Document.objects.select_related("case"), pk=doc_id)
        if not can_download(request.user, document):
            raise Http404("Không tìm thấy tài liệu.")

        storage = get_storage()
        if not storage.exists(document.storage_ref):
            raise Http404("Tệp lưu trữ không tồn tại.")

        log_event(
            actor=request.user,
            action="document.download",
            object_type="Document",
            object_id=str(document.pk),
            case=document.case,
            data={"doc_type": document.doc_type, "version": document.version},
            request=request,
        )

        response = StreamingHttpResponse(
            storage.open_stream(document.storage_ref),
            content_type=document.mime_type or "application/octet-stream",
        )
        # Không đặt Content-Length cố định để StreamingHttpResponse truyền dạng chunked,
        # tránh bị giới hạn 32 MiB/response của Cloud Run với tệp dung lượng lớn (mục 9).
        safe_name = escape_uri_path(document.original_filename)
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{safe_name}"
        return response


class UploadBeginView(LoginRequiredMixin, View):
    """Khởi tạo phiên upload chia phần (mỗi phần <= 8 MiB)."""

    def post(self, request):
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Dữ liệu JSON không hợp lệ."}, status=400)

        case_id = payload.get("case_id")
        case = get_object_or_404(cases_visible_to(request.user), pk=case_id)
        try:
            session = begin_document_upload(
                user=request.user,
                case=case,
                doc_type=payload.get("doc_type", ""),
                form_code=payload.get("form_code", ""),
                filename=payload.get("filename", ""),
                total_size=int(payload.get("total_size", 0)),
                mime_type=payload.get("mime_type", "application/octet-stream"),
            )
        except PermissionDenied as exc:
            return JsonResponse({"error": str(exc)}, status=403)
        except (ValidationError, ValueError) as exc:
            msg = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            return JsonResponse({"error": msg}, status=400)

        return JsonResponse(
            {
                "session_id": str(session.pk),
                "chunk_size": CHUNK_SIZE,
                "expires_at": session.expires_at.isoformat(),
            },
            status=201,
        )


class UploadChunkView(LoginRequiredMixin, View):
    """Nhận một phần dữ liệu (chunk <= 8 MiB) tại đúng offset."""

    def post(self, request, session_id):
        session = get_object_or_404(UploadSession.objects.select_related("case"), pk=session_id)
        try:
            offset = int(request.headers.get("X-Upload-Offset", request.GET.get("offset", "-1")))
            received = upload_chunk(
                user=request.user,
                session=session,
                offset=offset,
                data=request.body,
            )
        except PermissionDenied as exc:
            return JsonResponse({"error": str(exc)}, status=403)
        except (ValidationError, ValueError) as exc:
            msg = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            return JsonResponse({"error": msg}, status=400)

        return JsonResponse({"received_bytes": received, "total_size": session.total_size})


class UploadCompleteView(LoginRequiredMixin, View):
    """Hoàn tất phiên upload chia phần và tạo bản ghi Document mới."""

    def post(self, request, session_id):
        session = get_object_or_404(UploadSession.objects.select_related("case"), pk=session_id)
        note = ""
        if request.body:
            try:
                note = json.loads(request.body.decode("utf-8")).get("note", "")
            except (ValueError, UnicodeDecodeError):
                note = ""

        try:
            doc = complete_document_upload(
                user=request.user,
                session=session,
                note=note,
                request=request,
            )
        except PermissionDenied as exc:
            return JsonResponse({"error": str(exc)}, status=403)
        except ValidationError as exc:
            return JsonResponse({"error": "; ".join(exc.messages)}, status=400)

        return JsonResponse(
            {
                "document_id": doc.pk,
                "version": doc.version,
                "sha256": doc.sha256,
                "size_bytes": doc.size_bytes,
                "download_url": f"/documents/{doc.pk}/download/",
            },
            status=201,
        )
