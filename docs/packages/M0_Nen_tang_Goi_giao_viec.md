# GÓI GIAO VIỆC M0 – NỀN TẢNG
UEH Publishing Portal V2 (bản gọn) · Phiên bản 1.2 · 25/11/2026 · Owner: Nguyễn Thanh Sử

> **Thay đổi 1.2:** làm rõ "người đại diện" (5.3, 5.4); thêm `form_code` cho tài liệu (5.5); mixin phân quyền đặt tên sẵn (6); upload chia nhỏ và tải xuống dạng stream vì giới hạn 32 MiB của Cloud Run (9); HTMX, Mailpit, GitHub Actions (3, 11, 13).

> **Thay đổi 1.1:** bổ sung quyền tài chính (5.1), danh mục loại phí (5.2), model `Receivable` và `Collection` (5.13, 5.14), quyền tài chính trong mục 6, menu Thống kê, test tài chính.

> Tài liệu này giao cho **một AI duy nhất** xây dựng phần nền của Portal. Mọi module sau (M1–M7) xây trên nền này và **không được sửa** những gì M0 định nghĩa ở mục 4, 5, 6, 7. Đọc hết tài liệu trước khi viết code. Gặp điểm chưa rõ: ghi vào `docs/QUESTIONS.md` và chọn phương án đơn giản nhất, không tự mở rộng phạm vi.

---

## 1. Bối cảnh

- Đơn vị: Nhà xuất bản Kinh tế TP.HCM (trực thuộc Đại học Kinh tế TP.HCM – UEH).
- Portal số hóa quy trình xuất bản theo kiểu **bán thủ công**: con người xử lý và quyết định; hệ thống ghi nhận, theo dõi, lưu trữ, thông báo.
- Có 3 phần: trang công khai, cổng khách hàng (tác giả/đối tác), cổng nội bộ (biên tập viên, admin).
- Cổng nội bộ có mục **Thống kê**: danh mục xuất bản theo thời gian, tài chính, công nợ. Tài chính và công nợ chỉ là **sổ theo dõi nhập tay** các khoản phí dịch vụ xuất bản (phải thu, đã thu); không thay phần mềm kế toán.
- **Ngoài phạm vi tuyệt đối:** in ấn, phát hành (kể cả chi phí và công nợ in ấn, phát hành), hạch toán kế toán, xuất hóa đơn, thanh toán trực tuyến, ký số, tự động duyệt. Không tạo model, trường, menu hay màn hình nào cho các nội dung này.

## 2. Mục tiêu của M0

Tạo một dự án Django chạy được, có:
1. Cấu trúc thư mục và quy ước chung cho mọi module.
2. **Toàn bộ mô hình dữ liệu lõi** (mục 5).
3. Đăng nhập: Google cho nhân sự, email + mật khẩu cho khách hàng.
4. 3 vai trò và **lớp phân quyền dùng chung** (mục 6).
5. **Lớp quy trình**: danh sách trạng thái, bảng chuyển trạng thái, hàm đổi trạng thái duy nhất (mục 7).
6. Cấp mã NXB và kiểm tra ISBN.
7. Nhật ký thao tác (audit log) chỉ ghi thêm.
8. Giao diện khung (layout, menu theo vai trò, trang chủ trống cho từng vai trò).
9. Lớp lưu trữ file trừu tượng, cài đặt tạm bằng ổ đĩa local (Drive do M1 làm).
10. Docker, cấu hình môi trường, dữ liệu mẫu, test tự động.

## 3. Công nghệ bắt buộc

| Thành phần | Lựa chọn |
|---|---|
| Ngôn ngữ | Python 3.12 |
| Framework | Django 5.2 (LTS) |
| Database | PostgreSQL 16 |
| Đăng nhập | django-allauth (Google provider + email/mật khẩu) |
| Giao diện | Django templates + Bootstrap 5 + HTMX (lọc danh sách, đổi trạng thái, thêm dòng không tải lại trang). Không dùng SPA/React/Vue, không thêm thư viện CSS/JS khác |
| Cấu hình | django-environ, đọc từ biến môi trường / file `.env` |
| Chạy | gunicorn + whitenoise, Dockerfile + docker-compose (app + postgres) |
| Test | pytest + pytest-django, factory_boy |
| Email khi phát triển | Mailpit (container trong docker-compose) |
| CI | GitHub Actions: ruff + pytest với PostgreSQL trên mọi pull request |
| Chất lượng code | ruff (lint + format) |

Ngôn ngữ giao diện: tiếng Việt (`LANGUAGE_CODE = "vi"`), múi giờ `Asia/Ho_Chi_Minh`. Tên biến, hàm, model, bảng: tiếng Anh. Chuỗi hiển thị: tiếng Việt, bọc trong `gettext_lazy`.

