"""Unit tests for the Channel capability parser and local filter semantics."""

from decimal import Decimal

import pytest

from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical
from dogopencli.plugins.payment.channel import CHANNEL_CAPABILITY as CAP


def envelope(result_obj: dict, **outer) -> bytes:
    document = {"success": True, "status": True, "data": None, **outer}
    if result_obj is not None:
        document["resultObj"] = result_obj
    return canonical(document).encode()


def result_page(rows: list, **paging) -> dict:
    base = {
        "success": True,
        "code": "IPAY_RS_100000200",
        "pageNum": 1,
        "pageSize": 100,
        "totalCount": len(rows),
        "totalPages": 1 if rows else 0,
        "payoutAbilityVOList": rows,
    }
    base.update(paging)
    return base


def test_parse_success_page_preserves_decimal():
    body = envelope(
        result_page([{"abilityId": 1, "chargeAmount": {"amount": Decimal("0.10")}}])
    )
    page = CAP.parse_page(body)
    assert page.total_count == 1
    assert page.records[0]["chargeAmount"]["amount"] == Decimal("0.10")


def test_parse_empty_result_echoes_page_zero():
    body = envelope(result_page([], pageNum=0, pageSize=10))
    page = CAP.parse_page(body)
    assert page.records == []
    assert page.page_num == 0
    assert page.total_pages == 0


@pytest.mark.parametrize(
    "body, code",
    [
        (
            canonical({"success": False, "status": False}).encode(),
            BUSINESS_QUERY_FAILED,
        ),
        (envelope(None), INVALID_RESPONSE),
        (envelope({"success": False}), BUSINESS_QUERY_FAILED),
        (envelope(result_page([], pageNum="1")), INVALID_RESPONSE),
        (
            envelope(
                {
                    "success": True,
                    "pageNum": 0,
                    "pageSize": 10,
                    "totalCount": 0,
                    "totalPages": 0,
                }
            ),
            INVALID_RESPONSE,
        ),
        (
            envelope(result_page([{"a": 1}], totalCount=0, totalPages=0)),
            INVALID_RESPONSE,
        ),
        (b"not json", INVALID_RESPONSE),
    ],
)
def test_parse_rejects_bad_envelopes(body, code):
    with pytest.raises(CliError) as caught:
        CAP.parse_page(body)
    assert caught.value.code == code


def test_filter_records_or_within_and_across():
    records = [
        {"status": "ENABLE", "debitCurrency": "USD"},
        {"status": "DISABLE", "debitCurrency": "USD"},
        {"status": "ENABLE", "debitCurrency": "EUR"},
    ]
    assert CAP.filter_records(records, {"status": ["ENABLE", "DISABLE"]}) == records
    assert CAP.filter_records(
        records, {"status": ["ENABLE"], "debitCurrencyList": ["EUR"]}
    ) == [records[2]]
    assert CAP.filter_records(records, {"status": ["GRAY"]}) == []


def test_request_filters_requires_strings():
    with pytest.raises(CliError) as caught:
        CAP.request_filters({"status": 1})
    assert caught.value.code == REQUEST_NOT_ALLOWED
    assert CAP.request_filters({"debitCurrencyList": ["USD"]}) == {
        "debitCurrencyList": ["USD"]
    }
