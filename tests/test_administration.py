"""Test M7 — Quản trị hệ thống (người dùng, danh mục, biểu mẫu, nhật ký)."""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import FinanceAccess, User, UserRole
from apps.administration import services
from apps.core.audit import log_event
from apps.core.models import AuditEvent, Category, FeeType, Field, FormTemplate
from apps.core.storage import LocalFileStorage, StoredFile, sanitize_filename
from tests.factories import (
    AdminFactory,
    CategoryFactory,
    EditorFactory,
    PublicationCaseFactory,
    UserFactory,
)

# ---------------------------------------------------------------------------
# Bản giả `save_library_file` (CR-001) — thay bằng bản thật khi CR-001 vào main
# ---------------------------------------------------------------------------


class FakeLibraryStorage(LocalFileStorage):
    LIBRARY_CATEGORIES = {"form_templates", "public_media"}

    def __init__(self, media_root):
        super().__init__(media_root)
        self.saved: list[dict] = []

    def save_library_file(self, category, filename, fileobj, size, mime_type) -> StoredFile:
        assert category in self.LIBRARY_CATEGORIES
        rel = Path("library") / category / f"{uuid.uuid4().hex}_{sanitize_filename(filename)}"
        dest = self.media_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = b"".join(fileobj.chunks()) if hasattr(fileobj, "chunks") else fileobj.read()
        dest.write_bytes(data)
        self.saved.append({"category": category, "filename": filename, "size": size})
        return StoredFile(
            storage_ref=rel.as_posix(), size=len(data), mime=mime_type, sha256="0" * 64
        )


@pytest.fixture
def fake_storage(tmp_path, monkeypatch):
    storage = FakeLibraryStorage(tmp_path)
    monkeypatch.setattr("apps.administration.services.get_storage", lambda: storage)
    monkeypatch.setattr("apps.administration.views.get_storage", lambda: storage)
    return storage


@pytest.fixture
def admins(db):
    """Hai Admin đang hoạt động (số tối thiểu)."""
    return AdminFactory(email="admin1@ueh.edu.vn"), AdminFactory(email="admin2@ueh.edu.vn")


@pytest.fixture
def admin_client(client, admins):
    client.force_login(admins[0])
    return client