**Không dùng:** Firebase, Firestore, Apps Script, dịch vụ chỉ có trên một cloud. Ứng dụng phải chạy giống nhau trên Google Cloud Run và trên máy chủ UEH.

## 4. Cấu trúc repository

```
ueh-portal/
├── portal/                  # project Django
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── core/                # M0 – SỞ HỮU: models lõi, workflow, permissions, audit, codes, storage
│   ├── accounts/            # M0 – đăng nhập, đăng ký, hồ sơ người dùng
│   ├── documents_drive/     # M1 (để trống, chỉ có __init__.py + README)
│   ├── customer/            # M2
│   ├── backoffice/          # M3
│   ├── notifications/       # M4
│   ├── reports/             # M5 – tra cứu, thống kê danh mục xuất bản
│   ├── finance/             # M8 – màn hình nhập khoản thu, thống kê tài chính, công nợ
│   ├── public_site/         # M6
│   └── administration/      # M7
├── templates/
│   ├── base.html            # M0 – layout chung
│   ├── partials/            # M0 – menu, thông báo, phân trang
│   └── <app>/...            # mỗi module dùng thư mục riêng
├── static/
├── tests/                   # test dùng chung (permissions, workflow)
├── docs/
│   ├── CONVENTIONS.md       # M0 viết – quy ước cho các module sau
│   ├── DATA_MODEL.md        # M0 viết – mô tả model + sơ đồ quan hệ
│   └── QUESTIONS.md
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── pyproject.toml
└── README.md
```

**Quyền sở hữu thư mục:** `apps/core`, `apps/accounts`, `portal/settings/base.py`, `templates/base.html`, `templates/partials/` thuộc M0. Module sau chỉ được **dùng**, không được sửa; cần thay đổi thì đề xuất cho Owner.

**Model:** mọi model nghiệp vụ (hồ sơ, tài liệu, trạng thái, tài chính) do M0 khai báo và tạo migration. Module sau chỉ viết views, forms, templates, services trên các model đó. Ngoại lệ duy nhất: model phục vụ riêng module, không phải dữ liệu nghiệp vụ (ví dụ `NewsPost` của M6, `ImportBatch` của M5), đặt trong app của module và phải được Owner duyệt trước.

## 5. Mô hình dữ liệu lõi (apps/core, apps/accounts)

Quy ước chung: mọi model có `created_at`, `updated_at` (tự động). Khóa chính là `BigAutoField` trừ khi ghi khác. Không lưu số CCCD, ngày cấp, nơi cấp trong database — các thông tin này chỉ nằm trong file biểu mẫu tải lên.

### 5.1 User (apps/accounts)
Custom user, đặt `AUTH_USER_MODEL = "accounts.User"`. Đăng nhập bằng email, không dùng username.

| Trường | Kiểu | Ghi chú |
|---|---|---|
| email | EmailField, unique | dùng để đăng nhập |
| full_name | CharField(200) | |
| phone | CharField(20), blank | |
| role | CharField choices: `CUSTOMER`, `EDITOR`, `ADMIN` | mặc định `CUSTOMER` |
| organization | CharField(255), blank | tên đơn vị/đối tác của khách hàng |
| finance_access | CharField choices: `NONE`, `VIEW`, `MANAGE` | mặc định `NONE`; chỉ có ý nghĩa với EDITOR; Admin gán |
| is_active | bool | admin khóa tài khoản |

Quy tắc:
- Người đăng nhập bằng Google với email `@ueh.edu.vn` **không tự động** thành EDITOR. Tài khoản nhân sự phải được Admin tạo trước hoặc gán vai trò; người lạ có email UEH đăng nhập sẽ là CUSTOMER.
- Đăng nhập Google chỉ chấp nhận domain `ueh.edu.vn` cho vai trò EDITOR/ADMIN; EDITOR/ADMIN **không** được đăng nhập bằng mật khẩu.
- Khách hàng đăng ký bằng email + mật khẩu, bắt buộc xác thực email.
- Lệnh `python manage.py bootstrap_admin` tạo Admin từ biến môi trường `BOOTSTRAP_ADMIN_EMAILS` (danh sách, cho phép 2 email).

### 5.2 Category, Field (danh mục do Admin quản lý)
- `Category` (thể loại sách): `name`, `is_active`, `sort_order`.
- `Field` (lĩnh vực, dùng cho Mẫu 5): `name`, `is_active`, `sort_order`.
- `FeeType` (loại phí): `name`, `is_active`, `sort_order`. Dữ liệu mẫu: "Phí quản lý xuất bản", "Phí biên tập", "Phí khác".

