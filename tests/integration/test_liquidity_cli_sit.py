"""Liquidity public CLI + fake CDP + real SQLite acceptance (issue #72).

Covers peer-plugin registration and different-origin routing, verified
encodings and identities, offline-default isolation from the browser,
independent list/detail acquisition, partial live results, refresh rollback,
retention metadata, deferred discovery and auth expiry. All data synthetic.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_cdp import PAYMENT_URL, FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

CDP_URL = "http://127.0.0.1:9222"
LIQUIDITY_URL = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"


def route_probes(state: FakeBrowser, liquidity_sequence: tuple[str, ...] = ()) -> None:
    """Answer each probe by the URL its target was created with.

    The session setup probes the liquidity entry; origin checks,
    query-page settles and re-probes all target the liquidity entry. A
    scripted liquidity sequence overrides the default liquidity answer.
    """
    calls = {"count": 0}

    def route(browser: FakeBrowser) -> str:
        url = browser.transports[-1].created[-1]
        if url == PAYMENT_URL:
            return PAYMENT_URL
        calls["count"] += 1
        if liquidity_sequence:
            index = min(calls["count"], len(liquidity_sequence)) - 1
            return liquidity_sequence[index]
        return LIQUIDITY_URL

    state.href = route


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    profile = tmp_path / "chrome-profile"
    cache_path = tmp_path / "cache.sqlite3"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[cache]\n"
        f'path = "{cache_path}"\n'
        "ttl_hours = 72\n"
        "\n"
        "[auth]\n"
        f'profile = "{profile}"\n'
        f'cdp_url = "{CDP_URL}"\n'
        "\n"
        "[sources.liquidity]\n"
        'kind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config_path))
    state = FakeBrowser(href=LIQUIDITY_URL)
    route_probes(state)
    cdp.set_transport_factory(state.transport)
    yield SimpleNamespace(
        state=state,
        profile=profile,
        tmp_path=tmp_path,
        cache_path=cache_path,
    )
    cdp.set_transport_factory(None)


def holding(index, day="20261001", amount="10.00"):
    return {
        "investmentNo": f"H{index:04d}",
        "valueDate": day,
        "amount": amount,
        "currency": "USD",
    }


def holdings_page(rows, total):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": total, "rowStart": 0, "pageSize": 10},
        },
    }


def holdings_listing(rows_by_offset, total):
    def answer(payload, index):
        return holdings_page(
            rows_by_offset(payload["rowStart"], payload["pageSize"]), total
        )

    return answer


def seed_holdings(run_cli, setup, total=12, day="20261001"):
    rows = [holding(i, day) for i in range(total)]

    def by_offset(row_start, page_size):
        return rows[row_start : row_start + page_size]

    setup.state.business_handler = holdings_listing(by_offset, total)
    code, out, err = run_cli(
        ["refresh", "liquidity", "investment", "holdings", "--date", day]
    )
    assert code == 0, err
    envelope = parse(out)
    assert envelope["data"]["row_count"] == total
    return rows


def accounts_handler(rows, cash_total=None):
    """Answer every native component of the composite directory."""
    cash_total = len(rows) if cash_total is None else cash_total
    baselines = [{**row, "accountType": "OA", "status": "NORMAL"} for row in rows]

    def answer(payload, index):
        if "aliasName" in payload:
            detail = next(
                row for row in baselines if row["aliasName"] == payload["aliasName"]
            )
            return {
                "status": 200,
                "body": {"resultFlag": True, "result": {"data": detail}},
            }
        if "bankAccountQueryVO" in payload:
            vo = json.loads(payload["bankAccountQueryVO"])
            source, container, total = rows, "bankAccountPropertyVOList", cash_total
        else:
            vo = json.loads(payload["bankAccountBaseLineQuery"])
            source, container, total = baselines, "data", len(baselines)
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "result": {
                    container: source[vo["rowStart"] : vo["rowStart"] + vo["pageSize"]]
                },
                "count": total,
            },
        }

    return answer


def account_row(alias):
    return {
        "id": "0",
        "aliasName": alias,
        "currency": "USD",
        "bankId": "BANK",
        "instId": "ENTITY",
    }


def _seed_returns_captures(setup, captures):
    """Publish dated cash-return captures with explicit fetch times."""
    from dogopencli.cache import Cache
    from dogopencli.plugins.liquidity import store as capture_store
    from dogopencli.plugins.liquidity.leaves import list_leaf

    leaf = list_leaf(("investment", "returns"))
    store = Cache(setup.cache_path)
    for window, rows, fetched_at in captures:
        resolved = leaf.resolve(
            {"basis": "cash", "from_date": window[0], "to_date": window[1]}
        )
        plan = capture_store.plan_capture_publish(
            store,
            resolved.spec,
            resolved.scope_key,
            resolved.window,
            rows,
            len(rows),
            fetched_at,
            fetched_at,
        )
        capture_store.commit_plan(store, resolved.spec.name, plan, fetched_at)


def _returns_row(identity, day, income):
    return {
        "transactionId": identity,
        "settlementDate": day,
        "interestIncome": income,
        "currency": "USD",
    }


RETURNS_QUERY = [
    "liquidity",
    "investment",
    "returns",
    "list",
    "--basis",
    "cash",
    "--limit",
    "0",
]
