"""Bounded native composition through public CLI, fake CDP and real SQLite."""

import hashlib
import json

import pytest

from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.forecast_accuracy import BASE_FIELDS, METRIC_FIELDS

pytest_plugins = ["test_liquidity_cli_sit"]
ACCOUNT = "TEST-ACCOUNT"
ROW = {
    "id": "TEST-RECORD-1",
    "bankAccountAliasName": ACCOUNT,
    "currency": "USD",
    "valueDate": "20260930",
    "baseValueDate": "20260929",
    "recordCreateTime": "2026-10-05 01:02:03",
    "forecastBalance": "0.00",
    "cashFlowTransIn": "-10.00000000000001",
    "cashFlowTransOut": "",
    "forecastTaskId": 0,
    "forecastBatchNo": None,
    "forecastRuleId": "unknown",
    "accountNo": "TEST-PRIVATE-NUMBER",
    "instId": "TEST-INST",
    "bankId": "TEST-BANK",
    "operator": "TEST-PERSON",
    "memo": "TEST-PRIVATE-MEMO",
}
METRICS = {
    field: str(index) + ".000000000000001" for index, field in enumerate(METRIC_FIELDS)
}
METRICS.update(
    cashFlowAccuracy="", inflowAccuracy="0", outflowAccuracy="-2", realizedBalance=None
)


def args(*extra, refresh=False, account=ACCOUNT, day="2026-10-05"):
    command = (
        ["refresh", "liquidity", "forecast", "accuracy"]
        if refresh
        else ["liquidity", "forecast", "accuracy", "list"]
    )
    return command + ["--account", account, "--record-date", day, *extra]


def base_page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "count": len(rows) if total is None else total,
                "dataValue": rows,
            },
        },
    }


def metric_page(metrics=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "bankAccountDetailDayVO": METRICS if metrics is None else metrics,
            },
        },
    }


def handler(rows, *, total=None, metric=None):
    by_id = {row["id"]: row for row in rows}

    def answer(body, index):
        assert body["tntInstId"] == "GUAPW3SG"
        if "bankCashForecastRecordQueryVo" in body:
            assert set(body) == {"tntInstId", "bankCashForecastRecordQueryVo"}
            assert json.loads(body["bankCashForecastRecordQueryVo"]) == {
                "tntInstId": "GUAPW3SG",
                "rowStart": 0,
                "pageSize": 5000,
                "aliasName": [ACCOUNT],
                "valueStartDay": "20261005",
                "valueEndDay": "20261005",
                "recordStartTime": "000000",
                "recordEndTime": "235959",
            }
            return base_page(rows, total)
        assert set(body) == {"tntInstId", "bankAccountDetailCashFlowQueryVO"}
        vo = json.loads(body["bankAccountDetailCashFlowQueryVO"])
        row = by_id[vo["forecastRecordId"]]
        assert vo == {
            "valueDate": row["valueDate"],
            "accountNo": row["accountNo"],
            "instId": row["instId"],
            "currency": row["currency"],
            "bankId": row["bankId"],
            "forecastRecordId": row["id"],
            "aliasName": ACCOUNT,
            "forecastBalance": "0"
            if row["forecastBalance"] in ("0.0", "0.00")
            else row["forecastBalance"],
        }
        return metric_page() if metric is None else metric(vo, index)

    return answer


def digest(setup):
    return hashlib.sha256(setup.cache_path.read_bytes()).hexdigest()


def seed(setup, run_cli):
    setup.state.business_handler = handler([ROW])
    code, out, err = run_cli(args("--require-complete", refresh=True))
    assert code == 0, err
    return parse(out), digest(setup)


