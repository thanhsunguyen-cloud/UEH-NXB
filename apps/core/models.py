"""Toàn bộ mô hình dữ liệu lõi của UEH Publishing Portal V2 (mục 5 & 9).

QUY ƯỚC BẮT BUỘC:
- Mọi model có created_at, updated_at tự động.
- Không lưu số CCCD, ngày cấp, nơi cấp trong database.
- Không có bất kỳ model hoặc trường nào về in ấn, phát hành, hạch toán kế toán.
- Không sửa/xóa AuditEvent, StatusHistory, Document, Receivable, Collection.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.codes import generate_temp_code, normalize_isbn, validate_isbn13


class TimeStampedModel(models.Model):
    """Lớp cơ sở trừu tượng bổ sung created_at và updated_at tự động cho mọi model."""

    created_at = models.DateTimeField(_("Ngày tạo"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Ngày cập nhật"), auto_now=True)

    class Meta:
        abstract = True


class NoDeleteQuerySet(models.QuerySet):
    """Chặn xóa hàng loạt ở cấp QuerySet đối với các bảng bất biến không được xóa (S5)."""

    def delete(self):
        raise PermissionDenied(
            _("Không được phép xóa hàng loạt bản ghi %(model)s.") % {"model": self.model.__name__}
        )


class NoDeleteManager(models.Manager.from_queryset(NoDeleteQuerySet)):
    """Manager dùng chung cho Document, Receivable, Collection (chặn delete hàng loạt)."""


class AppendOnlyQuerySet(NoDeleteQuerySet):
    """Chặn cả xóa hàng loạt lẫn cập nhật hàng loạt ở cấp QuerySet (S5)."""

    def update(self, **kwargs):
        raise PermissionDenied(
            _("Bản ghi %(model)s chỉ được ghi thêm, không được cập nhật hàng loạt.")
            % {"model": self.model.__name__}
        )


class AppendOnlyManager(models.Manager.from_queryset(AppendOnlyQuerySet)):
    """Manager dùng chung cho AuditEvent và StatusHistory (chỉ ghi thêm)."""


# ---------------------------------------------------------------------------
# 5.2 Danh mục do Admin quản lý: Category, Field, FeeType
# ---------------------------------------------------------------------------


class Category(TimeStampedModel):
    """Thể loại sách."""

    name = models.CharField(_("Tên thể loại"), max_length=200, unique=True)
    is_active = models.BooleanField(_("Đang sử dụng"), default=True)
    sort_order = models.PositiveIntegerField(_("Thứ tự hiển thị"), default=0)

    class Meta:
        verbose_name = _("Thể loại sách")
        verbose_name_plural = _("Thể loại sách")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Field(TimeStampedModel):
    """Lĩnh vực chuyên môn (dùng cho Mẫu 5)."""

    name = models.CharField(_("Tên lĩnh vực"), max_length=200, unique=True)
    is_active = models.BooleanField(_("Đang sử dụng"), default=True)
    sort_order = models.PositiveIntegerField(_("Thứ tự hiển thị"), default=0)

    class Meta:
        verbose_name = _("Lĩnh vực")
        verbose_name_plural = _("Lĩnh vực")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class FeeType(TimeStampedModel):
    """Danh mục loại phí dịch vụ xuất bản (tuyệt đối không có phí in ấn, phát hành)."""

    name = models.CharField(_("Tên loại phí"), max_length=200, unique=True)
    is_active = models.BooleanField(_("Đang sử dụng"), default=True)
    sort_order = models.PositiveIntegerField(_("Thứ tự hiển thị"), default=0)

    class Meta:
        verbose_name = _("Loại phí dịch vụ xuất bản")
        verbose_name_plural = _("Loại phí dịch vụ xuất bản")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# 5.3 PublicationCase (1 hồ sơ = 1 đầu sách)
# ---------------------------------------------------------------------------


class CaseStatus(models.TextChoices):
    """Danh sách 13 trạng thái chuẩn theo mục 7.1."""

    DRAFT = "DRAFT", _("Nháp")
    SUBMITTED = "SUBMITTED", _("Đã nộp")
    NEED_SUPPLEMENT = "NEED_SUPPLEMENT", _("Cần bổ sung")
    ACCEPTED = "ACCEPTED", _("Đã tiếp nhận")
    EDITING = "EDITING", _("Đang biên tập")
    REVISION_REQUIRED = "REVISION_REQUIRED", _("Trả tác giả chỉnh sửa")
    REVIEW_APPROVED = "REVIEW_APPROVED", _("Đã duyệt bản thảo")
    REJECTED = "REJECTED", _("Từ chối")
    REGISTERED = "REGISTERED", _("Đã đăng ký xuất bản")
    DECISION_ISSUED = "DECISION_ISSUED", _("Đã có quyết định xuất bản")
    DEPOSITED = "DEPOSITED", _("Đã nộp lưu chiểu")
    COMPLETED = "COMPLETED", _("Hoàn tất")
    ARCHIVED = "ARCHIVED", _("Lưu trữ")


class PublicationMode(models.TextChoices):
    SELF = "SELF", _("Tự xuất bản")
    LINKED = "LINKED", _("Liên kết")


class PublicationCase(TimeStampedModel):
    """Hồ sơ xuất bản (1 hồ sơ tương ứng 1 đầu sách)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    temp_code = models.CharField(
        _("Mã tạm"),
        max_length=20,
        unique=True,
        default=generate_temp_code,
    )
    nxb_code = models.CharField(_("Mã NXB"), max_length=20, unique=True, null=True, blank=True)
    isbn = models.CharField(
        _("Mã ISBN-13"),
        max_length=13,
        unique=True,
        null=True,
        blank=True,
        validators=[validate_isbn13],
    )
    status = models.CharField(
        _("Trạng thái"),
        max_length=30,
        choices=CaseStatus.choices,
        default=CaseStatus.DRAFT,
        db_index=True,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_cases",
        verbose_name=_("Người đại diện (Chủ hồ sơ)"),
    )
    primary_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_cases",
        verbose_name=_("Biên tập viên phụ trách chính"),
    )
    title = models.CharField(_("Tên tác phẩm"), max_length=500)
    subtitle = models.CharField(_("Phụ đề"), max_length=500, blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Thể loại"),
    )
    field = models.ForeignKey(
        Field,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Lĩnh vực"),
    )
    language = models.CharField(_("Ngôn ngữ"), max_length=50, default="Tiếng Việt")
    translated_from = models.CharField(_("Ngôn ngữ gốc"), max_length=50, blank=True)
    edition_number = models.PositiveSmallIntegerField(_("Lần xuất bản"), default=1)
    is_reprint = models.BooleanField(_("Tái bản"), default=False)
    publication_mode = models.CharField(
        _("Hình thức xuất bản"),
        max_length=20,
        choices=PublicationMode.choices,
        default=PublicationMode.SELF,
    )
    partner_name = models.CharField(_("Đơn vị liên kết"), max_length=255, blank=True)
    summary = models.TextField(_("Tóm tắt nội dung"), blank=True)
    page_count = models.PositiveIntegerField(_("Số trang"), null=True, blank=True)
    book_size = models.CharField(_("Khổ sách"), max_length=50, blank=True)

    submitted_at = models.DateTimeField(_("Thời điểm nộp"), null=True, blank=True)
    accepted_at = models.DateTimeField(_("Thời điểm tiếp nhận"), null=True, blank=True)
    registration_number = models.CharField(
        _("Số xác nhận đăng ký xuất bản"), max_length=100, blank=True
    )
    registration_date = models.DateField(_("Ngày xác nhận đăng ký xuất bản"), null=True, blank=True)
    decision_number = models.CharField(_("Số quyết định xuất bản"), max_length=100, blank=True)
    decision_date = models.DateField(_("Ngày quyết định xuất bản"), null=True, blank=True)
    contract_number = models.CharField(_("Số hợp đồng liên kết"), max_length=100, blank=True)
    contract_date = models.DateField(_("Ngày hợp đồng liên kết"), null=True, blank=True)
    deposit_date = models.DateField(_("Ngày nộp lưu chiểu"), null=True, blank=True)

    # Cờ nội bộ chỉ được bật bởi apps.core.workflow.change_status()
    _allow_status_mutation: bool = False

    class Meta:
        verbose_name = _("Hồ sơ xuất bản")
        verbose_name_plural = _("Hồ sơ xuất bản")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.display_code} — {self.title}"

    def save(self, *args, **kwargs) -> None:
        if self.isbn:
            self.isbn = normalize_isbn(self.isbn)
        else:
            self.isbn = None

        if not self._state.adding and not self._allow_status_mutation:
            previous = (
                PublicationCase.objects.filter(pk=self.pk).values_list("status", "nxb_code").first()
            )
            if previous is not None:
                prev_status, prev_nxb_code = previous
                if prev_status != self.status:
                    raise ValidationError(
                        _(
                            "Không được gán trực tiếp case.status; bắt buộc gọi apps.core.workflow.change_status()."
                        )
                    )
                if prev_nxb_code and self.nxb_code != prev_nxb_code:
                    raise ValidationError(_("Mã NXB sau khi cấp không bao giờ được phép thay đổi."))

        super().save(*args, **kwargs)

    @property
    def display_code(self) -> str:
        """Mã hiển thị ưu tiên: isbn -> nxb_code -> temp_code (mục 5.3)."""
        return self.isbn or self.nxb_code or self.temp_code

    def clean(self) -> None:
        if self.isbn:
            self.isbn = normalize_isbn(self.isbn)
        if self.publication_mode == PublicationMode.LINKED and not self.partner_name.strip():
            raise ValidationError(
                {
                    "partner_name": _(
                        "Bắt buộc nhập tên đơn vị liên kết khi chọn hình thức Liên kết."
                    )
                }
            )