def _docx(name="mau.docx", content=b"PK\x03\x04 noi dung bieu mau"):
    return SimpleUploadedFile(
        name,
        content,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _actions(**filters):
    return list(AuditEvent.objects.filter(**filters).values_list("action", flat=True))


# ---------------------------------------------------------------------------
# Phân quyền: mọi URL của M7
# ---------------------------------------------------------------------------


def _m7_urls():
    user = UserFactory()
    cat = CategoryFactory()
    tpl = FormTemplate.objects.create(
        code="MAU_1",
        name="Mẫu 1",
        version="1",
        effective_from=dt.date(2026, 1, 1),
        storage_ref="library/form_templates/x.docx",
        original_filename="x.docx",
    )
    return [
        ("get", reverse("administration:home")),
        ("get", reverse("administration:user_create")),
        ("post", reverse("administration:user_create")),
        ("get", reverse("administration:user_update", args=[user.pk])),
        ("post", reverse("administration:user_update", args=[user.pk])),
        ("get", reverse("administration:catalogs")),
        ("post", reverse("administration:catalogs")),
        ("get", reverse("administration:catalog_update", args=["the-loai", cat.pk])),
        ("post", reverse("administration:catalog_update", args=["the-loai", cat.pk])),
        ("post", reverse("administration:catalog_toggle", args=["the-loai", cat.pk])),
        ("get", reverse("administration:templates")),
        ("get", reverse("administration:template_create")),
        ("post", reverse("administration:template_create")),
        ("post", reverse("administration:template_toggle", args=[tpl.pk])),
        ("get", reverse("administration:template_download", args=[tpl.pk])),
        ("get", reverse("administration:audit_logs")),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["customer", "editor"])
def test_non_admin_gets_404_on_every_m7_url(client, role):
    if role == "customer":
        user = UserFactory()
    else:
        user = EditorFactory(finance_access=FinanceAccess.MANAGE)
    urls = _m7_urls()
    client.force_login(user)
    for method, url in urls:
        response = getattr(client, method)(url)
        assert response.status_code == 404, (role, method, url, response.status_code)


@pytest.mark.django_db
def test_locked_admin_is_treated_as_logged_out(client):
    client.force_login(AdminFactory(is_active=False))
    for method, url in _m7_urls():
        response = getattr(client, method)(url)
        assert response.status_code == 302, (method, url)
        assert response["Location"].startswith("/tai-khoan/dang-nhap/")


@pytest.mark.django_db
def test_anonymous_is_redirected_to_login_on_every_m7_url(client):
    for method, url in _m7_urls():
        response = getattr(client, method)(url)
        assert response.status_code == 302, (method, url)
        assert response["Location"].startswith("/tai-khoan/dang-nhap/")


@pytest.mark.django_db
def test_admin_can_open_every_page(admin_client, fake_storage):
    for method, url in _m7_urls():
        if method != "get" or "tai-ve" in url:
            continue
        assert admin_client.get(url).status_code == 200, url


# ---------------------------------------------------------------------------
# 2.1 Người dùng
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_user_list_filters_search_and_htmx_partial(admin_client):
    EditorFactory(email="bien.tap@ueh.edu.vn", full_name="Trần Biên Tập")
    UserFactory(email="khach@example.com", full_name="Khách Hàng", is_active=False)

    page = admin_client.get(reverse("administration:home"))
    html = page.content.decode()
    assert "bien.tap@ueh.edu.vn" in html and "khach@example.com" in html
    assert 'id="user-filter"' in html

    resp = admin_client.get(reverse("administration:home"), {"q": "biên tập"})
    assert "bien.tap@ueh.edu.vn" in resp.content.decode()
    assert "khach@example.com" not in resp.content.decode()

    resp = admin_client.get(reverse("administration:home"), {"role": "CUSTOMER"})
    assert "khach@example.com" in resp.content.decode()
    assert "bien.tap@ueh.edu.vn" not in resp.content.decode()

    resp = admin_client.get(reverse("administration:home"), {"status": "locked"})
    assert list(resp.context["users"]) == [User.objects.get(email="khach@example.com")]
    resp = admin_client.get(reverse("administration:home"), {"status": "active"})
    assert User.objects.get(email="khach@example.com") not in resp.context["users"]

    partial = admin_client.get(
        reverse("administration:home"), {"q": "khach"}, headers={"HX-Request": "true"}
    )
    body = partial.content.decode()
    assert "<html" not in body and 'id="user-filter"' not in body
    assert "khach@example.com" in body


@pytest.mark.django_db
def test_user_list_is_paginated(admin_client):
    for i in range(25):
        UserFactory(email=f"kh{i:02d}@example.com")
    resp = admin_client.get(reverse("administration:home"))
    assert resp.context["is_paginated"]
    assert len(resp.context["users"]) == 20
    assert "Trang 1 / 2" in resp.content.decode()


@pytest.mark.django_db
def test_create_staff_outside_ueh_domain_is_rejected(admin_client):
    url = reverse("administration:user_create")
    resp = admin_client.post(
        url,
        {
            "email": "ai.do@gmail.com",
            "full_name": "Người Ngoài",
            "role": UserRole.EDITOR,
            "finance_access": FinanceAccess.NONE,
        },
    )
    assert resp.status_code == 200
    assert "@ueh.edu.vn" in resp.content.decode()
    assert not User.objects.filter(email="ai.do@gmail.com").exists()
    assert not AuditEvent.objects.filter(action="user.create").exists()

    with pytest.raises(ValidationError):
        services.create_staff_user(
            actor=User.objects.get(email="admin1@ueh.edu.vn"),
            email="x@ueh.edu.vn.evil.com",
            full_name="X",
            role=UserRole.EDITOR,
        )


@pytest.mark.django_db
def test_create_editor_with_finance_access_logs_event(admin_client, admins):
    resp = admin_client.post(
        reverse("administration:user_create"),
        {
            "email": "Moi.BTV@UEH.edu.vn",
            "full_name": "Biên Tập Mới",
            "role": UserRole.EDITOR,
            "finance_access": FinanceAccess.VIEW,
        },
        REMOTE_ADDR="10.0.0.5",
    )
    assert resp.status_code == 302
    user = User.objects.get(email="moi.btv@ueh.edu.vn")
    assert user.role == UserRole.EDITOR
    assert user.finance_access == FinanceAccess.VIEW
    assert not user.has_usable_password()
    event = AuditEvent.objects.get(action="user.create")
    assert event.actor == admins[0]
    assert event.object_id == str(user.pk)
    assert event.data["after"]["role"] == UserRole.EDITOR
    assert event.data["after"]["finance_access"] == FinanceAccess.VIEW
    assert event.ip_address == "10.0.0.5"


@pytest.mark.django_db
def test_create_staff_rejects_duplicate_and_finance_for_admin(admin_client):
    EditorFactory(email="trung@ueh.edu.vn")
    resp = admin_client.post(
        reverse("administration:user_create"),
        {"email": "trung@ueh.edu.vn", "full_name": "A", "role": "EDITOR", "finance_access": "NONE"},
    )
    assert "Email này đã có tài khoản." in resp.content.decode()

    resp = admin_client.post(
        reverse("administration:user_create"),
        {"email": "qtv@ueh.edu.vn", "full_name": "B", "role": "ADMIN", "finance_access": "VIEW"},
    )
    assert "Quyền tài chính chỉ áp dụng cho Biên tập viên." in resp.content.decode()
    assert not User.objects.filter(email="qtv@ueh.edu.vn").exists()

    resp = admin_client.post(
        reverse("administration:user_create"),
        {"email": "kh@ueh.edu.vn", "full_name": "C", "role": "CUSTOMER", "finance_access": "NONE"},
    )
    assert resp.status_code == 200
    assert not User.objects.filter(email="kh@ueh.edu.vn").exists()


@pytest.mark.django_db
def test_create_staff_service_guards(admins):
    actor = admins[0]
    with pytest.raises(ValidationError):
        services.create_staff_user(
            actor=actor, email="a@ueh.edu.vn", full_name="A", role="CUSTOMER"
        )
    with pytest.raises(ValidationError):
        services.create_staff_user(
            actor=actor, email="a@ueh.edu.vn", full_name="A", role="ADMIN", finance_access="VIEW"
        )
    with pytest.raises(ValidationError):
        services.create_staff_user(
            actor=actor, email="admin2@ueh.edu.vn", full_name="A", role="EDITOR"
        )


def _update(client, user, **data):
    payload = {"role": user.role, "finance_access": user.finance_access}
    if user.is_active:
        payload["is_active"] = "on"
    payload.update(data)
    if payload.get("is_active") is False:
        payload.pop("is_active")
    return client.post(reverse("administration:user_update", args=[user.pk]), payload)


@pytest.mark.django_db
def test_cannot_lock_or_demote_self(admin_client, admins):
    me = admins[0]
    AdminFactory(email="admin3@ueh.edu.vn")  # đủ Admin để chỉ còn ràng buộc "tự mình"
    resp = _update(admin_client, me, is_active=False)
    assert "không thể tự hạ quyền hoặc tự khóa" in resp.content.decode()
    resp = _update(admin_client, me, role=UserRole.EDITOR)
    assert "không thể tự hạ quyền hoặc tự khóa" in resp.content.decode()
    me.refresh_from_db()
    assert me.is_active and me.role == UserRole.ADMIN
    assert not AuditEvent.objects.filter(action__startswith="user.").exists()


@pytest.mark.django_db
def test_active_admins_never_drop_below_two(admin_client, admins):
    other = admins[1]
    for change in ({"is_active": False}, {"role": UserRole.EDITOR}):
        resp = _update(admin_client, other, **change)
        assert resp.status_code == 200
        assert "ít nhất 2 Quản trị viên" in resp.content.decode()
        other.refresh_from_db()
        assert other.is_active and other.role == UserRole.ADMIN

    # Có Admin thứ 3 thì khóa được 1 người (còn lại 2)
    third = AdminFactory(email="admin3@ueh.edu.vn")
    assert _update(admin_client, third, is_active=False).status_code == 302
    third.refresh_from_db()
    assert not third.is_active
    # Lúc này lại chỉ còn 2 → hạ quyền admin2 bị từ chối
    resp = _update(admin_client, other, role=UserRole.EDITOR)
    assert "ít nhất 2 Quản trị viên" in resp.content.decode()


@pytest.mark.django_db
def test_locked_admin_can_be_changed_without_admin_count_check(admin_client, admins):
    locked = AdminFactory(email="admin.khoa@ueh.edu.vn", is_active=False)
    assert _update(admin_client, locked, role=UserRole.EDITOR, is_active=False).status_code == 302
    locked.refresh_from_db()
    assert locked.role == UserRole.EDITOR


@pytest.mark.django_db
def test_role_finance_lock_unlock_write_correct_audit_events(admin_client, admins):
    editor = EditorFactory(email="btv@ueh.edu.vn", finance_access=FinanceAccess.NONE)

    _update(admin_client, editor, finance_access=FinanceAccess.MANAGE)
    ev = AuditEvent.objects.get(action="user.finance_access_change")
    assert ev.data["before"] == {"finance_access": "NONE"}
    assert ev.data["after"] == {"finance_access": "MANAGE"}
    assert ev.actor == admins[0] and ev.object_type == "User" and ev.object_id == str(editor.pk)

    editor.refresh_from_db()
    _update(admin_client, editor, is_active=False)
    ev = AuditEvent.objects.get(action="user.lock")
    assert ev.data["before"] == {"is_active": True} and ev.data["after"] == {"is_active": False}

    editor.refresh_from_db()
    _update(admin_client, editor, is_active="on")
    ev = AuditEvent.objects.get(action="user.unlock")
    assert ev.data["before"] == {"is_active": False} and ev.data["after"] == {"is_active": True}

    editor.refresh_from_db()
    _update(admin_client, editor, role=UserRole.ADMIN)
    ev = AuditEvent.objects.get(action="user.role_change")
    assert ev.data["before"] == {"role": "EDITOR"} and ev.data["after"] == {"role": "ADMIN"}
    # Lên ADMIN thì quyền tài chính tự về NONE và cũng được ghi nhật ký
    assert _actions(action="user.finance_access_change").count("user.finance_access_change") == 2
    editor.refresh_from_db()
    assert editor.finance_access == FinanceAccess.NONE

    # Lưu mà không đổi gì: không ghi thêm nhật ký
    count = AuditEvent.objects.count()
    resp = _update(admin_client, editor)
    assert resp.status_code == 302
    assert AuditEvent.objects.count() == count


@pytest.mark.django_db
def test_customer_promotion_requires_ueh_domain(admin_client):
    outsider = UserFactory(email="tacgia@gmail.com")
    resp = _update(admin_client, outsider, role=UserRole.EDITOR)
    assert resp.status_code == 200
    assert "@ueh.edu.vn" in resp.content.decode()
    outsider.refresh_from_db()
    assert outsider.role == UserRole.CUSTOMER

    insider = UserFactory(email="giangvien@ueh.edu.vn")
    assert insider.has_usable_password()
    assert _update(admin_client, insider, role=UserRole.EDITOR).status_code == 302
    insider.refresh_from_db()
    assert insider.role == UserRole.EDITOR
    assert not insider.has_usable_password()
    assert _actions(object_id=str(insider.pk)) == ["user.role_change"]


@pytest.mark.django_db
def test_staff_cannot_be_turned_into_customer(admins):
    editor = EditorFactory()
    with pytest.raises(ValidationError):
        services.update_user(
            actor=admins[0],
            user=editor,
            role=UserRole.CUSTOMER,
            finance_access=FinanceAccess.NONE,
            is_active=True,
        )
    with pytest.raises(ValidationError):
        services.update_user(
            actor=admins[0], user=editor, role="ROOT", finance_access="NONE", is_active=True
        )
    with pytest.raises(ValidationError):
        services.update_user(
            actor=admins[0], user=editor, role="EDITOR", finance_access="ALL", is_active=True
        )


@pytest.mark.django_db
def test_update_form_offers_only_staff_roles_for_staff(admin_client):
    editor = EditorFactory()
    resp = admin_client.get(reverse("administration:user_update", args=[editor.pk]))
    roles = [value for value, _label in resp.context["form"].fields["role"].choices]
    assert roles == ["EDITOR", "ADMIN"]
    customer = UserFactory()
    resp = admin_client.get(reverse("administration:user_update", args=[customer.pk]))
    roles = [value for value, _label in resp.context["form"].fields["role"].choices]
    assert "CUSTOMER" in roles


@pytest.mark.django_db
def test_no_delete_route_for_users_or_catalogs():
    from apps.administration.urls import urlpatterns

    names = [p.name for p in urlpatterns]
    assert not any(
        "delete" in n or "xoa" in str(p.pattern) for n, p in zip(names, urlpatterns, strict=True)
    )


# ---------------------------------------------------------------------------
# 2.2 Danh mục
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kind,model", [("the-loai", Category), ("linh-vuc", Field), ("loai-phi", FeeType)]
)
def test_catalog_create_update_toggle(admin_client, kind, model):
    url = reverse("administration:catalogs")
    assert admin_client.get(url, {"loai": kind}).status_code == 200

    resp = admin_client.post(
        url, {"loai": kind, "name": "Mục mới", "sort_order": 5, "is_active": "on"}
    )
    assert resp.status_code == 302
    item = model.objects.get(name="Mục mới")
    ev = AuditEvent.objects.get(action="catalog.create")
    assert ev.object_type == model.__name__ and ev.data["after"]["name"] == "Mục mới"

    resp = admin_client.post(
        reverse("administration:catalog_update", args=[kind, item.pk]),
        {"name": "Mục đã sửa", "sort_order": 1, "is_active": "on"},
    )
    assert resp.status_code == 302
    item.refresh_from_db()
    assert item.name == "Mục đã sửa" and item.sort_order == 1
    ev = AuditEvent.objects.get(action="catalog.update")
    assert ev.data["before"]["name"] == "Mục mới" and ev.data["after"]["name"] == "Mục đã sửa"

    admin_client.post(reverse("administration:catalog_toggle", args=[kind, item.pk]))
    item.refresh_from_db()
    assert item.is_active is False
    assert AuditEvent.objects.filter(action="catalog.update").count() == 2


