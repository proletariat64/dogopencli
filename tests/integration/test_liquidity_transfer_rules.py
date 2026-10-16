"""Public transfer-rule list acceptance; all records and identities invented."""

import pytest

from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.plugins.liquidity.transfer_rules import project_transfer_rule

pytest_plugins = ["test_liquidity_cli_sit"]
QUERY = ["liquidity", "rules", "transfer", "list", "--limit", "0"]
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