# ---------------------------------------------------------------------------
# 5.4 Contributor (thông tin thư mục, không liên kết User)
# ---------------------------------------------------------------------------


class ContributorRole(models.TextChoices):
    AUTHOR = "AUTHOR", _("Tác giả")
    CHIEF_EDITOR = "CHIEF_EDITOR", _("Chủ biên")
    CO_AUTHOR = "CO_AUTHOR", _("Đồng tác giả")
    TRANSLATOR = "TRANSLATOR", _("Dịch giả")
    COMPILER = "COMPILER", _("Biên soạn")


class Contributor(TimeStampedModel):
    """Tác giả / đồng tác giả của tác phẩm (chỉ phục vụ thư mục, không có quyền trên hồ sơ)."""

    case = models.ForeignKey(
        PublicationCase,
        on_delete=models.CASCADE,
        related_name="contributors",
        verbose_name=_("Hồ sơ"),
    )
    full_name = models.CharField(_("Họ và tên"), max_length=200)
    academic_title = models.CharField(_("Học hàm / Học vị"), max_length=100, blank=True)
    role = models.CharField(_("Vai trò"), max_length=20, choices=ContributorRole.choices)
    email = models.EmailField(_("Email"), blank=True)
    phone = models.CharField(_("Số điện thoại"), max_length=20, blank=True)
    order = models.PositiveSmallIntegerField(_("Thứ tự hiển thị"), default=1)
    affiliation = models.CharField(_("Đơn vị công tác"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("Tác giả tác phẩm")
        verbose_name_plural = _("Tác giả tác phẩm")
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.get_role_display()})"