@pytest.mark.django_db
def test_catalog_in_use_can_be_disabled_and_is_never_deleted(admin_client):
    category = CategoryFactory(name="Giáo trình")
    case = PublicationCaseFactory(category=category)
    resp = admin_client.post(
        reverse("administration:catalog_toggle", args=["the-loai", category.pk])
    )
    assert resp.status_code == 302
    category.refresh_from_db()
    assert category.is_active is False
    case.refresh_from_db()
    assert case.category_id == category.pk

    # Không có đường xóa: GET/DELETE trên endpoint bật/tắt không làm gì
    toggle = reverse("administration:catalog_toggle", args=["the-loai", category.pk])
    assert admin_client.delete(toggle).status_code == 405
    assert admin_client.get(toggle).status_code == 405
    assert Category.objects.filter(pk=category.pk).exists()


@pytest.mark.django_db
def test_catalog_validation_unknown_kind_and_no_change(admin_client):
    CategoryFactory(name="Chuyên khảo")
    resp = admin_client.post(
        reverse("administration:catalogs"),
        {"loai": "the-loai", "name": "Chuyên khảo", "sort_order": 1},
    )
    assert resp.status_code == 200 and resp.context["form"].errors
    assert (
        admin_client.get(reverse("administration:catalogs"), {"loai": "khong-co"}).status_code
        == 404
    )

    item = CategoryFactory(name="Tham khảo", sort_order=3)
    url = reverse("administration:catalog_update", args=["the-loai", item.pk])
    resp = admin_client.post(url, {"name": "", "sort_order": 3, "is_active": "on"})
    assert resp.status_code == 200 and "name" in resp.context["form"].errors
    resp = admin_client.post(url, {"name": "Tham khảo", "sort_order": 3, "is_active": "on"})
    assert resp.status_code == 302
    assert not AuditEvent.objects.filter(action="catalog.update").exists()