### 5.3 PublicationCase (hồ sơ – 1 hồ sơ = 1 đầu sách)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| id | UUIDField, primary key | dùng trong URL, không đoán được |
| temp_code | CharField(20), unique | sinh khi tạo nháp, dạng `TMP-XXXXXXXX` (8 ký tự ngẫu nhiên, chữ hoa + số) |
| nxb_code | CharField(20), unique, null | `NXB-YYYY-NNNN`, cấp khi tiếp nhận, **không bao giờ đổi** |
| isbn | CharField(13), unique, null | chỉ chứa số, kiểm tra theo mục 8 |
| status | CharField choices (mục 7) | mặc định `DRAFT`, **chỉ đổi qua `change_status()`** |
| owner | FK User (CUSTOMER) | **người đại diện** làm việc với NXB, PROTECT (xem quy tắc dưới bảng) |
| primary_editor | FK User (EDITOR), null | biên tập viên phụ trách chính |
| title | CharField(500) | tên tác phẩm |
| subtitle | CharField(500), blank | |
| category | FK Category, null | |
| field | FK Field, null | |
| language | CharField(50), mặc định "Tiếng Việt" | |
| translated_from | CharField(50), blank | ngôn ngữ gốc nếu là sách dịch |
| edition_number | PositiveSmallIntegerField, mặc định 1 | lần xuất bản |
| is_reprint | bool | tái bản |
| publication_mode | choices `SELF` (tự xuất bản), `LINKED` (liên kết) | |
| partner_name | CharField(255), blank | bắt buộc khi `LINKED` |
| summary | TextField | tóm tắt nội dung |
| page_count | PositiveIntegerField, null | |
| book_size | CharField(50), blank | khổ sách, ví dụ "16 x 24 cm" |
| submitted_at | DateTimeField, null | |
| accepted_at | DateTimeField, null | |
| registration_number | CharField(100), blank | số xác nhận đăng ký xuất bản |
| registration_date | DateField, null | |
| decision_number | CharField(100), blank | số QĐXB |
| decision_date | DateField, null | |
| contract_number | CharField(100), blank | số hợp đồng liên kết (Mẫu 7) |
| contract_date | DateField, null | |
| deposit_date | DateField, null | ngày nộp lưu chiểu |

Thuộc tính tính toán: `display_code` = `isbn` nếu có, nếu không thì `nxb_code`, nếu không thì `temp_code`.

**Quy tắc người đại diện:** một tác phẩm có thể có nhiều đồng tác giả, nhưng khi làm việc với NXB chỉ có **một người đại diện**. Người đại diện là tài khoản `owner`: người duy nhất nộp, bổ sung, theo dõi hồ sơ và nhận email. Người đại diện có thể là một đồng tác giả hoặc người của đơn vị đối tác. Các tác giả khác chỉ là thông tin trong `Contributor`, không có tài khoản, không nhận email. Đổi người đại diện là thao tác của EDITOR, có ghi chú và ghi AuditEvent (`case.owner_change`).

### 5.4 Contributor (tác giả của tác phẩm)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| case | FK PublicationCase, CASCADE, related_name `contributors` | |
| full_name | CharField(200) | |
| academic_title | CharField(100), blank | học hàm/học vị |
| role | choices `AUTHOR`, `CHIEF_EDITOR` (chủ biên), `CO_AUTHOR`, `TRANSLATOR`, `COMPILER` (biên soạn) | |
| email | EmailField, blank | |
| phone | CharField(20), blank | |
| order | PositiveSmallIntegerField | thứ tự hiển thị |
| affiliation | CharField(255), blank | đơn vị công tác |

Contributor chỉ là thông tin thư mục để hiển thị, tra cứu, xuất báo cáo; không liên kết với User và không có quyền gì trên hồ sơ.

### 5.5 Document (tài liệu và phiên bản)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| case | FK PublicationCase, PROTECT, related_name `documents` | |
| doc_type | choices: `MANUSCRIPT`, `FORM_1`, `FORM_2`, `FORM_3`, `FORM_4`, `FORM_5`, `FORM_6`, `FORM_7`, `FORM_9`, `REGISTRATION_PROOF`, `DEPOSIT_PROOF`, `OTHER` | |
| form_code | CharField(30), blank | mã biểu mẫu theo `FormTemplate.code` (ví dụ `MAU_4`, `BIZ_F4_03`). Biểu mẫu chưa có `doc_type` riêng (bộ BIZ-F4-01…12) dùng `doc_type = OTHER` + `form_code`, không cần sửa schema |
| version | PositiveIntegerField | tự tăng theo (case, doc_type, form_code), bắt đầu 1 |
| is_current | bool | bản mới nhất của (case, doc_type) |
| original_filename | CharField(255) | |
| mime_type | CharField(100) | |
| size_bytes | PositiveBigIntegerField | |
| sha256 | CharField(64) | tính khi tải lên |
| storage_backend | CharField(20) | `local` (M0) hoặc `gdrive` (M1) |
| storage_ref | CharField(255) | đường dẫn local hoặc Drive file id |
| uploaded_by | FK User, PROTECT | |
| uploaded_at | DateTimeField | |
| note | CharField(500), blank | |