# ---------------------------------------------------------------------------
# 5.5 Document (tài liệu và phiên bản — không xóa, không ghi đè)
# ---------------------------------------------------------------------------


class DocumentType(models.TextChoices):
    MANUSCRIPT = "MANUSCRIPT", _("Bản thảo")
    FORM_1 = "FORM_1", _("Mẫu 1")
    FORM_2 = "FORM_2", _("Mẫu 2")
    FORM_3 = "FORM_3", _("Mẫu 3")
    FORM_4 = "FORM_4", _("Mẫu 4 (Phiếu duyệt bản thảo)")
    FORM_5 = "FORM_5", _("Mẫu 5")
    FORM_6 = "FORM_6", _("Mẫu 6")
    FORM_7 = "FORM_7", _("Mẫu 7 (Hợp đồng liên kết)")
    FORM_9 = "FORM_9", _("Mẫu 9 (Nộp lưu chiểu)")
    REGISTRATION_PROOF = "REGISTRATION_PROOF", _("Minh chứng đăng ký xuất bản")
    DEPOSIT_PROOF = "DEPOSIT_PROOF", _("Minh chứng nộp lưu chiểu")
    OTHER = "OTHER", _("Tài liệu khác")


class Document(TimeStampedModel):
    """Tài liệu đính kèm hồ sơ, lưu phiên bản bất biến (không xóa, không ghi đè)."""

    case = models.ForeignKey(
        PublicationCase,
        on_delete=models.PROTECT,
        related_name="documents",
        verbose_name=_("Hồ sơ"),
    )
    doc_type = models.CharField(_("Loại tài liệu"), max_length=30, choices=DocumentType.choices)
    form_code = models.CharField(_("Mã biểu mẫu"), max_length=30, blank=True)
    version = models.PositiveIntegerField(_("Phiên bản"))
    is_current = models.BooleanField(_("Bản hiện hành"), default=True)
    original_filename = models.CharField(_("Tên tệp gốc"), max_length=255)
    mime_type = models.CharField(_("Kiểu MIME"), max_length=100)
    size_bytes = models.PositiveBigIntegerField(_("Dung lượng (bytes)"))
    sha256 = models.CharField(_("Mã băm SHA-256"), max_length=64)
    storage_backend = models.CharField(_("Kho lưu trữ"), max_length=20, default="local")
    storage_ref = models.CharField(_("Đường dẫn / Mã lưu trữ"), max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_documents",
        verbose_name=_("Người tải lên"),
    )
    uploaded_at = models.DateTimeField(_("Thời điểm tải lên"), default=timezone.now)
    note = models.CharField(_("Ghi chú"), max_length=500, blank=True)

    objects = NoDeleteManager()

    class Meta:
        verbose_name = _("Tài liệu hồ sơ")
        verbose_name_plural = _("Tài liệu hồ sơ")
        ordering = ["-uploaded_at", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "doc_type", "form_code", "version"],
                name="uniq_document_case_type_form_version",
            )
        ]

    def __str__(self) -> str:
        return f"{self.case.display_code} — {self.doc_type} v{self.version}"

    def delete(self, *args, **kwargs):
        raise PermissionDenied(_("Không được phép xóa tài liệu đã tải lên (mục 5.5)."))