# ---------------------------------------------------------------------------
# 2.3 Biểu mẫu tải về
# ---------------------------------------------------------------------------


def _post_template(client, **overrides):
    data = {
        "code": "MAU_2",
        "name": "Mẫu 2 — Đơn đề nghị xuất bản",
        "version": "2026.1",
        "effective_from": "2026-12-01",
        "file": _docx(),
        "activate": "on",
    }
    data.update(overrides)
    data = {k: v for k, v in data.items() if v is not None}
    return client.post(reverse("administration:template_create"), data)


@pytest.mark.django_db
def test_create_template_saves_via_library_storage_and_logs(admin_client, fake_storage):
    resp = _post_template(admin_client)
    assert resp.status_code == 302
    tpl = FormTemplate.objects.get(code="MAU_2")
    assert tpl.is_active and tpl.original_filename == "mau.docx"
    assert tpl.storage_ref.startswith("library/form_templates/")
    assert fake_storage.saved[0]["category"] == "form_templates"
    assert _actions(object_type="FormTemplate") == [
        "form_template.activate",
        "form_template.create",
    ]

    page = admin_client.get(reverse("administration:templates")).content.decode()
    assert "MAU_2" in page and "Đang áp dụng" in page and "mau.docx" in page
    assert tpl.storage_ref not in page  # không lộ đường dẫn lưu trữ


