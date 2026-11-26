"""Fixture cho test M6.

`fake_storage`: kho lưu trữ giả có `save_library_file` theo đúng chữ ký CR-001
(`save_library_file(category, filename, fileobj, size, mime_type) -> StoredFile`),
dùng trong lúc CR-001 chưa gộp vào main.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from apps.core.storage import LocalFileStorage, StoredFile, sanitize_filename
from tests.factories import AdminFactory, EditorFactory, UserFactory

LIBRARY_CATEGORIES = {"form_templates", "public_media"}


class FakeLibraryStorage(LocalFileStorage):
    """LocalFileStorage + save_library_file giả lập hành vi mô tả trong CR-001."""

    def __init__(self, media_root):
        super().__init__(media_root)
        self.saved: list[tuple[str, str, int, str]] = []

    def save_library_file(self, category, filename, fileobj, size, mime_type) -> StoredFile:
        assert category in LIBRARY_CATEGORIES
        data = fileobj.read()
        assert len(data) == size
        rel = f"library/{category}/{uuid.uuid4().hex}_{sanitize_filename(filename)}"
        target = self.media_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.saved.append((category, filename, size, mime_type))
        return StoredFile(
            storage_ref=rel, size=size, mime=mime_type, sha256=hashlib.sha256(data).hexdigest()
        )


@pytest.fixture
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def fake_storage(media_root, monkeypatch):
    storage = FakeLibraryStorage(media_root)
    monkeypatch.setattr("apps.public_site.services.get_storage", lambda: storage)
    monkeypatch.setattr("apps.public_site.views.get_storage", lambda: storage)
    return storage


@pytest.fixture
def editor(db):
    return EditorFactory()


@pytest.fixture
def customer(db):
    return UserFactory()


@pytest.fixture
def admin_user(db):
    return AdminFactory()


@pytest.fixture
def editor_client(client, editor):
    client.force_login(editor)
    return client
