"""Test M3 — Danh sách, hàng đợi, chi tiết hồ sơ và các thao tác sửa của BTV."""

from __future__ import annotations

import datetime

import pytest
from django.forms.models import model_to_dict
from django.urls import reverse

from apps.accounts.models import UserRole
from apps.core.models import (
    AuditEvent,
    CaseNote,
    CaseStatus,
    Contributor,
    DocumentType,
    ManuscriptReview,
    NoteVisibility,
    PublicationCase,
    PublicationMode,
    ReviewResult,
    StatusHistory,
    SupplementRequest,
    SupplementStatus,
)
from tests.factories import (
    CategoryFactory,
    ContributorFactory,
    DocumentFactory,
    EditorFactory,
    PublicationCaseFactory,
    UserFactory,
)

VALID_ISBN = "9786043000009"  # số kiểm tra hợp lệ
OTHER_ISBN = "9780306406157"


# ---------------------------------------------------------------------------
# Hàm hỗ trợ (factory riêng của M3)
# ---------------------------------------------------------------------------


def make_case(status=CaseStatus.SUBMITTED, **kwargs) -> PublicationCase:
    """Tạo hồ sơ ở trạng thái bất kỳ (chỉ dùng trong test, ghi trạng thái lúc tạo mới)."""
    return PublicationCaseFactory(status=status, **kwargs)


def info_data(case: PublicationCase, **overrides) -> dict:
    """Dữ liệu POST đầy đủ cho form sửa thông tin hồ sơ từ giá trị hiện tại."""
    from apps.backoffice.forms import CaseInfoForm

    data = model_to_dict(case, fields=CaseInfoForm.Meta.fields)
    for key, value in list(data.items()):
        if value is None:
            data[key] = ""
        elif isinstance(value, datetime.date):
            data[key] = value.isoformat()
    if not data.get("is_reprint"):
        data.pop("is_reprint", None)
    data.update(overrides)
    return data


def detail_url(case, tab=None):
    url = reverse("backoffice:case_detail", args=[case.pk])
    return f"{url}?tab={tab}" if tab else url


def messages_of(response) -> list[str]:
    return [str(m) for m in response.context["messages"]] if response.context else []


@pytest.fixture
def editor(db):
    return EditorFactory(email="btv@ueh.edu.vn", full_name="Biên tập viên A")


@pytest.fixture
def editor_client(client, editor):
    client.force_login(editor)
    return client


# ---------------------------------------------------------------------------
# Phân quyền mọi URL M3
# ---------------------------------------------------------------------------


def all_m3_urls(case, contributor_pk=1, supplement_pk=1):
    args = [case.pk]
    return [
        ("get", reverse("backoffice:home")),
        ("get", reverse("backoffice:queue")),
        ("get", reverse("backoffice:case_detail", args=args)),
        ("post", reverse("backoffice:case_update", args=args)),
        ("post", reverse("backoffice:case_assign_editor", args=args)),
        ("post", reverse("backoffice:case_change_owner", args=args)),
        ("post", reverse("backoffice:contributor_create", args=args)),
        ("post", reverse("backoffice:contributor_update", args=[case.pk, contributor_pk])),
        ("post", reverse("backoffice:contributor_delete", args=[case.pk, contributor_pk])),
        ("post", reverse("backoffice:case_transition", args=args)),
        ("post", reverse("backoffice:case_review", args=args)),
        ("post", reverse("backoffice:note_create", args=args)),
        ("post", reverse("backoffice:supplement_resolve", args=[case.pk, supplement_pk])),
    ]


@pytest.mark.django_db
def test_anonymous_redirected_to_login(client):
    case = make_case()
    for method, url in all_m3_urls(case):
        response = getattr(client, method)(url)
        assert response.status_code == 302, url
        assert "/tai-khoan/dang-nhap/" in response["Location"], url