Quy tắc: **không xóa, không ghi đè**. Tải bản mới = tạo bản ghi mới với `version + 1`, bản cũ chuyển `is_current = False`. Không có thao tác xóa Document trong giao diện; Django admin để chỉ đọc.

### 5.6 ManuscriptReview (kết quả duyệt theo Mẫu 4)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| case | FK PublicationCase, PROTECT | |
| manuscript | FK Document (doc_type = MANUSCRIPT), PROTECT | **đúng phiên bản bản thảo được duyệt** |
| form4 | FK Document (doc_type = FORM_4), PROTECT | Mẫu 4 đã ký |
| result | choices `APPROVED`, `REVISION_REQUIRED`, `REJECTED` | |
| confirmed_by | FK User (EDITOR) | người tích xác nhận "đúng hồ sơ" |
| confirmed_at | DateTimeField | |
| note | TextField, blank | |

Ràng buộc kiểm tra trong `clean()` và trong service: `manuscript.case == form4.case == case`, đúng `doc_type`.

### 5.7 CaseNote (ghi chú, trao đổi)
`case`, `author` (FK User), `body` (TextField), `visibility` choices `INTERNAL` (chỉ nhân sự thấy) / `CUSTOMER` (khách hàng thấy).

### 5.8 SupplementRequest (yêu cầu bổ sung)
`case`, `requested_by` (EDITOR), `message`, `status` choices `OPEN` / `RESOLVED`, `resolved_at` (null).

### 5.9 StatusHistory
`case`, `from_status`, `to_status`, `actor` (FK User), `note`, `at`. Chỉ ghi thêm.

### 5.10 FormTemplate (file biểu mẫu trống cho khách hàng tải)
`code` (ví dụ `MAU_1`), `name`, `version` (CharField), `effective_from` (DateField), `is_active`, `storage_backend`, `storage_ref`, `original_filename`. Nhiều phiên bản cùng `code`; trang công khai lấy bản `is_active` mới nhất.

### 5.11 CodeSequence
`prefix` (ví dụ `NXB`), `year`, `last_number`; unique (prefix, year). Dùng để cấp mã NXB (mục 8).

### 5.12 AuditEvent
| Trường | Kiểu | Ghi chú |
|---|---|---|
| actor | FK User, null (hệ thống) | |
| action | CharField(50) | ví dụ `case.create`, `case.status_change`, `document.upload`, `document.download`, `user.role_change`, `auth.login` |
| object_type | CharField(50) | |
| object_id | CharField(64) | |
| case | FK PublicationCase, null | để lọc theo hồ sơ |
| data | JSONField | trước/sau, ghi chú |
| ip_address | GenericIPAddressField, null | |
| at | DateTimeField | |

Chỉ ghi thêm: `save()` từ chối cập nhật bản ghi đã có, `delete()` bị chặn; Django admin chỉ đọc.

### 5.13 Receivable (khoản phải thu – phí dịch vụ xuất bản)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| case | FK PublicationCase, PROTECT, related_name `receivables` | |
| fee_type | FK FeeType, PROTECT | |
| description | CharField(255), blank | |
| amount | DecimalField(15, 0) | VNĐ, không có số lẻ; > 0, trừ bút toán đảo |
| payer_name | CharField(255) | đối tác/tác giả phải trả; mặc định lấy `partner_name` hoặc tên chủ hồ sơ |
| contract_number | CharField(100), blank | |
| invoice_number | CharField(100), blank | |
| invoice_date | DateField, null | |
| due_date | DateField, null | hạn thanh toán |
| is_adjustment | bool | bút toán đảo/điều chỉnh (amount được âm), bắt buộc `note` |
| adjusts | FK self, null | khoản bị điều chỉnh |
| note | TextField, blank | |
| created_by | FK User | |

### 5.14 Collection (khoản đã thu)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| receivable | FK Receivable, PROTECT, related_name `collections` | |
| paid_date | DateField | |
| amount | DecimalField(15, 0) | VNĐ; > 0, trừ bút toán đảo |
| method | choices `TRANSFER` (chuyển khoản), `CASH` (tiền mặt), `OTHER` | |
| reference | CharField(100), blank | số chứng từ |
| is_adjustment | bool | bút toán đảo, bắt buộc `note` |
| note | TextField, blank | |
| created_by | FK User | |

