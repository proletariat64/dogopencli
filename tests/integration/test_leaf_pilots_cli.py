"""New leaf pilots through the public CLI and fake CDP browser."""

import builtins
import json
from decimal import Decimal

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp


@pytest.fixture
def pilots(tmp_path, monkeypatch, run_cli):
    config = tmp_path / "config.toml"
    config.write_text(
        '[auth]\nprofile = "'
        + str(tmp_path / "chrome")
        + '"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    browser = FakeBrowser()
    cdp.set_transport_factory(browser.transport)
    for identity in (
        "collection.cost",
        "liquidity.reference.entities",
        "payment.sla.baselines",
        "fx.trade",
    ):
        code, out, _ = run_cli(["plugins", "install", "bundled:" + identity])
        assert code == 0, out
    yield browser
    cdp.set_transport_factory(None)


def test_payment_native_list_and_detail(run_cli, pilots):
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "pageNo": 0,
                "pageSize": 10000,
                "totalCount": 1,
                "resultDataList": [{"id": "101", "status": "ACTIVE"}],
            },
        }
    )
    code, out, _ = run_cli(["payment", "list", "sla.baselines", "--live"])
    assert code == 0
    assert json.loads(out)["data"] == [{"id": "101", "status": "ACTIVE"}]
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "resultData": {"id": "101", "detailOnly": "native"},
            },
        }
    )
    code, out, _ = run_cli(["payment", "get", "sla.baselines", "101"])
    assert code == 0
    assert json.loads(out)["data"]["detailOnly"] == "native"
    assert pilots.business_requests[-1] == {"slaBaselineId": "101"}


def fx_page(rows, number=0, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "result": {
                "success": True,
                "value": {
                    "items": rows,
                    "totalCount": len(rows) if total is None else total,
                    "currentPage": number,
                    "pageSize": 50,
                },
            },
        },
    }


def test_fx_native_pages_preserve_unknown_identity(run_cli, pilots):
    from dogopencli.domain_contracts import FX_STARTUP_URL

    pilots.href = FX_STARTUP_URL
    rows = [{"uniqueId": str(i), "amount": "0.1234567890123456789"} for i in range(52)]
    pilots.business_script.extend(
        [fx_page(rows[:50], total=52), fx_page(rows[50:], number=1, total=52)]
    )
    code, out, err = run_cli(
        ["fx", "list", "trade", "--live", "--trade-id", "TEST", "--limit", "1"]
    )
    value = json.loads(out)
    assert code == 0
    assert value["data"] == rows[:1]
    assert value["meta"]["collected_total"] == 52
    assert value["meta"]["complete"] is False
    assert value["meta"]["unique_count"] is None
    assert value["meta"]["total_semantics"] == "unknown"
    assert "IDENTITY_UNPROVEN" in value["meta"]["acquisition"]["reasons"]
    assert "TOTAL_SEMANTICS_UNPROVEN" in value["meta"]["acquisition"]["reasons"]
    assert "INCOMPLETE_RESULT" in err
    assert [request["pageNo"] for request in pilots.business_requests] == [0, 1]
    assert pilots.business_requests[0]["queryRequest"] == {"uniqueIds": ["TEST"]}
    pilots.business_script.append(fx_page(rows[:1]))
    code, out, _ = run_cli(
        ["fx", "list", "trade", "--live", "--trade-id", "TEST", "--require-complete"]
    )
    assert code == 1 and json.loads(out)["data"] is None


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("command", [["list", "trade", "--live"], ["refresh", "trade"]])
def test_fx_authorization_failure_requires_login_without_publishing(
    run_cli, pilots, status, command
):
    from dogopencli.domain_contracts import FX_STARTUP_URL

    pilots.href = FX_STARTUP_URL
    pilots.business_script.append({"status": status, "body": {}})
    code, out, _ = run_cli(["fx", *command, "--trade-id", "TEST"])
    value = json.loads(out)
    assert code == 1, out
    assert value["error"]["code"] == "AUTH_REQUIRED"
    assert "dogopencli login" in value["error"]["message"]
    assert value["error"]["retryable"] is False
    assert value["data"] is None
    if command[0] == "refresh":
        assert value["meta"]["published"] is False
    else:
        assert value["meta"] is None
    code, out, _ = run_cli(["fx", "list", "trade"])
    assert code == 1 and json.loads(out)["error"]["code"] == "CACHE_MISS", out