def test_composition_request_projection_offline_live_snapshot(setup, run_cli):
    rows = [
        ROW,
        dict(
            ROW,
            id="TEST-RECORD-2",
            valueDate="20260928",
            forecastBalance="-1.0000000000000001",
        ),
    ]
    setup.state.business_handler = handler(rows)
    code, out, err = run_cli(args("--require-complete", refresh=True))
    assert code == 0, err
    refresh = parse(out)
    proof = refresh["meta"]["acquisition"]["attempts"][0]
    assert (
        proof["base_arrivals"]
        == proof["base_unique"]
        == proof["base_reported_total"]
        == proof["metric_succeeded"]
        == 2
    )
    assert proof["composition"] == "native-request-binding"
    assert len(setup.state.business_requests) == 3
    expressions = [
        expr
        for transport in setup.state.transports
        for expr in transport.expressions
        if "fetch(" in expr
    ]
    assert len(expressions) == 3
    assert (
        "https://iliquidity.alipay.com/bankCashForecastRecordAccuracyQuery.json"
        in expressions[0]
    )
    assert all(
        "https://iliquidity.alipay.com/cashFlowDetailDay.json" in expr
        for expr in expressions[1:]
    )
    assert all(
        'method: "GET"' in expr
        and "new URLSearchParams(payload)" in expr
        and 'credentials: "include"' in expr
        for expr in expressions
    )
    before = digest(setup)
    assert b"TEST-PRIVATE" not in setup.cache_path.read_bytes()
    code, out, err = run_cli(args("--live", "--all"))
    assert code == 0, err
    live = parse(out)
    assert len(live["data"]) == 2
    assert live["meta"]["source_observed_from"] is None
    assert live["data"][0]["accuracy"] == METRICS
    assert live["data"][0]["forecastBalance"] == "0.00"
    assert live["data"][0]["valueDate"] != "20261005"
    assert set(live["data"][0]) == {*BASE_FIELDS, "accuracy"}
    assert digest(setup) == before
    setup.state.reachable = False
    code, out, err = run_cli(args("--all"))
    assert code == 0, err
    offline = parse(out)
    assert offline["data"] == live["data"]
    for field in ("scope", "fetched_at", "acquisition", "snapshot_id"):
        assert offline["meta"][field] == refresh["meta"][field]
    for account, day in (("OTHER", "2026-10-05"), (ACCOUNT, "2026-10-04")):
        code, out, _ = run_cli(args(account=account, day=day))
        assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    code, out, err = run_cli(
        ["snapshot", "liquidity", "forecast", "accuracy", "list", "--format", "json"]
    )
    assert code == 0, err
    assert parse(out)["tree"]["cache"]["status"] == "present"


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["--account", ACCOUNT],
        ["--record-date", "2026-10-05"],
        ["--account", "", "--record-date", "2026-10-05"],
        ["--account", ACCOUNT, "--record-date", "2026-02-30"],
        ["--account", ACCOUNT, "--record-date", "20261005"],
        ["--account", ACCOUNT, "--account", "OTHER", "--record-date", "2026-10-05"],
    ],
)
def test_invalid_scope_before_business_request(setup, run_cli, options):
    code, _, _ = run_cli(
        ["liquidity", "forecast", "accuracy", "list", "--live", *options]
    )
    assert code != 0
    assert not setup.state.business_requests


@pytest.mark.parametrize(
    "rows,total", [([ROW], 2), ([ROW, ROW], 1), ([ROW, ROW], 2), ([], 1)]
)
@pytest.mark.parametrize("strict", [False, True])
def test_base_coverage_gap_never_publishes_half_composition(
    setup, run_cli, rows, total, strict
):
    _, before = seed(setup, run_cli)
    start = len(setup.state.business_requests)
    setup.state.business_handler = handler(rows, total=total)
    code, out, _ = run_cli(
        args(*(["--require-complete"] if strict else []), refresh=True)
    )
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert parse(out)["data"] is None
    assert len(setup.state.business_requests) == start + 1
    assert digest(setup) == before


@pytest.mark.parametrize("size", [100, 101])
def test_client_base_budget_boundary(setup, run_cli, size):
    rows = [dict(ROW, id=f"TEST-{i}") for i in range(size)]
    setup.state.business_handler = handler(rows)
    code, out, err = run_cli(args(refresh=True))
    if size == 100:
        assert code == 0, err
        assert (
            parse(out)["meta"]["acquisition"]["attempts"][0]["metric_succeeded"] == 100
        )
        assert len(setup.state.business_requests) == 101
    else:
        assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
        assert len(setup.state.business_requests) == 1
        assert parse(out)["data"] is None