@pytest.mark.django_db
@pytest.mark.parametrize("role", [UserRole.CUSTOMER, UserRole.ADMIN])
def test_customer_and_admin_get_404(client, role):
    case = make_case()
    user = UserFactory(role=role)
    # Kể cả khách hàng là chủ hồ sơ cũng không vào được M3.
    owned = make_case(owner=user) if role == UserRole.CUSTOMER else case
    client.force_login(user)
    for target in (case, owned):
        for method, url in all_m3_urls(target):
            response = getattr(client, method)(url)
            assert response.status_code == 404, (role, url)
    assert not AuditEvent.objects.exists()


@pytest.mark.django_db
def test_inactive_editor_gets_404(client):
    editor = EditorFactory(is_active=False)
    client.force_login(editor)
    # Tài khoản bị khóa sẽ bị đăng xuất bởi middleware hoặc nhận 404.
    response = client.get(reverse("backoffice:home"))
    assert response.status_code in (302, 404)


@pytest.mark.django_db
def test_unknown_case_404(editor_client):
    import uuid

    response = editor_client.get(reverse("backoffice:case_detail", args=[uuid.uuid4()]))
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 2.1 Danh sách hồ sơ
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_hides_drafts_unless_explicit(editor_client):
    draft = make_case(status=CaseStatus.DRAFT, title="Sách nháp riêng")
    submitted = make_case(title="Sách đã nộp")
    response = editor_client.get(reverse("backoffice:home"))
    assert response.status_code == 200
    content = response.content.decode()
    assert submitted.title in content
    assert draft.title not in content

    response = editor_client.get(reverse("backoffice:home"), {"status": CaseStatus.DRAFT})
    content = response.content.decode()
    assert draft.title in content
    assert submitted.title not in content


@pytest.mark.django_db
def test_search_by_isbn_nxb_code_author_and_email(editor_client):
    by_isbn = make_case(status=CaseStatus.REGISTERED, title="Sách có ISBN", isbn=VALID_ISBN)
    by_nxb = make_case(status=CaseStatus.ACCEPTED, title="Sách có mã NXB", nxb_code="NXB-2026-0042")
    by_author = make_case(title="Sách tác giả đặc biệt")
    ContributorFactory(case=by_author, full_name="Trần Văn Độc Nhất")
    owner = UserFactory(email="nguoi.dai.dien@doitac.vn")
    by_email = make_case(title="Sách của đối tác", owner=owner)
    noise = make_case(title="Sách không liên quan")

    def search(q):
        response = editor_client.get(reverse("backoffice:home"), {"q": q})
        assert response.status_code == 200
        return response.content.decode()

    content = search("978-604-300-000-9")
    assert by_isbn.title in content and noise.title not in content
    content = search("NXB-2026-0042")
    assert by_nxb.title in content and noise.title not in content
    content = search("Độc Nhất")
    assert by_author.title in content and noise.title not in content
    content = search("nguoi.dai.dien@")
    assert by_email.title in content and noise.title not in content
    content = search(by_author.temp_code)
    assert by_author.title in content and noise.title not in content


@pytest.mark.django_db
def test_filter_unassigned_mine_mode_category(editor_client, editor):
    other = EditorFactory()
    category = CategoryFactory()
    unassigned = make_case(title="Hồ sơ chưa giao")
    mine = make_case(title="Hồ sơ của tôi", primary_editor=editor)
    theirs = make_case(
        title="Hồ sơ của BTV khác",
        primary_editor=other,
        publication_mode=PublicationMode.LINKED,
        partner_name="Đối tác X",
        category=category,
    )

    content = editor_client.get(reverse("backoffice:home"), {"editor": "none"}).content.decode()
    assert unassigned.title in content
    assert mine.title not in content and theirs.title not in content

    content = editor_client.get(reverse("backoffice:home"), {"mine": "on"}).content.decode()
    assert mine.title in content
    assert unassigned.title not in content and theirs.title not in content

    content = editor_client.get(
        reverse("backoffice:home"), {"editor": str(other.pk)}
    ).content.decode()
    assert theirs.title in content and mine.title not in content

    content = editor_client.get(
        reverse("backoffice:home"), {"mode": PublicationMode.LINKED}
    ).content.decode()
    assert theirs.title in content and mine.title not in content

    content = editor_client.get(
        reverse("backoffice:home"), {"category": category.pk}
    ).content.decode()
    assert theirs.title in content and unassigned.title not in content