Quy tắc tài chính (apps/core/finance.py):
- **Không xóa** Receivable/Collection; sửa sai bằng bút toán điều chỉnh có ghi chú. Mọi lần tạo/sửa ghi AuditEvent (`finance.receivable_create`, `finance.collection_create`, …) kèm giá trị trước/sau.
- Hàm tính: `outstanding(receivable)` = amount − tổng collections; `receivable_status(receivable, today)` → `UNPAID` (Chưa thu), `PARTIAL` (Thu một phần), `PAID` (Đã thu đủ), `OVERDUE` (Quá hạn: còn nợ và quá `due_date`); `aging_bucket(receivable, today)` → `NOT_DUE`, `D1_30`, `D31_60`, `D61_90`, `D90_PLUS`.
- Tổng đã thu không được vượt amount (trừ khi có ghi chú và người dùng xác nhận).
- Không có trường hay loại phí nào cho chi phí in, phát hành.

## 6. Phân quyền (apps/core/permissions.py)

Mọi kiểm tra quyền nằm ở **một file duy nhất**. View của mọi module phải gọi các hàm này; không tự viết điều kiện quyền trong view hoặc template.

| Hàm | CUSTOMER | EDITOR | ADMIN |
|---|---|---|---|
| `cases_visible_to(user)` → QuerySet | hồ sơ có `owner = user` | tất cả | không có (trả về rỗng) |
| `can_view_case(user, case)` | chủ hồ sơ | có | không |
| `can_edit_case_info(user, case)` | chủ hồ sơ khi trạng thái `DRAFT` hoặc `NEED_SUPPLEMENT` | có, trừ khi `COMPLETED`/`ARCHIVED` | không |
| `can_upload(user, case, doc_type)` | chủ hồ sơ; chỉ `MANUSCRIPT`, `FORM_1`, `FORM_2`, `FORM_3`, `OTHER`; chỉ khi `DRAFT`/`NEED_SUPPLEMENT`/`REVISION_REQUIRED` | mọi loại | không |
| `can_download(user, document)` | chủ hồ sơ; không tải được `FORM_4` | có | không |
| `can_view_note(user, note)` | chỉ note `CUSTOMER` của hồ sơ mình | có | không |
| `can_change_status(user, case, to_status)` | theo bảng chuyển trạng thái (mục 7) | theo bảng | không |
| `can_manage_system(user)` | không | không | có |
| `can_view_publication_stats(user)` | không | có | không |
| `can_view_finance(user)` | không | khi `finance_access` là `VIEW` hoặc `MANAGE` | không |
| `can_manage_finance(user)` | không | khi `finance_access` là `MANAGE` | không |

Quy tắc bắt buộc:
- Hồ sơ không có quyền xem → trả **404** (không trả 403, để không lộ hồ sơ tồn tại).
- Mixin dùng chung (apps/core/mixins.py), mọi view của mọi module **bắt buộc** kế thừa, không tự viết điều kiện quyền:
  - `CustomerRequiredMixin`, `EditorRequiredMixin`, `AdminRequiredMixin` (đều gồm `LoginRequiredMixin`);
  - `CaseAccessMixin` – lấy hồ sơ theo UUID qua `cases_visible_to`, không có quyền → 404;
  - `FinanceViewMixin`, `FinanceManageMixin`, `PublicationStatsMixin`.
- Test kiểm tra tự động: mọi URL trong `apps/*` (trừ `public_site` và trang đăng nhập) trả về chuyển hướng đăng nhập khi chưa đăng nhập.
- ADMIN không xem nội dung hồ sơ. Nếu Owner muốn Admin xem được, sẽ có Change Request riêng.
- Người không có quyền tài chính: không thấy menu Tài chính/Công nợ, không thấy số tiền trong trang hồ sơ, gọi URL tài chính → 404. Khách hàng không bao giờ thấy số liệu tài chính.

## 7. Quy trình (apps/core/workflow.py)

### 7.1 Trạng thái

| Mã | Nhãn hiển thị |
|---|---|
| `DRAFT` | Nháp |
| `SUBMITTED` | Đã nộp |
| `NEED_SUPPLEMENT` | Cần bổ sung |
| `ACCEPTED` | Đã tiếp nhận |
| `EDITING` | Đang biên tập |
| `REVISION_REQUIRED` | Trả tác giả chỉnh sửa |
| `REVIEW_APPROVED` | Đã duyệt bản thảo |
| `REJECTED` | Từ chối |
| `REGISTERED` | Đã đăng ký xuất bản |
| `DECISION_ISSUED` | Đã có quyết định xuất bản |
| `DEPOSITED` | Đã nộp lưu chiểu |
| `COMPLETED` | Hoàn tất |
| `ARCHIVED` | Lưu trữ |

### 7.2 Bảng chuyển trạng thái (khai báo dạng dữ liệu trong code)

