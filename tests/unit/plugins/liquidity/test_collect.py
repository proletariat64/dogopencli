"""Offset/single acquisition: duplicates, stalls, changed totals, conflicts."""

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from dogopencli.errors import INVALID_RESPONSE, CliError
from dogopencli.plugins.liquidity.capability import (
    LiquidityListCapability,
    encode_scope,
)
from dogopencli.plugins.liquidity.collect import collect_liquidity_scope
from dogopencli.plugins.liquidity.leaves import (
    CASH_ACCOUNTS,
    FORECAST_CASHFLOWS,
    INVESTMENT_HOLDINGS,
    INVESTMENT_PRODUCTS,
)
from dogopencli.transport import OriginMetadata, TransportResponse


@pytest.mark.parametrize("bounds", [{"deadline": -1.0}, {"budget_seconds": -1.0}])
def test_account_collection_obeys_expired_explicit_bounds(bounds):
    from dogopencli.plugins.liquidity.account_forecasts import ACCOUNT_DEMANDS

    fake = FakeQueryTransport(lambda body: {})
    with pytest.raises(CliError) as caught:
        collect_liquidity_scope(
            LiquidityListCapability(ACCOUNT_DEMANDS), fake, "", **bounds
        )
    assert caught.value.code == "TIMEOUT"
    assert fake.requests == []


@pytest.mark.parametrize(
    ("bounds", "expected_deadline"),
    [
        ({}, 1900.0),
        ({"budget_seconds": 10.0}, 110.0),
        ({"deadline": 105.0, "budget_seconds": 999.0}, 105.0),
    ],
)
def test_account_collection_keeps_default_and_explicit_budgets(
    monkeypatch, bounds, expected_deadline
):
    from dogopencli.plugins.liquidity import collect as liquidity_collect
    from dogopencli.plugins.liquidity.account_strategies import ACCOUNT_STRATEGIES

    monkeypatch.setattr(liquidity_collect.time, "monotonic", lambda: 100.0)
    fake = FakeQueryTransport(
        lambda body: {"success": True, "data": {"data": [], "totalCount": 0}}
    )
    result = collect_liquidity_scope(
        LiquidityListCapability(ACCOUNT_STRATEGIES), fake, "", **bounds
    )
    assert result.complete
    assert result.deadline == expected_deadline


ORIGIN = OriginMetadata(
    backend="cdp",
    simulated=False,
    dataset_id=None,
    dataset_complete=None,
    backend_complete=None,
    source_observed_from=None,
    source_observed_to=None,
)


class FakeQueryTransport:
    """Answers each request from a handler keyed by the request body."""

    def __init__(self, handler: Callable[[dict], dict]) -> None:
        self.handler = handler
        self.requests: list[dict[str, Any]] = []

    def execute(self, request, *, timeout=None):
        self.requests.append(request.body)
        document = self.handler(request.body)
        return TransportResponse(
            status=200, body=json.dumps(document).encode(), origin=ORIGIN
        )


def holdings_page(rows, total):
    return {
        "success": True,
        "data": {"data": rows, "totalCount": total, "rowStart": 0, "pageSize": 10},
    }


def holding(index, day="20261001", amount="10.00"):
    return {
        "investmentNo": f"H{index:04d}",
        "valueDate": day,
        "amount": amount,
        "currency": "USD",
    }


def collect(rows_by_offset, total):
    holdings = LiquidityListCapability(replace(INVESTMENT_HOLDINGS, page_size=10))
    transport = FakeQueryTransport(
        lambda body: holdings_page(rows_by_offset(body), total)
    )
    return transport, collect_liquidity_scope(
        holdings, transport, encode_scope({"date": "20261001"})
    )


def test_offset_collection_merges_pages_until_the_total():
    transport, result = collect(
        lambda body: [
            holding(i) for i in range(body["rowStart"], min(body["rowStart"] + 10, 25))
        ],
        25,
    )
    assert result.complete
    assert result.total_count == 25
    assert len(result.records) == 25
    assert [body["rowStart"] for body in transport.requests] == [0, 10, 20]


def test_overlapping_pages_are_incomplete_never_deduplicated_to_success():
    # The 2026-10-01 defect: page 2 repeats a page-1 row, so unique coverage
    # stays below the reported total.
    def rows(body):
        if body["rowStart"] == 0:
            return [holding(i) for i in range(10)]
        return [holding(9), holding(10)]

    _, result = collect(rows, 12)
    assert not result.complete
    assert len(result.records) == 11


def test_conflicting_identity_content_is_a_hard_failure():
    def rows(body):
        if body["rowStart"] == 0:
            return [holding(i) for i in range(10)]
        return [holding(1, amount="99.99")]

    with pytest.raises(CliError, match="conflicting content"):
        collect(rows, 11)


def test_short_page_keeps_the_verified_offset_stride():
    def rows(body):
        if body["rowStart"] == 0:
            return [holding(i) for i in range(9)]
        return [holding(i) for i in range(9, 19)]

    transport, result = collect(rows, 19)
    assert [body["rowStart"] for body in transport.requests] == [0, 10]
    assert result.complete
    assert len(result.records) == 19


def test_short_page_missing_source_row_remains_incomplete():
    transport, result = collect(
        lambda body: [
            holding(i) for i in range(body["rowStart"], body["rowStart"] + 9)
        ],
        20,
    )
    assert [body["rowStart"] for body in transport.requests] == [0, 10]
    assert not result.complete
    assert result.total_count == 20
    assert len(result.records) == 18