# ---------------------------------------------------------------------------
# 5.6 ManuscriptReview
# ---------------------------------------------------------------------------


class ReviewResult(models.TextChoices):
    APPROVED = "APPROVED", _("Đồng ý xuất bản")
    REVISION_REQUIRED = "REVISION_REQUIRED", _("Yêu cầu chỉnh sửa")
    REJECTED = "REJECTED", _("Từ chối xuất bản")


class ManuscriptReview(TimeStampedModel):
    """Kết quả duyệt bản thảo theo Mẫu 4."""

    case = models.ForeignKey(
        PublicationCase,
        on_delete=models.PROTECT,
        related_name="reviews",
        verbose_name=_("Hồ sơ"),
    )
    manuscript = models.ForeignKey(
        Document,
        on_delete=models.PROTECT,
        related_name="manuscript_reviews",
        verbose_name=_("Phiên bản bản thảo được duyệt"),
    )
    form4 = models.ForeignKey(
        Document,
        on_delete=models.PROTECT,
        related_name="form4_reviews",
        verbose_name=_("Mẫu 4 đã ký"),
    )
    result = models.CharField(_("Kết quả duyệt"), max_length=30, choices=ReviewResult.choices)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="confirmed_reviews",
        verbose_name=_("Biên tập viên xác nhận"),
    )
    confirmed_at = models.DateTimeField(_("Thời điểm xác nhận"), default=timezone.now)
    note = models.TextField(_("Ghi chú"), blank=True)

    class Meta:
        verbose_name = _("Kết quả duyệt bản thảo")
        verbose_name_plural = _("Kết quả duyệt bản thảo")
        ordering = ["-confirmed_at", "-id"]

    def __str__(self) -> str:
        return f"{self.case.display_code} — {self.get_result_display()}"

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        errors = {}
        if self.manuscript_id:
            if self.manuscript.case_id != self.case_id:
                errors["manuscript"] = _("Bản thảo được duyệt phải thuộc cùng hồ sơ.")
            if self.manuscript.doc_type != DocumentType.MANUSCRIPT:
                errors["manuscript"] = _("Tài liệu bản thảo phải có loại MANUSCRIPT.")
        if self.form4_id:
            if self.form4.case_id != self.case_id:
                errors["form4"] = _("Mẫu 4 phải thuộc cùng hồ sơ.")
            if self.form4.doc_type != DocumentType.FORM_4:
                errors["form4"] = _("Tài liệu phiếu duyệt phải có loại FORM_4.")
        if errors:
            raise ValidationError(errors)