def test_liquidity_entities_accept_native_inst_id_without_synthetic_id(run_cli, pilots):
    from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL

    pilots.href = LIQUIDITY_STARTUP_URL
    rows = [{"instId": "INSTITUTION-A", "instName": "Synthetic institution"}]
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": 1,
                "result": {"entityMaintVOList": rows},
            },
        }
    )
    code, out, _ = run_cli(["liquidity", "list", "reference.entities", "--live"])
    assert code == 0
    assert json.loads(out)["data"] == rows


def test_collection_single_verified_capacity_reports_incomplete(run_cli, pilots):
    rows = [{"itemId": "1", "itemType": "FUND_IN_CHANNEL_TRANS_FEE"}]
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": 1001,
                "resultDataList": rows,
            },
        }
    )
    code, out, err = run_cli(["collection", "list", "cost", "--live"])
    assert code == 0
    value = json.loads(out)
    assert value["data"] == rows
    assert value["meta"]["complete"] is False
    assert "INCOMPLETE_RESULT" in err
    assert pilots.business_requests == [
        {"costTypeCode": "FUND_IN_CHANNEL_TRANS_FEE", "pageNo": 0, "pageSize": 1000}
    ]


def test_collection_installed_inquiry_without_legacy_import(
    run_cli, pilots, monkeypatch
):

    original_import = builtins.__import__

    def independent_import(name, *args, **kwargs):
        if name.startswith("dogopencli.plugins.collection"):
            raise ImportError("retired business runtime is unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", independent_import)
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": 1,
                "resultDataList": [
                    {
                        "itemId": "native-1",
                        "itemType": "FUND_IN_CHANNEL_TRANS_FEE",
                        "amount": "0.000000000000000001",
                        "extension": {"enabled": False},
                    }
                ],
            },
        }
    )
    code, out, _ = run_cli(["collection", "list", "cost", "--live"])
    assert code == 0, out
    row = json.loads(out)["data"][0]
    assert row["amount"] == "0.000000000000000001"
    assert row["extension"] == {"enabled": False}


def test_liquidity_installed_offset_pages_without_legacy_import(
    run_cli, pilots, monkeypatch
):
    from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL

    original_import = builtins.__import__

    def independent_import(name, *args, **kwargs):
        if name.startswith("dogopencli.plugins.liquidity"):
            raise ImportError("retired business runtime is unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", independent_import)
    pilots.href = LIQUIDITY_STARTUP_URL
    rows = [
        {"instId": f"INSTITUTION-{i}", "instCode": "SAME", "extension": {"value": None}}
        for i in range(5001)
    ]
    for page in (rows[:5000], rows[5000:]):
        pilots.business_script.append(
            {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": 5001,
                    "result": {"entityMaintVOList": page},
                },
            }
        )
    code, out, _ = run_cli(
        ["liquidity", "list", "reference.entities", "--live", "--limit", "0"]
    )
    assert code == 0, out
    value = json.loads(out)
    assert value["data"] == rows
    assert value["meta"]["complete"] is True
    requests = pilots.business_requests
    assert [json.loads(item["entityMaintQueryVO"]) for item in requests] == [
        {"tntInstId": "GUAPW3SG", "rowStart": 0, "pageSize": 5000},
        {"tntInstId": "GUAPW3SG", "rowStart": 5000, "pageSize": 5000},
    ]


