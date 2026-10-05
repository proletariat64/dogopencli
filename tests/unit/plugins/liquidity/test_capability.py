"""Request construction, scope validation and response parsing per contract."""

import json

import pytest

from dogopencli.errors import CliError
from dogopencli.plugins.liquidity import spec
from dogopencli.plugins.liquidity.capability import (
    LiquidityDetailCapability,
    LiquidityListCapability,
    decode_scope,
    encode_scope,
    scope_values,
)
from dogopencli.plugins.liquidity.leaves import (
    CASH_ACCOUNTS,
    FORECAST_CASHFLOWS,
    INVESTMENT_HOLDINGS,
    INVESTMENT_INTEREST_RATES,
    LIST_LEAVES,
    RISK_METRICS,
)
from dogopencli.plugins.liquidity.spec import ScopeOption


def page(rows, total=None, **extra):
    data = {"data": rows}
    if total is not None:
        data["totalCount"] = total
    return json.dumps({"success": True, "data": data, **extra}).encode()


def result_page(rows, total=None, container="dataValue"):
    result = {container: rows}
    if total is not None:
        result["count"] = total
    return json.dumps({"resultFlag": True, "result": result}).encode()


def test_encode_decode_scope_roundtrip():
    values = {"currency": "SGD", "aliasNameList": ["A1"], "n": 3}
    assert decode_scope(encode_scope(values)) == values
    with pytest.raises(CliError):
        decode_scope("broken-scope")


def test_scope_values_required_choices_and_dates():
    options = (
        ScopeOption(
            "book_type", "bookType", "t", required=True, choices=("INNER", "OUTER")
        ),
        ScopeOption("from_date", "d0", "t", required=True, date=True, window="from"),
        ScopeOption("to_date", "d1", "t", required=True, date=True, window="to"),
    )
    fields, window = scope_values(
        options,
        {"book_type": "INNER", "from_date": "20260901", "to_date": "20260930"},
    )
    assert fields == {"bookType": "INNER", "d0": "20260901", "d1": "20260930"}
    assert window == ("20260901", "20260930")
    for provided, fragment in (
        ({}, "required"),
        (
            {"book_type": "SIDE", "from_date": "20260901", "to_date": "20260930"},
            "one of",
        ),
        (
            {"book_type": "INNER", "from_date": "2026-09-01", "to_date": "20260930"},
            "YYYYMMDD",
        ),
        (
            {"book_type": "INNER", "from_date": "20260230", "to_date": "20260930"},
            "valid YYYYMMDD",
        ),
        (
            {"book_type": "INNER", "from_date": "20260901", "to_date": "20261301"},
            "valid YYYYMMDD",
        ),
        (
            {"book_type": "INNER", "from_date": "20260930", "to_date": "20260901"},
            "after its end",
        ),
    ):
        with pytest.raises(CliError, match=fragment):
            scope_values(options, provided)


def test_scope_values_list_of_one_and_virtual():
    options = (
        ScopeOption("account", "aliasNameList", "t", required=True, list_of_one=True),
        ScopeOption(
            "source", "source", "t", required=True, virtual=True, match="market"
        ),
    )
    fields, _ = scope_values(options, {"account": "A1", "source": "market"})
    assert fields["aliasNameList"] == ["A1"]


def test_flat_json_page_body_and_allowlist():
    capability = LiquidityListCapability(INVESTMENT_HOLDINGS)
    scope = encode_scope({"date": "20261001"})
    body = capability.page_body(scope, 500)
    assert body == {
        "tntInstId": "GUAPW3SG",
        "status": ["ACTIVE", "INACTIVE"],
        "date": "20261001",
        "rowStart": 500,
        "pageSize": 500,
    }
    assert set(body) <= capability.contract.allowed_body_keys


def test_vo_query_body_keeps_json_string_shape():
    capability = LiquidityListCapability(CASH_ACCOUNTS)
    body = capability.page_body("", 10)
    assert body["wallet"] is False
    assert body["tntInstId"] == "GUAPW3SG"
    vo = json.loads(body["bankAccountQueryVO"])
    assert vo == {"tntInstId": "GUAPW3SG", "rowStart": 10, "pageSize": 5000}
    assert capability.contract.page_size == 5000


def test_virtual_option_never_reaches_the_wire():
    capability = LiquidityListCapability(INVESTMENT_INTEREST_RATES)
    scope = encode_scope(
        {"source": "market", "beginDate": "20261001", "endDate": "20261001"}
    )
    body = capability.page_body(scope, 0)
    assert "source" not in body
    assert "source" not in capability.contract.allowed_body_keys
    assert body["isPage"] == "Y"


