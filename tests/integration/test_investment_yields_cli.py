"""Independent native accrual/settlement Lists preserve source records."""

from copy import deepcopy
from decimal import Decimal

import pytest
from integration.test_native_relationship_leaves import source_envelope

pytest_plugins = ["integration.test_native_relationship_leaves"]

CASES = [
    (
        "investment.accrual",
        {
            "investmentNo": "INVESTMENT",
            "transactionDate": "20261015",
            "amount": Decimal("0.123456789012345678901"),
            "unknown": [None, False],
        },
        "/accrualBaseList.json",
    ),
    (
        "investment.settlement",
        {
            "id": "EVENT",
            "transactionId": "INVESTMENT",
            "settlementDate": "20261015",
            "amount": "1.0000",
            "unknown": [None, False],
        },
        "/cashBaseList.json",
    ),
]


@pytest.mark.parametrize("installed", [name for name, _, _ in CASES], indirect=True)
def test_single_yield_source_preserves_rows_without_parent_assembly(installed):
    name, cli, browser, _ = installed
    row = next(row for leaf, row, _ in CASES if leaf == name)
    browser.business_script.append(source_envelope([row]))
    data = cli(
        "liquidity",
        "list",
        name,
        "--from-date",
        "20261015",
        "--to-date",
        "20261015",
        "--live",
        "--limit",
        "0",
        "--require-complete",
    )
    assert data["data"] == [row]
    assert data["meta"]["complete"] is True
    assert len(browser.business_requests) == 1
    request = browser.business_requests[0]
    assert request["pageSize"] == 5000 and request["rowStart"] == 0
    if name == "investment.accrual":
        assert request["queryBeginTime"] == request["queryEndTime"] == "20261015"
        assert request["transactionId"] == []
        assert "settlementDateBegin" not in request
    else:
        assert (
            request["settlementDateBegin"] == request["settlementDateEnd"] == "20261015"
        )
        assert request["postingDateBegin"] == request["postingDateEnd"] == ""
        assert "transactionId" not in request


@pytest.mark.parametrize(
    "installed", ["investment.accrual", "investment.settlement"], indirect=True
)
def test_yield_occurrences_remain_flat_and_history_uses_own_date_axis(installed):
    name, cli, browser, _ = installed
    row = deepcopy(next(row for leaf, row, _ in CASES if leaf == name))
    second = deepcopy(row)
    date_field = "transactionDate" if name == "investment.accrual" else "settlementDate"
    second[date_field] = "20261016"
    if name == "investment.settlement":
        second["id"] = "EVENT-TWO"
    browser.business_script.append(source_envelope([row, second]))
    result = cli(
        "liquidity",
        "list",
        name,
        "--from-date",
        "20261015",
        "--to-date",
        "20261016",
        "--live",
        "--require-complete",
        "--limit",
        "0",
    )
    assert result["data"] == [row, second]
    plan = cli(
        "workflow",
        "plan",
        "create",
        "--leaf",
        "liquidity." + name,
        "--mode",
        "history",
        "--parameters",
        '{"from-date":"20261015","to-date":"20261016"}',
    )["data"]
    assert plan["contract"]["time_basis"] == date_field
    assert plan["desired_range"] == {"from": "2026-10-15", "to": "2026-10-16"}


@pytest.mark.parametrize(
    "installed", ["investment.accrual", "investment.settlement"], indirect=True
)
@pytest.mark.parametrize("fault", ["identity", "date", "tenant"])
def test_invalid_yield_source_preserves_prior_capture(installed, fault):
    name, cli, browser, _ = installed
    row = deepcopy(next(row for leaf, row, _ in CASES if leaf == name))
    flags = ["--from-date", "20261015", "--to-date", "20261015"]
    browser.business_script.append(source_envelope([row]))
    cli("liquidity", "refresh", name, *flags, "--require-complete")
    saved = cli("liquidity", "list", name, "--limit", "0")
    bad = deepcopy(row)
    if fault == "identity":
        bad["investmentNo" if name == "investment.accrual" else "id"] = None
    elif fault == "date":
        bad["transactionDate" if name == "investment.accrual" else "settlementDate"] = (
            "20261016"
        )
    else:
        bad["tntInstId"] = "OTHER"
    browser.business_script.append(source_envelope([bad]))
    cli("liquidity", "refresh", name, *flags, "--require-complete", code=1)
    after = cli("liquidity", "list", name, "--limit", "0")
    assert after["data"] == saved["data"]
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
