"""Public transfer-rule list acceptance; all records and identities invented."""

import copy
import json

import pytest

from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.transfer_rules import project_transfer_rule

pytest_plugins = ["test_liquidity_cli_sit"]
QUERY = ["liquidity", "rules", "transfer", "list", "--all"]
REFRESH = ["refresh", "liquidity", "rules", "transfer"]


def rule(identity="SYN-RULE"):
    return {
        "ruleId": identity,
        "ruleNo": "SYN-NO",
        "version": 7,
        "tntInstId": "GUAPW3SG",
        "status": "UNKNOWN-STATE",
        "ruleName": "SYN-NAME",
        "debitEntity": "SYN-DEBIT",
        "creditEntity": "SYN-CREDIT",
        "debitCurrency": "unknown",
        "creditCurrency": "",
        "paymentAmount": "1.234500",
        "effectiveTime": 0,
        "expiryTime": None,
        "gmtModified": "unknown-config-time",
        "bizConditions": [
            {
                "condition": "SYN-CONFIG",
                "conditionLogical": 0,
                "gradeVOList": [{"minValue": None, "maxValue": "", "gradeNo": 0}],
                "operator": "SYN-PRIVATE",
                "subscribers": ["SYN-PRIVATE"],
            }
        ],
        "timeConditions": [
            {
                "type": "unknown",
                "days": ["MON", "https://example.invalid/private"],
                "calendarConditionVos": [
                    {
                        "exclude": False,
                        "memo": "SYN-PRIVATE",
                        "condition": "contact@example.invalid",
                    }
                ],
                "webhookUrl": "https://example.invalid/private",
            }
        ],
        "ruleActionVOS": [[{"actionPara": {"subscribers": ["SYN-PRIVATE"]}}]],
        "nextTriggerTime": 123,
        "operator": "SYN-PRIVATE",
        "processId": "SYN-PROCESS",
    }


def response(rows, total=None):
    return {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {
                "success": True,
                "transferRuleVOS": rows,
                "ruleCount": len(rows) if total is None else total,
            },
        },
    }


def seed(setup, run_cli, rows=None):
    setup.state.business_handler = lambda payload, index: response(
        [rule()] if rows is None else rows
    )
    code, out, err = run_cli(REFRESH)
    assert code == 0, err
    return parse(out)