def test_single_response_without_pagination_fields():
    for list_spec in (RISK_METRICS, FORECAST_CASHFLOWS):
        capability = LiquidityListCapability(list_spec)
        assert "rowStart" not in capability.contract.allowed_body_keys
        assert "pageSize" not in capability.contract.allowed_body_keys


def test_parse_rows_success_and_typed_identity():
    capability = LiquidityListCapability(INVESTMENT_HOLDINGS)
    rows, total = capability.parse_rows(
        page([{"investmentNo": "H1", "valueDate": "20261001"}], total=1)
    )
    assert total == 1
    assert capability.identity_key(rows[0]) == ('"H1"',)
    with pytest.raises(CliError, match="identity field"):
        capability.parse_rows(page([{"valueDate": "20261001"}], total=1))


def test_parse_rows_envelope_and_total_validation():
    capability = LiquidityListCapability(CASH_ACCOUNTS)
    rows, total = capability.parse_rows(
        json.dumps(
            {
                "resultFlag": True,
                "result": {
                    "bankAccountPropertyVOList": [
                        {"id": "0", "aliasName": "A1", "currency": "USD"}
                    ]
                },
                "count": 1,
            }
        ).encode()
    )
    assert total == 1
    with pytest.raises(CliError):
        capability.parse_rows(result_page([{"id": "A1"}], total="many"))
    with pytest.raises(CliError):
        capability.parse_rows(result_page("not-a-list", total=1))


def test_detail_body_typed_identity():
    get_spec = next(
        detail
        for detail in _detail_specs()
        if detail.name == "liquidity.rules.operation.get"
    )
    get_capability = LiquidityDetailCapability(get_spec)
    # GET details carry the tenant field, exactly as probed.
    assert get_capability.detail_body({"rule_id": "R1"}) == {
        "ruleId": "R1",
        "tntInstId": "GUAPW3SG",
    }
    assert get_capability.contract.allowed_body_keys == frozenset(
        {"ruleId", "tntInstId"}
    )
    capability = LiquidityDetailCapability(
        next(
            detail
            for detail in _detail_specs()
            if detail.name == "liquidity.network.account-capabilities.get"
        )
    )
    # The verified POST detail request carries no tntInstId.
    assert capability.detail_body({"id": "100014"}) == {"id": 100014}
    for invalid in ("abc", "²"):
        with pytest.raises(CliError, match="integer"):
            capability.detail_body({"id": invalid})
    with pytest.raises(CliError):
        capability.detail_body({})


def _detail_specs():
    from dogopencli.plugins.liquidity.leaves import DETAIL_SPECS

    return DETAIL_SPECS


def test_parse_detail_echo_validation():
    detail_spec = next(
        detail
        for detail in _detail_specs()
        if detail.name == "liquidity.investment.holdings.get"
    )
    capability = LiquidityDetailCapability(detail_spec)
    body = json.dumps({"success": True, "data": {"orderId": "H1", "amount": "1.5"}})
    detail = capability.parse_detail(body.encode(), {"investment_no": "H1"})
    assert detail["orderId"] == "H1"
    wrong = json.dumps({"success": True, "data": {"orderId": "H2"}})
    with pytest.raises(CliError, match="does not match"):
        capability.parse_detail(wrong.encode(), {"investment_no": "H1"})
    missing = json.dumps({"success": True, "data": {"amount": "1.5"}})
    with pytest.raises(CliError, match="does not match"):
        capability.parse_detail(missing.encode(), {"investment_no": "H1"})


def test_parse_detail_list_payload_echoes_each_row():
    detail_spec = next(
        detail
        for detail in _detail_specs()
        if detail.name == "liquidity.investment.products.history"
    )
    capability = LiquidityDetailCapability(detail_spec)
    body = json.dumps(
        {
            "success": True,
            "data": [
                {"incrementProductCode": "P1", "version": 2},
                {"incrementProductCode": "P1", "version": 1},
            ],
        }
    )
    rows = capability.parse_detail(body.encode(), {"product_code": "P1"})
    assert [row["version"] for row in rows] == [2, 1]


def test_every_shipped_leaf_builds_a_valid_contract():
    assert (
        len(LIST_LEAVES) == 58
    )  # includes fee orders, pool balances, credit usage and quotes
    for leaf in LIST_LEAVES.values():
        for variant in leaf.variants:
            capability = leaf.capability(variant)
            contract = capability.contract
            assert contract.host == "iliquidity.alipay.com"
            assert contract.path == variant.endpoint
            if variant.pagination == spec.PAGE_OFFSET:
                assert variant.total is not None
            if variant.profile == spec.PROFILE_DATED:
                assert variant.series_field