@pytest.mark.django_db
def test_activating_new_version_deactivates_old_same_code(admin_client, fake_storage):
    _post_template(admin_client, version="1")
    _post_template(admin_client, version="2", activate=None)
    _post_template(admin_client, code="MAU_3", version="1")
    v1 = FormTemplate.objects.get(code="MAU_2", version="1")
    v2 = FormTemplate.objects.get(code="MAU_2", version="2")
    other = FormTemplate.objects.get(code="MAU_3")
    assert v1.is_active and not v2.is_active

    resp = admin_client.post(
        reverse("administration:template_toggle", args=[v2.pk]), {"active": "1"}
    )
    assert resp.status_code == 302
    v1.refresh_from_db()
    v2.refresh_from_db()
    other.refresh_from_db()
    assert v2.is_active and not v1.is_active and other.is_active
    assert AuditEvent.objects.filter(
        action="form_template.deactivate", object_id=str(v1.pk)
    ).exists()
    assert AuditEvent.objects.filter(action="form_template.activate", object_id=str(v2.pk)).exists()
    assert FormTemplate.objects.filter(code="MAU_2", is_active=True).count() == 1

    # Tạo bản mới có "áp dụng ngay" cũng tự tắt bản đang áp dụng
    _post_template(admin_client, version="3")
    v2.refresh_from_db()
    assert not v2.is_active
    assert FormTemplate.objects.get(code="MAU_2", version="3").is_active

    # Tắt áp dụng
    v3 = FormTemplate.objects.get(code="MAU_2", version="3")
    admin_client.post(reverse("administration:template_toggle", args=[v3.pk]), {"active": "0"})
    v3.refresh_from_db()
    assert not v3.is_active
    assert AuditEvent.objects.filter(
        action="form_template.deactivate", object_id=str(v3.pk)
    ).exists()

    # Bật/tắt lại đúng trạng thái hiện có: không ghi thêm
    count = AuditEvent.objects.count()
    admin_client.post(reverse("administration:template_toggle", args=[v3.pk]), {"active": "0"})
    assert AuditEvent.objects.count() == count


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["mau.exe", "mau.jpg", "mau", "mau.docx.sh"])
def test_template_rejects_wrong_extension(admin_client, fake_storage, name):
    resp = _post_template(admin_client, file=_docx(name=name))
    assert resp.status_code == 200
    assert "không được hỗ trợ" in resp.content.decode()
    assert not FormTemplate.objects.exists() and fake_storage.saved == []


