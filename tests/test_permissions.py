"""Nhóm test 1: Phân quyền toàn diện và cô lập dữ liệu (mục 6 & mục 12.1)."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from apps.core.models import CaseNote, CaseStatus, DocumentType, NoteVisibility
from apps.core.permissions import (
    CUSTOMER_EDITABLE_STATUSES,
    CUSTOMER_UPLOADABLE_DOC_TYPES,
    CUSTOMER_UPLOADABLE_STATUSES,
    EDITOR_READONLY_STATUSES,
    can_change_status,
    can_download,
    can_edit_case_info,
    can_manage_finance,
    can_manage_system,
    can_upload,
    can_view_case,
    can_view_finance,
    can_view_note,
    can_view_publication_stats,
    cases_visible_to,
)
from tests.factories import DocumentFactory, PublicationCaseFactory


@pytest.mark.django_db
def test_customer_isolation_and_404(client, customer_a, customer_b):
    case_b = PublicationCaseFactory(owner=customer_b)
    doc_b = DocumentFactory(case=case_b, doc_type=DocumentType.MANUSCRIPT, uploaded_by=customer_b)

    assert not can_view_case(customer_a, case_b)
    assert not can_edit_case_info(customer_a, case_b)
    assert not can_upload(customer_a, case_b, DocumentType.MANUSCRIPT)
    assert not can_download(customer_a, doc_b)
    assert case_b not in cases_visible_to(customer_a)

    client.force_login(customer_a)
    assert client.get(reverse("customer:case_detail", args=[case_b.pk])).status_code == 404
    assert client.get(reverse("core:document_download", args=[doc_b.pk])).status_code == 404


@pytest.mark.django_db
def test_customer_cannot_download_form4_or_see_internal_note(customer_a, editor_none, admin_user):
    case_a = PublicationCaseFactory(owner=customer_a)
    doc_form4 = DocumentFactory(case=case_a, doc_type=DocumentType.FORM_4, uploaded_by=editor_none)
    doc_ms = DocumentFactory(case=case_a, doc_type=DocumentType.MANUSCRIPT, uploaded_by=customer_a)
    internal_note = CaseNote.objects.create(
        case=case_a,
        author=editor_none,
        body="Ghi chú nội bộ mật",
        visibility=NoteVisibility.INTERNAL,
    )
    customer_note = CaseNote.objects.create(
        case=case_a,
        author=editor_none,
        body="Trao đổi công khai với tác giả",
        visibility=NoteVisibility.CUSTOMER,
    )

    assert not can_download(customer_a, doc_form4)
    assert can_download(customer_a, doc_ms)
    assert can_download(editor_none, doc_form4)
    assert not can_download(admin_user, doc_ms)
    assert not can_download(AnonymousUser(), doc_ms)
    assert not can_download(customer_a, None)

    assert not can_view_note(customer_a, internal_note)
    assert can_view_note(customer_a, customer_note)
    assert can_view_note(editor_none, internal_note)
    assert not can_view_note(admin_user, customer_note)
    assert not can_view_note(AnonymousUser(), customer_note)
    assert not can_view_note(customer_a, None)


@pytest.mark.django_db
def test_admin_cannot_view_cases_and_editor_sees_all(
    client,
    admin_user,
    editor_none,
    customer_a,
    customer_b,
):
    case_a = PublicationCaseFactory(owner=customer_a)
    case_b = PublicationCaseFactory(owner=customer_b)

    assert cases_visible_to(AnonymousUser()).count() == 0
    assert cases_visible_to(admin_user).count() == 0
    assert not can_view_case(admin_user, case_a)
    assert not can_view_case(AnonymousUser(), case_a)
    assert not can_view_case(customer_a, None)
    assert cases_visible_to(editor_none).count() == 2
    assert can_view_case(editor_none, case_a)
    assert can_view_case(editor_none, case_b)
    assert can_view_case(customer_a, case_a)

    client.force_login(admin_user)
    assert client.get(reverse("backoffice:case_detail", args=[case_a.pk])).status_code == 404
    assert client.get(reverse("customer:case_detail", args=[case_a.pk])).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("status", list(CaseStatus.values))
def test_can_edit_case_info_by_role_and_status(
    status, customer_a, customer_b, editor_none, admin_user
):
    case = PublicationCaseFactory(owner=customer_a, status=status)

    assert can_edit_case_info(customer_a, case) is (status in CUSTOMER_EDITABLE_STATUSES)
    assert can_edit_case_info(customer_b, case) is False
    assert can_edit_case_info(editor_none, case) is (status not in EDITOR_READONLY_STATUSES)
    assert can_edit_case_info(admin_user, case) is False
    assert can_edit_case_info(AnonymousUser(), case) is False
    assert can_edit_case_info(editor_none, None) is False


@pytest.mark.django_db
@pytest.mark.parametrize("status", list(CaseStatus.values))
@pytest.mark.parametrize(
    "doc_type",
    [DocumentType.MANUSCRIPT, DocumentType.FORM_1, DocumentType.FORM_4, DocumentType.FORM_9],
)
def test_can_upload_by_role_status_and_doc_type(
    status,
    doc_type,
    customer_a,
    customer_b,
    editor_none,
    admin_user,
):
    case = PublicationCaseFactory(owner=customer_a, status=status)

    expected_customer = (
        status in CUSTOMER_UPLOADABLE_STATUSES and doc_type in CUSTOMER_UPLOADABLE_DOC_TYPES
    )
    assert can_upload(customer_a, case, doc_type) is expected_customer
    assert can_upload(customer_b, case, doc_type) is False
    assert can_upload(editor_none, case, doc_type) is True
    assert can_upload(admin_user, case, doc_type) is False
    assert can_upload(AnonymousUser(), case, doc_type) is False
    assert can_upload(editor_none, case, "INVALID_DOC_TYPE") is False
    assert can_upload(editor_none, None, doc_type) is False


@pytest.mark.django_db
def test_finance_system_stats_and_status_change_permissions(
    customer_a,
    customer_b,
    editor_none,
    editor_view,
    editor_manage,
    admin_user,
):
    anon = AnonymousUser()

    # Quản trị hệ thống: chỉ ADMIN
    assert can_manage_system(admin_user) is True
    assert can_manage_system(editor_manage) is False
    assert can_manage_system(customer_a) is False
    assert can_manage_system(anon) is False

    # Thống kê danh mục xuất bản: chỉ EDITOR
    assert can_view_publication_stats(editor_none) is True
    assert can_view_publication_stats(editor_view) is True
    assert can_view_publication_stats(admin_user) is False
    assert can_view_publication_stats(customer_a) is False
    assert can_view_publication_stats(anon) is False

    # Xem tài chính: EDITOR có VIEW hoặc MANAGE
    assert can_view_finance(editor_none) is False
    assert can_view_finance(editor_view) is True
    assert can_view_finance(editor_manage) is True
    assert can_view_finance(admin_user) is False
    assert can_view_finance(customer_a) is False
    assert can_view_finance(anon) is False

    # Quản lý tài chính: chỉ EDITOR có MANAGE
    assert can_manage_finance(editor_none) is False
    assert can_manage_finance(editor_view) is False
    assert can_manage_finance(editor_manage) is True
    assert can_manage_finance(admin_user) is False
    assert can_manage_finance(customer_a) is False
    assert can_manage_finance(anon) is False

    # can_change_status cho từng vai trò và trường hợp biên
    case_draft = PublicationCaseFactory(owner=customer_a, status=CaseStatus.DRAFT)
    case_submitted = PublicationCaseFactory(owner=customer_a, status=CaseStatus.SUBMITTED)
    assert can_change_status(customer_a, case_draft, CaseStatus.SUBMITTED) is True
    assert can_change_status(customer_b, case_draft, CaseStatus.SUBMITTED) is False
    assert can_change_status(editor_none, case_draft, CaseStatus.SUBMITTED) is False
    assert can_change_status(editor_none, case_submitted, CaseStatus.ACCEPTED) is True
    assert can_change_status(admin_user, case_submitted, CaseStatus.ACCEPTED) is False
    assert can_change_status(anon, case_draft, CaseStatus.SUBMITTED) is False
    assert can_change_status(customer_a, None, CaseStatus.SUBMITTED) is False
    assert can_change_status(editor_none, case_draft, CaseStatus.ARCHIVED) is False

    # Tài khoản bị khóa (is_active = False) bị từ chối mọi quyền
    editor_manage.is_active = False
    editor_manage.save()
    assert can_view_finance(editor_manage) is False
    assert can_manage_finance(editor_manage) is False
    assert can_view_case(editor_manage, case_draft) is False
