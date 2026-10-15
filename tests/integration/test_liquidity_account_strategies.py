"""S01 public CLI, fake CDP and temporary SQLite acceptance."""

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "operations", "account_strategies"]


def strategy(alias="SYN-A", version=1, **changes):
    return {
        "aliasName": alias,
        "version": version,
        "entity": "SYN-ENTITY",
        "bankId": "SYN-BANK",
        "currency": "USD",
        "accountType": "CASH",
        "operationStrategy": "Self-Built Cash Pool,No Need,Self-Built Cash Pool",
        "coverAlgorithm": "N",
        "status": "Invalid",
        "processStatus": "APPROVED",
        "lastModifiedTime": "2026-10-15 12:30:00",
        **changes,
    }


def install(setup, rows):
    def answer(payload, index):
        start = payload["rowStart"]
        page = rows[start : start + payload["pageSize"]]
        return {
            "status": 200,
            "body": {"success": True, "data": {"data": page, "totalCount": len(rows)}},
        }

    setup.state.business_handler = answer


def test_default_view_preserves_invalid_and_native_versions_without_status(
    setup, run_cli
):
    rows = [strategy(), strategy(version=2, status="Valid", processStatus="SUBMITTED")]
    install(setup, rows)
    code, out, err = run_cli([*ROOT, "list", "--live", "--limit", "1"])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == rows[:1]
    assert result["meta"]["complete"] is True
    assert result["meta"]["collected_total"] == 2
    assert setup.state.business_requests == [
        {"rowStart": 0, "pageSize": 5000},
        {"rowStart": 2, "pageSize": 5000},
    ]
    assert not setup.cache_path.exists()
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert expressions and all(
        "/strategyManage/queryList.json" in e for e in expressions
    )
    assert all("POST" in e for e in expressions)


@pytest.mark.parametrize(
    "flag,native,value",
    [
        ("--entity", "fundEntityList", "SYN-ENTITY"),
        ("--bank", "fundBankIdList", "SYN-BANK"),
        ("--alias", "aliasNameList", "SYN-A"),
        ("--currency", "currencyList", "USD"),
        ("--account-type", "accountTypeList", "CASH"),
        ("--operation-strategy", "operationStrategyList", "SELF_BUILD_CASH_POOL"),
        ("--cover-algorithm", "coverAlgorithm", "N"),
    ],
)
def test_each_filter_sent_to_native_without_status(setup, run_cli, flag, native, value):
    install(setup, [strategy()])
    code, out, err = run_cli([*ROOT, "list", "--live", flag, value])
    assert code == 0, err
    assert parse(out)["data"] == [strategy()]
    expected = value if native == "coverAlgorithm" else [value]
    assert setup.state.business_requests == [
        {native: expected, "rowStart": 0, "pageSize": 5000},
        {native: expected, "rowStart": 1, "pageSize": 5000},
    ]


def test_multiple_native_values_and_cross_dimension_filters(setup, run_cli):
    install(setup, [strategy()])
    flags = [
        "--entity",
        "SYN-ENTITY",
        "--entity",
        "SYN-OTHER",
        "--bank",
        "SYN-BANK",
        "--alias",
        "SYN-A",
        "--alias",
        "SYN-B",
        "--currency",
        "USD",
        "--currency",
        "EUR",
        "--account-type",
        "CASH",
        "--account-type",
        "POOL",
        "--operation-strategy",
        "SELF_BUILD_CASH_POOL",
        "--operation-strategy",
        "BANK_SWEEPING",
        "--cover-algorithm",
        "N",
    ]
    code, out, err = run_cli(["refresh", *ROOT, *flags])
    assert code == 0, err
    assert parse(out)["meta"]["published"] is True
    expected = {
        "fundEntityList": ["SYN-ENTITY", "SYN-OTHER"],
        "fundBankIdList": ["SYN-BANK"],
        "aliasNameList": ["SYN-A", "SYN-B"],
        "currencyList": ["USD", "EUR"],
        "accountTypeList": ["CASH", "POOL"],
        "operationStrategyList": ["SELF_BUILD_CASH_POOL", "BANK_SWEEPING"],
        "coverAlgorithm": "N",
        "rowStart": 0,
        "pageSize": 5000,
    }
    assert setup.state.business_requests[0] == expected
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli([*ROOT, "list", "--live", *flags])
    assert code == 0, err
    assert parse(out)["data"] == [strategy()]
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    requests = len(setup.state.business_requests)
    code, out, err = run_cli([*ROOT, "list", *flags])
    assert code == 0, err
    assert parse(out)["data"] == [strategy()]
    assert len(setup.state.business_requests) == requests