@pytest.mark.django_db
def test_template_rejects_file_over_limit(admin_client, fake_storage, settings):
    settings.MAX_LIBRARY_FILE_MB = 1
    resp = _post_template(admin_client, file=_docx(content=b"x" * (1024 * 1024 + 1)))
    assert resp.status_code == 200
    assert "vượt quá dung lượng tối đa 1 MB" in resp.content.decode()
    assert not FormTemplate.objects.exists() and fake_storage.saved == []

    resp = _post_template(admin_client, file=_docx(content=b"x" * (1024 * 1024)))
    assert resp.status_code == 302


@pytest.mark.django_db
def test_template_code_format_and_duplicate_version(admin_client, fake_storage):
    for bad in ["ma", "mau-2", "M" * 31, "MÃU_2"]:
        resp = _post_template(admin_client, code=bad)
        assert resp.status_code == 200 and "code" in resp.context["form"].errors, bad
    assert _post_template(admin_client, code="biz_f4_01").status_code == 302
    assert FormTemplate.objects.filter(code="BIZ_F4_01").exists()
    assert _post_template(admin_client, code="CUSTOM_FORM_9").status_code == 302

    resp = _post_template(admin_client, code="BIZ_F4_01")
    assert resp.status_code == 200
    assert "đã có phiên bản" in resp.content.decode()

    with pytest.raises(ValidationError):
        services.validate_form_template_file("a.pdf", 0)


