"""Consume installed descriptions and synthetic results through the public CLI."""

import json
from decimal import Decimal

import pytest
from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for
from test_cost_cli_sit import cost_row, refreshed
from test_cost_cli_sit import cost_setup as cost_setup
from test_sla_cli_sit import refreshed as refresh_sla
from test_sla_cli_sit import sla_detail, sla_row
from test_sla_cli_sit import sla_setup as sla_setup

PATHS = [
    "payment channel list",
    "payment cost list",
    "payment sla baselines list",
    "payment sla baselines get",
]


def success(run_cli, command):
    code, out, err = run_cli(command.split())
    assert code == 0, (out, err)
    return json.loads(out, parse_float=Decimal)


def description(run_cli, path):
    return success(run_cli, "describe " + path)


def validate(doc, result):
    assert result["error"] is None
    validator_for(doc["data_schema"])(doc["data_schema"]).validate(result["data"])
    assert set(result["meta"]) <= set(doc["read_guide"]["metadata"])


@pytest.mark.parametrize("path", PATHS)
def test_declared_dialect_and_evidence_contract(run_cli, path):
    doc = description(run_cli, path)
    schema = doc["data_schema"]
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert validator_for(schema) is Draft202012Validator
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert not validator.is_valid([] if path.endswith("get") else {})
    assert not validator.is_valid(None)
    guide = doc["read_guide"]
    values = set(guide["annotations"]["x-evidence"]["values"])
    aspects = set(guide["annotations"]["x-evidence"]["aspects"])

    def check(node):
        if isinstance(node, dict):
            if "x-evidence" in node:
                assert set(node["x-evidence"]) == aspects
                assert set(node["x-evidence"].values()) <= values
            for key, value in node.items():
                if key not in {"x-annotation-vocabulary", "x-evidence"}:
                    check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)

    check(schema)
    help_doc = success(run_cli, "help " + path)
    options = {
        flag: option for option in help_doc["options"] for flag in option["flags"]
    }
    for mapping in guide["filters"]:
        assert mapping["flag"] in options
        field = mapping["record_field"]
        if field is not None:
            record = schema if path.endswith("get") else schema["items"]
            assert field in record["properties"]


def test_channel_schema_projection_and_partial_source(
    run_cli, dataset_factory, config_factory, bulk_channel_rows
):
    path = "payment channel list"
    doc = description(run_cli, path)  # Before config or cache exists.
    rows = bulk_channel_rows(101)
    rows[0].update(
        status="FUTURE_STATUS",
        supportCreditInstIdList=[None, {"future": [1, "x"]}],
        futureExtension={"enabled": None},
    )
    rows[1]["chargeAmount"] = None
    del rows[2]["chargeAmount"]
    config_factory(dataset_factory(rows))
    success(run_cli, "refresh payment channel")
    result = success(run_cli, path)
    validate(doc, result)
    assert len(result["data"]) == 100
    meta = result["meta"]
    assert meta["has_more"] and meta["matched_total"] == 101
    assert meta["dataset_complete"] and not meta["complete"]
    assert meta["simulated"] and meta["backend"] == "snapshot"
    assert meta["source"] == "cache" and meta["scope"] == "EXTERNAL"
    assert meta["snapshot_id"] and meta["dataset_id"]
    assert meta["source_observed_from"] and meta["source_observed_to"]
    full = success(run_cli, path + " --limit 0")
    validate(doc, full)
    assert len(full["data"]) == 101 and not full["meta"]["has_more"]
    by_id = {row["abilityId"]: row for row in full["data"]}
    assert by_id[rows[1]["abilityId"]]["chargeAmount"] is None
    assert "chargeAmount" not in by_id[rows[2]["abilityId"]]
    projected = success(run_cli, path + " --limit 0 --fields status")
    assert all(set(row) == {"status"} for row in projected["data"])
    assert projected["meta"] == full["meta"]
    assert "partial data" in doc["read_guide"]["projection"]
    empty = success(run_cli, path + " --debit-account-name NO_MATCH")
    validate(doc, empty)
    assert empty["data"] == [] and not empty["meta"]["complete"]
    code, out, _ = run_cli((path + " --require-complete").split())
    assert code == 1 and json.loads(out)["error"]["code"] == "INCOMPLETE_RESULT"
    props = doc["data_schema"]["items"]["properties"]
    assert "enum" not in props["status"]
    assert "FUTURE_STATUS" not in props["status"]["x-observed-values"]
    assert props["supportCreditInstIdList"]["items"]["x-evidence"]["type"] == "unknown"
    assert "local" in props["seqid"]["description"]
    assert "globally unique" in props["abilityId"]["description"]
    assert "alias" in props["debitAccountName"]["description"]
    assert "sensitive" in props["debitAccountNo"]["description"]
    assert description(run_cli, path) == doc  # Business state cannot alter it.