@pytest.mark.parametrize(
    "failure",
    [
        {"status": 401, "body": {}},
        {"status": 200, "body": {"resultFlag": False, "result": {"success": True}}},
        {
            "status": 200,
            "body": {
                "resultFlag": True,
                "result": {"success": False, "bankAccountDetailDayVO": {}},
            },
        },
        {
            "status": 200,
            "body": {
                "resultFlag": True,
                "result": {"success": True, "bankAccountDetailDayVO": []},
            },
        },
    ],
)
def test_later_metric_failure_is_hard_and_preserves_capture(setup, run_cli, failure):
    _, before = seed(setup, run_cli)
    rows = [ROW, dict(ROW, id="TEST-RECORD-2")]
    setup.state.business_handler = handler(
        rows,
        metric=lambda vo, index: (
            failure if vo["forecastRecordId"] == "TEST-RECORD-2" else metric_page()
        ),
    )
    code, out, _ = run_cli(args(refresh=True))
    assert code == 1
    assert parse(out)["data"] is None
    assert digest(setup) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"id": 1},
        {"bankAccountAliasName": "OTHER"},
        {"tntInstId": "OTHER"},
        {"accountNo": None},
        {"instId": ""},
        {"bankId": []},
        {"forecastBalance": None},
    ],
)
def test_binding_and_identity_failure_before_metrics(setup, run_cli, changes):
    _, before = seed(setup, run_cli)
    start = len(setup.state.business_requests)
    setup.state.business_handler = handler([dict(ROW, **changes)])
    code, out, _ = run_cli(args(refresh=True))
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert len(setup.state.business_requests) == start + 1
    assert digest(setup) == before


def test_empty_scope_no_metrics(setup, run_cli):
    setup.state.business_handler = handler([])
    code, out, err = run_cli(args(refresh=True))
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is True
    assert len(setup.state.business_requests) == 1
    setup.state.reachable = False
    assert parse(run_cli(args())[1])["data"] == []


def test_shared_deadline_after_metric_preserves_capture(setup, run_cli, monkeypatch):
    from dogopencli import collect

    _, before = seed(setup, run_cli)
    ticks = {"now": 0.0}
    native_clock = collect.time.monotonic
    monkeypatch.setattr(
        collect.time, "monotonic", lambda: native_clock() + ticks["now"]
    )
    monkeypatch.setattr(collect, "REFRESH_BUDGET_SECONDS", 5.0)

    def metrics(vo, index):
        ticks["now"] += 6.0
        return metric_page()

    setup.state.business_handler = handler(
        [ROW, dict(ROW, id="TEST-2")], metric=metrics
    )
    start = len(setup.state.business_requests)
    code, out, _ = run_cli(args(refresh=True))
    assert code == 1 and parse(out)["error"]["code"] == "TIMEOUT"
    assert len(setup.state.business_requests) == start + 2
    assert digest(setup) == before


def test_discovery_without_browser_and_no_accuracy_get(setup, run_cli):
    setup.state.reachable = False
    code, out, err = run_cli(["describe", "liquidity", "forecast", "accuracy", "list"])
    assert code == 0, err
    description = parse(out)
    assert description["read_guide"]["kind"] == "runtimes"
    assert description["read_guide"]["offline_profile"] == "history"
    assert description["read_guide"]["series_time"] is None
    assert (
        description["read_guide"]["schema_version"]
        == "forecast-accuracy-composition-v1"
    )
    assert description["read_guide"]["live_verified"] == "2026-10-05"
    assert set(
        description["data_schema"]["properties"]["accuracy"]["properties"]
    ) == set(METRIC_FIELDS)
    code, out, _ = run_cli(args())
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert run_cli(["liquidity", "forecast", "accuracy", "get"])[0] != 0
    assert not setup.state.business_requests


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"forecastBalance": "2"}, "INVALID_RESPONSE"),
        ({"memo": "changed private", "unknownField": "changed"}, "INCOMPLETE_RESULT"),
    ],
)
def test_duplicate_conflict_uses_business_projection_and_bindings(
    setup, run_cli, change, expected
):
    _, before = seed(setup, run_cli)
    setup.state.business_handler = handler([ROW, dict(ROW, **change)], total=2)
    start = len(setup.state.business_requests)
    code, out, _ = run_cli(args(refresh=True))
    assert code == 1 and parse(out)["error"]["code"] == expected
    assert len(setup.state.business_requests) == start + 1
    assert digest(setup) == before