# ---------------------------------------------------------------------------
# 5.7 CaseNote, 5.8 SupplementRequest, 5.9 StatusHistory
# ---------------------------------------------------------------------------


class NoteVisibility(models.TextChoices):
    INTERNAL = "INTERNAL", _("Nội bộ (chỉ nhân sự thấy)")
    CUSTOMER = "CUSTOMER", _("Trao đổi với khách hàng")


class CaseNote(TimeStampedModel):
    """Ghi chú nội bộ hoặc trao đổi với khách hàng trên hồ sơ."""

    case = models.ForeignKey(
        PublicationCase,
        on_delete=models.CASCADE,
        related_name="notes",
        verbose_name=_("Hồ sơ"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="case_notes",
        verbose_name=_("Người ghi"),
    )
    body = models.TextField(_("Nội dung"))
    visibility = models.CharField(
        _("Phạm vi hiển thị"),
        max_length=20,
        choices=NoteVisibility.choices,
        default=NoteVisibility.INTERNAL,
    )

    class Meta:
        verbose_name = _("Ghi chú hồ sơ")
        verbose_name_plural = _("Ghi chú hồ sơ")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.case.display_code} ({self.visibility})"


class SupplementStatus(models.TextChoices):
    OPEN = "OPEN", _("Đang chờ bổ sung")
    RESOLVED = "RESOLVED", _("Đã bổ sung")


class SupplementRequest(TimeStampedModel):
    """Yêu cầu bổ sung hồ sơ do biên tập viên gửi cho khách hàng."""

    case = models.ForeignKey(
        PublicationCase,
        on_delete=models.CASCADE,
        related_name="supplement_requests",
        verbose_name=_("Hồ sơ"),
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_supplements",
        verbose_name=_("Biên tập viên yêu cầu"),
    )
    message = models.TextField(_("Nội dung yêu cầu bổ sung"))
    status = models.CharField(
        _("Trạng thái"),
        max_length=20,
        choices=SupplementStatus.choices,
        default=SupplementStatus.OPEN,
    )
    resolved_at = models.DateTimeField(_("Thời điểm hoàn tất bổ sung"), null=True, blank=True)

    class Meta:
        verbose_name = _("Yêu cầu bổ sung")
        verbose_name_plural = _("Yêu cầu bổ sung")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.case.display_code} — {self.get_status_display()}"


