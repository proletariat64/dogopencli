"""Independent access lists through public CLI and isolated external seams."""

import json

import pytest

from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.access_lists import ACCOUNT_BLACKLIST
from dogopencli.plugins.liquidity.capability import LiquidityListCapability
from dogopencli.transport import QueryRequest, validate_request

pytest_plugins = ["test_liquidity_cli_sit"]


@pytest.mark.parametrize(
    "path",
    [
        ["whitelist", "entity"],
        ["blacklist", "account"],
    ],
)
def test_access_list_offline_without_slot_never_opens_browser(setup, run_cli, path):
    code, out, err = run_cli(["liquidity", "reference", *path, "list"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    assert setup.state.business_requests == []
    assert not setup.cache_path.exists()


def test_bank_blacklist_unproven_identity_is_unavailable(setup, run_cli):
    code, out, err = run_cli(["liquidity", "reference", "blacklist", "bank", "list"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    assert "identity" in parse(out)["error"]["message"]
    assert setup.state.transports == []
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "path,vo_field,identity",
    [
        (["whitelist", "entity"], "instFilterConfigQuery", "instId"),
        (["blacklist", "account"], "accountFilterConfigQuery", "aliasName"),
    ],
)
def test_live_access_list_preserves_rows_and_proves_coverage(
    setup, run_cli, path, vo_field, identity
):
    rows = [
        {
            identity: "S1",
            "status": "INVALID",
            "id": 0,
            "gmtModified": 123,
            "nested": {"value": None},
            "empty": "",
        },
        {identity: "S2", "status": "VALID", "id": 0, "gmtModified": 0, "tntInstId": ""},
    ]

    def answer(payload, index):
        vo = json.loads(payload[vo_field])
        page = rows[vo["rowStart"] : vo["rowStart"] + vo["pageSize"]]
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": 2,
                "result": {"success": True, "data": page, "count": 2},
            },
        }

    setup.state.business_handler = answer
    code, out, err = run_cli(
        ["liquidity", "reference", *path, "list", "--live", "--limit", "0"]
    )
    assert code == 0, err
    result = parse(out)
    assert result["data"] == rows
    assert result["meta"]["kind"] == "settings"
    assert result["meta"]["complete"] is True
    assert [
        json.loads(p[vo_field])["rowStart"] for p in setup.state.business_requests
    ] == [0, 1, 2]
    assert not setup.cache_path.exists()


@pytest.mark.parametrize("status", ["NORMAL", "valid"])
def test_access_status_rejects_unverified_value_before_browser(setup, run_cli, status):
    code, out, err = run_cli(
        [
            "liquidity",
            "reference",
            "whitelist",
            "entity",
            "list",
            "--live",
            "--status",
            status,
        ]
    )
    assert code == 2, err
    assert setup.state.transports == []


@pytest.mark.parametrize(
    "row",
    [
        {"instId": 1},
        {"instId": True},
        {"instId": ""},
        {"instId": None},
        {"aliasName": "WRONG-SOURCE"},
        {"instId": "E1", "tntInstId": "OTHER"},
        {"instId": "E1", "tntInstId": None},
    ],
)
def test_access_native_identity_and_tenant_are_validated(setup, run_cli, row):
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": 1,
            "result": {"success": True, "count": 1, "data": [row]},
        },
    }
    code, out, err = run_cli(
        ["liquidity", "reference", "whitelist", "entity", "list", "--live"]
    )
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert parse(out)["data"] is None
    assert len(setup.state.business_requests) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"Edit": True},
        {"status": "VALID"},
        {"tntInstId": "OTHER"},
        {"currentArea": "2"},
        {"timezone": "UTC"},
        {"rowStart": -1},
        {"rowStart": True},
        {"rowStart": 1.0},
        {"rowStart": "1"},
        {"rowStart": {}},
        {"rowStart": None},
        {"pageSize": 0},
        {"pageSize": 10},
        {"pageSize": 1001},
        {"pageSize": True},
        {"pageSize": 1000.0},
        {"pageSize": "1000"},
        {"pageSize": {}},
        {"pageSize": None},
    ],
)
def test_access_transport_rejects_unverified_nested_requests(change):
    capability = LiquidityListCapability(ACCOUNT_BLACKLIST)
    body = capability.page_body("", 0)
    vo = json.loads(body["accountFilterConfigQuery"])
    vo.update(change)
    body["accountFilterConfigQuery"] = json.dumps(vo)
    request = QueryRequest(
        capability.name,
        "GET",
        "iliquidity.alipay.com",
        "/accountFilterConfigQuery.json",
        body,
    )
    with pytest.raises(CliError) as caught:
        validate_request(request, capability.contract)
    assert caught.value.code == "REQUEST_NOT_ALLOWED"