@pytest.mark.parametrize(
    "flags",
    [
        ["--status", "VALID"],
        ["--status", "INVALID"],
        ["--entity", " "],
        ["--bank", ""],
        ["--alias", " "],
        ["--currency", " "],
        ["--account-type", " "],
        ["--operation-strategy", "Self-Built Cash Pool"],
        ["--operation-strategy", "UNKNOWN"],
        ["--cover-algorithm", "yes"],
        ["--cover-algorithm", "Y", "--cover-algorithm", "N"],
    ],
)
def test_invalid_filters_fail_before_transport(setup, run_cli, flags):
    for command in ([*ROOT, "list", "--live", *flags], ["refresh", *ROOT, *flags]):
        code, out, _ = run_cli(command)
        assert code == 2
        assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert not setup.cache_path.exists()


def test_offline_membership_or_and_and_scope_coverage(setup, run_cli):
    rows = [
        strategy(),
        strategy("SYN-B", operationStrategy="Bank Sweeping Agreement"),
        strategy("SYN-C", currency="EUR", operationStrategy="No Need"),
    ]
    install(setup, rows)
    code, out, err = run_cli(["refresh", *ROOT])
    assert code == 0, err
    source_scope = parse(out)["meta"]["scope"]
    setup.state.reachable = False
    requests = len(setup.state.business_requests)
    code, out, err = run_cli(
        [
            *ROOT,
            "list",
            "--operation-strategy",
            "SELF_BUILD_CASH_POOL",
            "--operation-strategy",
            "BANK_SWEEPING",
            "--currency",
            "USD",
        ]
    )
    assert code == 0, err
    result = parse(out)
    assert result["data"] == rows[:2]
    assert result["meta"]["scope"] == source_scope
    assert result["meta"]["complete"] is True
    assert result["meta"]["collected_total"] == 3
    assert len(setup.state.business_requests) == requests
    code, out, err = run_cli([*ROOT, "list", "--alias", "MISSING"])
    assert code == 0, err
    assert parse(out)["data"] == []
    assert len(setup.state.business_requests) == requests


@pytest.mark.parametrize(
    "local_flags",
    [[], ["--currency", "USD"], ["--operation-strategy", "SELF_BUILD_CASH_POOL"]],
)
def test_complete_filtered_snapshot_replays_without_repeating_source_scope(
    setup, run_cli, local_flags
):
    install(setup, [strategy()])
    code, out, err = run_cli(
        ["refresh", *ROOT, "--alias", "SYN-A", "--require-complete"]
    )
    assert code == 0, err
    source_scope = parse(out)["meta"]["scope"]
    before = setup.cache_path.read_bytes()
    requests = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list", "--require-complete", *local_flags])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == [strategy()]
    assert result["meta"]["complete"] is True
    assert result["meta"]["requested_scope_covered"] is True
    assert result["meta"]["scope"] == source_scope
    assert len(setup.state.business_requests) == requests
    assert setup.cache_path.read_bytes() == before


def test_filtered_snapshot_does_not_cover_broader_native_scope(setup, run_cli):
    install(setup, [strategy()])
    code, out, err = run_cli(["refresh", *ROOT, "--alias", "SYN-A"])
    assert code == 0, err
    source_scope = parse(out)["meta"]["scope"]
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list", "--alias", "SYN-A", "--alias", "SYN-B"])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == [strategy()]
    assert result["meta"]["scope"] == source_scope
    assert result["meta"]["complete"] is False
    assert result["meta"]["warnings"]
    code, out, _ = run_cli([*ROOT, "list", "--alias", "SYN-B", "--require-complete"])
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert parse(out)["data"] is None


def test_empty_strict_and_hard_failure_refresh_preserve_nonempty_slot(
    setup, run_cli, monkeypatch
):
    install(setup, [strategy()])
    assert run_cli(["refresh", *ROOT])[0] == 0
    before = setup.cache_path.read_bytes()
    install(setup, [])
    code, out, err = run_cli(["refresh", *ROOT])
    assert code == 0, err
    assert parse(out)["meta"]["published"] is False
    assert setup.cache_path.read_bytes() == before

    from dogopencli.plugins.liquidity import account_collection

    install(setup, [strategy(version=2)])
    monkeypatch.setattr(account_collection, "MAX_PAGES", 1)
    code, out, _ = run_cli(["refresh", *ROOT, "--require-complete"])
    assert code == 1
    result = parse(out)
    assert result["error"]["code"] == "INCOMPLETE_RESULT"
    assert result["data"] is None
    assert setup.cache_path.read_bytes() == before
    monkeypatch.setattr(account_collection, "MAX_PAGES", 512)

    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": False, "message": "synthetic rejection"},
    }
    assert run_cli(["refresh", *ROOT])[0] == 1
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list"])
    assert code == 0, err
    assert parse(out)["data"] == [strategy()]


