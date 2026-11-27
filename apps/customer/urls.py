"""Module M2 — Cổng khách hàng."""

from django.urls import path

from apps.customer import views

app_name = "customer"

urlpatterns = [
    path("", views.CustomerHomeView.as_view(), name="home"),
    path("tao-moi/", views.CustomerNewCaseView.as_view(), name="case_create"),
    path("tai-khoan/", views.CustomerProfileView.as_view(), name="profile"),
    path("ho-so/<uuid:case_id>/", views.CustomerCaseDetailView.as_view(), name="case_detail"),
    path("ho-so/<uuid:case_id>/sua/", views.CustomerCaseEditView.as_view(), name="case_edit"),
    path("ho-so/<uuid:case_id>/nop/", views.CustomerCaseSubmitView.as_view(), name="case_submit"),
    path("ho-so/<uuid:case_id>/trao-doi/", views.CustomerNoteAddView.as_view(), name="note_add"),
    path(
        "ho-so/<uuid:case_id>/tac-gia/them/",
        views.ContributorFormView.as_view(),
        name="contributor_add",
    ),
    path(
        "ho-so/<uuid:case_id>/tac-gia/<int:contributor_id>/sua/",
        views.ContributorFormView.as_view(),
        name="contributor_edit",
    ),
    path(
        "ho-so/<uuid:case_id>/tac-gia/<int:contributor_id>/xoa/",
        views.ContributorRemoveView.as_view(),
        name="contributor_remove",
    ),
]