@pytest.mark.django_db
def test_list_htmx_partial_and_pagination(editor_client):
    for i in range(30):
        make_case(title=f"Sách phân trang {i:02d}")
    response = editor_client.get(reverse("backoffice:home"), headers={"HX-Request": "true"})
    assert response.status_code == 200
    content = response.content.decode()
    assert "<html" not in content
    assert "Trang 1 / 2" in content
    assert len(response.context["cases"]) == 25

    response = editor_client.get(
        reverse("backoffice:home"), {"page": 2, "q": "phân trang"}, headers={"HX-Request": "true"}
    )
    assert len(response.context["cases"]) == 5
    assert "q=" in response.content.decode()


# ---------------------------------------------------------------------------
# 2.2 Hồ sơ cần xử lý
# ---------------------------------------------------------------------------


def _group(response, key):
    return next(g for g in response.context["groups"] if g["key"] == key)


@pytest.mark.django_db
def test_queue_groups(editor_client, editor):
    new = make_case(title="Hồ sơ mới nộp")

    resupplied = make_case(title="Hồ sơ đã bổ sung")
    StatusHistory.objects.create(
        case=resupplied,
        from_status=CaseStatus.SUBMITTED,
        to_status=CaseStatus.NEED_SUPPLEMENT,
        actor=editor,
    )
    SupplementRequest.objects.create(
        case=resupplied, requested_by=editor, message="Bổ sung Mẫu 2", status="RESOLVED"
    )

    accepted = make_case(status=CaseStatus.ACCEPTED, title="Hồ sơ đã tiếp nhận")

    revised = make_case(status=CaseStatus.REVISION_REQUIRED, title="Hồ sơ đã sửa bản thảo")
    ms1 = DocumentFactory(case=revised, doc_type=DocumentType.MANUSCRIPT, version=1)
    f4 = DocumentFactory(case=revised, doc_type=DocumentType.FORM_4, version=1)
    ManuscriptReview.objects.create(
        case=revised,
        manuscript=ms1,
        form4=f4,
        result=ReviewResult.REVISION_REQUIRED,
        confirmed_by=editor,
    )
    DocumentFactory(case=revised, doc_type=DocumentType.MANUSCRIPT, version=2)

    not_revised = make_case(status=CaseStatus.REVISION_REQUIRED, title="Hồ sơ chưa nộp lại")
    ms = DocumentFactory(case=not_revised, doc_type=DocumentType.MANUSCRIPT, version=1)
    f4b = DocumentFactory(case=not_revised, doc_type=DocumentType.FORM_4, version=1)
    ManuscriptReview.objects.create(
        case=not_revised,
        manuscript=ms,
        form4=f4b,
        result=ReviewResult.REVISION_REQUIRED,
        confirmed_by=editor,
    )

    approved = make_case(status=CaseStatus.REVIEW_APPROVED, primary_editor=editor)
    registered = make_case(status=CaseStatus.REGISTERED)
    decision = make_case(status=CaseStatus.DECISION_ISSUED)
    make_case(status=CaseStatus.DRAFT)

    response = editor_client.get(reverse("backoffice:queue"))
    assert response.status_code == 200
    assert [c.pk for c in _group(response, "new")["items"]] == [new.pk]
    assert [c.pk for c in _group(response, "resupplied")["items"]] == [resupplied.pk]
    assert [c.pk for c in _group(response, "accepted")["items"]] == [accepted.pk]
    assert [c.pk for c in _group(response, "revised")["items"]] == [revised.pk]
    assert _group(response, "approved")["count"] == 1
    assert [c.pk for c in _group(response, "approved")["items"]] == [approved.pk]
    assert [c.pk for c in _group(response, "registered")["items"]] == [registered.pk]
    assert [c.pk for c in _group(response, "decision")["items"]] == [decision.pk]

    response = editor_client.get(reverse("backoffice:queue"), {"mine": "1"})
    assert response.context["mine"] is True
    assert _group(response, "approved")["count"] == 1
    assert _group(response, "new")["count"] == 0