| Từ | Sang | Ai | Điều kiện kiểm tra |
|---|---|---|---|
| DRAFT | SUBMITTED | CUSTOMER (chủ) | có ≥1 `MANUSCRIPT`, có `FORM_2`, `FORM_3`; nếu `LINKED` thì có `FORM_1` và `partner_name`; có ≥1 Contributor |
| SUBMITTED | NEED_SUPPLEMENT | EDITOR | bắt buộc ghi chú |
| NEED_SUPPLEMENT | SUBMITTED | CUSTOMER (chủ) | như DRAFT → SUBMITTED |
| SUBMITTED | ACCEPTED | EDITOR | **cấp `nxb_code`**, ghi `accepted_at` |
| ACCEPTED | EDITING | EDITOR | có `primary_editor` |
| EDITING | REVIEW_APPROVED / REVISION_REQUIRED / REJECTED | EDITOR | có `ManuscriptReview` mới nhất với `result` tương ứng |
| REVISION_REQUIRED | EDITING | EDITOR | có bản thảo phiên bản mới hơn bản đã duyệt |
| REVIEW_APPROVED | REGISTERED | EDITOR | có `isbn` hợp lệ, `registration_number`, `registration_date`, `FORM_5` |
| REGISTERED | DECISION_ISSUED | EDITOR | có `decision_number`, `decision_date`, `FORM_6`; nếu `LINKED` thì có `FORM_7`, `contract_number` |
| DECISION_ISSUED | DEPOSITED | EDITOR | có `FORM_9`, `deposit_date` |
| DEPOSITED | COMPLETED | EDITOR | – |
| COMPLETED, REJECTED | ARCHIVED | EDITOR | – |

### 7.3 Hàm duy nhất để đổi trạng thái

```python
def change_status(case, to_status, actor, note="", request=None) -> PublicationCase:
    """Kiểm tra quyền + điều kiện, đổi trạng thái, ghi StatusHistory và AuditEvent
    trong cùng một transaction. Sai điều kiện -> raise WorkflowError với thông báo
    tiếng Việt liệt kê điều kiện còn thiếu."""
```

- Không chỗ nào khác được gán `case.status = ...`. Thêm test kiểm tra điều này (ví dụ grep trong test hoặc kiểm tra `save()`).
- Hàm phụ: `allowed_transitions(user, case)` → danh sách trạng thái đích hợp lệ, để giao diện hiện nút.
- Phát tín hiệu (Django signal) `case_status_changed(case, from_status, to_status, actor, note)` để M4 gửi email. M0 không gửi email.

## 8. Mã hồ sơ và ISBN (apps/core/codes.py)

- `issue_nxb_code(case)`: dùng `CodeSequence` với `select_for_update()` trong transaction; định dạng `NXB-{year}-{number:04d}`, `year` = năm tiếp nhận. Gọi lần hai trên hồ sơ đã có mã → giữ nguyên mã cũ.
- `normalize_isbn(value)`: bỏ dấu gạch, khoảng trắng; chấp nhận ISBN-13 (13 số, bắt đầu 978 hoặc 979, đúng số kiểm tra). ISBN-10 → báo lỗi "Vui lòng nhập ISBN-13".
- `validate_isbn13(value)`: kiểm tra số kiểm tra theo trọng số 1-3.
- Hiển thị ISBN dạng có gạch nếu muốn là việc của giao diện; database lưu 13 số liền.
- `validate_isbn13` gắn làm **validator của trường `isbn`** trong model, nên mọi đường nhập (form, Django admin, script import Excel của M5) đều bị kiểm tra như nhau.

## 9. Lưu trữ file (apps/core/storage.py)

**Ràng buộc từ Cloud Run:** mỗi request HTTP/1 tối đa 32 MiB; response trên 32 MiB phải gửi dạng stream; ổ đĩa tạm nằm trong RAM. Bản thảo có thể trên 32 MiB, nên upload **luôn chia thành từng phần** (chunk) và download **luôn stream**. Không tăng RAM/timeout để thay cho việc chia nhỏ.

Giao diện trừu tượng:

```python
class FileStorage(Protocol):
    # Upload chia phần: mỗi phần CHUNK_SIZE = 8 MiB (bội số của 256 KiB), phần cuối có thể nhỏ hơn
    def start_upload(self, case, doc_type, filename, total_size, mime_type) -> str: ...  # trả upload_id
    def append_chunk(self, upload_id, offset: int, data: bytes) -> int: ...              # trả số byte đã nhận
    def finish_upload(self, upload_id) -> StoredFile: ...   # trả storage_ref, size, mime, sha256
    def abort_upload(self, upload_id) -> None: ...
    # Đọc file
    def open_stream(self, storage_ref) -> Iterator[bytes]: ...   # đọc từng khối, không nạp cả file vào RAM
    def exists(self, storage_ref) -> bool: ...
```

