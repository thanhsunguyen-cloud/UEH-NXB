"""URL của M3 — Tác nghiệp biên tập viên (`/noi-bo/`)."""

from django.urls import path

from apps.backoffice import views

app_name = "backoffice"

urlpatterns = [
    path("", views.BackofficeHomeView.as_view(), name="home"),
    path("can-xu-ly/", views.BackofficeQueueView.as_view(), name="queue"),
    path("ho-so/<uuid:case_id>/", views.BackofficeCaseDetailView.as_view(), name="case_detail"),
    path("ho-so/<uuid:case_id>/cap-nhat/", views.CaseUpdateView.as_view(), name="case_update"),
    path(
        "ho-so/<uuid:case_id>/giao-btv/",
        views.CaseAssignEditorView.as_view(),
        name="case_assign_editor",
    ),
    path(
        "ho-so/<uuid:case_id>/doi-nguoi-dai-dien/",
        views.CaseChangeOwnerView.as_view(),
        name="case_change_owner",
    ),
    path(
        "ho-so/<uuid:case_id>/tac-gia/them/",
        views.ContributorCreateView.as_view(),
        name="contributor_create",
    ),
    path(
        "ho-so/<uuid:case_id>/tac-gia/<int:pk>/sua/",
        views.ContributorUpdateView.as_view(),
        name="contributor_update",
    ),
    path(
        "ho-so/<uuid:case_id>/tac-gia/<int:pk>/xoa/",
        views.ContributorDeleteView.as_view(),
        name="contributor_delete",
    ),
    path(
        "ho-so/<uuid:case_id>/chuyen-trang-thai/",
        views.CaseTransitionView.as_view(),
        name="case_transition",
    ),
    path(
        "ho-so/<uuid:case_id>/duyet-mau-4/",
        views.CaseReviewView.as_view(),
        name="case_review",
    ),
    path(
        "ho-so/<uuid:case_id>/ghi-chu/them/",
        views.CaseNoteCreateView.as_view(),
        name="note_create",
    ),
    path(
        "ho-so/<uuid:case_id>/bo-sung/<int:pk>/da-bo-sung/",
        views.SupplementResolveView.as_view(),
        name="supplement_resolve",
    ),
]