def test_changed_total_is_a_hard_failure():
    holdings = LiquidityListCapability(replace(INVESTMENT_HOLDINGS, page_size=10))
    calls = iter([12, 13])
    transport = FakeQueryTransport(
        lambda body: holdings_page([holding(1)], next(calls))
    )
    with pytest.raises(CliError, match="total changed"):
        collect_liquidity_scope(holdings, transport, encode_scope({"date": "20261001"}))


def test_empty_page_before_the_total_stalls():
    holdings = LiquidityListCapability(replace(INVESTMENT_HOLDINGS, page_size=10))
    fake = FakeQueryTransport(lambda body: holdings_page([], 5))
    with pytest.raises(CliError) as error:
        collect_liquidity_scope(holdings, fake, encode_scope({"date": "20261001"}))
    assert error.value.code == INVALID_RESPONSE


def test_oversized_page_is_rejected():
    holdings = LiquidityListCapability(replace(INVESTMENT_HOLDINGS, page_size=10))
    fake = FakeQueryTransport(
        lambda body: holdings_page([holding(i) for i in range(11)], 11)
    )
    with pytest.raises(CliError, match="more rows"):
        collect_liquidity_scope(holdings, fake, encode_scope({"date": "20261001"}))


def test_single_response_route_collects_the_whole_set():
    products = LiquidityListCapability(INVESTMENT_PRODUCTS)
    rows = [{"incrementProductId": f"P{i:03d}", "currency": "USD"} for i in range(908)]
    fake = FakeQueryTransport(
        lambda body: {"success": True, "data": {"data": rows, "totalCount": 908}}
    )
    result = collect_liquidity_scope(products, fake, "")
    assert result.complete
    assert len(result.records) == 908
    assert len(fake.requests) == 1


def test_single_response_with_uncovered_total_is_incomplete():
    products = LiquidityListCapability(INVESTMENT_PRODUCTS)
    rows = [{"incrementProductId": "P001"}]
    fake = FakeQueryTransport(
        lambda body: {"success": True, "data": {"data": rows, "totalCount": 2}}
    )
    result = collect_liquidity_scope(products, fake, "")
    assert not result.complete


def test_result_flag_offset_leaf_uses_vo_offsets():
    accounts = LiquidityListCapability(replace(CASH_ACCOUNTS, page_size=10))

    def answer(body):
        vo = json.loads(body["bankAccountQueryVO"])
        rows = [
            {"id": "0", "aliasName": f"A{i:03d}", "currency": "USD"}
            for i in range(vo["rowStart"], min(vo["rowStart"] + 10, 15))
        ]
        return {
            "resultFlag": True,
            "result": {"bankAccountPropertyVOList": rows},
            "count": 15,
        }

    fake = FakeQueryTransport(answer)
    result = collect_liquidity_scope(accounts, fake, "")
    assert result.complete
    assert len(result.records) == 15
    assert fake.requests[0]["wallet"] is False
    assert [
        json.loads(body["bankAccountQueryVO"])["rowStart"] for body in fake.requests
    ] == [0, 10]


def test_accounts_large_page_keeps_backend_shortfall_incomplete():
    rows = [{"id": "0", "aliasName": f"A{i}", "currency": "USD"} for i in range(3690)]
    fake = FakeQueryTransport(
        lambda body: {
            "resultFlag": True,
            "result": {"bankAccountPropertyVOList": rows},
            "count": 3691,
        }
    )
    result = collect_liquidity_scope(LiquidityListCapability(CASH_ACCOUNTS), fake, "")
    assert not result.complete
    assert len(result.records) == 3690
    assert result.total_count == 3691
    assert result.pages == 1
    assert result.page_size == 5000
    assert json.loads(fake.requests[0]["bankAccountQueryVO"])["pageSize"] == 5000


def test_large_page_uses_its_own_offset_stride():
    capability = LiquidityListCapability(INVESTMENT_HOLDINGS)
    fake = FakeQueryTransport(
        lambda body: holdings_page(
            [
                holding(i)
                for i in range(body["rowStart"], min(body["rowStart"] + 500, 1201))
            ],
            1201,
        )
    )
    result = collect_liquidity_scope(capability, fake, "")
    assert result.complete
    assert result.page_size == 500
    assert [body["rowStart"] for body in fake.requests] == [0, 500, 1000]


def test_accounts_alias_conflict_still_rejects_collection():
    rows = [
        {"id": "0", "aliasName": "A1", "currency": "USD", "accountNo": "N1"},
        {"id": "0", "aliasName": "A1", "currency": "USD", "accountNo": "N2"},
    ]
    fake = FakeQueryTransport(
        lambda body: {
            "resultFlag": True,
            "result": {"bankAccountPropertyVOList": rows},
            "count": 2,
        }
    )
    with pytest.raises(CliError, match="conflicting content"):
        collect_liquidity_scope(LiquidityListCapability(CASH_ACCOUNTS), fake, "")


def test_cashflows_preserve_identical_rows_without_a_native_key():
    row = {
        "bankAccountNo": "A1",
        "originalBizNo": "",
        "expectValueDate": "",
        "expectValueDateTime": "202609302359",
        "fundDirection": "Credit",
    }
    rows = [row, dict(row), {**row, "amountStr": "2.00"}]
    fake = FakeQueryTransport(
        lambda body: {
            "resultFlag": True,
            "result": {"bankAccountCashFlowVOList": rows},
        }
    )
    result = collect_liquidity_scope(
        LiquidityListCapability(FORECAST_CASHFLOWS), fake, ""
    )
    assert result.complete
    assert result.total_count is None
    assert result.evidence.arrivals == 3
    assert result.evidence.unique_count is None
    assert result.evidence.duplicate_count is None
    assert result.records == rows