def test_cost_nested_fee_branches_and_raw_representations(run_cli, cost_setup):
    path = "payment cost list"
    doc = description(run_cli, path)
    row = cost_row(101, costCurrencyCode="EUR", isFvt=None)
    ordinary = row["costRateConfigList"][0]
    segmented = {
        "feeCalcBasisType": "CA4",
        "futureRule": {"preserve": True},
        "costRateVO": {
            "costRateRangeList": [
                {
                    "includeRangeBottom": True,
                    "includeRangeTop": False,
                    "rangeBottom": {"amount": "0.0001", "currency": "USD"},
                    "rangeTop": None,
                    "rangeFixedAmount": {"amount": Decimal("0.1234567890123456789")},
                    "rangeFeeRateRatioValue": {"value": 7, "ratioUnit": "FUTURE"},
                    "futureBoundary": [None, {}],
                }
            ]
        },
    }
    row["costRateConfigList"] = [ordinary, segmented]
    missing = cost_row(102, costRateConfigList=[])
    del missing["isFvt"]
    refreshed(run_cli, cost_setup, [row, missing])
    result = success(run_cli, path + " --limit 0")
    validate(doc, result)
    first, second = result["data"]
    assert first["isFvt"] is None and "isFvt" not in second
    assert first["costRateConfigList"] == row["costRateConfigList"]
    assert first["transCurrencyCode"] != first["costCurrencyCode"]
    projected = success(run_cli, path + " --limit 0 --fields costRateConfigList")
    assert projected["data"][0] == {"costRateConfigList": row["costRateConfigList"]}
    assert projected["meta"] == result["meta"]
    schema = doc["data_schema"]
    props = schema["items"]["properties"]
    assert "alias" in props["bankAccountAliasName"]["description"]
    assert "not a channel ID" in props["itemId"]["description"]
    assert props["approveProcessStatus"]["x-evidence"]["type"] == "unknown"
    assert props["isFvt"]["x-evidence"]["nullability"] == "unknown"
    assert (
        schema["$defs"]["Ratio"]["properties"]["amount"]["x-evidence"]["unit"]
        == "unknown"
    )
    assert "division by 100" in schema["$defs"]["Money"]["description"]


def test_sla_list_to_detail_and_quality_policy(run_cli, sla_setup):
    path = "payment sla baselines"
    list_doc = description(run_cli, path + " list")
    detail_doc = description(run_cli, path + " get")
    sla_setup.write_config(ttl_hours=0)
    refresh_sla(
        run_cli, sla_setup, [sla_row(101, serviceLevelLimit=[None, {"new": 1}])]
    )
    listing = success(run_cli, path + " list --limit 0")
    validate(list_doc, listing)
    baseline_id = listing["data"][0]["id"]
    sla_setup.state.business_script.append(
        {"status": 200, "body": {"success": True, "resultData": sla_detail(101)}}
    )
    before = sla_setup.cache_path.read_bytes()
    detail = success(run_cli, path + f" get --id {baseline_id}")
    validate(detail_doc, detail)
    assert detail["data"]["riskRuleCode"] == "RISK-101"
    assert "riskRuleCode" not in listing["data"][0]
    assert detail["meta"]["source"] == "live"
    assert detail["meta"]["snapshot_id"] is None
    assert sla_setup.cache_path.read_bytes() == before
    code, out, _ = run_cli((path + f" get --id {baseline_id} --require-fresh").split())
    assert code == 2 and json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    sla_setup.state.business_script.append(
        {"status": 200, "body": {"success": True, "resultData": sla_detail(101)}}
    )
    projected = success(
        run_cli, path + f" get --id {baseline_id} --fields creditorMinAmount"
    )
    assert projected["data"] == {"creditorMinAmount": "0.10"}
    live_data = sla_detail(
        101, creditorSlaBuffer=None, serviceLevelLimit=[1, "unknown"]
    )
    sla_setup.state.business_script.append(
        {"status": 200, "body": {"success": True, "resultData": live_data}}
    )
    before = sla_setup.cache_path.read_bytes()
    live = success(run_cli, path + f" get --id {baseline_id} --live --require-complete")
    validate(detail_doc, live)
    assert live["meta"]["query"] == {
        "capability": "payment.sla.baselines.get",
        "id": baseline_id,
    }
    assert live["meta"]["source"] == "live" and live["meta"]["snapshot_id"] is None
    assert sla_setup.cache_path.read_bytes() == before
    props = detail_doc["data_schema"]["properties"]
    assert props["debitorSuccessSla"]["x-unit"] == "seconds"
    assert props["creditorSlaBuffer"]["x-evidence"]["unit"] == "unknown"
    assert "not observed" in detail_doc["data_schema"]["description"]
    assert "list_to_detail" in list_doc["read_guide"]


def test_channel_live_filter_help_matches_read_guide(run_cli):
    doc = description(run_cli, "payment channel list")
    help_doc = success(run_cli, "help payment channel list")
    constraint = next(
        text for text in help_doc["constraints"] if "--live accepts" in text
    )
    scalar, arrays = constraint.split(";", 1)
    assert all(
        flag in scalar
        for flag in ("--financial-inst-id", "--debit-inst-country-code", "--status")
    )
    assert all(
        flag in arrays
        for flag in (
            "--debit-account-name",
            "--debit-account-no",
            "--clearing-system-name",
            "--debit-currency",
            "--credit-currency",
        )
    )
    assert "repeated values" in arrays
    guide = " ".join(doc["read_guide"]["filter_semantics"])
    assert "scalar filters" in guide and "array filters accept repeated values" in guide
    assert all("backend_complete" not in text for text in help_doc["constraints"])