def access_page(rows, total):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": total,
            "result": {"success": True, "data": rows, "count": total},
        },
    }


@pytest.mark.parametrize("cap", [500, 1000])
@pytest.mark.parametrize("limit,offset", [(0, 0), (100, 0), (10, 20)])
def test_silent_cap_restarts_clean_and_uses_actual_row_offsets(
    setup, run_cli, cap, limit, offset
):
    rows = [{"aliasName": f"A{i}", "status": "INVALID"} for i in range(2100)]

    def answer(payload, index):
        vo = json.loads(payload["accountFilterConfigQuery"])
        start = vo["rowStart"]
        return access_page(rows[start : start + min(vo["pageSize"], cap)], 2100)

    setup.state.business_handler = answer
    code, out, err = run_cli(
        [
            "liquidity",
            "reference",
            "blacklist",
            "account",
            "list",
            "--live",
            "--limit",
            str(limit),
            "--offset",
            str(offset),
        ]
    )
    assert code == 0, err
    result = parse(out)
    end = offset + limit if limit else len(rows)
    assert result["data"] == rows[offset:end]
    evidence = result["meta"]["acquisition"]
    assert evidence["scope_complete"] is True
    assert evidence["arrivals"] == evidence["unique_count"] == 2100
    assert evidence["reasons"] == ["PAGE_SIZE_CAPPED"]
    assert evidence["attempts"][0]["discarded"] is True
    requests = [
        json.loads(p["accountFilterConfigQuery"]) for p in setup.state.business_requests
    ]
    assert [p["rowStart"] for p in requests] == [
        0,
        *range(0, 2100, cap),
        1,
        *range(cap - 1, 2099, cap),
        2100,
    ]
    assert [p["pageSize"] for p in requests] == [5000] + [1000] * (len(requests) - 1)


@pytest.mark.parametrize("http_status,inner", [(500, True), (200, False)])
def test_http_and_business_failures_never_retry_as_size_fallback(
    setup, run_cli, http_status, inner
):
    setup.state.business_handler = lambda payload, index: {
        "status": http_status,
        "body": {
            "resultFlag": True,
            "count": 0,
            "result": {"success": inner, "count": 0, "data": []},
        },
    }
    code, out, err = run_cli(
        ["liquidity", "reference", "blacklist", "account", "list", "--live"]
    )
    assert code == 1, err
    assert parse(out)["data"] is None
    assert len(setup.state.business_requests) == 1
    assert not setup.cache_path.exists()


def test_access_describe_has_native_fields_identity_and_current_proof(setup, run_cli):
    code, out, err = run_cli(
        ["describe", "liquidity", "reference", "blacklist", "account", "list"]
    )
    assert code == 0, err
    description = parse(out)
    assert description["read_guide"]["identity"] == ["aliasName"]
    assert description["read_guide"]["live_verified"] == "2026-10-15"
    properties = description["data_schema"]["properties"]
    assert properties["aliasName"]["x-observed-type"] == "str"
    assert "dummy" in properties["id"]["description"]
    assert "epoch milliseconds" in properties["gmtModified"]["description"]
    assert "activation" in properties["status"]["description"]
    assert setup.state.transports == []


@pytest.mark.parametrize(
    "body",
    [
        {"count": 0, "result": {"success": True, "count": 0, "data": []}},
        {"resultFlag": True, "count": 0, "result": {"count": 0, "data": []}},
        {
            "resultFlag": True,
            "count": 0,
            "result": {"success": False, "count": 0, "data": []},
        },
        {
            "resultFlag": True,
            "count": 0,
            "result": {"success": True, "count": True, "data": []},
        },
        {
            "resultFlag": True,
            "count": 1,
            "result": {"success": True, "count": 0, "data": []},
        },
        {
            "resultFlag": True,
            "count": 0,
            "result": {"success": True, "count": 0, "data": {}},
        },
    ],
)
def test_access_invalid_envelope_never_publishes_or_retries(setup, run_cli, body):
    setup.state.business_handler = lambda payload, index: {"status": 200, "body": body}
    code, out, err = run_cli(
        ["refresh", "liquidity", "reference", "whitelist", "entity"]
    )
    assert code == 1, err
    assert parse(out)["data"] is None
    assert parse(out)["error"]["code"] in {"INVALID_RESPONSE", "BUSINESS_QUERY_FAILED"}
    assert len(setup.state.business_requests) == 1
    assert not setup.cache_path.exists()


