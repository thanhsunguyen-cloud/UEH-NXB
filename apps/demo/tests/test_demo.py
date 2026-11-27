"""Test bản demo M2/M3: cổng bật/tắt /demo/ và 9 màn hình hiển thị với dữ liệu giả.

Các test không dùng fixture `db`: pytest-django sẽ báo lỗi nếu view nào chạm vào database.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.demo import fake_data
from apps.demo.views import demo_enabled

BANNER = "BẢN DEMO – DỮ LIỆU GIẢ – THAO TÁC KHÔNG ĐƯỢC LƯU"


@pytest.fixture
def demo_off(settings, monkeypatch):
    settings.DEBUG = False
    monkeypatch.delenv("DEMO_ENABLED", raising=False)


@pytest.fixture
def demo_on(settings, monkeypatch):
    settings.DEBUG = False
    monkeypatch.setenv("DEMO_ENABLED", "True")


ALL_SCREENS = [
    reverse("demo:index"),
    reverse("demo:customer_cases"),
    reverse("demo:customer_create"),
    reverse("demo:customer_case_detail", args=["hs-03"]),
    reverse("demo:editor_cases"),
    reverse("demo:editor_queue"),
    reverse("demo:editor_case_detail", args=["hs-08"]),
    reverse("demo:editor_case_detail", args=["hs-05"]) + "?tab=quy-trinh&mau_4=1",
    reverse("demo:stats_catalog"),
    reverse("demo:stats_debt"),
]


def test_demo_returns_404_when_debug_false_and_flag_off(client, demo_off):
    assert not demo_enabled()
    for url in ALL_SCREENS:
        assert client.get(url).status_code == 404, url


def test_demo_returns_200_when_flag_on(client, demo_on):
    assert client.get("/demo/").status_code == 200


def test_demo_returns_200_when_debug_true(client, settings, monkeypatch):
    settings.DEBUG = True
    monkeypatch.delenv("DEMO_ENABLED", raising=False)
    assert client.get("/demo/").status_code == 200


@pytest.mark.parametrize("value", ["False", "0", "", "no"])
def test_demo_flag_false_values_keep_demo_closed(client, demo_off, monkeypatch, value):
    monkeypatch.setenv("DEMO_ENABLED", value)
    assert client.get("/demo/").status_code == 404


@pytest.mark.parametrize("url", ALL_SCREENS)
def test_every_screen_renders_with_banner(client, demo_on, url):
    response = client.get(url)
    assert response.status_code == 200
    assert BANNER in response.content.decode()


def test_index_lists_nine_screens(client, demo_on):
    html = client.get("/demo/").content.decode()
    for number in range(1, 10):
        assert f"{number}. " in html
    assert "Khách hàng (người đại diện)" in html
    assert "Biên tập viên" in html


def test_fake_data_has_5_to_8_cases_in_different_statuses():
    assert 5 <= len(fake_data.CASES) <= 8
    assert len({c["status"] for c in fake_data.CASES}) >= 5


def test_customer_sees_friendly_labels_and_todo(client, demo_on):
    html = client.get(reverse("demo:customer_cases")).content.decode()
    assert "NXB đang biên tập" in html
    assert "Cần bổ sung Mẫu 2" in html
    # Hồ sơ không thuộc khách hàng demo không xuất hiện.
    assert "Logistics xanh" not in html


def test_customer_cannot_open_other_owner_case(client, demo_on):
    url = reverse("demo:customer_case_detail", args=["hs-07"])
    assert client.get(url).status_code == 404


def test_unknown_case_returns_404(client, demo_on):
    assert client.get(reverse("demo:customer_case_detail", args=["khong-co"])).status_code == 404
    assert client.get(reverse("demo:editor_case_detail", args=["khong-co"])).status_code == 404


def test_customer_detail_hides_internal_notes(client, demo_on):
    html = client.get(reverse("demo:customer_case_detail", args=["hs-03"])).content.decode()
    assert "Yêu cầu bổ sung đang mở" in html
    assert "chữ ký của đồng tác giả" in html
    assert "Ưu tiên tiếp nhận" not in html  # ghi chú nội bộ


@pytest.mark.parametrize(
    ("mode", "has_form1"),
    [("SELF", False), ("LINKED", True)],
)
def test_create_step3_shows_form1_only_when_linked(client, demo_on, mode, has_form1):
    url = reverse("demo:customer_create") + f"?buoc=3&hinh_thuc={mode}"
    html = client.get(url).content.decode()
    assert ("up-FORM_1" in html) is has_form1
    assert "up-FORM_2" in html and "up-FORM_3" in html and "up-MANUSCRIPT" in html


@pytest.mark.parametrize("step", ["1", "2", "4", "9", "abc"])
def test_create_steps_render(client, demo_on, step):
    url = reverse("demo:customer_create") + f"?buoc={step}&hinh_thuc=LINKED"
    response = client.get(url)
    assert response.status_code == 200


def test_create_step4_lists_missing_conditions(client, demo_on):
    url = reverse("demo:customer_create") + "?buoc=4&hinh_thuc=LINKED"
    html = client.get(url).content.decode()
    assert "Còn thiếu trước khi nộp" in html
    assert "Chưa tải Mẫu 1" in html


def test_create_invalid_mode_falls_back_to_self(client, demo_on):
    url = reverse("demo:customer_create") + "?buoc=3&hinh_thuc=XYZ"
    assert "up-FORM_1" not in client.get(url).content.decode()


def test_editor_search_and_filters(client, demo_on):
    url = reverse("demo:editor_cases")
    html = client.get(url, {"q": "9786049221057"}).content.decode()
    assert "Logistics xanh" in html and "Kinh tế học bên hiên nhà" not in html

    html = client.get(url, {"q": "NXB-2026-0041"}).content.decode()
    assert "Kinh tế tuần hoàn" in html and "Logistics xanh" not in html

    html = client.get(url, {"q": "đặng khải minh"}).content.decode()
    assert "Kinh tế tuần hoàn" in html

    html = client.get(url, {"trang_thai": "DRAFT"}).content.decode()
    assert "Kinh tế học bên hiên nhà" in html and "Logistics xanh" not in html

    html = client.get(url, {"hinh_thuc": "LINKED"}).content.decode()
    assert "Quản trị dòng tiền" in html and "Tài chính hành vi" not in html

    html = client.get(url, {"btv": "btv-ha"}).content.decode()
    assert "Tài chính hành vi" in html and "Kinh tế tuần hoàn" not in html

    html = client.get(url, {"btv": "chua-phan-cong"}).content.decode()
    assert "Quản trị dòng tiền" in html and "Tài chính hành vi" not in html


def test_editor_list_htmx_returns_partial_table(client, demo_on):
    response = client.get(reverse("demo:editor_cases"), {"q": "logistics"}, HTTP_HX_REQUEST="true")
    html = response.content.decode()
    assert response.status_code == 200
    assert "<table" in html and BANNER not in html
    assert "Tìm thấy 1 / " in html


def test_editor_queue_groups(client, demo_on):
    response = client.get(reverse("demo:editor_queue"))
    groups = {g["code"]: g["cases"] for g in response.context["groups"]}
    assert [c["slug"] for c in groups["moi-nop"]] == ["hs-02"]
    assert [c["slug"] for c in groups["khach-da-bo-sung"]] == ["hs-04"]
    assert [c["slug"] for c in groups["cho-dang-ky"]] == ["hs-07"]


def test_editor_detail_has_six_tabs_and_valid_transitions(client, demo_on):
    html = client.get(reverse("demo:editor_case_detail", args=["hs-08"])).content.decode()
    for tab in ["Tổng quan", "Tác giả", "Tài liệu &amp; phiên bản", "Quy trình", "Ghi chú &amp; trao đổi", "Tài chính"]:  # fmt: skip
        assert tab in html
    assert "215/QĐ-NXBKT" in html  # số QĐXB
    assert "Đã nộp lưu chiểu" in html  # bước chuyển hợp lệ DECISION_ISSUED -> DEPOSITED
    assert "Chưa có Mẫu 9" in html


def test_editor_detail_hides_finance_tab_without_permission(client, demo_on):
    url = reverse("demo:editor_case_detail", args=["hs-08"])
    html = client.get(url, {"tai_chinh": "0", "tab": "tai-chinh"}).content.decode()
    assert 'id="tab-tai-chinh"' not in html
    assert "Còn nợ" not in html
    response = client.get(url, {"tai_chinh": "0", "tab": "tai-chinh"})
    assert response.context["active_tab"] == "tong-quan"


def test_form4_modal_shows_case_and_manuscript_version(client, demo_on):
    url = reverse("demo:editor_case_detail", args=["hs-05"])
    response = client.get(url, {"tab": "quy-trinh", "mau_4": "1"})
    html = response.content.decode()
    assert response.context["open_form4"] is True
    assert 'id="form4Modal"' in html
    assert "NXB-2026-0041" in html
    assert "Phiên bản 2 – ktth-v2.docx" in html
    assert "Đồng ý xuất bản" in html and 'id="form4-confirm"' in html


def test_stats_catalog_filters_by_period(client, demo_on):
    url = reverse("demo:stats_catalog")
    response = client.get(url)
    assert response.context["year"] == 2026
    assert len(response.context["chart"]) == 12
    assert sum(c["count"] for c in response.context["chart"]) == len(response.context["books"])

    response = client.get(url, {"nam": "2026", "quy": "3"})
    assert [c["month"] for c in response.context["chart"]] == [7, 8, 9]
    assert all(b["decision_date"].month in (7, 8, 9) for b in response.context["books"])

    response = client.get(url, {"nam": "2025", "quy": "x"})
    assert response.context["year"] == 2025 and response.context["quarter"] == ""

    response = client.get(url, {"nam": "abc"})
    assert response.context["year"] == 2026
    response = client.get(url, {"nam": "1990"})
    assert response.context["year"] == 2026


def test_stats_debt_buckets(client, demo_on):
    url = reverse("demo:stats_debt")
    response = client.get(url)
    rows = response.context["rows"]
    assert rows and all(r["outstanding"] > 0 for r in rows)
    assert response.context["grand_total"] == sum(r["outstanding"] for r in rows)
    codes = {b["code"] for b in response.context["buckets"] if b["count"]}
    assert {"NOT_DUE", "D90_PLUS"} <= codes

    response = client.get(url, {"nhom": "D90_PLUS"})
    assert all(r["bucket"] == "D90_PLUS" for r in response.context["rows"])
    response = client.get(url, {"nhom": "SAI"})
    assert response.context["selected"] == ""


@pytest.mark.parametrize(
    ("due", "expected"),
    [
        (None, "NOT_DUE"),
        (fake_data.DEMO_TODAY, "NOT_DUE"),
        (fake_data.date(2026, 11, 1), "D1_30"),
        (fake_data.date(2026, 10, 1), "D31_60"),
        (fake_data.date(2026, 9, 1), "D61_90"),
        (fake_data.date(2026, 1, 1), "D90_PLUS"),
    ],
)
def test_aging_bucket(due, expected):
    assert fake_data.aging_bucket(due) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(25000000, "25.000.000"), (fake_data.Decimal("0"), "0"), ("abc", ""), (None, "")],
)
def test_vnd_filter(value, expected):
    from apps.demo.templatetags.demo_tags import vnd

    assert vnd(value) == expected


def test_published_books_have_unique_valid_isbn():
    from apps.core.codes import validate_isbn13

    isbns = [b["isbn"] for b in fake_data.PUBLISHED_BOOKS]
    assert len(isbns) == len(set(isbns))
    for isbn in isbns:
        validate_isbn13(isbn)