@pytest.mark.django_db
def test_queue_shows_link_to_full_list_when_many(editor_client):
    for _ in range(12):
        make_case()
    response = editor_client.get(reverse("backoffice:queue"))
    group = _group(response, "new")
    assert group["count"] == 12
    assert len(group["items"]) == 10
    assert "Xem tất cả 12 hồ sơ" in response.content.decode()


# ---------------------------------------------------------------------------
# 2.3 Chi tiết — Tổng quan
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_detail_renders_all_tabs(editor_client, editor):
    owner = UserFactory(full_name="Nguyễn Đại Diện", phone="0909000111", organization="Công ty Y")
    case = make_case(owner=owner)
    ContributorFactory(case=case, full_name="Tác giả Hiển Thị")
    doc = DocumentFactory(case=case, doc_type=DocumentType.MANUSCRIPT, note="Bản gốc")
    CaseNote.objects.create(case=case, author=editor, body="Ghi chú nội bộ X")
    for tab in ("overview", "contributors", "documents", "workflow", "notes", "khac"):
        response = editor_client.get(detail_url(case, tab))
        assert response.status_code == 200
    content = response.content.decode()
    assert response.context["tab"] == "overview"
    assert "Nguyễn Đại Diện" in content and "0909000111" in content and "Công ty Y" in content
    assert "Tác giả Hiển Thị" in content
    assert reverse("core:document_download", args=[doc.pk]) in content
    assert "Bản gốc" in content
    assert "ueh-chunked-upload" in content
    assert 'href="/bieu-mau/"' in content
    assert "thư mục chung của NXB" in content
    assert "Ghi chú nội bộ X" in content
    assert 'id="case-info-form"' in content


@pytest.mark.django_db
def test_accept_issues_nxb_code_then_isbn_shown(editor_client):
    case = make_case()
    response = editor_client.post(
        reverse("backoffice:case_transition", args=[case.pk]),
        {"to_status": CaseStatus.ACCEPTED, "note": ""},
        follow=True,
    )
    case.refresh_from_db()
    assert case.status == CaseStatus.ACCEPTED
    assert case.nxb_code and case.nxb_code.startswith("NXB-")
    assert case.nxb_code in response.content.decode()

    response = editor_client.post(
        reverse("backoffice:case_update", args=[case.pk]),
        info_data(case, isbn="978-604-300-000-9"),
        follow=True,
    )
    case.refresh_from_db()
    assert case.isbn == VALID_ISBN
    content = response.content.decode()
    assert VALID_ISBN in content
    assert case.nxb_code in content
    assert "Đã lưu thông tin hồ sơ." in messages_of(response)
    event = AuditEvent.objects.get(action="case.update", case=case)
    assert event.data["before"] == {"isbn": None}
    assert event.data["after"] == {"isbn": VALID_ISBN}