def source_rows(setup, rows_by_field):
    def answer(payload, index):
        field = next(k for k in rows_by_field if k in payload)
        rows = rows_by_field[field]
        vo = json.loads(payload[field])
        start = vo["rowStart"]
        return access_page(rows[start : start + vo["pageSize"]], len(rows))

    setup.state.business_handler = answer


def test_access_slots_independent_replacement_empty_preservation_and_prune(
    setup, run_cli
):
    sources = {
        "instFilterConfigQuery": [{"instId": "E1", "status": "INVALID"}],
        "accountFilterConfigQuery": [{"aliasName": "A1", "status": "VALID"}],
    }
    source_rows(setup, sources)
    entity = ["liquidity", "reference", "whitelist", "entity"]
    account = ["liquidity", "reference", "blacklist", "account"]
    for path in (entity, account):
        assert run_cli(["refresh", *path])[0] == 0
    before = setup.cache_path.read_bytes()
    sources["instFilterConfigQuery"] = []
    code, out, err = run_cli(["refresh", *entity])
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is True
    assert parse(out)["meta"]["published"] is False
    assert setup.cache_path.read_bytes() == before
    sources["accountFilterConfigQuery"] = [{"aliasName": "A2", "status": "INVALID"}]
    assert run_cli(["refresh", *account])[0] == 0
    setup.state.transports.clear()
    code, out, err = run_cli([*entity, "list"])
    assert code == 0, err
    assert parse(out)["data"] == [{"instId": "E1", "status": "INVALID"}]
    code, out, err = run_cli([*account, "list"])
    assert code == 0, err
    assert parse(out)["data"] == [{"aliasName": "A2", "status": "INVALID"}]
    assert run_cli([*entity, "prune"])[0] == 0
    assert run_cli([*entity, "list"])[0] == 1
    assert run_cli([*account, "list"])[0] == 0
    assert setup.state.transports == []


def test_access_prune_absent_database_creates_nothing(setup, run_cli):
    code, out, err = run_cli(["liquidity", "reference", "whitelist", "entity", "prune"])
    assert code == 0, err
    assert not setup.cache_path.exists()
    assert setup.state.transports == []


