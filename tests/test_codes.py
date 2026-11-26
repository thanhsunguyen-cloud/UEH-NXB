"""Nhóm test 3: Cấp mã NXB tuần tự (kể cả đồng thời 2 transaction) và kiểm tra ISBN-13."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.exceptions import ValidationError
from django.db import connections

from apps.core.codes import issue_nxb_code, normalize_isbn, validate_isbn13
from tests.factories import PublicationCaseFactory


@pytest.mark.django_db(transaction=True)
def test_issue_nxb_code_sequential_idempotent_and_concurrent(customer_a):
    c1 = PublicationCaseFactory(owner=customer_a)
    c2 = PublicationCaseFactory(owner=customer_a)

    def _worker(case_obj):
        try:
            return issue_nxb_code(case_obj, year=2026)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_worker, c1)
        f2 = pool.submit(_worker, c2)
        codes = {f1.result(), f2.result()}

    assert codes == {"NXB-2026-0001", "NXB-2026-0002"}

    # Gọi lại lần 2 không đổi mã
    c1.refresh_from_db()
    assert issue_nxb_code(c1, year=2026) == c1.nxb_code


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("978-604-346-001-8", "9786043460018"),
        ("978 0 306 40615 7", "9780306406157"),
        ("9791090636071", "9791090636071"),
    ],
)
def test_valid_isbn13(raw, expected):
    assert normalize_isbn(raw) == expected
    validate_isbn13(expected)


@pytest.mark.parametrize(
    "invalid,msg_fragment",
    [
        ("0-306-40615-2", "Vui lòng nhập ISBN-13"),  # ISBN-10
        ("9786043460019", "Số kiểm tra"),  # Sai check digit
        ("9776043460011", "978 hoặc 979"),  # Sai tiền tố
        ("978604346001", "đúng 13 chữ số"),  # Thiếu chữ số
        ("97860434600AB", "đúng 13 chữ số"),  # Chứa chữ cái
    ],
)
def test_invalid_isbn13(invalid, msg_fragment):
    with pytest.raises(ValidationError) as exc:
        normalize_isbn(invalid)
    assert msg_fragment in str(exc.value)
