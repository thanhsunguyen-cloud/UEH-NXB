"""M2 — Danh sách, tạo, sửa hồ sơ và tác giả."""

import pytest
from django.urls import reverse

from apps.core.models import (
    AuditEvent,
    CaseStatus,
    Contributor,
    ContributorRole,
    PublicationCase,
    PublicationMode,
)
from apps.customer.labels import (
    CUSTOMER_STATUS_LABELS,
    customer_status_badge,
    customer_status_choices,
    customer_status_label,
    customer_todo,
)
from tests.factories import (
    CategoryFactory,
    ContributorFactory,
    FieldFactory,
    PublicationCaseFactory,
)


def _case_payload(**overrides):
    data = {
        "title": "Kinh tế học vĩ mô",
        "subtitle": "",
        "category": "",
        "field": "",
        "language": "Tiếng Việt",
        "translated_from": "",
        "edition_number": "1",
        "publication_mode": PublicationMode.SELF,
        "partner_name": "",
        "summary": "Tóm tắt",
        "page_count": "250",
        "book_size": "16x24",
    }
    data.update(overrides)
    return data


# --- Nhãn ---------------------------------------------------------------


def test_labels_cover_all_statuses():
    assert set(CUSTOMER_STATUS_LABELS) == set(CaseStatus.values)
    assert customer_status_label(CaseStatus.SUBMITTED) == "Đã nộp – chờ NXB tiếp nhận"
    assert customer_status_label("UNKNOWN") == "UNKNOWN"
    assert customer_status_badge("UNKNOWN") == "secondary"
    assert customer_todo(CaseStatus.DRAFT) == "Hoàn thiện và nộp hồ sơ"
    assert customer_todo(CaseStatus.EDITING) == ""
    assert len(customer_status_choices()) == 13


# --- Danh sách ----------------------------------------------------------


@pytest.mark.django_db
def test_home_lists_own_cases_with_labels_and_todo(client, customer_a):
    PublicationCaseFactory(owner=customer_a, title="Sách nháp")
    client.force_login(customer_a)
    response = client.get(reverse("customer:home"))
    html = response.content.decode()
    assert response.status_code == 200
    assert "Sách nháp" in html
    assert "Đang soạn hồ sơ" in html
    assert "Hoàn thiện và nộp hồ sơ" in html


@pytest.mark.django_db
def test_home_filter_and_search(client, customer_a):
    a = PublicationCaseFactory(owner=customer_a, title="Quản trị chiến lược")
    PublicationCaseFactory(owner=customer_a, title="Tài chính doanh nghiệp")
    client.force_login(customer_a)

    response = client.get(reverse("customer:home"), {"q": "chiến lược"})
    titles = [c.title for c in response.context["cases"]]
    assert titles == ["Quản trị chiến lược"]

    response = client.get(reverse("customer:home"), {"q": a.temp_code})
    assert [c.pk for c in response.context["cases"]] == [a.pk]

    response = client.get(reverse("customer:home"), {"status": CaseStatus.SUBMITTED})
    assert list(response.context["cases"]) == []

    response = client.get(reverse("customer:home"), {"status": "BOGUS"})
    assert len(response.context["cases"]) == 2


@pytest.mark.django_db
def test_home_paginates_20(client, customer_a):
    PublicationCaseFactory.create_batch(21, owner=customer_a)
    client.force_login(customer_a)
    response = client.get(reverse("customer:home"))
    assert len(response.context["cases"]) == 20
    assert response.context["is_paginated"]
    response = client.get(reverse("customer:home"), {"page": 2})
    assert len(response.context["cases"]) == 1


# --- Tạo hồ sơ ----------------------------------------------------------


@pytest.mark.django_db
def test_create_case_get_form(client, customer_a):
    client.force_login(customer_a)
    response = client.get(reverse("customer:case_create"))
    assert response.status_code == 200
    assert 'name="title"' in response.content.decode()
    assert 'name="isbn"' not in response.content.decode()


@pytest.mark.django_db
def test_create_case_sets_owner_draft_and_audit(client, customer_a):
    category = CategoryFactory()
    field = FieldFactory()
    client.force_login(customer_a)
    response = client.post(
        reverse("customer:case_create"),
        _case_payload(category=category.pk, field=field.pk),
    )
    case = PublicationCase.objects.get(title="Kinh tế học vĩ mô")
    assert response.status_code == 302
    assert response["Location"] == reverse("customer:case_detail", args=[case.pk])
    assert case.owner == customer_a
    assert case.status == CaseStatus.DRAFT
    assert case.category == category
    assert AuditEvent.objects.filter(action="case.create", case=case, actor=customer_a).exists()


@pytest.mark.django_db
def test_create_case_ignores_restricted_fields(client, customer_a, editor_none):
    client.force_login(customer_a)
    client.post(
        reverse("customer:case_create"),
        _case_payload(
            isbn="9786043640000",
            nxb_code="NXB-HACK",
            registration_number="123",
            decision_number="456",
            contract_number="789",
            primary_editor=editor_none.pk,
            status=CaseStatus.COMPLETED,
            owner=editor_none.pk,
        ),
    )
    case = PublicationCase.objects.get(title="Kinh tế học vĩ mô")
    assert case.isbn is None
    assert case.nxb_code is None
    assert case.registration_number == ""
    assert case.decision_number == ""
    assert case.contract_number == ""
    assert case.primary_editor is None
    assert case.status == CaseStatus.DRAFT
    assert case.owner == customer_a


@pytest.mark.django_db
def test_create_linked_case_without_partner_rejected(client, customer_a):
    client.force_login(customer_a)
    response = client.post(
        reverse("customer:case_create"),
        _case_payload(publication_mode=PublicationMode.LINKED, partner_name="  "),
    )
    assert response.status_code == 200
    assert response.context["form"].errors["partner_name"]
    assert not PublicationCase.objects.exists()