@pytest.mark.django_db
def test_isbn_validation_messages(editor_client):
    make_case(isbn=OTHER_ISBN)
    case = make_case()
    url = reverse("backoffice:case_update", args=[case.pk])

    response = editor_client.post(url, info_data(case, isbn="9786043000004"))
    assert response.status_code == 200
    assert "Số kiểm tra của ISBN-13 không hợp lệ." in response.content.decode()

    response = editor_client.post(url, info_data(case, isbn="0306406152"))
    assert "Vui lòng nhập ISBN-13" in response.content.decode()

    response = editor_client.post(url, info_data(case, isbn=OTHER_ISBN))
    assert "Mã ISBN này đã được dùng cho một hồ sơ khác." in response.content.decode()

    case.refresh_from_db()
    assert case.isbn is None
    assert not AuditEvent.objects.filter(action="case.update").exists()


@pytest.mark.django_db
def test_update_linked_requires_partner(editor_client):
    case = make_case()
    response = editor_client.post(
        reverse("backoffice:case_update", args=[case.pk]),
        info_data(case, publication_mode=PublicationMode.LINKED, partner_name=""),
    )
    assert response.status_code == 200
    assert "Bắt buộc nhập tên đơn vị liên kết" in response.content.decode()
    case.refresh_from_db()
    assert case.publication_mode == PublicationMode.SELF


@pytest.mark.django_db
def test_update_without_changes_logs_nothing(editor_client):
    case = make_case()
    response = editor_client.post(
        reverse("backoffice:case_update", args=[case.pk]), info_data(case)
    )
    assert response.status_code == 302
    assert not AuditEvent.objects.filter(action="case.update").exists()


@pytest.mark.django_db
def test_completed_case_is_readonly(editor_client, editor):
    case = make_case(status=CaseStatus.COMPLETED, title="Sách đã hoàn tất")
    contributor = ContributorFactory(case=case)
    response = editor_client.get(detail_url(case))
    content = response.content.decode()
    assert 'id="case-info-form"' not in content
    assert 'id="assign-editor-form"' not in content
    assert 'id="change-owner-form"' not in content
    assert 'id="contributor-create-form"' not in content
    assert "chỉ xem, không sửa thông tin" in content

    customer = UserFactory()
    posts = [
        (reverse("backoffice:case_update", args=[case.pk]), info_data(case, title="Tên mới")),
        (reverse("backoffice:case_assign_editor", args=[case.pk]), {"primary_editor": editor.pk}),
        (
            reverse("backoffice:case_change_owner", args=[case.pk]),
            {"email": customer.email, "reason": "Đổi"},
        ),
        (
            reverse("backoffice:contributor_create", args=[case.pk]),
            {"new-full_name": "X", "new-role": "AUTHOR", "new-order": 2},
        ),
        (
            reverse("backoffice:contributor_update", args=[case.pk, contributor.pk]),
            {f"c{contributor.pk}-full_name": "Y", f"c{contributor.pk}-role": "AUTHOR"},
        ),
        (reverse("backoffice:contributor_delete", args=[case.pk, contributor.pk]), {}),
    ]
    for url, data in posts:
        response = editor_client.post(url, data, follow=True)
        assert "Hồ sơ đã hoàn tất hoặc lưu trữ, không thể sửa thông tin." in messages_of(
            response
        ), url
    case.refresh_from_db()
    assert case.title == "Sách đã hoàn tất"
    assert case.primary_editor is None
    assert case.owner != customer
    assert Contributor.objects.filter(case=case).count() == 1
    assert not AuditEvent.objects.exists()