def test_payment_installed_scope_filter_and_detail_without_legacy_import(
    run_cli, pilots, monkeypatch
):
    original_import = builtins.__import__

    def independent_import(name, *args, **kwargs):
        if name.startswith("dogopencli.plugins.payment"):
            raise ImportError("retired business runtime is unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", independent_import)
    rows = [
        {
            "id": "SLA-1",
            "status": "ACTIVE",
            "creditorCurrency": "USD",
            "limits": [{"amount": "0.000000000000000001"}],
        }
    ]
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "pageNo": 0,
                "pageSize": 10000,
                "totalCount": 1,
                "resultDataList": rows,
            },
        }
    )
    code, out, _ = run_cli(
        [
            "payment",
            "refresh",
            "sla.baselines",
            "--status",
            "ACTIVE",
            "--creditor-currency",
            "USD",
        ]
    )
    assert code == 0, out
    assert pilots.business_requests == [
        {"pageNo": 0, "pageSize": 10000, "status": "ACTIVE", "creditorCurrency": "USD"}
    ]
    code, out, _ = run_cli(["payment", "list", "sla.baselines", "--status", "ACTIVE"])
    assert code == 0 and json.loads(out)["data"] == rows
    code, out, _ = run_cli(["payment", "list", "sla.baselines", "--status", "DISABLED"])
    assert code == 0 and json.loads(out)["data"] == []
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "resultData": {"id": "SLA-1", "nativeDetail": {"enabled": False}},
            },
        }
    )
    code, out, _ = run_cli(["payment", "get", "sla.baselines", "SLA-1"])
    assert code == 0, out
    assert json.loads(out)["data"] == {
        "id": "SLA-1",
        "nativeDetail": {"enabled": False},
    }


def test_fx_installed_native_scope_without_legacy_import(run_cli, pilots, monkeypatch):
    from dogopencli.domain_contracts import FX_STARTUP_URL

    original_import = builtins.__import__

    def independent_import(name, *args, **kwargs):
        if name.startswith("dogopencli.plugins.fx"):
            raise ImportError("retired business runtime is unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", independent_import)
    pilots.href = FX_STARTUP_URL
    rows = [
        {
            "uniqueId": "UNPROVEN",
            "transactionAmountQuantity": {"value": "1234567890.1234567890123456789"},
        }
    ] * 2
    pilots.business_script.append(fx_page(rows))
    code, out, _ = run_cli(
        [
            "fx",
            "list",
            "trade",
            "--live",
            "--transact-from",
            "2026-10-03",
            "--transact-to",
            "2026-10-03",
            "--bcode",
            "B1",
            "--bcode",
            "B1",
            "--fulfilled",
            "0",
        ]
    )
    assert code == 0, out
    value = json.loads(out)
    assert value["data"] == rows
    assert value["meta"]["complete"] is False
    assert value["meta"]["unique_count"] is None
    assert pilots.business_requests[0]["queryRequest"] == {
        "p5Bcodes": ["B1"],
        "p5TimeOverDue": 0,
        "transactTimeRange": {"start": 1790956800000, "end": 1791043199999},
    }


PILOT_LEAVES = [
    ("collection", "cost"),
    ("liquidity", "reference.entities"),
    ("payment", "sla.baselines"),
    ("fx", "trade"),
]


def native_page(domain, rows):
    if domain == "liquidity":
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": len(rows),
                "result": {"entityMaintVOList": rows},
            },
        }
    if domain == "fx":
        return fx_page(rows)
    return {
        "status": 200,
        "body": {
            "success": True,
            "pageNo": 0,
            "pageSize": 1000 if domain == "collection" else 10000,
            "totalCount": len(rows),
            "resultDataList": rows,
        },
    }


def native_row(domain, identity="saved"):
    if domain == "collection":
        return {"itemId": identity, "itemType": "FUND_IN_CHANNEL_TRANS_FEE"}
    return {
        {"liquidity": "instId", "payment": "id", "fx": "uniqueId"}[domain]: identity
    }


def select_application(pilots, domain):
    from dogopencli.domain_contracts import FX_STARTUP_URL, LIQUIDITY_STARTUP_URL

    if domain == "fx":
        pilots.href = FX_STARTUP_URL
    elif domain == "liquidity":
        pilots.href = LIQUIDITY_STARTUP_URL