@pytest.mark.django_db
def test_create_linked_case_with_partner_ok(client, customer_a):
    client.force_login(customer_a)
    client.post(
        reverse("customer:case_create"),
        _case_payload(publication_mode=PublicationMode.LINKED, partner_name="Công ty ABC"),
    )
    case = PublicationCase.objects.get()
    assert case.partner_name == "Công ty ABC"


@pytest.mark.django_db
def test_create_case_requires_title(client, customer_a):
    client.force_login(customer_a)
    response = client.post(reverse("customer:case_create"), _case_payload(title=""))
    assert response.status_code == 200
    assert "title" in response.context["form"].errors
    assert "is-invalid" in response.content.decode()


# --- Sửa thông tin ------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("status", [CaseStatus.DRAFT, CaseStatus.NEED_SUPPLEMENT])
def test_edit_case_allowed_and_audited(client, customer_a, status):
    case = PublicationCaseFactory(owner=customer_a, status=status, title="Tên cũ")
    client.force_login(customer_a)
    assert client.get(reverse("customer:case_edit", args=[case.pk])).status_code == 200
    response = client.post(
        reverse("customer:case_edit", args=[case.pk]), _case_payload(title="Tên mới")
    )
    assert response.status_code == 302
    case.refresh_from_db()
    assert case.title == "Tên mới"
    event = AuditEvent.objects.get(action="case.update", case=case)
    assert event.data["before"]["title"] == "Tên cũ"
    assert event.data["after"]["title"] == "Tên mới"


@pytest.mark.django_db
def test_edit_case_invalid_rerenders(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)
    response = client.post(
        reverse("customer:case_edit", args=[case.pk]),
        _case_payload(publication_mode=PublicationMode.LINKED),
    )
    assert response.status_code == 200
    assert "partner_name" in response.context["form"].errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status", [CaseStatus.SUBMITTED, CaseStatus.EDITING, CaseStatus.REVISION_REQUIRED]
)
def test_edit_case_blocked_when_not_editable(client, customer_a, status):
    case = PublicationCaseFactory(owner=customer_a, status=status, title="Tên cũ")
    client.force_login(customer_a)
    detail = reverse("customer:case_detail", args=[case.pk])
    response = client.get(reverse("customer:case_edit", args=[case.pk]))
    assert response.status_code == 302 and response["Location"] == detail
    response = client.post(
        reverse("customer:case_edit", args=[case.pk]), _case_payload(title="Tên mới")
    )
    assert response.status_code == 302
    case.refresh_from_db()
    assert case.title == "Tên cũ"
    assert not AuditEvent.objects.filter(action="case.update").exists()
    html = client.get(detail).content.decode()
    assert reverse("customer:case_edit", args=[case.pk]) not in html


# --- Tác giả ------------------------------------------------------------


def _contributor_payload(**overrides):
    data = {
        "full_name": "Nguyễn Văn A",
        "academic_title": "TS.",
        "role": ContributorRole.AUTHOR,
        "affiliation": "UEH",
        "email": "a@example.com",
        "phone": "0900000000",
        "order": "1",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_contributor_add_update_remove(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)

    response = client.get(reverse("customer:contributor_add", args=[case.pk]))
    assert response.status_code == 200
    assert "Chỉ người đại diện có tài khoản" in response.content.decode()

    client.post(reverse("customer:contributor_add", args=[case.pk]), _contributor_payload())
    contributor = Contributor.objects.get(case=case)
    assert AuditEvent.objects.filter(action="case.contributor_add", case=case).exists()

    url = reverse("customer:contributor_edit", args=[case.pk, contributor.pk])
    assert client.get(url).status_code == 200
    client.post(url, _contributor_payload(full_name="Nguyễn Văn B"))
    contributor.refresh_from_db()
    assert contributor.full_name == "Nguyễn Văn B"
    event = AuditEvent.objects.get(action="case.contributor_update")
    assert event.data["before"]["full_name"] == "Nguyễn Văn A"

    client.post(reverse("customer:contributor_remove", args=[case.pk, contributor.pk]))
    assert not Contributor.objects.filter(case=case).exists()
    assert AuditEvent.objects.filter(action="case.contributor_remove", case=case).exists()


@pytest.mark.django_db
def test_contributor_invalid_form(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a)
    client.force_login(customer_a)
    response = client.post(
        reverse("customer:contributor_add", args=[case.pk]),
        _contributor_payload(full_name="", email="sai-email"),
    )
    assert response.status_code == 200
    assert "full_name" in response.context["form"].errors
    assert "email" in response.context["form"].errors


@pytest.mark.django_db
def test_contributor_changes_blocked_when_submitted(client, customer_a):
    case = PublicationCaseFactory(owner=customer_a, status=CaseStatus.SUBMITTED)
    contributor = ContributorFactory(case=case, full_name="Giữ nguyên")
    client.force_login(customer_a)

    response = client.get(reverse("customer:contributor_add", args=[case.pk]))
    assert response.status_code == 302
    client.post(reverse("customer:contributor_add", args=[case.pk]), _contributor_payload())
    client.post(
        reverse("customer:contributor_edit", args=[case.pk, contributor.pk]),
        _contributor_payload(full_name="Đã đổi"),
    )
    client.post(reverse("customer:contributor_remove", args=[case.pk, contributor.pk]))

    assert list(Contributor.objects.filter(case=case)) == [contributor]
    contributor.refresh_from_db()
    assert contributor.full_name == "Giữ nguyên"
    assert not AuditEvent.objects.filter(action__startswith="case.contributor").exists()