@pytest.mark.django_db
def test_assign_editor_only_active_editors(editor_client, editor):
    case = make_case()
    other = EditorFactory(full_name="BTV Hai")
    inactive = EditorFactory(is_active=False)
    url = reverse("backoffice:case_assign_editor", args=[case.pk])

    response = editor_client.post(url, {"primary_editor": inactive.pk})
    assert response.status_code == 200
    case.refresh_from_db()
    assert case.primary_editor is None

    customer = UserFactory()
    editor_client.post(url, {"primary_editor": customer.pk})
    case.refresh_from_db()
    assert case.primary_editor is None

    response = editor_client.post(url, {"primary_editor": other.pk})
    assert response.status_code == 302
    case.refresh_from_db()
    assert case.primary_editor == other
    event = AuditEvent.objects.get(action="case.assign_editor")
    assert event.data["before"]["primary_editor_id"] is None
    assert event.data["after"]["primary_editor_id"] == other.pk

    # Gán lại cùng người: không ghi thêm nhật ký; bỏ giao: ghi nhật ký.
    editor_client.post(url, {"primary_editor": other.pk})
    assert AuditEvent.objects.filter(action="case.assign_editor").count() == 1
    editor_client.post(url, {"primary_editor": ""})
    case.refresh_from_db()
    assert case.primary_editor is None
    assert AuditEvent.objects.filter(action="case.assign_editor").count() == 2


@pytest.mark.django_db
def test_change_owner_requires_reason_and_customer(editor_client, editor):
    case = make_case()
    old_owner = case.owner
    new_owner = UserFactory(email="chu.moi@example.com")
    url = reverse("backoffice:case_change_owner", args=[case.pk])

    response = editor_client.post(url, {"email": new_owner.email, "reason": "  "})
    assert response.status_code == 200
    assert "Bắt buộc nhập lý do khi đổi người đại diện." in response.content.decode()
    case.refresh_from_db()
    assert case.owner == old_owner

    response = editor_client.post(url, {"email": editor.email, "reason": "Chuyển"})
    assert "Không tìm thấy tài khoản khách hàng" in response.content.decode()

    response = editor_client.post(url, {"email": "CHU.MOI@example.com", "reason": "Đổi đại diện"})
    assert response.status_code == 302
    case.refresh_from_db()
    assert case.owner == new_owner
    event = AuditEvent.objects.get(action="case.owner_change")
    assert event.actor == editor
    assert event.data["before"]["owner_id"] == old_owner.pk
    assert event.data["after"]["owner_id"] == new_owner.pk
    assert event.data["note"] == "Đổi đại diện"


@pytest.mark.django_db
def test_change_owner_workflow_error_shown(editor_client, monkeypatch):
    from apps.backoffice import views
    from apps.core.workflow import WorkflowError

    def boom(*args, **kwargs):
        raise WorkflowError("Lỗi giả lập")

    monkeypatch.setattr(views, "change_case_owner", boom)
    case = make_case()
    new_owner = UserFactory()
    response = editor_client.post(
        reverse("backoffice:case_change_owner", args=[case.pk]),
        {"email": new_owner.email, "reason": "Đổi"},
    )
    assert response.status_code == 200
    assert "Lỗi giả lập" in response.content.decode()


# ---------------------------------------------------------------------------
# Tab Tác giả
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_contributor_crud_with_audit(editor_client):
    case = make_case()
    response = editor_client.post(
        reverse("backoffice:contributor_create", args=[case.pk]),
        {"new-full_name": "", "new-role": "AUTHOR", "new-order": 1},
    )
    assert response.status_code == 200
    assert response.context["tab"] == "contributors"
    assert not case.contributors.exists()

    response = editor_client.post(
        reverse("backoffice:contributor_create", args=[case.pk]),
        {
            "new-full_name": "PGS.TS Lê Văn A",
            "new-role": "AUTHOR",
            "new-order": 1,
            "new-email": "a@ueh.edu.vn",
        },
    )
    assert response.status_code == 302
    contributor = case.contributors.get()
    assert AuditEvent.objects.get(action="contributor.add").data["after"]["full_name"] == (
        "PGS.TS Lê Văn A"
    )

    prefix = f"c{contributor.pk}"
    response = editor_client.post(
        reverse("backoffice:contributor_update", args=[case.pk, contributor.pk]),
        {f"{prefix}-full_name": "", f"{prefix}-role": "AUTHOR", f"{prefix}-order": 1},
    )
    assert response.status_code == 200
    response = editor_client.post(
        reverse("backoffice:contributor_update", args=[case.pk, contributor.pk]),
        {f"{prefix}-full_name": "Lê Văn B", f"{prefix}-role": "CO_AUTHOR", f"{prefix}-order": 2},
    )
    assert response.status_code == 302
    contributor.refresh_from_db()
    assert contributor.full_name == "Lê Văn B"
    event = AuditEvent.objects.get(action="contributor.update")
    assert event.data["before"]["full_name"] == "PGS.TS Lê Văn A"
    assert event.data["after"]["full_name"] == "Lê Văn B"

    # Tác giả của hồ sơ khác -> 404
    other = ContributorFactory()
    response = editor_client.post(
        reverse("backoffice:contributor_delete", args=[case.pk, other.pk])
    )
    assert response.status_code == 404

    response = editor_client.post(
        reverse("backoffice:contributor_delete", args=[case.pk, contributor.pk])
    )
    assert response.status_code == 302
    assert not case.contributors.exists()
    assert AuditEvent.objects.get(action="contributor.delete").data["before"]["full_name"] == (
        "Lê Văn B"
    )