@pytest.mark.parametrize("domain,leaf", PILOT_LEAVES[:3])
def test_each_pilot_native_types_and_cache_publication(run_cli, pilots, domain, leaf):
    select_application(pilots, domain)
    rows = [
        {
            **native_row(domain),
            "decimal": Decimal("0.1234567890123456789"),
            "decimalText": "0.1000",
            "unknown": {"boolean": False, "null": None, "list": [1, "1"]},
        }
    ]
    pilots.business_script.append(native_page(domain, rows))
    code, out, _ = run_cli([domain, "list", leaf, "--live"])
    assert code == 0, out
    assert json.loads(out, parse_float=Decimal)["data"] == rows
    code, out, _ = run_cli([domain, "list", leaf])
    assert code == 1 and json.loads(out)["error"]["code"] == "CACHE_MISS"
    pilots.business_script.append(native_page(domain, rows))
    code, out, _ = run_cli(
        [
            domain,
            "refresh",
            leaf,
            "--fields",
            next(iter(native_row(domain))),
            "--limit",
            "1",
        ]
    )
    assert code == 0 and json.loads(out)["meta"]["published"] is True
    requests = list(pilots.business_requests)
    code, out, _ = run_cli([domain, "list", leaf])
    assert code == 0, out
    saved = json.loads(out, parse_float=Decimal)
    assert saved["data"] == rows
    assert pilots.business_requests == requests
    # Successful empty acquisition never replaces the previous nonempty capture.
    pilots.business_script.append(native_page(domain, []))
    code, out, _ = run_cli([domain, "refresh", leaf])
    assert code == 0 and json.loads(out)["meta"]["published"] is False
    failures = [
        ({"status": 401, "body": {}}, "AUTH_REQUIRED"),
        ({"status": 200, "body": "{"}, "INVALID_RESPONSE"),
        (
            {
                "status": 200,
                "body": {
                    "resultFlag": False,
                    "success": False,
                    "privateMessage": "DO-NOT-EXPOSE",
                },
            },
            "BUSINESS_QUERY_FAILED",
        ),
    ]
    for response, expected in failures:
        pilots.business_script.append(response)
        code, out, err = run_cli([domain, "refresh", leaf])
        value = json.loads(out)
        assert code == 1 and value["error"]["code"] == expected, out
        assert value["data"] is None and value["meta"]["published"] is False
        assert "DO-NOT-EXPOSE" not in out + err
        _, out, _ = run_cli([domain, "list", leaf])
        current = json.loads(out, parse_float=Decimal)
        assert current["data"] == saved["data"]
        assert current["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "domain,leaf,body",
    [
        (
            "collection",
            "cost",
            {
                "success": True,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": 0,
                "resultDataList": None,
            },
        ),
        (
            "collection",
            "cost",
            {"success": True, "pageNo": False, "pageSize": 1000, "totalCount": 0},
        ),
        (
            "collection",
            "cost",
            {
                "success": True,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": 1,
                "resultDataList": [
                    {"itemId": "1", "itemType": "FUND_OUT_CHANNEL_TRANS_FEE"}
                ],
            },
        ),
        (
            "collection",
            "cost",
            {
                "success": True,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": 1,
                "resultDataList": [
                    {"itemId": 1, "itemType": "FUND_IN_CHANNEL_TRANS_FEE"}
                ],
            },
        ),
        (
            "liquidity",
            "reference.entities",
            {"resultFlag": True, "count": True, "result": {"entityMaintVOList": []}},
        ),
        (
            "liquidity",
            "reference.entities",
            {
                "resultFlag": True,
                "count": 1,
                "result": {"entityMaintVOList": [{"id": "synthetic-id-only"}]},
            },
        ),
        (
            "payment",
            "sla.baselines",
            {
                "success": True,
                "pageNo": 0,
                "pageSize": 5000,
                "totalCount": 0,
                "resultDataList": None,
            },
        ),
        (
            "payment",
            "sla.baselines",
            {"success": True, "pageNo": 0, "pageSize": 10000, "totalCount": 1},
        ),
        (
            "payment",
            "sla.baselines",
            {
                "success": True,
                "pageNo": 0,
                "pageSize": 10000,
                "totalCount": 1,
                "resultDataList": [{"id": 101}],
            },
        ),
        (
            "payment",
            "sla.baselines",
            {"success": True, "pageNo": 0, "pageSize": 4999, "totalCount": 0},
        ),
        (
            "fx",
            "trade",
            {
                "success": True,
                "result": {
                    "success": True,
                    "value": {
                        "items": [],
                        "totalCount": True,
                        "currentPage": 0,
                        "pageSize": 50,
                    },
                },
            },
        ),
        (
            "fx",
            "trade",
            {
                "success": True,
                "result": {
                    "success": True,
                    "value": {
                        "items": [{}],
                        "totalCount": 1,
                        "currentPage": 0,
                        "pageSize": 50,
                    },
                },
            },
        ),
        (
            "fx",
            "trade",
            {
                "success": True,
                "result": {
                    "success": True,
                    "value": {
                        "items": [],
                        "totalCount": 0,
                        "currentPage": 1,
                        "pageSize": 50,
                    },
                },
            },
        ),
    ],
)
def test_invalid_native_response_never_becomes_success(
    run_cli, pilots, domain, leaf, body
):
    select_application(pilots, domain)
    pilots.business_script.append({"status": 200, "body": body})
    code, out, _ = run_cli([domain, "list", leaf, "--live"])
    value = json.loads(out)
    assert code == 1 and value["error"]["code"] == "INVALID_RESPONSE", out
    assert value["data"] is None


