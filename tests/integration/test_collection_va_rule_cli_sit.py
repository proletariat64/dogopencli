"""Collection VA rule public CLI + fake CDP + real SQLite acceptance (#32)."""

from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
from test_sla_cli_sit import sla_setup  # noqa: F401

from dogopencli import cli
from dogopencli.errors import CliError
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.collection_va]\nkind = "cdp"\n')
    return sla_setup


def row(identity="1", **changes):
    return {
        "vaRuleId": identity,
        "bankRuleId": 7001,
        "aliasName": "SYNTHETIC-ALIAS",
        "bankAccountNo": "SYNTHETIC-ACCOUNT",
        "financialInst": "SYNTHETIC-INST",
        "reconInst": "SYNTHETIC-RECON",
        "entity": "SYNTHETIC-ENTITY",
        "currency": "USD",
        "memo": "synthetic memo",
        "operator": "synthetic-operator",
        "assembleStrategy": "SYNTHETIC-STRATEGY",
        "regionType": "SYNTHETIC-REGION",
        "ruleStatus": "ENABLED",
        "countries": ["US", "SG"],
        "sceneCodes": ["SYNTHETIC-SCENE"],
        "supportMultiCurrency": False,
        "gmtCreate": 1694000000000,
        "gmtModified": 1694100000000,
        **changes,
    }


def page(rows=None, **changes):
    rows = [row()] if rows is None else rows
    return {
        "status": 200,
        "body": {
            "success": True,
            "pageNo": 1,
            "pageSize": 1000,
            "totalCount": len(rows),
            "resultDataList": rows,
            **changes,
        },
    }


def detail(identity="1", **changes):
    base = row(identity)
    result = {
        "vaRuleId": identity,
        "bankRuleId": base["bankRuleId"],
        "assembleStrategy": base["assembleStrategy"],
        "entity": base["entity"],
        "memo": base["memo"],
        "regionType": base["regionType"],
        "ruleStatus": base["ruleStatus"],
        "sceneCodes": base["sceneCodes"],
        "clientEntity": "SYNTHETIC-CLIENT",
        "creditAreas": ["US", "SG"],
        "assignInfo": {
            "assignCount": 0,
            "assignFlows": [],
            "ruleVaTotal": 3,
            "vaAssignAble": 3,
            "vaAssigned": 0,
            "vaImported": 0,
            "vaRuleId": identity,
            "vaUnused": 3,
            "vaUsed": 0,
        },
        "vaWarningInfo": {"warningCount": 0},
    }
    result.update(changes)
    return {"status": 200, "body": {"success": True, "resultObj": result}}


def listing(run_cli, *flags):
    return run_cli(["collection", "va", "rules", "list", *flags])


def getting(run_cli, *flags):
    return run_cli(["collection", "va", "rules", "get", *flags])


def refresh(run_cli):
    return run_cli(["refresh", "collection", "va"])


def seed(run_cli, setup):
    setup.state.business_script.extend([page(), detail()])
    assert refresh(run_cli)[0] == 0
    return listing(run_cli)[1], getting(run_cli, "--id", "1")[1]