@pytest.mark.django_db
def test_template_create_page_lists_suggested_codes(admin_client):
    html = admin_client.get(reverse("administration:template_create")).content.decode()
    assert 'value="MAU_9"' in html and 'value="BIZ_F4_12"' in html


@pytest.mark.django_db
def test_admin_downloads_template_as_stream(admin_client, fake_storage):
    content = b"PK\x03\x04 bieu mau that"
    _post_template(admin_client, file=_docx(name="Mẫu 2.docx", content=content))
    tpl = FormTemplate.objects.get()
    resp = admin_client.get(reverse("administration:template_download", args=[tpl.pk]))
    assert resp.status_code == 200
    assert resp.streaming
    assert b"".join(resp.streaming_content) == content
    assert "attachment;" in resp["Content-Disposition"]
    assert resp["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    (fake_storage.media_root / tpl.storage_ref).unlink()
    assert (
        admin_client.get(reverse("administration:template_download", args=[tpl.pk])).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# 2.4 Nhật ký hệ thống
# ---------------------------------------------------------------------------

SECRET = "NOI-DUNG-MAT-CUA-HO-SO"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "action", ["case.update", "document.upload", "finance.collection", "status.change"]
)
def test_audit_log_hides_data_of_case_document_finance(admin_client, action):
    case = PublicationCaseFactory()
    log_event(
        action=action,
        object_type="PublicationCase",
        object_id=str(case.pk),
        case=case,
        data={"before": {"title": SECRET}, "after": {"title": SECRET + "-2"}},
    )
    resp = admin_client.get(reverse("administration:audit_logs"))
    html = resp.content.decode()
    assert resp.status_code == 200
    assert action in html
    assert case.display_code in html
    assert SECRET not in html
    assert case.title not in html


@pytest.mark.django_db
def test_audit_log_shows_data_of_system_actions(admin_client, admins):
    for action in ["user.lock", "auth.login", "catalog.update", "form_template.create"]:
        log_event(
            actor=admins[0],
            action=action,
            object_type="X",
            object_id="1",
            data={"marker": action + "-DATA"},
        )
    html = admin_client.get(reverse("administration:audit_logs")).content.decode()
    for action in ["user.lock", "auth.login", "catalog.update", "form_template.create"]:
        assert action + "-DATA" in html


@pytest.mark.django_db
def test_audit_log_filters_and_newest_first(admin_client, admins):
    editor = EditorFactory(email="loc.btv@ueh.edu.vn", full_name="Lọc Biên Tập")
    log_event(actor=editor, action="case.create", object_type="PublicationCase", object_id="1")
    # AuditEvent bất biến: tạo sẵn một bản ghi ở thời điểm quá khứ bằng tham số `at`
    AuditEvent.objects.create(
        actor=editor,
        action="document.download",
        object_type="Document",
        object_id="2",
        at=timezone.now() - dt.timedelta(days=10),
    )
    log_event(actor=admins[0], action="user.lock", object_type="User", object_id="3")
    log_event(actor=None, action="auth.login_failed", object_type="User", object_id="4")
    log_event(actor=admins[0], action="catalog.create", object_type="Category", object_id="5")
    log_event(actor=admins[0], action="finance.receivable", object_type="Receivable", object_id="6")

    url = reverse("administration:audit_logs")

    def actions(**params):
        return [row["action"] for row in admin_client.get(url, params).context["rows"]]

    everything = actions()
    assert everything[-1] == "document.download"  # cũ nhất ở cuối
    assert actions(group="case") == ["case.create"]
    assert actions(group="document") == ["document.download"]
    assert actions(group="finance") == ["finance.receivable"]
    assert actions(group="user") == ["user.lock"]
    assert actions(group="auth") == ["auth.login_failed"]
    assert actions(group="other") == ["catalog.create"]
    assert set(actions(actor="loc.btv")) == {"case.create", "document.download"}
    assert set(actions(actor="Lọc Biên")) == {"case.create", "document.download"}

    today = timezone.localdate()
    assert "document.download" not in actions(date_from=today.isoformat())
    assert actions(date_to=(today - dt.timedelta(days=5)).isoformat()) == ["document.download"]

    resp = admin_client.get(url, {"date_from": "2026-12-10", "date_to": "2026-12-01"})
    assert resp.context["rows"] == []
    assert "phải sau hoặc bằng" in resp.content.decode()

    partial = admin_client.get(url, {"group": "user"}, headers={"HX-Request": "true"})
    assert "<html" not in partial.content.decode()
    assert "user.lock" in partial.content.decode()


@pytest.mark.django_db
def test_audit_log_paginates_by_50_and_is_read_only(admin_client):
    for i in range(55):
        log_event(action="auth.login", object_type="User", object_id=str(i))
    resp = admin_client.get(reverse("administration:audit_logs"))
    assert len(resp.context["rows"]) == 50
    assert resp.context["is_paginated"]
    assert (
        len(admin_client.get(reverse("administration:audit_logs"), {"page": 2}).context["rows"])
        == 5
    )
    assert admin_client.post(reverse("administration:audit_logs")).status_code == 405


def test_audit_data_visibility_rule():
    from apps.administration.views import audit_data_visible

    assert audit_data_visible("user.create")
    assert audit_data_visible("form_template.activate")
    assert not audit_data_visible("case.update")
    assert not audit_data_visible("document.download")
    assert not audit_data_visible("finance.collection")
    assert not audit_data_visible("userx.something")
    assert not audit_data_visible("")