@pytest.mark.parametrize(
    "path,field,rows,filters,expected",
    [
        (
            ["whitelist", "entity"],
            "instFilterConfigQuery",
            [
                {"instId": "E1", "instCode": "F1", "status": "VALID"},
                {"instId": "E2", "instCode": "F1", "status": "INVALID"},
            ],
            ["--financial-code", "F1", "--status", "INVALID"],
            "E2",
        ),
        (
            ["blacklist", "account"],
            "accountFilterConfigQuery",
            [
                {"aliasName": "A1", "instId": "E1", "bankId": "B1", "status": "VALID"},
                {
                    "aliasName": "A2",
                    "instId": "E1",
                    "bankId": "B2",
                    "status": "INVALID",
                },
            ],
            ["--entity", "E1", "--bank-id", "B2", "--account-alias", "A2"],
            "A2",
        ),
    ],
)
def test_access_filters_are_local_and_offline_keeps_acquisition_quality(
    setup, run_cli, path, field, rows, filters, expected
):
    source_rows(setup, {field: rows})
    root = ["liquidity", "reference", *path]
    assert run_cli(["refresh", *root])[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_requests.clear()
    code, out, err = run_cli([*root, "list", "--live", *filters])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == [rows[1]]
    assert result["meta"]["complete"] is True
    for payload in setup.state.business_requests:
        vo = json.loads(payload[field])
        assert set(vo) == {"tntInstId", "timezone", "rowStart", "pageSize"} | (
            {"currentArea"} if field == "accountFilterConfigQuery" else set()
        )
    assert setup.cache_path.read_bytes() == before
    setup.state.transports.clear()
    code, out, err = run_cli([*root, "list", *filters])
    assert code == 0, err
    assert parse(out)["data"] == [rows[1]]
    assert parse(out)["meta"]["complete"] is True
    assert setup.state.transports == []


def test_access_budget_partial_strict_preserves_slot_and_default_can_publish(
    setup, run_cli, monkeypatch
):
    from dogopencli import collect

    sources = {"instFilterConfigQuery": [{"instId": "OLD"}]}
    source_rows(setup, sources)
    root = ["liquidity", "reference", "whitelist", "entity"]
    assert run_cli(["refresh", *root])[0] == 0
    before = setup.cache_path.read_bytes()
    sources["instFilterConfigQuery"] = [{"instId": "NEW"}]
    monkeypatch.setattr(collect, "MAX_PAGES", 1)
    code, out, err = run_cli(["refresh", *root, "--require-complete"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert parse(out)["data"] is None
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(["refresh", *root])
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["complete"] is False
    assert result["meta"]["published"] is True
    assert "COLLECTION_BUDGET_EXHAUSTED" in result["meta"]["acquisition"]["reasons"]
    setup.state.transports.clear()
    code, out, err = run_cli([*root, "list"])
    assert code == 0, err
    assert parse(out)["data"] == [{"instId": "NEW"}]
    assert parse(out)["meta"]["complete"] is False
    assert run_cli([*root, "list", "--require-complete"])[0] == 1
    assert setup.state.transports == []


def test_conflicting_identity_is_hard_even_on_short_5000_candidate(setup, run_cli):
    setup.state.business_handler = lambda payload, index: access_page(
        [
            {"aliasName": "A1", "status": "VALID"},
            {"aliasName": "A1", "status": "INVALID"},
        ],
        100,
    )
    code, out, err = run_cli(
        ["liquidity", "reference", "blacklist", "account", "list", "--live"]
    )
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert len(setup.state.business_requests) == 1


@pytest.mark.parametrize("fault", ["total", "overlap", "empty-before-total"])
def test_access_changed_source_is_hard_and_stable_shortfall_is_partial(
    setup, run_cli, fault
):
    rows = [{"instId": "E1"}, {"instId": "E2"}]

    def answer(payload, index):
        if index == 0:
            return access_page(rows, 2)
        if fault == "total":
            return access_page([], 3)
        if fault == "overlap":
            return access_page([{"instId": "DIFFERENT"}], 2)
        return access_page([], 2)

    setup.state.business_handler = answer
    code, out, err = run_cli(
        ["liquidity", "reference", "whitelist", "entity", "list", "--live"]
    )
    result = parse(out)
    if fault == "empty-before-total":
        assert code == 0, err
        assert result["data"] == rows
        assert result["meta"]["complete"] is False
    else:
        assert code == 1, err
        assert result["data"] is None
        assert result["error"]["code"] == "INVALID_RESPONSE"
    assert not setup.cache_path.exists()


def test_identical_duplicate_is_usable_incomplete_and_strict_withholds(setup, run_cli):
    rows = [{"instId": "E1"}, {"instId": "E1"}]
    source_rows(setup, {"instFilterConfigQuery": rows})
    root = ["liquidity", "reference", "whitelist", "entity", "list", "--live"]
    code, out, err = run_cli(root)
    assert code == 0, err
    result = parse(out)
    assert result["data"] == [{"instId": "E1"}]
    assert result["meta"]["complete"] is False
    assert result["meta"]["acquisition"]["duplicate_count"] == 1
    assert result["meta"]["acquisition"]["total_semantics"] == "occurrences"
    assert result["meta"]["acquisition"]["reported_total"] == 2
    assert result["meta"]["acquisition"]["arrivals"] == 2
    assert result["meta"]["acquisition"]["unique_count"] == 1
    code, out, err = run_cli([*root, "--require-complete"])
    assert code == 1, err
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert parse(out)["data"] is None


@pytest.mark.parametrize("later_cap", [False, True])
def test_large_access_list_tail_and_later_cap_use_independent_candidates(
    setup, run_cli, later_cap
):
    total = 12000 if later_cap else 7000
    rows = [{"aliasName": f"A{i}", "status": "VALID"} for i in range(total)]

    def answer(payload, index):
        vo = json.loads(payload["accountFilterConfigQuery"])
        size = vo["pageSize"]
        start = vo["rowStart"]
        if later_cap and size == 5000 and start == 5000:
            size = 1000
        return access_page(rows[start : start + size], total)

    setup.state.business_handler = answer
    code, out, err = run_cli(
        [
            "liquidity",
            "reference",
            "blacklist",
            "account",
            "list",
            "--live",
            "--limit",
            "0",
        ]
    )
    assert code == 0, err
    result = parse(out)
    assert result["data"] == rows
    evidence = result["meta"]["acquisition"]
    assert evidence["scope_complete"] is True
    assert evidence["total_semantics"] == "occurrences"
    assert evidence["reported_total"] == evidence["arrivals"] == total
    assert evidence["unique_count"] == total
    requests = [
        json.loads(p["accountFilterConfigQuery"]) for p in setup.state.business_requests
    ]
    if later_cap:
        assert [p["rowStart"] for p in requests] == [
            0,
            5000,
            *range(0, total, 1000),
            1,
            *range(999, total - 1, 1000),
            total,
        ]
        assert [p["pageSize"] for p in requests] == [5000, 5000] + [1000] * 25
        assert evidence["reasons"] == ["PAGE_SIZE_CAPPED"]
        assert [a.get("discarded", False) for a in evidence["attempts"]] == (
            [True, True] + [False] * 25
        )
    else:
        assert [p["rowStart"] for p in requests] == [0, 5000, 1, 4999, total]
        assert [p["pageSize"] for p in requests] == [5000, 5000, 1000, 1000, 1000]
        assert evidence["reasons"] == []


@pytest.mark.parametrize("changed_total", [False, True])
def test_later_cap_restart_keeps_total_and_global_request_budget(
    setup, run_cli, monkeypatch, changed_total
):
    from dogopencli import collect

    rows = [{"aliasName": f"A{i}"} for i in range(12000)]
    monkeypatch.setattr(collect, "MAX_PAGES", 3)

    def answer(payload, index):
        vo = json.loads(payload["accountFilterConfigQuery"])
        start = vo["rowStart"]
        size = 1000 if start == 5000 else vo["pageSize"]
        total = 12001 if changed_total and index == 2 else 12000
        return access_page(rows[start : start + size], total)

    setup.state.business_handler = answer
    code, out, err = run_cli(
        [
            "liquidity",
            "reference",
            "blacklist",
            "account",
            "list",
            "--live",
            "--limit",
            "0",
        ]
    )
    result = parse(out)
    assert len(setup.state.business_requests) == 3
    if changed_total:
        assert code == 1, err
        assert result["error"]["code"] == "INVALID_RESPONSE"
        assert result["data"] is None
    else:
        assert code == 0, err
        assert result["data"] == rows[:1000]
        evidence = result["meta"]["acquisition"]
        assert evidence["scope_complete"] is False
        assert evidence["reported_total"] == 12000
        assert evidence["arrivals"] == evidence["unique_count"] == 1000
        assert "COLLECTION_BUDGET_EXHAUSTED" in evidence["reasons"]
        assert [a.get("discarded", False) for a in evidence["attempts"]] == (
            [True, True, False]
        )


@pytest.mark.parametrize("capped", [False, True])
@pytest.mark.parametrize("refresh", [False, True])
def test_later_boundary_shift_with_same_total_withholds_data_and_preserves_slot(
    setup, run_cli, capped, refresh
):
    root = ["liquidity", "reference", "blacklist", "account"]
    source_rows(setup, {"accountFilterConfigQuery": [{"aliasName": "SAVED"}]})
    assert run_cli(["refresh", *root, "--require-complete"])[0] == 0
    before = setup.cache_path.read_bytes()
    total = 3500 if capped else 7000
    boundary = 2000 if capped else 5000
    rows = [{"aliasName": f"A{i}"} for i in range(total)]
    changed = False

    def answer(payload, index):
        nonlocal changed
        vo = json.loads(payload["accountFilterConfigQuery"])
        start = vo["rowStart"]
        size = min(vo["pageSize"], 1000) if capped else vo["pageSize"]
        page = rows[start : start + size]
        if not changed and start + size == boundary:
            # Keep the total and first overlap stable, but shift the next page.
            del rows[boundary - 1]
            rows.append({"aliasName": f"A{total}"})
            changed = True
        return access_page(page, total)

    setup.state.business_handler = answer
    argv = (
        ["refresh", *root, "--require-complete"]
        if refresh
        else [*root, "list", "--live", "--limit", "0"]
    )
    code, out, err = run_cli(argv)
    result = parse(out)
    assert changed
    assert code == 1, err
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result["data"] is None
    assert setup.cache_path.read_bytes() == before