def test_refresh_publishes_pairs_and_offline_reads(run_cli, envelope, setup):
    rows = [row("20"), row("2")]
    setup.state.business_script.extend([page(rows), detail("2"), detail("20")])
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    result = envelope(out)
    assert result["data"]["namespace"] == "collection.va.rules.list:rules:cdp"
    assert result["data"]["row_count"] == 2
    assert setup.state.business_requests == [
        {"pageNo": 1, "pageSize": 1000},
        {"vaRuleId": "2"},
        {"vaRuleId": "20"},
    ]
    expressions = [
        expression
        for transport in setup.state.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    assert len(expressions) == 3
    assert "virtualAccountRule/list.json" in expressions[0]
    assert 'method: "POST"' in expressions[0]
    for expression in expressions[1:]:
        assert "virtualAccountRule/detail.json" in expression
        assert 'method: "GET"' in expression
        # vaRuleId rides the URL query, never a JSON body.
        assert "URLSearchParams" in expression
    before = len(setup.state.transports)
    setup.state.running = False
    listed = envelope(
        listing(run_cli, "--all", "--require-fresh", "--require-complete")[1]
    )
    assert listed["data"] == list(reversed(rows))
    assert listed["meta"]["complete"] and not listed["meta"]["has_more"]
    for identity in ["2", "20"]:
        code, out, _ = getting(
            run_cli, "--id", identity, "--require-fresh", "--require-complete"
        )
        assert code == 0
        detail_data = envelope(out)["data"]
        assert detail_data == detail(identity)["body"]["resultObj"]
        # List-only fields never leak into the true detail.
        assert "countries" not in detail_data
        assert "bankAccountNo" not in detail_data
    assert len(setup.state.transports) == before
    assert b"FAKE-CTOKEN-SECRET" not in setup.cache_path.read_bytes()


def test_cache_miss_directs_refresh_and_live_never_writes_cache(
    run_cli, envelope, setup
):
    code, out, _ = listing(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_MISS"
    assert "refresh collection va" in envelope(out)["error"]["message"]
    assert envelope(getting(run_cli, "--id", "1")[1])["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []

    old = seed(run_cli, setup)
    digest = setup.cache_path.read_bytes()
    setup.state.business_script.append(page([row("3")]))
    code, out, _ = listing(run_cli, "--live")
    assert code == 0
    live_list = envelope(out)
    assert live_list["meta"]["source"] == "live"
    assert live_list["data"] == [row("3")]
    setup.state.business_script.append(detail("3"))
    code, out, _ = getting(run_cli, "--id", "3", "--live")
    assert code == 0
    live_get = envelope(out)
    assert live_get["data"]["clientEntity"] == "SYNTHETIC-CLIENT"
    assert live_get["meta"]["query"] == {
        "capability": "collection.va.rules.get",
        "id": "3",
    }
    # A live null detail is an explicit failure, never a cached substitute.
    setup.state.business_script.append(
        {"status": 200, "body": {"success": True, "resultObj": None}}
    )
    assert (
        envelope(getting(run_cli, "--id", "3", "--live")[1])["error"]["code"]
        == "INVALID_RESPONSE"
    )
    assert setup.cache_path.read_bytes() == digest
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old
    assert envelope(getting(run_cli, "--id", "absent")[1])["error"]["code"] == (
        "NOT_FOUND"
    )


def test_overflow_and_detail_mismatch_preserve_snapshot(run_cli, envelope, setup):
    old = seed(run_cli, setup)
    setup.state.business_script.append(page([row()], totalCount=1001))
    result = refresh(run_cli)
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INCOMPLETE_RESULT"
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old

    mismatched = detail()
    mismatched["body"]["resultObj"]["ruleStatus"] = "DRIFTED"
    setup.state.business_script.extend([page(), mismatched])
    result = refresh(run_cli)
    assert result[0] == 1
    assert envelope(result[1])["error"]["code"] == "INVALID_RESPONSE"
    assert (listing(run_cli)[1], getting(run_cli, "--id", "1")[1]) == old


def test_offline_help_describe_and_bare_navigation(run_cli, envelope, monkeypatch):
    monkeypatch.setattr(
        cli.config_mod, "load", lambda *args: pytest.fail("loaded config")
    )
    groups = [("collection", "va"), ("collection", "va", "rules")]
    leaves = [
        ("collection", "va", "rules", "list"),
        ("collection", "va", "rules", "get"),
        ("refresh", "collection", "va"),
    ]
    for path in groups:
        assert run_cli(list(path))[0] == 0
    for path in groups + leaves:
        assert run_cli(["help", *path])[0] == 0
        assert run_cli([*path, "--help"])[0] == 0
    list_help = run_cli(["help", "collection", "va", "rules", "list"])[1]
    assert "ASCII" in list_help and "original string" in list_help
    assert "bankRuleId" in list_help
    get_help = run_cli(["help", "collection", "va", "rules", "get"])[1]
    assert "bankAccountVaRule" in get_help
    for action, data in [("list", [row()]), ("get", detail()["body"]["resultObj"])]:
        code, out, _ = run_cli(["describe", "collection", "va", "rules", action])
        assert code == 0
        document = envelope(out)
        assert document["read_guide"]["evidence"].endswith(
            "2026-09-26-collection-va-rule-contract-recheck.md"
        )
        schema = document["data_schema"]
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(data)
    detail_schema = envelope(
        run_cli(["describe", "collection", "va", "rules", "get"])[1]
    )["data_schema"]
    assert set(detail_schema["properties"]["assignInfo"]["properties"]) == {
        "assignCount",
        "assignFlows",
        "ruleVaTotal",
        "vaAssignAble",
        "vaAssigned",
        "vaImported",
        "vaRuleId",
        "vaUnused",
        "vaUsed",
    }
    assert "vaWarningInfo" in detail_schema["properties"]
    assert "vaWarningInfo" not in detail_schema["required"]


def test_unsupported_domain_filters_rejected_before_browser(run_cli, envelope, setup):
    for argv in [
        ["collection", "va", "rules", "list", "--entity", "SYNTHETIC"],
        ["collection", "va", "rules", "list", "--live", "--alias-name", "X"],
        ["collection", "va", "rules", "get", "--id", "1", "--currency", "USD"],
        ["refresh", "collection", "va", "--rule-status", "ENABLED"],
    ]:
        code, out, _ = run_cli(argv)
        assert code == 2, argv
        assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert setup.state.business_requests == []


def test_transport_restrictions_before_browser(setup):
    from dogopencli.plugins.collection.va_rule import (
        COLLECTION_VA_RULES,
        COLLECTION_VA_RULES_DETAIL,
    )

    for capability, body in [
        (COLLECTION_VA_RULES, {"pageNo": 1, "pageSize": 1000}),
        (COLLECTION_VA_RULES_DETAIL, {"vaRuleId": "1"}),
    ]:
        transport = CdpQueryTransport(
            setup.state.transport("http://127.0.0.1:9222"),
            capability,
            page_url="https://ifundcontrol.alipay.com",
        )
        request = QueryRequest(
            capability.name,
            capability.contract.method,
            capability.contract.host,
            capability.contract.path,
            body,
        )
        for change in [
            {"path": "/ivostro/api/virtualAccountRule/save.json"},
            {"host": "evil.example"},
            {"method": "DELETE"},
            {"body": {**body, "action": "save"}},
            {"body": {"pageNo": 1, "pageSize": 10}},
            {"capability": "collection.sla.configs.list"},
        ]:
            with pytest.raises(CliError) as caught:
                transport.execute(replace(request, **change))
            assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert not setup.state.business_requests
    assert not any(t.created for t in setup.state.transports)
