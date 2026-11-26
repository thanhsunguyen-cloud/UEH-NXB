"""Factory Boy factories dùng chung cho toàn bộ bộ test M0 và các module M1–M8."""

import factory
from django.utils import timezone

from apps.accounts.models import FinanceAccess, User, UserRole
from apps.core.models import (
    CaseStatus,
    Category,
    Contributor,
    ContributorRole,
    Document,
    DocumentType,
    FeeType,
    Field,
    PublicationCase,
    PublicationMode,
)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Sequence(lambda n: f"Người dùng {n}")
    role = UserRole.CUSTOMER
    finance_access = FinanceAccess.NONE
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        if not create:
            return
        if self.role == UserRole.CUSTOMER:
            self.set_password(extracted or "TestPass@123")
        else:
            self.set_unusable_password()
        self.save()


class EditorFactory(UserFactory):
    email = factory.Sequence(lambda n: f"editor{n}@ueh.edu.vn")
    role = UserRole.EDITOR
    finance_access = FinanceAccess.NONE


class AdminFactory(UserFactory):
    email = factory.Sequence(lambda n: f"admin{n}@ueh.edu.vn")
    role = UserRole.ADMIN
    finance_access = FinanceAccess.NONE


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Thể loại {n}")
    sort_order = factory.Sequence(lambda n: n)


class FieldFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Field

    name = factory.Sequence(lambda n: f"Lĩnh vực {n}")
    sort_order = factory.Sequence(lambda n: n)


class FeeTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeeType

    name = factory.Sequence(lambda n: f"Phí dịch vụ xuất bản {n}")
    sort_order = factory.Sequence(lambda n: n)


class PublicationCaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PublicationCase

    owner = factory.SubFactory(UserFactory)
    title = factory.Sequence(lambda n: f"Tác phẩm xuất bản số {n}")
    publication_mode = PublicationMode.SELF
    status = CaseStatus.DRAFT
    summary = "Tóm tắt nội dung tác phẩm mẫu."


class ContributorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Contributor

    case = factory.SubFactory(PublicationCaseFactory)
    full_name = factory.Sequence(lambda n: f"Tác giả {n}")
    role = ContributorRole.AUTHOR
    order = 1


class DocumentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Document

    case = factory.SubFactory(PublicationCaseFactory)
    doc_type = DocumentType.MANUSCRIPT
    form_code = ""
    version = 1
    is_current = True
    original_filename = "sample.pdf"
    mime_type = "application/pdf"
    size_bytes = 1024
    sha256 = "a" * 64
    storage_backend = "local"
    storage_ref = factory.Sequence(lambda n: f"cases/sample/v1_doc_{n}.pdf")
    uploaded_by = factory.LazyAttribute(lambda obj: obj.case.owner)
    uploaded_at = factory.LazyFunction(timezone.now)