class StatusHistory(TimeStampedModel):
    """Lịch sử chuyển trạng thái hồ sơ (chỉ ghi thêm — mục 5.9)."""

    case = models.ForeignKey(
        PublicationCase,
        on_delete=models.PROTECT,
        related_name="status_history",
        verbose_name=_("Hồ sơ"),
    )
    from_status = models.CharField(_("Từ trạng thái"), max_length=30, choices=CaseStatus.choices)
    to_status = models.CharField(_("Sang trạng thái"), max_length=30, choices=CaseStatus.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="status_changes",
        verbose_name=_("Người thực hiện"),
    )
    note = models.TextField(_("Ghi chú"), blank=True)
    at = models.DateTimeField(_("Thời điểm"), default=timezone.now)

    objects = AppendOnlyManager()

    class Meta:
        verbose_name = _("Lịch sử trạng thái")
        verbose_name_plural = _("Lịch sử trạng thái")
        ordering = ["-at", "-id"]

    def __str__(self) -> str:
        return f"{self.case.display_code}: {self.from_status} -> {self.to_status}"

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise PermissionDenied(_("StatusHistory chỉ được ghi thêm, không được cập nhật."))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied(_("StatusHistory chỉ được ghi thêm, không được xóa."))


# ---------------------------------------------------------------------------
# 5.10 FormTemplate, 5.11 CodeSequence, 5.12 AuditEvent
# ---------------------------------------------------------------------------


class FormTemplate(TimeStampedModel):
    """Biểu mẫu trống cho khách hàng tải về; nhiều phiên bản theo code."""

    code = models.CharField(_("Mã biểu mẫu"), max_length=30, db_index=True)
    name = models.CharField(_("Tên biểu mẫu"), max_length=255)
    version = models.CharField(_("Phiên bản"), max_length=30)
    effective_from = models.DateField(_("Ngày hiệu lực"))
    is_active = models.BooleanField(_("Đang áp dụng"), default=True)
    storage_backend = models.CharField(_("Kho lưu trữ"), max_length=20, default="local")
    storage_ref = models.CharField(_("Đường dẫn / Mã lưu trữ"), max_length=255)
    original_filename = models.CharField(_("Tên tệp gốc"), max_length=255)

    class Meta:
        verbose_name = _("Biểu mẫu tải về")
        verbose_name_plural = _("Biểu mẫu tải về")
        ordering = ["code", "-effective_from", "-id"]

    def __str__(self) -> str:
        return f"{self.code} v{self.version} — {self.name}"


class CodeSequence(TimeStampedModel):
    """Bộ đếm tuần tự theo (prefix, year) để cấp mã NXB an toàn giao dịch."""

    prefix = models.CharField(_("Tiền tố"), max_length=16, default="NXB")
    year = models.PositiveIntegerField(_("Năm"))
    last_number = models.PositiveIntegerField(_("Số thứ tự gần nhất"), default=0)

    class Meta:
        verbose_name = _("Chuỗi cấp mã")
        verbose_name_plural = _("Chuỗi cấp mã")
        constraints = [
            models.UniqueConstraint(
                fields=["prefix", "year"], name="uniq_code_sequence_prefix_year"
            )
        ]

    def __str__(self) -> str:
        return f"{self.prefix}-{self.year}: {self.last_number}"