@pytest.mark.parametrize("kind", ["host", "path", "method", "extra", "tenant", "vo"])
def test_bound_shared_transport_default_deny(setup, kind):
    from dogopencli.errors import CliError
    from dogopencli.plugins.liquidity.forecast_accuracy import BoundInquiry, metric_body
    from dogopencli.transport import QueryRequest, validate_request

    body = metric_body(ROW, ACCOUNT)
    cap = BoundInquiry("accuracy.test", "/cashFlowDetailDay.json", body)
    values = {
        "capability": cap.name,
        "method": "GET",
        "host": "iliquidity.alipay.com",
        "path": cap.contract.path,
        "body": dict(body),
    }
    if kind in {"host", "path", "method"}:
        values[kind] = "OTHER"
    elif kind == "extra":
        values["body"]["unverified"] = "value"
    elif kind == "tenant":
        values["body"]["tntInstId"] = "OTHER"
    else:
        vo = json.loads(body["bankAccountDetailCashFlowQueryVO"])
        vo["forecastRecordId"] = "OTHER-ROW"
        values["body"]["bankAccountDetailCashFlowQueryVO"] = json.dumps(vo)
    with pytest.raises(CliError) as error:
        validate_request(QueryRequest(**values), cap.contract)
    assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert not setup.state.business_requests


def test_forecast_results_and_native_details_remain_independent(setup, run_cli):
    from dogopencli.cache import Cache
    from dogopencli.plugins.liquidity import details, store
    from dogopencli.plugins.liquidity.cash_forecast import FORECAST_RESULTS

    cache = Cache(setup.cache_path)
    detail = details.upsert_detail(
        cache,
        "liquidity.cash.pools.get",
        "TEST-KEY",
        {"id": "TEST-POOL"},
        "2026-10-05T00:00:00+00:00",
        "2026-10-05T00:00:00+00:00",
    )
    plan = store.plan_capture_publish(
        cache,
        FORECAST_RESULTS,
        "TEST-FORECAST-SCOPE",
        ("20261005", "20261005"),
        [{"id": "TEST-BASE", "valueDate": "20261005"}],
        1,
        "2026-10-05T00:00:00+00:00",
        "2026-10-05T00:00:00+00:00",
    )
    store.commit_plan(cache, FORECAST_RESULTS.name, plan, "2026-10-05T00:00:00+00:00")
    seed(setup, run_cli)
    assert details.read_detail_snapshot(cache, "liquidity.cash.pools.get") == detail
    assert details.read_details(cache, "liquidity.cash.pools.get")[
        "TEST-KEY"
    ].detail == {"id": "TEST-POOL"}
    entry = store.read_index(cache, FORECAST_RESULTS.name).captures[0]
    assert store.read_capture(cache, entry)[0] == {
        "id": "TEST-BASE",
        "valueDate": "20261005",
    }


def test_missing_optional_fields_are_unknown_and_blank_native_values_preserved(
    setup, run_cli
):
    row = {
        field: ROW[field]
        for field in (
            "id",
            "bankAccountAliasName",
            "valueDate",
            "accountNo",
            "instId",
            "currency",
            "bankId",
        )
    }
    row["forecastBalance"] = ""
    setup.state.business_handler = handler(
        [row], metric=lambda vo, index: metric_page({})
    )
    code, out, err = run_cli(args("--live"))
    assert code == 0, err
    record = parse(out)["data"][0]
    assert record["forecastBalance"] == ""
    assert record["baseValueDate"] is None
    assert record["recordCreateTime"] is None
    assert record["accuracy"] == dict.fromkeys(METRIC_FIELDS)