# ---------------------------------------------------------------------------
# Tab Ghi chú & trao đổi
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_note_defaults_internal_and_logged(editor_client, editor):
    case = make_case()
    url = reverse("backoffice:note_create", args=[case.pk])
    response = editor_client.get(detail_url(case, "notes"))
    assert response.context["note_form"]["visibility"].value() == NoteVisibility.INTERNAL

    response = editor_client.post(url, {"body": "Ghi chú không chọn phạm vi"})
    assert response.status_code == 302
    note = CaseNote.objects.get(case=case)
    assert note.visibility == NoteVisibility.INTERNAL
    assert note.author == editor
    event = AuditEvent.objects.get(action="case.note_add")
    assert event.object_id == str(note.pk)
    assert event.data == {"visibility": NoteVisibility.INTERNAL}

    editor_client.post(url, {"body": "Gửi khách", "visibility": NoteVisibility.CUSTOMER})
    assert CaseNote.objects.filter(case=case, visibility=NoteVisibility.CUSTOMER).count() == 1

    response = editor_client.post(url, {"body": ""})
    assert response.status_code == 200
    assert CaseNote.objects.filter(case=case).count() == 2

    content = editor_client.get(detail_url(case, "notes")).content.decode()
    assert "Nội bộ" in content and "Gửi khách hàng" in content


@pytest.mark.django_db
def test_supplement_resolve_manually(editor_client, editor):
    case = make_case(status=CaseStatus.NEED_SUPPLEMENT)
    sr = SupplementRequest.objects.create(case=case, requested_by=editor, message="Thiếu Mẫu 3")
    url = reverse("backoffice:supplement_resolve", args=[case.pk, sr.pk])
    response = editor_client.post(url)
    assert response.status_code == 302
    sr.refresh_from_db()
    assert sr.status == SupplementStatus.RESOLVED
    assert sr.resolved_at is not None
    assert AuditEvent.objects.filter(action="supplement.resolve", case=case).count() == 1

    response = editor_client.post(url, follow=True)
    assert "Yêu cầu bổ sung này đã được đánh dấu hoàn tất." in messages_of(response)
    assert AuditEvent.objects.filter(action="supplement.resolve").count() == 1


# ---------------------------------------------------------------------------
# Tài chính
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_finance_button_visibility(client, editor_none, editor_view, editor_manage):
    case = make_case()
    finance_url = f"/tai-chinh/ho-so/{case.pk}/"

    client.force_login(editor_none)
    content = client.get(detail_url(case)).content.decode()
    assert finance_url not in content
    assert "Xem tài chính hồ sơ" not in content

    for user in (editor_view, editor_manage):
        client.force_login(user)
        content = client.get(detail_url(case)).content.decode()
        assert finance_url in content
        assert "Xem tài chính hồ sơ" in content