class AuditEvent(TimeStampedModel):
    """Nhật ký thao tác bất biến (chỉ ghi thêm — mục 5.12)."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_events",
        verbose_name=_("Người thực hiện"),
    )
    action = models.CharField(_("Hành động"), max_length=50, db_index=True)
    object_type = models.CharField(_("Loại đối tượng"), max_length=50)
    object_id = models.CharField(_("Mã đối tượng"), max_length=64)
    case = models.ForeignKey(
        PublicationCase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        verbose_name=_("Hồ sơ liên quan"),
    )
    data = models.JSONField(_("Dữ liệu chi tiết"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_("Địa chỉ IP"), null=True, blank=True)
    at = models.DateTimeField(_("Thời điểm"), default=timezone.now, db_index=True)

    objects = AppendOnlyManager()

    class Meta:
        verbose_name = _("Nhật ký thao tác")
        verbose_name_plural = _("Nhật ký thao tác")
        ordering = ["-at", "-id"]

    def __str__(self) -> str:
        return f"[{self.action}] {self.object_type}:{self.object_id}"

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise PermissionDenied(
                _("AuditEvent chỉ được ghi thêm, từ chối cập nhật bản ghi đã có.")
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied(_("AuditEvent chỉ được ghi thêm, không được phép xóa."))


# ---------------------------------------------------------------------------
# 5.13 Receivable & 5.14 Collection (sổ theo dõi phí dịch vụ xuất bản)
# ---------------------------------------------------------------------------


class Receivable(TimeStampedModel):
    """Khoản phải thu phí dịch vụ xuất bản (không xóa; sửa sai bằng bút toán điều chỉnh)."""

    case = models.ForeignKey(
        PublicationCase,
        on_delete=models.PROTECT,
        related_name="receivables",
        verbose_name=_("Hồ sơ"),
    )
    fee_type = models.ForeignKey(
        FeeType,
        on_delete=models.PROTECT,
        related_name="receivables",
        verbose_name=_("Loại phí"),
    )
    description = models.CharField(_("Diễn giải"), max_length=255, blank=True)
    amount = models.DecimalField(_("Số tiền (VNĐ)"), max_digits=15, decimal_places=0)
    payer_name = models.CharField(_("Đơn vị / Tác giả phải trả"), max_length=255)
    contract_number = models.CharField(_("Số hợp đồng"), max_length=100, blank=True)
    invoice_number = models.CharField(_("Số chứng từ / biên lai"), max_length=100, blank=True)
    invoice_date = models.DateField(_("Ngày chứng từ"), null=True, blank=True)
    due_date = models.DateField(_("Hạn thanh toán"), null=True, blank=True)
    is_adjustment = models.BooleanField(_("Bút toán điều chỉnh"), default=False)
    adjusts = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adjustments",
        verbose_name=_("Khoản bị điều chỉnh"),
    )
    note = models.TextField(_("Ghi chú"), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_receivables",
        verbose_name=_("Người tạo"),
    )

    objects = NoDeleteManager()

    class Meta:
        verbose_name = _("Khoản phải thu")
        verbose_name_plural = _("Khoản phải thu")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.case.display_code} — {self.fee_type.name}: {self.amount:,} VNĐ"

    def save(self, *args, **kwargs) -> None:
        if not self.payer_name and self.case_id:
            self.payer_name = (
                self.case.partner_name or self.case.owner.full_name or self.case.owner.email
            )
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        if self.amount is None:
            raise ValidationError({"amount": _("Số tiền là bắt buộc.")})
        if self.is_adjustment:
            if not self.note.strip():
                raise ValidationError(
                    {"note": _("Bút toán điều chỉnh bắt buộc phải có ghi chú lý do.")}
                )
            if self.amount == Decimal("0"):
                raise ValidationError({"amount": _("Số tiền bút toán điều chỉnh phải khác 0.")})
        elif self.amount <= Decimal("0"):
            raise ValidationError(
                {"amount": _("Số tiền phải thu phải lớn hơn 0 (trừ bút toán điều chỉnh).")}
            )

    def delete(self, *args, **kwargs):
        raise PermissionDenied(
            _("Không được xóa khoản phải thu; hãy tạo bút toán điều chỉnh có ghi chú.")
        )


class CollectionMethod(models.TextChoices):
    TRANSFER = "TRANSFER", _("Chuyển khoản")
    CASH = "CASH", _("Tiền mặt")
    OTHER = "OTHER", _("Khác")


class Collection(TimeStampedModel):
    """Khoản đã thu tương ứng với một Receivable (không xóa; sửa sai bằng bút toán đảo)."""

    receivable = models.ForeignKey(
        Receivable,
        on_delete=models.PROTECT,
        related_name="collections",
        verbose_name=_("Khoản phải thu"),
    )
    paid_date = models.DateField(_("Ngày thu"))
    amount = models.DecimalField(_("Số tiền đã thu (VNĐ)"), max_digits=15, decimal_places=0)
    method = models.CharField(
        _("Phương thức"),
        max_length=20,
        choices=CollectionMethod.choices,
        default=CollectionMethod.TRANSFER,
    )
    reference = models.CharField(_("Số chứng từ"), max_length=100, blank=True)
    is_adjustment = models.BooleanField(_("Bút toán đảo / điều chỉnh"), default=False)
    note = models.TextField(_("Ghi chú"), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_collections",
        verbose_name=_("Người ghi nhận"),
    )

    objects = NoDeleteManager()

    class Meta:
        verbose_name = _("Khoản đã thu")
        verbose_name_plural = _("Khoản đã thu")
        ordering = ["-paid_date", "-id"]

    def __str__(self) -> str:
        return f"Thu {self.amount:,} VNĐ ({self.paid_date})"

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        if self.amount is None:
            raise ValidationError({"amount": _("Số tiền đã thu là bắt buộc.")})
        if self.is_adjustment:
            if not self.note.strip():
                raise ValidationError({"note": _("Bút toán đảo bắt buộc phải có ghi chú lý do.")})
            if self.amount == Decimal("0"):
                raise ValidationError({"amount": _("Số tiền bút toán đảo phải khác 0.")})
        elif self.amount <= Decimal("0"):
            raise ValidationError(
                {"amount": _("Số tiền đã thu phải lớn hơn 0 (trừ bút toán đảo).")}
            )

    def delete(self, *args, **kwargs):
        raise PermissionDenied(_("Không được xóa khoản đã thu; hãy tạo bút toán đảo có ghi chú."))


# ---------------------------------------------------------------------------
# Mục 9: UploadSession (quản lý phiên tải tệp chia nhỏ <= 8 MiB/chunk)
# ---------------------------------------------------------------------------


class UploadSessionStatus(models.TextChoices):
    OPEN = "OPEN", _("Đang tải lên")
    DONE = "DONE", _("Hoàn tất")
    ABORTED = "ABORTED", _("Đã hủy")


class UploadSession(TimeStampedModel):
    """Phiên tải tài liệu chia phần nhằm tuân thủ giới hạn 32 MiB/request của Cloud Run."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        PublicationCase,
        on_delete=models.CASCADE,
        related_name="upload_sessions",
        verbose_name=_("Hồ sơ"),
    )
    doc_type = models.CharField(_("Loại tài liệu"), max_length=30, choices=DocumentType.choices)
    form_code = models.CharField(_("Mã biểu mẫu"), max_length=30, blank=True)
    filename = models.CharField(_("Tên tệp"), max_length=255)
    mime_type = models.CharField(_("Kiểu MIME"), max_length=100, default="application/octet-stream")
    total_size = models.PositiveBigIntegerField(_("Tổng dung lượng (bytes)"))
    received_bytes = models.PositiveBigIntegerField(_("Số byte đã nhận"), default=0)
    backend_ref = models.CharField(_("Mã tham chiếu backend"), max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="upload_sessions",
        verbose_name=_("Người tải lên"),
    )
    expires_at = models.DateTimeField(_("Thời điểm hết hạn"))
    status = models.CharField(
        _("Trạng thái phiên"),
        max_length=20,
        choices=UploadSessionStatus.choices,
        default=UploadSessionStatus.OPEN,
        db_index=True,
    )

    class Meta:
        verbose_name = _("Phiên tải tệp chia phần")
        verbose_name_plural = _("Phiên tải tệp chia phần")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"UploadSession {self.pk} ({self.filename} — {self.status})"