- M0 cài `LocalFileStorage`: ghi nối từng phần vào file tạm, `finish_upload` chuyển về `MEDIA_ROOT/cases/<case_id>/<doc_type>/v<version>_<tên file an toàn>`. sha256 tính dần theo từng phần.
- Chọn backend qua `FILE_STORAGE_BACKEND` (`local` | `gdrive`). M1 thêm `GoogleDriveStorage` cùng giao diện (resumable upload của Drive API).
- Model phụ `UploadSession` (apps/core): `id` UUID, `case`, `doc_type`, `form_code`, `filename`, `total_size`, `received_bytes`, `backend_ref` (ví dụ URL phiên resumable của Drive), `created_by`, `expires_at`, `status` (`OPEN`/`DONE`/`ABORTED`). Phiên quá 24 giờ bị hủy bằng lệnh `cleanup_uploads`.
- Service: `begin_document_upload(...)`, `upload_chunk(...)`, `complete_document_upload(...) -> Document` – kiểm tra quyền ở **mỗi bước**, kiểm tra đuôi file (`.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.jpg`, `.png`), tổng dung lượng ≤ `MAX_FILE_MB` (mặc định 200), tăng version, ghi AuditEvent khi hoàn tất.
- M0 cung cấp sẵn một **partial template + JS nhỏ** (`templates/partials/chunked_upload.html`, không thư viện ngoài) để module sau nhúng vào form: chia file bằng `File.slice`, gửi tuần tự, hiện thanh tiến trình, thử lại phần lỗi tối đa 3 lần.
- Tải xuống **luôn qua view của Portal** (`/documents/<id>/download/`) sau khi kiểm tra `can_download`, trả `StreamingHttpResponse` từ `open_stream`; không bao giờ đưa đường dẫn trực tiếp tới file.
- Ghi chú cho M1 (M0 không làm): service account không có dung lượng lưu trữ riêng, nên chỉ được ghi vào **Shared Drive** của NXB, nơi service account có vai trò Content Manager; mọi lời gọi Drive API phải có `supportsAllDrives=True`.

## 10. Giao diện khung

- `base.html`: header (logo chữ "NXB Kinh tế TP.HCM", tên người dùng, đăng xuất), menu theo vai trò, vùng thông báo, footer.
- Menu theo vai trò (link có thể trỏ tới trang placeholder "Đang xây dựng"):
  - CUSTOMER: Hồ sơ của tôi, Tạo hồ sơ mới, Tài khoản.
  - EDITOR: Danh sách hồ sơ, Hồ sơ cần xử lý, Tra cứu, **Thống kê** (tab con: Danh mục xuất bản; Tài chính và Công nợ chỉ hiện khi có quyền tài chính).
  - ADMIN: Người dùng, Danh mục, Biểu mẫu, Nhật ký hệ thống.
- **Không có** mục nào liên quan in ấn, phát hành.
- Sau đăng nhập chuyển tới trang chủ theo vai trò: `/khach-hang/`, `/noi-bo/`, `/quan-tri/`.
- Responsive, dùng tốt trên điện thoại.
- Django admin (`/django-admin/`) chỉ cho ADMIN, đăng ký đủ model; AuditEvent, StatusHistory, Document ở chế độ chỉ đọc.

## 11. Môi trường và triển khai

- `.env.example` liệt kê đủ biến: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `STAFF_GOOGLE_DOMAIN=ueh.edu.vn`, `BOOTSTRAP_ADMIN_EMAILS`, `FILE_STORAGE_BACKEND`, `MEDIA_ROOT`, `MAX_FILE_MB`, `EMAIL_URL` (khi phát triển trỏ tới Mailpit).
- `docker compose up` chạy được app + PostgreSQL + Mailpit trên máy trống, kèm `migrate` tự động khi khởi động. Lệnh test thống nhất: `docker compose run --rm web pytest`.
- `.github/workflows/ci.yml`: trên mọi pull request chạy `ruff check`, `ruff format --check`, `pytest` với PostgreSQL service. Pull request chỉ được gộp khi CI xanh.
- Dockerfile chạy được trên Cloud Run (lắng nghe `$PORT`) và trên máy chủ Linux thường.
- Không có bất kỳ secret nào trong repository.
- Lệnh `python manage.py seed_demo` tạo: 1 admin, 2 editor (1 có `finance_access = MANAGE`, 1 `NONE`), 2 customer, 5 hồ sơ ở các trạng thái khác nhau, danh mục mẫu (kể cả loại phí), vài khoản phải thu/đã thu ở các tình trạng khác nhau. Chỉ chạy khi `DJANGO_DEBUG=True`.

## 12. Test bắt buộc

Tối thiểu các nhóm sau, chạy bằng `pytest`:

1. **Phân quyền** (quan trọng nhất):
   - Customer A không xem/sửa/tải được hồ sơ và tài liệu của Customer B (qua URL trực tiếp → 404).
   - Customer không tải được `FORM_4`, không thấy note `INTERNAL`.
   - Admin không xem được hồ sơ.
   - Editor xem được mọi hồ sơ.
2. **Quy trình:** mỗi dòng của bảng 7.2 có ít nhất 1 test thành công và 1 test thiếu điều kiện; chuyển trạng thái không có trong bảng bị từ chối; mỗi lần chuyển có đúng 1 StatusHistory và 1 AuditEvent.
3. **Mã:** cấp mã NXB liên tiếp, không trùng khi gọi song song (test với 2 transaction), không đổi khi gọi lại; ISBN hợp lệ/không hợp lệ (ít nhất 5 ca).
4. **Tài liệu:** upload chia phần ghép đúng file (sha256 khớp với file gốc), file 70 MiB tải lên được qua nhiều phần 8 MiB, mỗi request ≤ 8 MiB + phần đầu; thiếu phần/sai offset bị từ chối; tăng version, bản cũ còn nguyên; sai định dạng/quá dung lượng bị từ chối; người không có quyền không gửi được phần nào; download trả response dạng stream.
5. **Audit:** không sửa, không xóa được AuditEvent.
6. **ManuscriptReview:** từ chối khi bản thảo hoặc Mẫu 4 thuộc hồ sơ khác.
7. **Đăng nhập:** EDITOR không đăng nhập được bằng mật khẩu; email Google UEH chưa được gán vai trò → CUSTOMER.
8. **Tài chính:** editor `finance_access = NONE` gọi URL/khung tài chính → 404; `VIEW` không tạo được khoản thu; không xóa được Receivable/Collection; `outstanding`, `receivable_status`, `aging_bucket` đúng với các ca: chưa thu, thu một phần, thu đủ, quá hạn 15/45/75/120 ngày, có bút toán điều chỉnh.

Mục tiêu độ phủ test của `apps/core` ≥ 85%.

## 13. Sản phẩm bàn giao

- [ ] Repository chạy được bằng `docker compose up`, đăng nhập được bằng tài khoản seed.
- [ ] Toàn bộ model mục 5 + migration.
- [ ] `permissions.py`, `workflow.py`, `codes.py`, `storage.py`, `audit.py`, `finance.py` trong `apps/core`, có docstring tiếng Việt.
- [ ] Giao diện khung mục 10.
- [ ] Test mục 12, tất cả pass; kèm file `docs/TEST_REPORT.md` ghi lệnh chạy và kết quả thật.
- [ ] `docs/DATA_MODEL.md` (bảng model + sơ đồ quan hệ dạng Mermaid).
- [ ] `docs/CONVENTIONS.md` — hướng dẫn cho M1–M8: cách dùng `cases_visible_to`, các mixin phân quyền, `change_status`, upload chia phần (`begin_document_upload`, `upload_chunk`, `complete_document_upload`, partial `chunked_upload.html`), `log_event`, các hàm tài chính; quy tắc đặt URL, template, test; danh sách file thuộc M0 không được sửa.
- [ ] `README.md`: cài đặt, biến môi trường, lệnh thường dùng.
- [ ] `apps/core/mixins.py` và `templates/partials/chunked_upload.html`.
- [ ] `.github/workflows/ci.yml` chạy xanh trên repository.
- [ ] `docs/QUESTIONS.md`: các điểm đã tự quyết định và lý do.

## 14. M0 không làm

- Không tích hợp Google Drive (M1).
- Không màn hình nghiệp vụ cho khách hàng hay biên tập viên ngoài trang placeholder (M2, M3).
- Không gửi email thật (M4), không báo cáo/thống kê/xuất Excel (M5, M8), không màn hình nhập khoản thu (M8), không trang công khai (M6). M0 chỉ làm model, hàm tính và quyền tài chính.
- Không thêm trạng thái, trường hay model ngoài tài liệu này. Cần thêm → ghi vào `QUESTIONS.md` và hỏi Owner.
- Không có bất kỳ chức năng in ấn, phát hành, hạch toán kế toán, xuất hóa đơn, thanh toán trực tuyến.

## 15. Tiêu chí nghiệm thu M0 (Owner kiểm tra)

1. Chạy `docker compose up` trên máy sạch, mở trình duyệt, đăng nhập 3 vai trò bằng tài khoản seed, thấy đúng menu.
2. Chạy `pytest` → toàn bộ pass, có báo cáo độ phủ.
3. Thử mở URL hồ sơ của customer khác → 404.
4. Trong Django admin, thử sửa một AuditEvent → không được.
5. Đọc `CONVENTIONS.md` và thấy đủ để giao M1–M7 mà không cần hỏi thêm về nền.