def test_request_projection_refresh_offline_live_and_detail_isolation(setup, run_cli):
    assert parse(run_cli(QUERY)[1])["error"]["code"] == "CACHE_MISS"
    assert setup.state.transports == []
    detail = {
        "success": True,
        "result": {
            "success": True,
            "transferRuleVO": {
                "ruleId": "SYN-RULE",
                "ruleActionVOS": [{"synthetic": "detail-only"}],
            },
        },
    }
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": detail,
    }
    get = ["liquidity", "rules", "transfer", "get", "--rule-id", "SYN-RULE"]
    code, out, err = run_cli([*get, "--live"])
    assert code == 0, (out, err)
    assert (
        run_cli(
            [
                "refresh",
                "liquidity",
                "rules",
                "transfer",
                "detail",
                "get",
                "--rule-id",
                "SYN-RULE",
            ]
        )[0]
        == 0
    )
    detail_before = parse(run_cli(get)[1])
    start = len(setup.state.business_requests)
    refreshed = seed(setup, run_cli)
    assert len(setup.state.business_requests) == start + 1
    request = setup.state.business_requests[-1]
    assert set(request) == {"tntInstId", "transferRuleQueryRequest"}
    assert request["tntInstId"] == "GUAPW3SG"
    assert json.loads(request["transferRuleQueryRequest"]) == {
        "tntInstId": "GUAPW3SG",
        "rowStart": 0,
        "pageSize": 5000,
        "debitEntity": [],
        "creditEntity": [],
    }
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert any("transferRuleQuery.json" in e and "GET" in e for e in expressions)
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli([*QUERY, "--live", "--require-complete"])
    assert code == 0, err
    live = parse(out)
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    request_count = len(setup.state.business_requests)
    offline = parse(run_cli([*QUERY, "--require-complete"])[1])
    assert offline["data"] == live["data"]
    assert offline["meta"]["kind"] == "settings"
    assert offline["meta"]["complete"] is True
    assert offline["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert offline["meta"]["reported_total"] == 1
    assert len(setup.state.business_requests) == request_count
    got = offline["data"][0]
    assert got["ruleId"] == "SYN-RULE" and got["version"] == 7
    assert got["paymentAmount"] == "1.234500" and got["debitCurrency"] == "unknown"
    assert got["effectiveTime"] == 0 and got["expiryTime"] is None
    assert got["bizConditions"][0]["gradeVOList"] == [
        {"minValue": None, "maxValue": "", "gradeNo": 0}
    ]
    assert "SYN-PRIVATE" not in json.dumps(got)
    assert "webhookUrl" not in json.dumps(got)
    assert "example.invalid" not in json.dumps(got)
    assert "nextTriggerTime" not in got and "ruleActionVOS" not in got
    assert parse(run_cli(get)[1]) == detail_before


@pytest.mark.parametrize(
    "case",
    [
        "id_int",
        "id_blank",
        "id_missing",
        "tenant",
        "nested_tenant",
        "conflict",
        "private_conflict",
        "missing_total",
        "boolean_total",
        "negative_total",
        "string_total",
        "container",
        "outer_failure",
        "inner_failure",
        "inner_missing",
        "auth",
        "permission",
    ],
)
def test_hard_failures_preserve_capture(setup, run_cli, case):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    row = rule()
    rows = [row]
    answer = response(rows)
    result = answer["body"]["result"]
    if case == "id_int":
        row["ruleId"] = 5
    elif case == "id_blank":
        row["ruleId"] = " "
    elif case == "id_missing":
        del row["ruleId"]
    elif case == "tenant":
        row["tntInstId"] = "OTHER"
    elif case == "nested_tenant":
        row["bizConditions"][0]["tntInstId"] = "OTHER"
    elif case == "conflict":
        rows.append({**copy.deepcopy(row), "version": 8})
    elif case == "private_conflict":
        rows.append({**copy.deepcopy(row), "operator": "OTHER"})
    elif case == "missing_total":
        del result["ruleCount"]
    elif case == "boolean_total":
        result["ruleCount"] = True
    elif case == "negative_total":
        result["ruleCount"] = -1
    elif case == "string_total":
        result["ruleCount"] = "1"
    elif case == "container":
        result["transferRuleVOS"] = {}
    elif case == "outer_failure":
        answer["body"]["resultFlag"] = False
    elif case == "inner_failure":
        result["success"] = False
    elif case == "inner_missing":
        del result["success"]
    elif case == "auth":
        answer["status"] = 401
    elif case == "permission":
        answer["status"] = 403
    setup.state.business_handler = lambda payload, index: answer
    for command in ([*QUERY, "--live"], REFRESH):
        code, out, _ = run_cli(command)
        assert code == 1 and parse(out)["error"] is not None
        assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize(
    "rows,total", [([rule()], 5001), ([rule(), rule()], 1), ([rule(), rule()], 2)]
)
def test_single_response_partial_default_strict_and_persistent_warning(
    setup, run_cli, rows, total
):
    seed(setup, run_cli)
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = lambda payload, index: response(rows, total)
    start = len(setup.state.business_requests)
    code, out, _ = run_cli([*REFRESH, "--require-complete"])
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert len(setup.state.business_requests) == start + 1
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(REFRESH)
    assert code == 0 and "INCOMPLETE_RESULT" in err
    setup.state.reachable = False
    code, out, err = run_cli(QUERY)
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert parse(out)["meta"]["complete"] is False
    assert len(parse(out)["data"]) == 1
    assert run_cli([*QUERY, "--require-complete"])[0] == 1


def test_complete_empty_and_catalog_are_offline(setup, run_cli):
    seed(setup, run_cli, [])
    setup.state.reachable = False
    code, out, err = run_cli([*QUERY, "--require-complete"])
    assert code == 0, err
    assert parse(out)["data"] == [] and parse(out)["meta"]["complete"] is True
    count = len(setup.state.business_requests)
    description = parse(run_cli(["describe", *QUERY[:-1]])[1])
    assert description["read_guide"]["kind"] == "settings"
    assert description["read_guide"]["identity"] == ["ruleId"]
    assert description["read_guide"]["request"]["pagination"] == "single"
    assert description["data_schema"]["properties"]["paymentAmount"]
    assert run_cli(["help", "liquidity", "rules", "transfer"])[0] == 0
    assert run_cli(["snapshot"])[0] == 0
    assert len(setup.state.business_requests) == count
    assert run_cli([*QUERY, "--page-size", "10"])[0] == 2
    assert run_cli([*QUERY, "--debit-entity", "SYN"])[0] == 2
    assert run_cli(["liquidity", "rules", "treasury-transfer", "list"])[0] != 0


@pytest.mark.parametrize("mutation", ["tenant", "entity", "offset", "width", "extra"])
def test_shared_transport_rejects_unverified_nested_requests(
    setup, run_cli, monkeypatch, mutation
):
    from dogopencli.plugins.liquidity.capability import LiquidityListCapability

    original = LiquidityListCapability.page_body

    def altered(self, scope, row_start, page_size=None):
        body = original(self, scope, row_start, page_size)
        vo = json.loads(body["transferRuleQueryRequest"])
        if mutation == "tenant":
            vo["tntInstId"] = "OTHER"
        elif mutation == "entity":
            vo["debitEntity"] = ["SYN-OTHER"]
        elif mutation == "offset":
            vo["rowStart"] = 5000
        elif mutation == "width":
            vo["pageSize"] = 10
        elif mutation == "extra":
            vo["unverified"] = "SYN"
        body["transferRuleQueryRequest"] = json.dumps(vo)
        return body

    monkeypatch.setattr(LiquidityListCapability, "page_body", altered)
    code, out, _ = run_cli(REFRESH)
    assert code == 1 and parse(out)["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []


@pytest.mark.parametrize("field", ["ruleName", "title"])
@pytest.mark.parametrize(
    "private", ["CONTACT@EXAMPLE.INVALID", "MAILTO:contact", "HTTPS://example.invalid"]
)
def test_top_level_private_strings_are_omitted(field, private):
    source = rule()
    source[field] = private
    projected = project_transfer_rule(source)
    assert field not in projected
    assert projected["ruleId"] == source["ruleId"]
    assert projected["paymentAmount"] == "1.234500"


def test_top_level_safe_configuration_and_identity_are_preserved():
    source = rule("native@identity.invalid")
    source.update(
        title="Safe configuration title",
        ruleNo="native@number.invalid",
        debitAliasName="https://native-alias.invalid",
        debitEntity=["ENTITY-A", "ENTITY-B"],
        creditEntity={"source": "ENTITY-C"},
        paymentAmount=0,
    )
    projected = project_transfer_rule(source)
    for field in (
        "ruleId",
        "ruleNo",
        "debitAliasName",
        "ruleName",
        "title",
        "debitEntity",
        "creditEntity",
        "paymentAmount",
        "expiryTime",
        "creditCurrency",
    ):
        assert projected[field] == source[field]


@pytest.mark.parametrize("field", ["preCheckCondtions", "ruleCheckCondtions"])
def test_check_conditions_use_allowlist_and_private_value_filter(field):
    source = rule()
    source[field] = [
        {
            "condition": "SYN-CONFIG",
            "conditionLogical": 0,
            "tntInstId": "GUAPW3SG",
            "operator": "SYN-PRIVATE",
            "gradeVOList": [
                {"minValue": None, "maxValue": "", "gradeNo": 0, "memo": "SYN-PRIVATE"}
            ],
            "days": [
                "MON",
                "MAILTO:contact",
                "HTTPS://example.invalid",
                "CONTACT@EXAMPLE.INVALID",
            ],
        }
    ]
    assert project_transfer_rule(source)[field] == [
        {
            "condition": "SYN-CONFIG",
            "conditionLogical": 0,
            "tntInstId": "GUAPW3SG",
            "gradeVOList": [{"minValue": None, "maxValue": "", "gradeNo": 0}],
            "days": ["MON"],
        }
    ]
    source[field][0]["tntInstId"] = "OTHER"
    with pytest.raises(CliError, match="condition tenant is outside scope"):
        project_transfer_rule(source)
