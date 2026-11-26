"""Cấu hình fixture dùng chung cho pytest."""

import pytest

from apps.accounts.models import FinanceAccess
from tests.factories import AdminFactory, EditorFactory, UserFactory


@pytest.fixture
def customer_a(db):
    return UserFactory(email="customer_a@example.com", full_name="Khách hàng A")


@pytest.fixture
def customer_b(db):
    return UserFactory(email="customer_b@example.com", full_name="Khách hàng B")


@pytest.fixture
def editor_none(db):
    return EditorFactory(email="editor_none@ueh.edu.vn", finance_access=FinanceAccess.NONE)


@pytest.fixture
def editor_view(db):
    return EditorFactory(email="editor_view@ueh.edu.vn", finance_access=FinanceAccess.VIEW)


@pytest.fixture
def editor_manage(db):
    return EditorFactory(email="editor_manage@ueh.edu.vn", finance_access=FinanceAccess.MANAGE)


@pytest.fixture
def admin_user(db):
    return AdminFactory(email="admin@ueh.edu.vn")
