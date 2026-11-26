"""URLs của apps.core cho tải xuống dạng stream và upload chia phần."""

from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("<int:doc_id>/download/", views.DocumentDownloadView.as_view(), name="document_download"),
    path("uploads/begin/", views.UploadBeginView.as_view(), name="upload_begin"),
    path("uploads/<uuid:session_id>/chunk/", views.UploadChunkView.as_view(), name="upload_chunk"),
    path(
        "uploads/<uuid:session_id>/complete/",
        views.UploadCompleteView.as_view(),
        name="upload_complete",
    ),
]