@pytest.mark.parametrize(
    "body,error",
    [
        ({"success": True, "resultData": None}, "NOT_FOUND"),
        ({"success": True, "resultData": []}, "INVALID_RESPONSE"),
        ({"success": True, "resultData": {"id": "OTHER"}}, "INVALID_RESPONSE"),
        ({"success": True, "resultData": {"id": 101}}, "INVALID_RESPONSE"),
        ({"success": False, "resultData": {"id": "101"}}, "BUSINESS_QUERY_FAILED"),
    ],
)
def test_payment_native_detail_errors(run_cli, pilots, body, error):
    pilots.business_script.append({"status": 200, "body": body})
    code, out, _ = run_cli(["payment", "get", "sla.baselines", "101"])
    assert code == 1 and json.loads(out)["error"]["code"] == error, out
    assert pilots.business_requests == [{"slaBaselineId": "101"}]


@pytest.mark.parametrize(
    "flags",
    [
        ["--trade-id", "ANY"],
        ["--trade-id", " "],
        ["--transact-from", "2026-10-03"],
        ["--transact-from", "2026-10-04", "--transact-to", "2026-10-03"],
        ["--transact-from", "2026-02-30", "--transact-to", "2026-03-01"],
        [
            "--transact-from",
            "2026-10-03T01:00:00",
            "--transact-to",
            "2026-10-03T02:00:00",
        ],
        ["--trade-id", "ID", "--bcode", "B1"],
        ["--trade-id", "ID", "--scene", "ANY"],
    ],
)
def test_fx_invalid_scope_rejected_before_business_request(run_cli, pilots, flags):
    select_application(pilots, "fx")
    code, out, _ = run_cli(["fx", "list", "trade", "--live", *flags])
    assert code == 2 and json.loads(out)["error"]["code"] == "INVALID_ARGUMENT", out
    assert pilots.business_requests == []


