"""Consumer validation of bundled payment schemas, without backend access."""

import pytest
from jsonschema import Draft202012Validator, ValidationError

from dogopencli.plugins.payment.descriptions import data_schema

CAPABILITIES = (
    "payment.channel.list",
    "payment.cost.list",
    "payment.sla.baselines.list",
    "payment.sla.baselines.get",
)


@pytest.mark.parametrize("capability", CAPABILITIES)
def test_schema_dialect_open_nulls_and_freshness(capability):
    schema = data_schema(capability)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    record_schema = schema if capability.endswith("get") else schema["items"]
    record = dict.fromkeys(record_schema["properties"])
    record["futureExtension"] = {"arbitrary": [True, None, "new"]}
    validator.validate(record if capability.endswith("get") else [record])
    with pytest.raises(ValidationError):
        validator.validate([] if capability.endswith("get") else {})
    record_schema["properties"].clear()
    assert data_schema(capability) != schema


def test_nested_fee_branches_remain_open():
    schema = data_schema("payment.cost.list")
    data = [
        {
            "itemId": "SYNTHETIC",
            "costRateConfigList": [
                {
                    "feeCalcBasisType": "FUTURE_METHOD",
                    "costRateVO": {
                        "fixedAmount": {"amount": 0.125, "cent": None, "extra": True},
                        "feeRateRatioValue": {"value": "future-wire-format"},
                        "costRateRangeList": [
                            {
                                "includeRangeBottom": None,
                                "rangeBottom": {"amount": "preserved-extension"},
                                "rangeFeeRateRatioValue": {"ratioUnit": "FUTURE_UNIT"},
                            }
                        ],
                    },
                }
            ],
        }
    ]
    Draft202012Validator(schema).validate(data)


def test_unknown_array_elements_and_sla_units():
    schema = data_schema("payment.sla.baselines.get")
    Draft202012Validator(schema).validate(
        {
            "id": "SYNTHETIC",
            "serviceLevelLimit": [None, 1, "future", {"unknown": True}],
            "creditorMinAmount": "0.0000000000000000001",
        }
    )
    fields = schema["properties"]
    assert fields["serviceLevelLimit"]["items"]["x-evidence"]["type"] == "unknown"
    assert fields["debitorSuccessSla"]["x-unit"] == "seconds"
    assert fields["gmtCreate"]["x-evidence"]["unit"] == "unknown"


def test_field_roles_distinguish_currency_bounds_and_configuration():
    fields = data_schema("payment.channel.list")["items"]["properties"]
    assert "payment currency" in fields["debitCurrency"]["description"]
    assert "receiving currency" in fields["creditCurrency"]["description"]
    assert "minimum debit" in fields["debitMinAmount"]["description"]
    assert "maximum credit" in fields["creditMaxAmount"]["description"]
    assert "not measured" in fields["efficiencyLevel"]["description"]
    assert "modification timestamp" in fields["gmtModified"]["description"]
    assert fields["gmtModified"]["x-evidence"]["unit"] == "unknown"
    cost = data_schema("payment.cost.list")["items"]["properties"]
    rules = cost["costRateConfigList"]["items"]["properties"]
    fee = rules["costRateVO"]["properties"]
    assert "fixed fee" in fee["fixedAmount"]["description"]
    assert "not an actual charge" in fee["fixedAmount"]["description"]
