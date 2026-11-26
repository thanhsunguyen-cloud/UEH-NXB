"""Lệnh tạo dữ liệu mẫu phục vụ phát triển và nghiệm thu M0 (mục 11).

Chỉ chạy khi DJANGO_DEBUG=True. Tạo:
- 1 admin, 2 editor (1 finance_access=MANAGE, 1 NONE), 2 customer
- Danh mục mẫu (Category, Field, FeeType)
- 5 hồ sơ ở các trạng thái khác nhau
- Vài khoản phải thu / đã thu ở các tình trạng khác nhau (chưa thu, thu một phần, thu đủ, quá hạn)
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import FinanceAccess, User, UserRole
from apps.core.codes import issue_nxb_code
from apps.core.finance import create_collection, create_receivable
from apps.core.models import (
    CaseNote,
    CaseStatus,
    Category,
    CollectionMethod,
    Contributor,
    ContributorRole,
    Document,
    DocumentType,
    FeeType,
    Field,
    FormTemplate,
    NoteVisibility,
    PublicationCase,
    PublicationMode,
)


class Command(BaseCommand):
    help = "Tạo dữ liệu mẫu cho môi trường phát triển (chỉ chạy khi DJANGO_DEBUG=True)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Lệnh seed_demo chỉ được phép chạy khi DJANGO_DEBUG=True.")

        # 1. Người dùng mẫu (5 tài khoản)
        admin_user, _ = User.objects.get_or_create(
            email="admin@ueh.edu.vn",
            defaults={
                "full_name": "Nguyễn Thanh Sử (Quản trị)",
                "role": UserRole.ADMIN,
                "finance_access": FinanceAccess.NONE,
                "is_active": True,
            },
        )
        editor_fin, _ = User.objects.get_or_create(
            email="bientap.taichinh@ueh.edu.vn",
            defaults={
                "full_name": "Trần Minh Thư (BTV Tài chính)",
                "role": UserRole.EDITOR,
                "finance_access": FinanceAccess.MANAGE,
                "is_active": True,
            },
        )
        editor_plain, _ = User.objects.get_or_create(
            email="bientap@ueh.edu.vn",
            defaults={
                "full_name": "Lê Quốc Bảo (Biên tập viên)",
                "role": UserRole.EDITOR,
                "finance_access": FinanceAccess.NONE,
                "is_active": True,
            },
        )

        customer_a, created_a = User.objects.get_or_create(
            email="tacgia.a@gmail.com",
            defaults={
                "full_name": "PGS.TS. Phạm Văn An",
                "phone": "0903111222",
                "organization": "Khoa Tài chính — UEH",
                "role": UserRole.CUSTOMER,
                "is_active": True,
            },
        )
        if created_a:
            customer_a.set_password("Demo@123456")
            customer_a.save()

        customer_b, created_b = User.objects.get_or_create(
            email="tacgia.b@doitac.vn",
            defaults={
                "full_name": "Nguyễn Thị Bình",
                "phone": "0908333444",
                "organization": "Công ty CP Tri thức Kinh tế",
                "role": UserRole.CUSTOMER,
                "is_active": True,
            },
        )
        if created_b:
            customer_b.set_password("Demo@123456")
            customer_b.save()

        # 2. Danh mục mẫu
        cat_gt, _ = Category.objects.get_or_create(
            name="Giáo trình đại học", defaults={"sort_order": 1}
        )
        cat_ck, _ = Category.objects.get_or_create(
            name="Sách chuyên khảo", defaults={"sort_order": 2}
        )
        cat_tk, _ = Category.objects.get_or_create(
            name="Sách tham khảo", defaults={"sort_order": 3}
        )

        fld_kt, _ = Field.objects.get_or_create(name="Kinh tế học", defaults={"sort_order": 1})
        fld_tc, _ = Field.objects.get_or_create(
            name="Tài chính – Ngân hàng", defaults={"sort_order": 2}
        )
        fld_qt, _ = Field.objects.get_or_create(
            name="Quản trị kinh doanh", defaults={"sort_order": 3}
        )

        fee_ql, _ = FeeType.objects.get_or_create(
            name="Phí quản lý xuất bản", defaults={"sort_order": 1}
        )
        fee_bt, _ = FeeType.objects.get_or_create(name="Phí biên tập", defaults={"sort_order": 2})
        FeeType.objects.get_or_create(name="Phí khác", defaults={"sort_order": 3})

        today = timezone.localdate()
        FormTemplate.objects.get_or_create(
            code="MAU_1",
            version="2026.1",
            defaults={
                "name": "Mẫu 1 — Đề nghị liên kết xuất bản",
                "effective_from": today - timedelta(days=30),
                "is_active": True,
                "storage_backend": "local",
                "storage_ref": "templates/MAU_1_v2026.1.docx",
                "original_filename": "MAU_1_De_nghi_lien_ket.docx",
            },
        )
        FormTemplate.objects.get_or_create(
            code="MAU_2",
            version="2026.1",
            defaults={
                "name": "Mẫu 2 — Bản đăng ký xuất bản",
                "effective_from": today - timedelta(days=30),
                "is_active": True,
                "storage_backend": "local",
                "storage_ref": "templates/MAU_2_v2026.1.docx",
                "original_filename": "MAU_2_Dang_ky_xuat_ban.docx",
            },
        )

        # 3. 5 hồ sơ ở các trạng thái khác nhau
        if PublicationCase.objects.exists():
            self.stdout.write(self.style.WARNING("Dữ liệu hồ sơ mẫu đã tồn tại, bỏ qua tạo trùng."))
            return

        c1 = PublicationCase.objects.create(
            owner=customer_a,
            title="Kinh tế vĩ mô ứng dụng tại Việt Nam",
            category=cat_gt,
            field=fld_kt,
            publication_mode=PublicationMode.SELF,
            summary="Giáo trình chuẩn cho sinh viên khối ngành kinh tế.",
            page_count=340,
            book_size="16 x 24 cm",
            status=CaseStatus.DRAFT,
        )
        Contributor.objects.create(
            case=c1,
            full_name="Phạm Văn An",
            academic_title="PGS.TS.",
            role=ContributorRole.CHIEF_EDITOR,
            affiliation="UEH",
            order=1,
        )

        c2 = PublicationCase.objects.create(
            owner=customer_a,
            title="Quản trị rủi ro ngân hàng thương mại hiện đại",
            category=cat_ck,
            field=fld_tc,
            publication_mode=PublicationMode.SELF,
            summary="Phân tích khung Basel III và thực tiễn Việt Nam.",
            page_count=280,
            book_size="16 x 24 cm",
            status=CaseStatus.SUBMITTED,
            submitted_at=timezone.now() - timedelta(days=4),
        )
        Contributor.objects.create(
            case=c2,
            full_name="Phạm Văn An",
            academic_title="PGS.TS.",
            role=ContributorRole.AUTHOR,
            affiliation="UEH",
            order=1,
        )

        c3 = PublicationCase.objects.create(
            owner=customer_b,
            primary_editor=editor_plain,
            title="Chuyển đổi số trong doanh nghiệp vừa và nhỏ",
            category=cat_tk,
            field=fld_qt,
            publication_mode=PublicationMode.LINKED,
            partner_name="Công ty CP Tri thức Kinh tế",
            summary="Tài liệu thực hành chuyển đổi số quản trị vận hành.",
            page_count=260,
            book_size="14.5 x 20.5 cm",
            status=CaseStatus.EDITING,
            submitted_at=timezone.now() - timedelta(days=20),
            accepted_at=timezone.now() - timedelta(days=15),
        )
        issue_nxb_code(c3)
        Contributor.objects.create(
            case=c3,
            full_name="Nguyễn Thị Bình",
            academic_title="ThS.",
            role=ContributorRole.AUTHOR,
            affiliation="Công ty CP Tri thức Kinh tế",
            order=1,
        )
        CaseNote.objects.create(
            case=c3,
            author=editor_plain,
            body="Bản thảo cần rà soát lại chương 3 theo chuẩn trích dẫn APA 7.",
            visibility=NoteVisibility.INTERNAL,
        )
        CaseNote.objects.create(
            case=c3,
            author=editor_plain,
            body="Hồ sơ đã được tiếp nhận và đang trong giai đoạn biên tập.",
            visibility=NoteVisibility.CUSTOMER,
        )

        c4 = PublicationCase.objects.create(
            owner=customer_b,
            primary_editor=editor_fin,
            title="Phân tích dữ liệu tài chính bằng Python",
            category=cat_ck,
            field=fld_tc,
            publication_mode=PublicationMode.LINKED,
            partner_name="Công ty CP Tri thức Kinh tế",
            isbn="9786043460018",
            registration_number="128-2026/CXBIPH/04-12/KTTPHCM",
            registration_date=today - timedelta(days=35),
            summary="Ứng dụng phân tích định lượng trong thị trường vốn.",
            page_count=412,
            book_size="16 x 24 cm",
            status=CaseStatus.REGISTERED,
            submitted_at=timezone.now() - timedelta(days=60),
            accepted_at=timezone.now() - timedelta(days=50),
        )
        issue_nxb_code(c4)
        Contributor.objects.create(
            case=c4,
            full_name="Trần Hoàng Nam",
            academic_title="TS.",
            role=ContributorRole.AUTHOR,
            affiliation="UEH",
            order=1,
        )

        c5 = PublicationCase.objects.create(
            owner=customer_a,
            primary_editor=editor_fin,
            title="Kinh tế tuần hoàn và phát triển bền vững đô thị",
            category=cat_ck,
            field=fld_kt,
            publication_mode=PublicationMode.SELF,
            isbn="9786043460025",
            registration_number="089-2026/CXBIPH/02-09/KTTPHCM",
            registration_date=today - timedelta(days=90),
            decision_number="45/QĐ-NXBKT",
            decision_date=today - timedelta(days=70),
            deposit_date=today - timedelta(days=40),
            summary="Công trình nghiên cứu liên ngành về đô thị xanh.",
            page_count=320,
            book_size="16 x 24 cm",
            status=CaseStatus.COMPLETED,
            submitted_at=timezone.now() - timedelta(days=120),
            accepted_at=timezone.now() - timedelta(days=110),
        )
        issue_nxb_code(c5)
        Contributor.objects.create(
            case=c5,
            full_name="Phạm Văn An",
            academic_title="PGS.TS.",
            role=ContributorRole.CHIEF_EDITOR,
            affiliation="UEH",
            order=1,
        )

        # Tài liệu mẫu (gồm cả FORM_4 để kiểm tra quyền tải của customer)
        Document.objects.create(
            case=c3,
            doc_type=DocumentType.MANUSCRIPT,
            version=1,
            is_current=True,
            original_filename="ban_thao_chuyen_doi_so.pdf",
            mime_type="application/pdf",
            size_bytes=2048000,
            sha256="0" * 64,
            storage_backend="local",
            storage_ref=f"cases/{c3.pk}/MANUSCRIPT/v1_ban_thao_chuyen_doi_so.pdf",
            uploaded_by=customer_b,
        )
        Document.objects.create(
            case=c3,
            doc_type=DocumentType.FORM_4,
            form_code="MAU_4",
            version=1,
            is_current=True,
            original_filename="mau_4_duyet_noi_bo.pdf",
            mime_type="application/pdf",
            size_bytes=512000,
            sha256="1" * 64,
            storage_backend="local",
            storage_ref=f"cases/{c3.pk}/FORM_4/v1_mau_4_duyet_noi_bo.pdf",
            uploaded_by=editor_plain,
        )

        # 4. Khoản phải thu / đã thu ở các tình trạng khác nhau (chưa thu, thu một phần, thu đủ, quá hạn)
        # Khoản 1: Đã thu đủ (PAID)
        r_paid = create_receivable(
            actor=editor_fin,
            case=c5,
            fee_type=fee_ql,
            amount=Decimal("12000000"),
            description="Phí quản lý xuất bản sách chuyên khảo",
            due_date=today - timedelta(days=50),
        )
        create_collection(
            actor=editor_fin,
            receivable=r_paid,
            paid_date=today - timedelta(days=52),
            amount=Decimal("12000000"),
            method=CollectionMethod.TRANSFER,
            reference="UNC-2026-001",
        )

        # Khoản 2: Thu một phần, chưa quá hạn (PARTIAL)
        r_partial = create_receivable(
            actor=editor_fin,
            case=c4,
            fee_type=fee_bt,
            amount=Decimal("15000000"),
            description="Phí biên tập bản thảo định lượng",
            due_date=today + timedelta(days=15),
        )
        create_collection(
            actor=editor_fin,
            receivable=r_partial,
            paid_date=today - timedelta(days=5),
            amount=Decimal("6000000"),
            method=CollectionMethod.TRANSFER,
            reference="UNC-2026-014",
        )

        # Khoản 3: Chưa thu, chưa đến hạn (UNPAID)
        create_receivable(
            actor=editor_fin,
            case=c3,
            fee_type=fee_ql,
            amount=Decimal("8000000"),
            description="Phí quản lý xuất bản liên kết",
            due_date=today + timedelta(days=20),
        )

        # Khoản 4: Quá hạn 45 ngày (OVERDUE / D31_60)
        create_receivable(
            actor=editor_fin,
            case=c4,
            fee_type=fee_ql,
            amount=Decimal("10000000"),
            description="Phí quản lý xuất bản đợt 1",
            due_date=today - timedelta(days=45),
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Đã khởi tạo xong dữ liệu mẫu M0 (1 admin, 2 editor, 2 customer, 5 hồ sơ, 4 khoản phải thu)."
            )
        )