@pytest.mark.parametrize("domain,leaf", PILOT_LEAVES[:3])
def test_native_identity_conflicts_select_last_arrival_with_incomplete_evidence(
    run_cli, pilots, domain, leaf
):
    select_application(pilots, domain)
    first = native_row(domain)
    pilots.business_script.append(
        native_page(domain, [first, {**first, "different": True}])
    )
    if domain == "payment":
        fallback = native_page(domain, [first, {**first, "different": True}])
        fallback["body"]["pageSize"] = 5000
        pilots.business_script.append(fallback)
    code, out, _ = run_cli([domain, "list", leaf, "--live"])
    value = json.loads(out)
    assert code == 0 and value["data"] == [{**first, "different": True}], out
    assert value["meta"]["complete"] is False
    assert "IDENTITY_CONTENT_CONFLICT" in value["meta"]["acquisition"]["reasons"]


def test_payment_capacity_rebuild_replaces_entire_candidate(run_cli, pilots):
    truncated = native_page("payment", [{"id": "discarded"}])
    truncated["body"]["totalCount"] = 2
    recovered = native_page("payment", [{"id": "new-1"}, {"id": "new-2"}])
    recovered["body"]["pageSize"] = 5000
    pilots.business_script.extend([truncated, recovered])
    code, out, _ = run_cli(["payment", "list", "sla.baselines", "--live"])
    value = json.loads(out)
    assert code == 0 and value["data"] == [{"id": "new-1"}, {"id": "new-2"}], out
    assert value["meta"]["complete"] is True
    assert [request["pageSize"] for request in pilots.business_requests] == [
        10000,
        5000,
    ]


def test_payment_live_legal_entity_passthrough_and_all_local_filters(run_cli, pilots):
    rows = [
        {
            "id": "1",
            "bizCategory": "CATEGORY",
            "creditorCurrency": "USD",
            "regionCode": "US",
            "status": "ACTIVE",
        }
    ]
    pilots.business_script.append(native_page("payment", rows))
    flags = [
        "--biz-category",
        "CATEGORY",
        "--creditor-currency",
        "USD",
        "--region-code",
        "US",
        "--status",
        "ACTIVE",
    ]
    code, out, _ = run_cli(
        [
            "payment",
            "list",
            "sla.baselines",
            "--live",
            "--biz-legal-entity",
            "ENTITY",
            *flags,
        ]
    )
    assert code == 0 and json.loads(out)["data"] == rows, out
    assert pilots.business_requests == [
        {
            "pageNo": 0,
            "pageSize": 10000,
            "bizCategory": "CATEGORY",
            "creditorCurrency": "USD",
            "regionCode": "US",
            "status": "ACTIVE",
            "bizLegalEntity": "ENTITY",
        }
    ]
    pilots.business_script.append(native_page("payment", rows))
    assert run_cli(["payment", "refresh", "sla.baselines"])[0] == 0
    code, out, _ = run_cli(["payment", "list", "sla.baselines", *flags])
    assert code == 0 and json.loads(out)["data"] == rows
    before = list(pilots.business_requests)
    code, out, _ = run_cli(
        ["payment", "list", "sla.baselines", "--biz-legal-entity", "ENTITY"]
    )
    assert code == 2 and json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert pilots.business_requests == before


def test_fx_business_failure_only_exposes_safe_code(run_cli, pilots):
    select_application(pilots, "fx")
    for code, suffix in [
        ("NATIVE_ERROR", " (NATIVE_ERROR)"),
        ("SQL SELECT credential", ""),
    ]:
        pilots.business_script.append(
            {
                "status": 200,
                "body": {
                    "success": True,
                    "result": {
                        "success": False,
                        "fvCode": code,
                        "message": "DO-NOT-EXPOSE",
                    },
                },
            }
        )
        status, out, err = run_cli(
            ["fx", "list", "trade", "--live", "--trade-id", "ID"]
        )
        value = json.loads(out)
        assert status == 1 and value["error"]["code"] == "BUSINESS_QUERY_FAILED"
        assert value["error"]["message"] == "FX trade query failed" + suffix
        assert "DO-NOT-EXPOSE" not in out + err


