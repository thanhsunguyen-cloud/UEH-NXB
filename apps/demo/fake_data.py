"""Dữ liệu giả viết cứng cho bản demo M2/M3.

Toàn bộ tên sách, tác giả, đối tác, số liệu dưới đây là HƯ CẤU, chỉ để biên tập viên bấm thử.
Không đọc/ghi database; mã trạng thái và nhãn lấy theo bảng 7.1 của gói M0 (CaseStatus).
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date
from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from apps.core.models import (
    CaseStatus,
    ContributorRole,
    DocumentType,
    PublicationMode,
    ReviewResult,
)

# Ngày "hôm nay" cố định để tuổi nợ và dòng thời gian luôn ổn định khi demo.
DEMO_TODAY = date(2026, 11, 26)

DEMO_CUSTOMER_NAME = "Trần Thị Mai (hư cấu)"
EDITORS = OrderedDict(
    [
        ("btv-khoa", "Lê Minh Khoa"),
        ("btv-ha", "Phạm Thu Hà"),
    ]
)

# Nhãn dễ hiểu cho khách hàng (thay cho nhãn nội bộ của bảng 7.1).
CUSTOMER_STATUS_LABELS = {
    CaseStatus.DRAFT: _("Bản nháp – chưa nộp"),
    CaseStatus.SUBMITTED: _("Đã nộp – chờ NXB tiếp nhận"),
    CaseStatus.NEED_SUPPLEMENT: _("Cần bổ sung hồ sơ"),
    CaseStatus.ACCEPTED: _("NXB đã tiếp nhận"),
    CaseStatus.EDITING: _("NXB đang biên tập"),
    CaseStatus.REVISION_REQUIRED: _("Cần chỉnh sửa bản thảo"),
    CaseStatus.REVIEW_APPROVED: _("Bản thảo đã được duyệt"),
    CaseStatus.REJECTED: _("Không được duyệt xuất bản"),
    CaseStatus.REGISTERED: _("NXB đã đăng ký xuất bản"),
    CaseStatus.DECISION_ISSUED: _("Đã có quyết định xuất bản"),
    CaseStatus.DEPOSITED: _("Đã nộp lưu chiểu"),
    CaseStatus.COMPLETED: _("Hoàn tất"),
    CaseStatus.ARCHIVED: _("Đã lưu trữ"),
}

# Màu nhãn Bootstrap theo trạng thái.
STATUS_COLORS = {
    CaseStatus.DRAFT: "secondary",
    CaseStatus.SUBMITTED: "primary",
    CaseStatus.NEED_SUPPLEMENT: "warning",
    CaseStatus.ACCEPTED: "info",
    CaseStatus.EDITING: "info",
    CaseStatus.REVISION_REQUIRED: "warning",
    CaseStatus.REVIEW_APPROVED: "success",
    CaseStatus.REJECTED: "danger",
    CaseStatus.REGISTERED: "primary",
    CaseStatus.DECISION_ISSUED: "primary",
    CaseStatus.DEPOSITED: "success",
    CaseStatus.COMPLETED: "success",
    CaseStatus.ARCHIVED: "dark",
}

# Bảng chuyển trạng thái hợp lệ cho biên tập viên (mục 7.2 gói M0) – chỉ để hiển thị nút.
EDITOR_TRANSITIONS = {
    CaseStatus.SUBMITTED: [CaseStatus.NEED_SUPPLEMENT, CaseStatus.ACCEPTED],
    CaseStatus.ACCEPTED: [CaseStatus.EDITING],
    CaseStatus.EDITING: [
        CaseStatus.REVIEW_APPROVED,
        CaseStatus.REVISION_REQUIRED,
        CaseStatus.REJECTED,
    ],
    CaseStatus.REVISION_REQUIRED: [CaseStatus.EDITING],
    CaseStatus.REVIEW_APPROVED: [CaseStatus.REGISTERED],
    CaseStatus.REGISTERED: [CaseStatus.DECISION_ISSUED],
    CaseStatus.DECISION_ISSUED: [CaseStatus.DEPOSITED],
    CaseStatus.DEPOSITED: [CaseStatus.COMPLETED],
    CaseStatus.COMPLETED: [CaseStatus.ARCHIVED],
    CaseStatus.REJECTED: [CaseStatus.ARCHIVED],
}

# Nhóm "Hồ sơ cần xử lý" của biên tập viên: (mã nhóm, tên nhóm, mô tả, hàm lọc).
QUEUE_GROUPS = [
    (
        "moi-nop",
        _("Mới nộp – chờ tiếp nhận"),
        _("Kiểm tra hồ sơ, tiếp nhận (cấp mã NXB) hoặc yêu cầu bổ sung."),
        lambda c: c["status"] == CaseStatus.SUBMITTED and not c.get("resubmitted"),
    ),
    (
        "khach-da-bo-sung",
        _("Khách đã bổ sung"),
        _("Khách hàng đã nộp lại sau yêu cầu bổ sung; xem phần đã bổ sung."),
        lambda c: c["status"] == CaseStatus.SUBMITTED and c.get("resubmitted"),
    ),
    (
        "cho-duyet",
        _("Đang biên tập – chờ kết quả Mẫu 4"),
        _("Duyệt bản thảo và xác nhận Mẫu 4 đúng hồ sơ."),
        lambda c: c["status"] in (CaseStatus.ACCEPTED, CaseStatus.EDITING),
    ),
    (
        "cho-dang-ky",
        _("Chờ đăng ký xuất bản"),
        _("Bản thảo đã duyệt: nhập ISBN, số XNĐK, tải Mẫu 5."),
        lambda c: c["status"] == CaseStatus.REVIEW_APPROVED,
    ),
    (
        "cho-quyet-dinh-luu-chieu",
        _("Chờ quyết định / nộp lưu chiểu"),
        _("Nhập số QĐXB, Mẫu 6/7 hoặc Mẫu 9 và ngày nộp lưu chiểu."),
        lambda c: c["status"] in (CaseStatus.REGISTERED, CaseStatus.DECISION_ISSUED),
    ),
]


def _doc(doc_type, version, filename, uploaded, by, form_code=""):
    return {
        "doc_type": doc_type,
        "label": DocumentType(doc_type).label,
        "version": version,
        "filename": filename,
        "uploaded_at": uploaded,
        "uploaded_by": by,
        "form_code": form_code,
    }


def _hist(status, when, actor, note=""):
    return {
        "status": status,
        "label": CaseStatus(status).label,
        "customer_label": CUSTOMER_STATUS_LABELS[status],
        "date": when,
        "actor": actor,
        "note": note,
    }


def _author(order, name, role, email=""):
    return {
        "order": order,
        "name": name,
        "role": role,
        "role_label": ContributorRole(role).label,
        "email": email,
    }


def _note(visibility, author, when, text):
    return {"visibility": visibility, "author": author, "date": when, "text": text}


def _rec(fee, amount, collected, due):
    amount = Decimal(amount)
    collected = Decimal(collected)
    return {
        "fee": fee,
        "amount": amount,
        "collected": collected,
        "outstanding": amount - collected,
        "due_date": due,
    }


KH = DEMO_CUSTOMER_NAME
BTV_KHOA = EDITORS["btv-khoa"]
BTV_HA = EDITORS["btv-ha"]

CASES = [
    {
        "slug": "hs-01",
        "mine": True,
        "temp_code": "TMP-7QK2M9XA",
        "nxb_code": "",
        "isbn": "",
        "title": "Kinh tế học bên hiên nhà",
        "subtitle": "Những câu chuyện kinh tế đời thường",
        "mode": PublicationMode.SELF,
        "partner_name": "",
        "category": "Sách tham khảo",
        "owner": KH,
        "editor": "",
        "status": CaseStatus.DRAFT,
        "created": date(2026, 11, 20),
        "todo": _("Tải lên Mẫu 2, Mẫu 3 rồi bấm Nộp hồ sơ"),
        "authors": [
            _author(1, "Trần Thị Mai", ContributorRole.AUTHOR, "mai.tran@example.com"),
        ],
        "documents": [
            _doc(DocumentType.MANUSCRIPT, 1, "ban-thao-v1.docx", date(2026, 11, 20), KH),
        ],
        "history": [_hist(CaseStatus.DRAFT, date(2026, 11, 20), KH, "Tạo hồ sơ")],
        "notes": [],
        "supplements": [],
        "missing": [_("Chưa có Mẫu 2"), _("Chưa có Mẫu 3")],
        "receivables": [],
    },
    {
        "slug": "hs-02",
        "mine": True,
        "temp_code": "TMP-3HD8PZ1C",
        "nxb_code": "",
        "isbn": "",
        "title": "Quản trị dòng tiền cho doanh nghiệp nhỏ",
        "subtitle": "",
        "mode": PublicationMode.LINKED,
        "partner_name": "Công ty Sách Bình Minh (hư cấu)",
        "category": "Giáo trình",
        "owner": KH,
        "editor": "",
        "status": CaseStatus.SUBMITTED,
        "created": date(2026, 11, 10),
        "todo": "",
        "authors": [
            _author(1, "Trần Thị Mai", ContributorRole.CHIEF_EDITOR, "mai.tran@example.com"),
            _author(2, "Hoàng Gia Bảo", ContributorRole.CO_AUTHOR),
            _author(3, "Đỗ Ngọc Lan", ContributorRole.CO_AUTHOR),
        ],
        "documents": [
            _doc(DocumentType.MANUSCRIPT, 1, "dong-tien-ban-thao.pdf", date(2026, 11, 10), KH),
            _doc(DocumentType.FORM_1, 1, "mau-1-lien-ket.pdf", date(2026, 11, 10), KH, "MAU_1"),
            _doc(DocumentType.FORM_2, 1, "mau-2.pdf", date(2026, 11, 10), KH, "MAU_2"),
            _doc(DocumentType.FORM_3, 1, "mau-3.pdf", date(2026, 11, 10), KH, "MAU_3"),
        ],
        "history": [
            _hist(CaseStatus.DRAFT, date(2026, 11, 8), KH, "Tạo hồ sơ"),
            _hist(CaseStatus.SUBMITTED, date(2026, 11, 10), KH),
        ],
        "notes": [],
        "supplements": [],
        "missing": [],
        "receivables": [],
    },
    {
        "slug": "hs-03",
        "mine": True,
        "temp_code": "TMP-9WC4RT6B",
        "nxb_code": "",
        "isbn": "",
        "title": "Marketing số cho hợp tác xã",
        "subtitle": "",
        "mode": PublicationMode.SELF,
        "partner_name": "",
        "category": "Sách chuyên khảo",
        "owner": KH,
        "editor": BTV_HA,
        "status": CaseStatus.NEED_SUPPLEMENT,
        "created": date(2026, 11, 2),
        "todo": _("Cần bổ sung Mẫu 2"),
        "authors": [
            _author(1, "Trần Thị Mai", ContributorRole.AUTHOR, "mai.tran@example.com"),
            _author(2, "Vũ Đình Phong", ContributorRole.CO_AUTHOR),
        ],
        "documents": [
            _doc(DocumentType.MANUSCRIPT, 1, "marketing-so.docx", date(2026, 11, 5), KH),
            _doc(DocumentType.FORM_2, 1, "mau-2-thieu-chu-ky.pdf", date(2026, 11, 5), KH, "MAU_2"),
            _doc(DocumentType.FORM_3, 1, "mau-3.pdf", date(2026, 11, 5), KH, "MAU_3"),
        ],
        "history": [
            _hist(CaseStatus.DRAFT, date(2026, 11, 2), KH, "Tạo hồ sơ"),
            _hist(CaseStatus.SUBMITTED, date(2026, 11, 5), KH),
            _hist(
                CaseStatus.NEED_SUPPLEMENT,
                date(2026, 11, 7),
                BTV_HA,
                "Mẫu 2 thiếu chữ ký đồng tác giả.",
            ),
        ],
        "notes": [
            _note(
                "CUSTOMER",
                BTV_HA,
                date(2026, 11, 7),
                "Chị vui lòng bổ sung Mẫu 2 có đủ chữ ký của đồng tác giả Vũ Đình Phong.",
            ),
            _note(
                "INTERNAL",
                BTV_HA,
                date(2026, 11, 7),
                "Bản thảo ổn, chỉ chờ Mẫu 2. Ưu tiên tiếp nhận khi khách bổ sung.",
            ),
        ],
        "supplements": [
            {
                "status": "OPEN",
                "created": date(2026, 11, 7),
                "text": "Bổ sung Mẫu 2 có đủ chữ ký các tác giả.",
            }
        ],
        "missing": [_("Mẫu 2 cần nộp lại (yêu cầu bổ sung đang mở)")],
        "receivables": [],
    },
    {
        "slug": "hs-04",
        "mine": False,
        "temp_code": "TMP-5LN1XE8D",
        "nxb_code": "",
        "isbn": "",
        "title": "Thống kê ứng dụng trong kinh doanh",
        "subtitle": "Tái bản lần 2",
        "mode": PublicationMode.SELF,
        "partner_name": "",
        "category": "Giáo trình",
        "owner": "Ngô Quốc Tuấn (hư cấu)",
        "editor": BTV_KHOA,
        "status": CaseStatus.SUBMITTED,
        "resubmitted": True,
        "created": date(2026, 10, 25),
        "todo": "",
        "authors": [
            _author(1, "Ngô Quốc Tuấn", ContributorRole.CHIEF_EDITOR, "tuan.ngo@example.com"),
            _author(2, "Lý Thanh Hương", ContributorRole.COMPILER),
        ],
        "documents": [
            _doc(
                DocumentType.MANUSCRIPT, 1, "thong-ke-ud.pdf", date(2026, 10, 28), "Ngô Quốc Tuấn"
            ),
            _doc(DocumentType.FORM_2, 1, "mau-2.pdf", date(2026, 10, 28), "Ngô Quốc Tuấn", "MAU_2"),
            _doc(DocumentType.FORM_3, 1, "mau-3.pdf", date(2026, 10, 28), "Ngô Quốc Tuấn", "MAU_3"),
            _doc(
                DocumentType.FORM_3,
                2,
                "mau-3-bo-sung.pdf",
                date(2026, 11, 24),
                "Ngô Quốc Tuấn",
                "MAU_3",
            ),
        ],
        "history": [
            _hist(CaseStatus.DRAFT, date(2026, 10, 25), "Ngô Quốc Tuấn", "Tạo hồ sơ"),
            _hist(CaseStatus.SUBMITTED, date(2026, 10, 28), "Ngô Quốc Tuấn"),
            _hist(CaseStatus.NEED_SUPPLEMENT, date(2026, 11, 3), BTV_KHOA, "Mẫu 3 sai năm."),
            _hist(CaseStatus.SUBMITTED, date(2026, 11, 24), "Ngô Quốc Tuấn", "Đã bổ sung Mẫu 3."),
        ],
        "notes": [
            _note(
                "CUSTOMER",
                BTV_KHOA,
                date(2026, 11, 3),
                "Mẫu 3 ghi sai năm xuất bản, nhờ anh sửa lại.",
            ),
        ],
        "supplements": [
            {"status": "RESOLVED", "created": date(2026, 11, 3), "text": "Sửa năm trên Mẫu 3."},
        ],
        "missing": [],
        "receivables": [],
    },
    {
        "slug": "hs-05",
        "mine": True,
        "temp_code": "TMP-2PB6VY4K",
        "nxb_code": "NXB-2026-0041",
        "isbn": "",
        "title": "Kinh tế tuần hoàn: từ lý thuyết đến thực tiễn",
        "subtitle": "",
        "mode": PublicationMode.LINKED,
        "partner_name": "Công ty Văn hóa Rạng Đông (hư cấu)",
        "category": "Sách chuyên khảo",
        "owner": KH,
        "editor": BTV_KHOA,
        "status": CaseStatus.EDITING,
        "created": date(2026, 9, 15),
        "todo": "",
        "authors": [
            _author(1, "Trần Thị Mai", ContributorRole.AUTHOR, "mai.tran@example.com"),
            _author(2, "Đặng Khải Minh", ContributorRole.TRANSLATOR),
        ],
        "documents": [
            _doc(DocumentType.MANUSCRIPT, 1, "ktth-v1.docx", date(2026, 9, 18), KH),
            _doc(DocumentType.MANUSCRIPT, 2, "ktth-v2.docx", date(2026, 10, 20), KH),
            _doc(DocumentType.FORM_1, 1, "mau-1.pdf", date(2026, 9, 18), KH, "MAU_1"),
            _doc(DocumentType.FORM_2, 1, "mau-2.pdf", date(2026, 9, 18), KH, "MAU_2"),
            _doc(DocumentType.FORM_3, 1, "mau-3.pdf", date(2026, 9, 18), KH, "MAU_3"),
        ],
        "history": [
            _hist(CaseStatus.DRAFT, date(2026, 9, 15), KH, "Tạo hồ sơ"),
            _hist(CaseStatus.SUBMITTED, date(2026, 9, 18), KH),
            _hist(CaseStatus.ACCEPTED, date(2026, 9, 22), BTV_KHOA, "Cấp mã NXB-2026-0041"),
            _hist(CaseStatus.EDITING, date(2026, 9, 25), BTV_KHOA),
        ],
        "notes": [
            _note(
                "CUSTOMER",
                BTV_KHOA,
                date(2026, 10, 21),
                "NXB đã nhận bản thảo phiên bản 2, dự kiến có kết quả duyệt trong tháng 12.",
            ),
            _note(
                "INTERNAL",
                BTV_KHOA,
                date(2026, 10, 22),
                "Chương 4 cần kiểm tra lại nguồn số liệu trước khi lập Mẫu 4.",
            ),
        ],
        "supplements": [],
        "missing": [_("Chưa có Mẫu 4 (kết quả duyệt bản thảo) cho bản thảo phiên bản 2")],
        "receivables": [
            _rec("Phí biên tập", 12000000, 6000000, date(2026, 10, 15)),
            _rec("Phí quản lý xuất bản", 3000000, 0, date(2026, 12, 15)),
        ],
    },
    {
        "slug": "hs-06",
        "mine": True,
        "temp_code": "TMP-8RJ3QS7N",
        "nxb_code": "NXB-2026-0033",
        "isbn": "",
        "title": "Tài chính hành vi nhập môn",
        "subtitle": "",
        "mode": PublicationMode.SELF,
        "partner_name": "",
        "category": "Giáo trình",
        "owner": KH,
        "editor": BTV_HA,
        "status": CaseStatus.REVISION_REQUIRED,
        "created": date(2026, 8, 5),
        "todo": _("Tải lên bản thảo đã chỉnh sửa"),
        "authors": [
            _author(1, "Trần Thị Mai", ContributorRole.AUTHOR, "mai.tran@example.com"),
        ],
        "documents": [
            _doc(DocumentType.MANUSCRIPT, 1, "tchv-v1.pdf", date(2026, 8, 7), KH),
            _doc(DocumentType.FORM_2, 1, "mau-2.pdf", date(2026, 8, 7), KH, "MAU_2"),
            _doc(DocumentType.FORM_3, 1, "mau-3.pdf", date(2026, 8, 7), KH, "MAU_3"),
            _doc(
                DocumentType.FORM_4, 1, "mau-4-yeu-cau-sua.pdf", date(2026, 10, 30), BTV_HA, "MAU_4"
            ),
        ],
        "history": [
            _hist(CaseStatus.DRAFT, date(2026, 8, 5), KH, "Tạo hồ sơ"),
            _hist(CaseStatus.SUBMITTED, date(2026, 8, 7), KH),
            _hist(CaseStatus.ACCEPTED, date(2026, 8, 12), BTV_HA, "Cấp mã NXB-2026-0033"),
            _hist(CaseStatus.EDITING, date(2026, 8, 14), BTV_HA),
            _hist(
                CaseStatus.REVISION_REQUIRED,
                date(2026, 10, 30),
                BTV_HA,
                "Mẫu 4: yêu cầu chỉnh sửa chương 2 và 5.",
            ),
        ],
        "notes": [
            _note(
                "CUSTOMER",
                BTV_HA,
                date(2026, 10, 30),
                "Chị chỉnh sửa theo góp ý trong Mẫu 4 và tải lên bản thảo mới giúp NXB.",
            ),
        ],
        "supplements": [],
        "missing": [_("Cần bản thảo phiên bản mới hơn phiên bản 1 đã duyệt")],
        "receivables": [
            _rec("Phí biên tập", 8000000, 8000000, date(2026, 9, 1)),
        ],
    },
    {
        "slug": "hs-07",
        "mine": False,
        "temp_code": "TMP-4TZ9GU2H",
        "nxb_code": "NXB-2026-0019",
        "isbn": "9786049221057",
        "title": "Logistics xanh và chuỗi cung ứng bền vững",
        "subtitle": "",
        "mode": PublicationMode.SELF,
        "partner_name": "",
        "category": "Sách chuyên khảo",
        "owner": "Bùi Thị Hạnh (hư cấu)",
        "editor": BTV_HA,
        "status": CaseStatus.REVIEW_APPROVED,
        "created": date(2026, 6, 3),
        "todo": "",
        "authors": [
            _author(1, "Bùi Thị Hạnh", ContributorRole.CHIEF_EDITOR, "hanh.bui@example.com"),
            _author(2, "Mạc Văn Toàn", ContributorRole.CO_AUTHOR),
            _author(3, "Kiều Anh Thư", ContributorRole.CO_AUTHOR),
        ],
        "documents": [
            _doc(
                DocumentType.MANUSCRIPT,
                1,
                "logistics-xanh-v1.pdf",
                date(2026, 6, 5),
                "Bùi Thị Hạnh",
            ),
            _doc(
                DocumentType.MANUSCRIPT,
                2,
                "logistics-xanh-v2.pdf",
                date(2026, 8, 20),
                "Bùi Thị Hạnh",
            ),
            _doc(DocumentType.FORM_2, 1, "mau-2.pdf", date(2026, 6, 5), "Bùi Thị Hạnh", "MAU_2"),
            _doc(DocumentType.FORM_3, 1, "mau-3.pdf", date(2026, 6, 5), "Bùi Thị Hạnh", "MAU_3"),
            _doc(DocumentType.FORM_4, 1, "mau-4-dong-y.pdf", date(2026, 9, 10), BTV_HA, "MAU_4"),
        ],
        "history": [
            _hist(CaseStatus.DRAFT, date(2026, 6, 3), "Bùi Thị Hạnh", "Tạo hồ sơ"),
            _hist(CaseStatus.SUBMITTED, date(2026, 6, 5), "Bùi Thị Hạnh"),
            _hist(CaseStatus.ACCEPTED, date(2026, 6, 9), BTV_HA, "Cấp mã NXB-2026-0019"),
            _hist(CaseStatus.EDITING, date(2026, 6, 10), BTV_HA),
            _hist(CaseStatus.REVIEW_APPROVED, date(2026, 9, 10), BTV_HA, "Mẫu 4: đồng ý xuất bản."),
        ],
        "notes": [
            _note(
                "INTERNAL",
                BTV_HA,
                date(2026, 9, 12),
                "Đã xin ISBN, chờ Cục cấp số XNĐK để nhập.",
            ),
        ],
        "supplements": [],
        "missing": [
            _("Chưa có số xác nhận đăng ký (XNĐK) và ngày đăng ký"),
            _("Chưa có Mẫu 5"),
        ],
        "receivables": [
            _rec("Phí biên tập", 15000000, 5000000, date(2026, 7, 10)),
            _rec("Phí quản lý xuất bản", 4000000, 0, date(2026, 8, 20)),
        ],
    },
    {
        "slug": "hs-08",
        "mine": False,
        "temp_code": "TMP-6YF5KA3W",
        "nxb_code": "NXB-2026-0007",
        "isbn": "9786049221026",
        "title": "Kinh tế lượng thực hành với dữ liệu Việt Nam",
        "subtitle": "",
        "mode": PublicationMode.LINKED,
        "partner_name": "Công ty Sách Bình Minh (hư cấu)",
        "category": "Giáo trình",
        "owner": "Châu Minh Đức (hư cấu)",
        "editor": BTV_KHOA,
        "status": CaseStatus.DECISION_ISSUED,
        "created": date(2026, 3, 2),
        "registration_number": "1234-2026/CXBIPH/05-67/KT",
        "registration_date": date(2026, 7, 1),
        "decision_number": "215/QĐ-NXBKT",
        "decision_date": date(2026, 7, 15),
        "contract_number": "HĐLK-2026-012",
        "todo": "",
        "authors": [
            _author(1, "Châu Minh Đức", ContributorRole.AUTHOR, "duc.chau@example.com"),
            _author(2, "Tạ Hồng Nhung", ContributorRole.CO_AUTHOR),
        ],
        "documents": [
            _doc(DocumentType.MANUSCRIPT, 1, "ktl-v1.pdf", date(2026, 3, 5), "Châu Minh Đức"),
            _doc(DocumentType.FORM_1, 1, "mau-1.pdf", date(2026, 3, 5), "Châu Minh Đức", "MAU_1"),
            _doc(DocumentType.FORM_2, 1, "mau-2.pdf", date(2026, 3, 5), "Châu Minh Đức", "MAU_2"),
            _doc(DocumentType.FORM_3, 1, "mau-3.pdf", date(2026, 3, 5), "Châu Minh Đức", "MAU_3"),
            _doc(DocumentType.FORM_4, 1, "mau-4.pdf", date(2026, 5, 20), BTV_KHOA, "MAU_4"),
            _doc(DocumentType.FORM_5, 1, "mau-5.pdf", date(2026, 6, 10), BTV_KHOA, "MAU_5"),
            _doc(DocumentType.FORM_6, 1, "mau-6.pdf", date(2026, 7, 15), BTV_KHOA, "MAU_6"),
            _doc(
                DocumentType.FORM_7, 1, "mau-7-hop-dong.pdf", date(2026, 7, 15), BTV_KHOA, "MAU_7"
            ),
        ],
        "history": [
            _hist(CaseStatus.DRAFT, date(2026, 3, 2), "Châu Minh Đức", "Tạo hồ sơ"),
            _hist(CaseStatus.SUBMITTED, date(2026, 3, 5), "Châu Minh Đức"),
            _hist(CaseStatus.ACCEPTED, date(2026, 3, 9), BTV_KHOA, "Cấp mã NXB-2026-0007"),
            _hist(CaseStatus.EDITING, date(2026, 3, 10), BTV_KHOA),
            _hist(CaseStatus.REVIEW_APPROVED, date(2026, 5, 20), BTV_KHOA),
            _hist(CaseStatus.REGISTERED, date(2026, 7, 1), BTV_KHOA),
            _hist(CaseStatus.DECISION_ISSUED, date(2026, 7, 15), BTV_KHOA),
        ],
        "notes": [
            _note(
                "CUSTOMER",
                BTV_KHOA,
                date(2026, 7, 15),
                "NXB đã ra quyết định xuất bản. Anh gửi bản in mẫu để làm thủ tục lưu chiểu.",
            ),
        ],
        "supplements": [],
        "missing": [_("Chưa có Mẫu 9 (nộp lưu chiểu)"), _("Chưa có ngày nộp lưu chiểu")],
        "receivables": [
            _rec("Phí biên tập", 20000000, 20000000, date(2026, 4, 30)),
            _rec("Phí quản lý xuất bản", 5000000, 2000000, date(2026, 5, 31)),
        ],
    },
]


def _enrich(case: dict) -> dict:
    status = case["status"]
    case["display_code"] = case["isbn"] or case["nxb_code"] or case["temp_code"]
    case["status_label"] = CaseStatus(status).label
    case["customer_status_label"] = CUSTOMER_STATUS_LABELS[status]
    case["status_color"] = STATUS_COLORS[status]
    case["mode_label"] = PublicationMode(case["mode"]).label
    case["author_names"] = ", ".join(a["name"] for a in case["authors"])
    case["open_supplements"] = [s for s in case["supplements"] if s["status"] == "OPEN"]
    case["customer_notes"] = [n for n in case["notes"] if n["visibility"] == "CUSTOMER"]
    manuscripts = [d for d in case["documents"] if d["doc_type"] == DocumentType.MANUSCRIPT]
    case["latest_manuscript"] = (
        max(manuscripts, key=lambda d: d["version"]) if manuscripts else None
    )
    case["next_statuses"] = [
        {"code": s, "label": CaseStatus(s).label} for s in EDITOR_TRANSITIONS.get(status, [])
    ]
    total = sum((r["amount"] for r in case["receivables"]), Decimal("0"))
    paid = sum((r["collected"] for r in case["receivables"]), Decimal("0"))
    case["finance_total"] = total
    case["finance_collected"] = paid
    case["finance_outstanding"] = total - paid
    for key in (
        "registration_number",
        "registration_date",
        "decision_number",
        "decision_date",
        "contract_number",
    ):
        case.setdefault(key, "" if "number" in key else None)
    case.setdefault("resubmitted", False)
    return case


for _case in CASES:
    _enrich(_case)

CASES_BY_SLUG = {c["slug"]: c for c in CASES}

REVIEW_RESULT_CHOICES = list(ReviewResult.choices)

# ---------------------------------------------------------------------------
# Thống kê – danh mục xuất bản (sách đã có quyết định xuất bản, hư cấu)
# ---------------------------------------------------------------------------

PUBLISHED_BOOKS = [
    {"isbn": "9786049221019", "title": "Nhập môn kinh tế vi mô", "author": "Lâm Quế Chi", "mode": PublicationMode.SELF, "decision_date": date(2026, 1, 12)},
    {"isbn": "9786049221026", "title": "Kinh tế lượng thực hành với dữ liệu Việt Nam", "author": "Châu Minh Đức", "mode": PublicationMode.LINKED, "decision_date": date(2026, 7, 15)},
    {"isbn": "9786049221033", "title": "Kế toán quản trị căn bản", "author": "Phùng Mỹ Linh", "mode": PublicationMode.SELF, "decision_date": date(2026, 2, 20)},
    {"isbn": "9786049221040", "title": "Luật kinh doanh tóm lược", "author": "Hà Quang Vinh", "mode": PublicationMode.LINKED, "decision_date": date(2026, 3, 3)},
    {"isbn": "9786049221064", "title": "Đổi mới sáng tạo trong doanh nghiệp Việt", "author": "Tôn Nữ Hoài An", "mode": PublicationMode.SELF, "decision_date": date(2026, 3, 28)},
    {"isbn": "9786049221071", "title": "Phân tích dữ liệu cho nhà quản lý", "author": "Dương Thế Hiển", "mode": PublicationMode.SELF, "decision_date": date(2026, 5, 6)},
    {"isbn": "9786049221088", "title": "Thương mại điện tử xuyên biên giới", "author": "Lục Bảo Ngọc", "mode": PublicationMode.LINKED, "decision_date": date(2026, 5, 22)},
    {"isbn": "9786049221095", "title": "Kinh tế phát triển vùng Đồng bằng", "author": "Giang Văn Lợi", "mode": PublicationMode.SELF, "decision_date": date(2026, 6, 9)},
    {"isbn": "9786049221101", "title": "Quản trị nguồn nhân lực hiện đại", "author": "Mai Xuân Trường", "mode": PublicationMode.SELF, "decision_date": date(2026, 8, 18)},
    {"isbn": "9786049221118", "title": "Bảo hiểm và quản trị rủi ro", "author": "Ông Thị Diệu", "mode": PublicationMode.LINKED, "decision_date": date(2026, 9, 2)},
    {"isbn": "9786049221125", "title": "Chính sách tiền tệ qua các thời kỳ", "author": "Quách Đại Nghĩa", "mode": PublicationMode.SELF, "decision_date": date(2026, 9, 25)},
    {"isbn": "9786049221132", "title": "Khởi nghiệp tinh gọn cho sinh viên", "author": "Thái Hải Yến", "mode": PublicationMode.SELF, "decision_date": date(2026, 10, 30)},
    {"isbn": "9786049221149", "title": "Kinh tế quốc tế (tái bản)", "author": "Lâm Quế Chi", "mode": PublicationMode.SELF, "decision_date": date(2025, 11, 14)},
    {"isbn": "9786049221156", "title": "Nguyên lý thống kê", "author": "Phùng Mỹ Linh", "mode": PublicationMode.LINKED, "decision_date": date(2025, 12, 5)},
]  # fmt: skip

for _book in PUBLISHED_BOOKS:
    _book["mode_label"] = PublicationMode(_book["mode"]).label

# ---------------------------------------------------------------------------
# Thống kê – công nợ (nhóm tuổi nợ giống apps.core.finance.aging_bucket)
# ---------------------------------------------------------------------------

AGING_BUCKETS = [
    ("NOT_DUE", _("Chưa đến hạn")),
    ("D1_30", _("Quá hạn 1–30 ngày")),
    ("D31_60", _("Quá hạn 31–60 ngày")),
    ("D61_90", _("Quá hạn 61–90 ngày")),
    ("D90_PLUS", _("Quá hạn trên 90 ngày")),
]


def aging_bucket(due_date: date | None, today: date = DEMO_TODAY) -> str:
    """Bản sao logic nhóm tuổi nợ của M0 cho dữ liệu giả (không dùng model)."""
    if due_date is None:
        return "NOT_DUE"
    overdue = (today - due_date).days
    if overdue <= 0:
        return "NOT_DUE"
    if overdue <= 30:
        return "D1_30"
    if overdue <= 60:
        return "D31_60"
    if overdue <= 90:
        return "D61_90"
    return "D90_PLUS"


EXTRA_DEBTS = [
    {"display_code": "NXB-2026-0012", "title": "Kinh tế số và chuyển đổi số", "owner": "Hứa Minh Tâm (hư cấu)", "fee": "Phí biên tập", "amount": Decimal("10000000"), "collected": Decimal("2000000"), "due_date": date(2026, 6, 30)},
    {"display_code": "NXB-2026-0025", "title": "Văn hóa doanh nghiệp Á Đông", "owner": "Lạc Thu Trang (hư cấu)", "fee": "Phí khác", "amount": Decimal("2500000"), "collected": Decimal("0"), "due_date": date(2026, 11, 10)},
]  # fmt: skip


def debt_rows() -> list[dict]:
    """Các khoản còn nợ (> 0) từ hồ sơ giả và vài khoản bổ sung, kèm nhóm tuổi nợ."""
    rows = []
    for case in CASES:
        for rec in case["receivables"]:
            rows.append(
                {
                    "display_code": case["display_code"],
                    "title": case["title"],
                    "owner": case["owner"],
                    "slug": case["slug"],
                    **rec,
                }
            )
    for extra in EXTRA_DEBTS:
        rows.append({**extra, "slug": "", "outstanding": extra["amount"] - extra["collected"]})
    labels = dict(AGING_BUCKETS)
    result = []
    for row in rows:
        if row["outstanding"] <= 0:
            continue
        bucket = aging_bucket(row["due_date"])
        row["bucket"] = bucket
        row["bucket_label"] = labels[bucket]
        row["overdue_days"] = max((DEMO_TODAY - row["due_date"]).days, 0)
        result.append(row)
    result.sort(key=lambda r: r["due_date"])
    return result
