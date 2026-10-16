"""Collection VA rule public CLI + fake CDP + real SQLite acceptance (#32)."""

from dataclasses import replace

import pytest
from test_sla_cli_sit import sla_setup  # noqa: F401

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


def refusal():
    """The observed platform refusal: HTTP 200 declaring success=false."""
    return {"status": 200, "body": {"success": False, "errorCode": "SYNTHETIC-REFUSAL"}}


def listing(run_cli, *flags):
    return run_cli(["collection", "va", "rules", "list", *flags])


def getting(run_cli, *flags):
    return run_cli(["collection", "va", "rules", "get", *flags])


def refresh(run_cli, *flags):
    return run_cli(["refresh", "collection", "va", *flags])


def seed(run_cli, setup):
    setup.state.business_script.append(page())
    assert refresh(run_cli)[0] == 0
    return listing(run_cli)[1], None


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


DETAIL_REQUIRED_FIELDS = [
    "assembleStrategy",
    "assignInfo",
    "bankRuleId",
    "clientEntity",
    "creditAreas",
    "entity",
    "memo",
    "regionType",
    "ruleStatus",
    "sceneCodes",
    "vaRuleId",
]