def test_fx_rpc_transport_uses_one_element_json_array(run_cli, pilots):
    select_application(pilots, "fx")
    pilots.business_script.append(fx_page([{"uniqueId": "ID"}]))
    code, out, _ = run_cli(["fx", "list", "trade", "--live", "--trade-id", "ID"])
    assert code == 0, out
    fetches = [
        expression
        for transport in pilots.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert len(fetches) == 1
    assert "JSON.stringify([payload])" in fetches[0]


@pytest.mark.parametrize(
    "domain,leaf", [("liquidity", "reference.entities"), ("fx", "trade")]
)
def test_sdk_rejects_changed_native_total(run_cli, pilots, domain, leaf):
    select_application(pilots, domain)
    if domain == "fx":
        first = fx_page([{"uniqueId": str(i)} for i in range(50)], total=51)
        second = fx_page([{"uniqueId": "last"}], number=1, total=52)
    else:
        first = {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": 5001,
                "result": {"entityMaintVOList": [{"instId": "first"}]},
            },
        }
        second = {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": 5002,
                "result": {"entityMaintVOList": [{"instId": "last"}]},
            },
        }
    pilots.business_script.extend([first, second])
    code, out, _ = run_cli([domain, "list", leaf, "--live"])
    assert code == 1 and json.loads(out)["error"]["code"] == "INVALID_RESPONSE", out
    assert json.loads(out)["data"] is None
    assert len(pilots.business_requests) == 2


def test_liquidity_overlap_retains_safe_incomplete_evidence(run_cli, pilots):
    select_application(pilots, "liquidity")
    response = {
        "status": 200,
        "body": {
            "resultFlag": True,
            "count": 5001,
            "result": {
                "entityMaintVOList": [{"instId": "SAME", "instCode": "DISPLAY"}]
            },
        },
    }
    pilots.business_script.extend([response, response])
    code, out, _ = run_cli(["liquidity", "list", "reference.entities", "--live"])
    value = json.loads(out)
    assert code == 0 and value["data"] == [{"instId": "SAME", "instCode": "DISPLAY"}], (
        out
    )
    assert value["meta"]["complete"] is False
    assert value["meta"]["acquisition"]["arrivals"] == 2
    assert value["meta"]["unique_count"] == 1


def test_fx_sdk_refresh_rejects_unproven_rows_without_publication(run_cli, pilots):
    select_application(pilots, "fx")
    rows = [{"uniqueId": "UNPROVEN", "unknown": {"native": True}}] * 2
    pilots.business_script.append(fx_page(rows))
    code, out, _ = run_cli(["fx", "list", "trade", "--live", "--trade-id", "TEST"])
    value = json.loads(out)
    assert code == 0 and value["data"] == rows
    assert value["meta"]["acquisition"]["attempts"][0]["arrivals"] == 2
    pilots.business_script.append(fx_page(rows))
    code, out, _ = run_cli(["fx", "refresh", "trade", "--trade-id", "TEST"])
    rejected = json.loads(out)
    assert code == 1 and rejected["error"]["code"] == "INCOMPLETE_RESULT"
    assert rejected["data"] is None and rejected["meta"]["published"] is False
    code, out, _ = run_cli(["fx", "list", "trade"])
    assert code == 1 and json.loads(out)["error"]["code"] == "CACHE_MISS"


def test_entity_empty_hole_is_partial_live_and_rejected_by_refresh(run_cli, pilots):
    select_application(pilots, "liquidity")
    response = {
        "status": 200,
        "body": {"resultFlag": True, "count": 1, "result": {"entityMaintVOList": []}},
    }
    pilots.business_script.append(response)
    code, out, _ = run_cli(["liquidity", "list", "reference.entities", "--live"])
    value = json.loads(out)
    assert code == 0 and value["data"] == []
    assert value["meta"]["complete"] is False
    assert "EMPTY_INTERIOR_PAGE" in value["meta"]["acquisition"]["reasons"]
    pilots.business_script.append(response)
    code, out, _ = run_cli(["liquidity", "refresh", "reference.entities"])
    assert code == 1 and json.loads(out)["error"]["code"] == "INCOMPLETE_RESULT"