@pytest.mark.parametrize(
    "defect", ["terminal-rows", "conflict", "bad-version", "total-drift"]
)
def test_invalid_native_coverage_or_identity_never_publishes(setup, run_cli, defect):
    install(setup, [strategy()])
    assert run_cli(["refresh", *ROOT])[0] == 0
    before = setup.cache_path.read_bytes()

    def answer(payload, index):
        start = payload["rowStart"]
        rows, total = [strategy()], 1
        if defect == "terminal-rows":
            pass
        elif defect == "conflict":
            rows = [strategy(), strategy(status="Valid")]
            total = 2
        elif defect == "bad-version":
            rows[0]["version"] = "1"
        elif defect == "total-drift" and start:
            rows, total = [], 2
        if start and defect not in ("terminal-rows", "total-drift"):
            rows = []
        return {
            "status": 200,
            "body": {"success": True, "data": {"data": rows, "totalCount": total}},
        }

    setup.state.business_handler = answer
    code, out, _ = run_cli(["refresh", *ROOT])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == before


def test_leaf_prune_and_offline_no_alias_keep_other_slots(setup, run_cli):
    rule = {"id": "SYN-RULE", "ruleName": "SYN-NAME", "runStatus": "UNKNOWN"}
    install(setup, [rule])
    assert run_cli(["refresh", "liquidity", "rules", "realtime"])[0] == 0
    install(setup, [strategy(), strategy(version=2)])
    assert run_cli(["refresh", *ROOT])[0] == 0
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list", "--limit", "0"])
    assert code == 0, err
    assert [row["version"] for row in parse(out)["data"]] == [1, 2]
    assert run_cli(["prune", *ROOT])[0] == 0
    assert run_cli(["prune", *ROOT])[0] == 0
    code, out, _ = run_cli([*ROOT, "list"])
    assert code == 1
    assert parse(out)["error"]["code"] == "CACHE_MISS"

    code, out, err = run_cli(["liquidity", "rules", "realtime", "list"])
    assert code == 0, err
    assert parse(out)["data"] == [rule]


def test_native_filter_scope_violation_is_hard_failure(setup, run_cli):
    install(setup, [strategy(currency="EUR")])
    code, out, _ = run_cli([*ROOT, "list", "--live", "--currency", "USD"])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert parse(out)["data"] is None
    assert not setup.cache_path.exists()


def test_safe_partial_quality_survives_projection_and_offline(setup, run_cli):
    # Identical duplicate arrivals cannot establish unique-row coverage.
    install(setup, [strategy(), strategy()])
    code, out, err = run_cli(["refresh", *ROOT])
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["complete"] is False
    assert result["meta"]["published"] is True
    assert "warning" in err.lower()
    setup.state.reachable = False
    code, out, err = run_cli([*ROOT, "list", "--fields", "aliasName"])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == [{"aliasName": "SYN-A"}]
    assert result["meta"]["complete"] is False
    assert result["meta"]["warnings"]
    assert result["meta"]["reported_total"] == 2
    assert result["meta"]["collected_total"] == 1
    assert "warning" in err.lower()


def test_readonly_allowlist_rejects_status_and_mutation_before_cdp(setup):
    from dataclasses import replace

    from dogopencli.errors import CliError
    from dogopencli.plugins.liquidity.account_strategies import ACCOUNT_STRATEGIES
    from dogopencli.plugins.liquidity.leaves import list_leaf
    from dogopencli.transport import QueryRequest
    from dogopencli.transport.cdp import CdpQueryTransport

    capability = list_leaf(ACCOUNT_STRATEGIES.path).capability(ACCOUNT_STRATEGIES)
    request = QueryRequest(
        capability=capability.name,
        method="POST",
        host="iliquidity.alipay.com",
        path=ACCOUNT_STRATEGIES.endpoint,
        body={"rowStart": 0, "pageSize": 5000},
    )
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url=capability.page_url,
    )
    for changed in (
        replace(request, body={**request.body, "status": "INVALID"}),
        replace(request, path="/strategyManage/update.json"),
        replace(request, method="GET"),
        replace(request, host="ifundcontrol.alipay.com"),
    ):
        with pytest.raises(CliError) as error:
            transport.execute(changed)
        assert error.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []


def test_source_pagination_collects_beyond_display_and_probes_exact_terminal(
    setup, run_cli
):
    rows = [strategy(f"SYN-{index}") for index in range(5001)]
    install(setup, rows)
    code, out, err = run_cli(
        [*ROOT, "list", "--live", "--limit", "1", "--offset", "5000"]
    )
    assert code == 0, err
    result = parse(out)
    assert result["data"] == [strategy("SYN-5000")]
    assert result["meta"]["collected_total"] == 5001
    assert result["meta"]["complete"] is True
    assert [request["rowStart"] for request in setup.state.business_requests] == [
        0,
        5000,
        5001,
    ]
    assert all(request["pageSize"] == 5000 for request in setup.state.business_requests)
