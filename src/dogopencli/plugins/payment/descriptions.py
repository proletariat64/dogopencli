"""Bundled, offline descriptions of unprojected payment query data.

Business observations come from docs/research/payment/2026-09-08-*
query contracts. Observations are annotations, never validation assertions.
"""

from typing import Any

DIALECT = "https://json-schema.org/draft/2020-12/schema"


def _field(
    description: str,
    observed: str | None = None,
    *,
    meaning: str = "unknown",
    unit: str = "not_applicable",
    values: list[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "description": description,
        "x-evidence": {
            "type": "observed" if observed else "unknown",
            "presence": "observed" if observed else "unknown",
            "nullability": "unknown",
            "unit": unit,
            "meaning": meaning,
        },
    }
    if observed:
        result["x-observed-type"] = observed
    if values:
        result["x-observed-values"] = values
    return result


def _object(description: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        **_field(description, "object"),
        "properties": properties,
        "additionalProperties": True,
    }


def _array(description: str, items: dict[str, Any]) -> dict[str, Any]:
    return {**_field(description, "array"), "items": items}


def _unknown_items() -> dict[str, Any]:
    return _field(
        "Element structure and semantics unresolved; preserve arbitrary JSON."
    )


def _strings(names: str) -> dict[str, Any]:
    return {
        name: _field(
            f"Backend {name} value; full encoding and business semantics unverified.",
            "string",
        )
        for name in names.split()
    }


def _numbers(names: str, observed: str = "integer") -> dict[str, Any]:
    return {
        name: _field(
            f"Raw {name}; unit, scaling and conversion rules unverified.",
            observed,
            unit="unknown",
        )
        for name in names.split()
    }


def _money() -> dict[str, Any]:
    return _object(
        "Money observation. Preserve numeric precision and original currency fields; "
        "cent does not imply division by 100. Conversion rules are unverified.",
        {
            **_numbers("amount", "number"),
            **_numbers("cent centFactor"),
            **_strings("currency currencyCode currencyValue"),
        },
    )


def _ratio() -> dict[str, Any]:
    return _object(
        "Ratio observation. Scaling is unverified; amount, value and hundredthValue "
        "are not interchangeable. Preserve raw values; do not infer percentages.",
        {
            **_numbers(
                "amount value hundredthValue thousandthValue tenThousandthValue",
                "number",
            ),
            **_strings("ratioUnit ratioUnitCode"),
        },
    )


def _channel() -> dict[str, Any]:
    fields = {
        **_strings(
            "configVersion financialInstCode operateTime lastOperator discardReason "
            "debitInstBic debitInstCountryCode debitInstMemberId clearingSystemName "
            "clearingSystemType creditRegion integrationMode communicateMode "
            "debitCurrency creditCurrency chargeBearer chargeDescription chargeMode "
            "fvtChargeType holidayPayoutSolution insufficientBalanceSolution "
            "regulatoryRequiredObo supportMultiCurrency supportPayoutReverse "
            "supportedDisplayNonUd supportedFvt supportedObo"
        ),
        **_numbers(
            "gmtModified costLevel noFvtCostLevel chargePercent efficiencyLevel "
            "grayOrderCount exceptedGrayOrderCount"
        ),
    }
    for name in (
        "averageProcessingTime businessAcceptStartTime businessAcceptEndTime "
        "cutOffTime overCutOffTime overLimitTime payoutEfficiency valueDateEfficiency "
        "timeZone"
    ).split():
        fields[name] = _field(
            f"Raw channel {name}; format, units and timezone unverified.",
            "string",
            unit="unknown",
        )
    fields.update(
        abilityId=_field(
            "Channel ability identifier; not an unqualified globally unique key. "
            "No verified one-to-one association with Cost itemId.",
            "integer",
            meaning="verified",
        ),
        seqid=_field(
            "CLI local dataset position; unstable across datasets and snapshots, "
            "not a business identifier or cross-domain join key.",
            "integer",
            meaning="verified",
        ),
        debitAccountName=_field(
            "Account alias/name; distinct from the full debitAccountNo.",
            "string",
            meaning="verified",
        ),
        debitAccountNo=_field(
            "Bank deposit account number; sensitive. Distinct from account alias.",
            "string",
            meaning="verified",
        ),
        payoutType=_field(
            "Outflow scenario. Observed choices are open, not an exhaustive enum.",
            "string",
            meaning="verified",
            values=["EXTERNAL", "LIQUIDITY", "MANUAL", "SETTLEMENT"],
        ),
        status=_field(
            "Channel activation state: ENABLE enabled, DISABLE deprecated, GRAY gray "
            "release, TEST pending launch, INIT draft. Future values remain open.",
            "string",
            meaning="verified",
            values=["ENABLE", "DISABLE", "GRAY", "TEST", "INIT"],
        ),
    )
    for name in (
        "debitMinAmount debitMaxAmount creditMinAmount creditMaxAmount chargeAmount"
    ).split():
        fields[name] = {"$ref": "#/$defs/Money"}
    for name in ("grayOrderBizNos", "supportCreditInstIdList"):
        fields[name] = _array(
            f"{name}: only empty arrays observed; element structure unknown.",
            _unknown_items(),
        )
    fields["transferTypeList"] = _array(
        "Transfer type codes; empty arrays and string elements observed; enum unknown.",
        _field("Transfer type code; meaning unresolved.", "string"),
    )
    return _object(
        "Payment channel capability record; preserve extension fields.", fields
    )


def _cost() -> dict[str, Any]:
    fee_range = _object(
        "CA4 interval; calculation and full boundary rules unverified.",
        {
            **_strings("feeRateRangeId status lastOperator"),
            **_numbers("gmtCreate gmtModified"),
            "includeRangeBottom": _field(
                "Whether the lower interval boundary is included.",
                "boolean",
                meaning="verified",
            ),
            "includeRangeTop": _field(
                "Whether the upper interval boundary is included.",
                "boolean",
                meaning="verified",
            ),
            **{
                name: {"$ref": "#/$defs/Money"}
                for name in (
                    "rangeBottom rangeTop rangeBottomFeeAmount rangeTopFeeAmount "
                    "rangeFixedAmount"
                ).split()
            },
            "rangeFeeRateRatioValue": {"$ref": "#/$defs/Ratio"},
        },
    )
    rate = _object(
        "Fee rate configuration; preserve ordinary and segmented branches.",
        {
            **_strings("feeItemRateConfigId feeCalcBasisTypeCode status lastOperator"),
            **_numbers("gmtCreate gmtModified"),
            **{
                name: {"$ref": "#/$defs/Money"}
                for name in ("bottomAmount", "fixedAmount", "topAmount")
            },
            "feeRateRatioValue": {"$ref": "#/$defs/Ratio"},
            "costRateRangeList": _array("Observed CA4 fee intervals.", fee_range),
        },
    )
    config = _object(
        "Fee rule and validity interval; multiple rules may exist, not just one.",
        {
            **_strings("feeItemRateConfigId"),
            **_numbers("validStartTime validEndTime"),
            "costRateVO": rate,
        },
    )
    for name, values in {
        "feeCalcBasisType": ["CA1", "CA4"],
        "feeCalcScale": ["TWO_DECIMAL_AFTER_POINTS"],
        "feeRoundingMode": ["HALF_UP"],
        "progressType": ["FULL_PROGRESS"],
    }.items():
        config["properties"][name] = _field(
            f"Observed {name} codes; full enum and calculation semantics unverified.",
            "string",
            values=values,
        )
    fields = {
        **_strings(
            "mappingCode legalEntity financialInst chargeBearer clearingNetworkName "
            "lastOperator"
        ),
        **_numbers("gmtCreate gmtModified"),
        "itemId": _field(
            "Cost configuration item identifier, not a channel ID; no verified "
            "one-to-one Channel/Cost association or universal join key.",
            "string",
            meaning="verified",
        ),
        "itemType": _field(
            "Payment cost configuration type; current query scope is fixed.",
            "string",
            meaning="verified",
            values=["FUND_OUT_CHANNEL_TRANS_FEE"],
        ),
        "bankAccountAliasName": _field(
            "Bank deposit account alias, not the full account number.",
            "string",
            meaning="verified",
        ),
        "transCurrencyCode": _field(
            "Transaction currency; distinct from the cost/fee currency.",
            "string",
            meaning="verified",
        ),
        "costCurrencyCode": _field(
            "Cost/fee currency; may differ from transaction currency.",
            "string",
            meaning="verified",
        ),
        "status": _field(
            "Cost configuration status; observed values are not exhaustive.",
            "string",
            values=["ACTIVATED", "OFFLINE"],
        ),
        "approveProcessStatus": _field(
            "UI approval column absent from inspected rows; type unresolved. "
            "Do not derive it from status."
        ),
        "costRateConfigList": _array("Embedded fee configuration rules.", config),
    }
    for name in ("isExistFvtAbility", "isFvt"):
        fields[name] = _field(
            f"Raw {name} flag; missing, null and empty differ from N. "
            "Do not infer an unknown enum meaning.",
            "string",
            values=["Y", "N"],
        )
    return _object(
        "Channel cost configuration, not actual charges or aggregate spending; "
        "does not provide a verified fee calculation engine.",
        fields,
    )


def _sla(detail: bool) -> dict[str, Any]:
    fields = {
        **_strings(
            "bizCategory creditorCurrency regionCode status creator lastOperator"
        ),
        **_numbers("gmtCreate gmtModified", "number"),
        "id": _field(
            "SLA baseline identifier returned by the list; pass this exact value "
            "to detail lookup. Not a channel or cost identifier.",
            "string",
            meaning="verified",
        ),
        "timezone": _field(
            "TimeZone display value; format, default and allowed zones unverified.",
            "string",
            meaning="verified",
        ),
        "holidayLimit": _field(
            "Holiday display value; encoding and relation to SLA computation unknown.",
            "string",
        ),
        "serviceLevelLimit": _array(
            "Service level list; only empty arrays observed, element types unknown.",
            _unknown_items(),
        ),
    }
    for name in ("creditorMinAmount", "creditorMaxAmount"):
        fields[name] = _field(
            "Creditor amount bound observed as decimal text; preserve strings and "
            "precision. Currency conversion and bound semantics unverified.",
            "string",
            unit="unknown",
        )
    for name, label in (
        ("debitorSuccessSla", "PaymentSucceedSLA"),
        ("creditorSuccessSla", "PaymentArrivalSLA"),
    ):
        fields[name] = _field(
            f"{label} product baseline, not measured arrival/performance. "
            "Numeric text has verified seconds unit from UI hour/minute rendering; "
            "preserve original text, never treat an unknown format as zero.",
            "string",
            meaning="verified",
            unit="verified",
        )
        fields[name]["x-unit"] = "seconds"
    if detail:
        for name in (
            "creditorBankBicLimit creditorSlaBuffer creditorSlaDecide debtorSlaBuffer "
            "debtorSlaDecide riskRuleCode"
        ).split():
            fields[name] = _field(
                f"{name} is a frontend detail-renderer hint, absent from inspected "
                "responses; structure, type and semantics unresolved.",
                unit="unknown",
            )
    return _object(
        "Product SLA baseline detail; not observed channel performance."
        if detail
        else "Product SLA baseline list row; fetch detail independently using id.",
        fields,
    )


def data_schema(capability: str) -> dict[str, Any]:
    """Return a fresh Draft 2020-12 schema; reject unsupported capability IDs."""
    if capability == "payment.channel.list":
        record = _channel()
    elif capability == "payment.cost.list":
        record = _cost()
    elif capability in {"payment.sla.baselines.list", "payment.sla.baselines.get"}:
        record = _sla(capability.endswith(".get"))
    else:
        raise ValueError(f"No payment data schema for {capability}")
    record["type"] = "object"
    record["x-evidence"]["type"] = "verified"
    result = (
        record
        if capability.endswith(".get")
        else {
            "type": "array",
            "items": record,
            "description": "Unprojected successful payment records.",
        }
    )
    if capability in {"payment.channel.list", "payment.cost.list"}:
        result["$defs"] = {"Money": _money()}
    if capability == "payment.cost.list":
        result["$defs"]["Ratio"] = _ratio()
    result["$schema"] = DIALECT
    result["title"] = capability
    result["x-annotation-vocabulary"] = {
        "x-evidence": {
            "dimensions": {
                "type": "Evidence for JSON type; only verified types constrain values.",
                "presence": "Presence evidence; observed does not mean required.",
                "nullability": "Nullability evidence; unknown remains open.",
                "unit": "Unit evidence; unknown prohibits inferred conversion.",
                "meaning": "Evidence for business interpretation.",
            },
            "values": {
                "verified": "Guaranteed by CLI behavior or explicit verification.",
                "observed": "Seen in documented samples, not a universal constraint.",
                "unknown": "Unresolved; no guarantee or semantic inference.",
                "not_applicable": "Dimension does not apply to this description.",
            },
        },
        "x-observed-type": "Observed JSON type only; not a validation assertion.",
        "x-observed-values": "Non-exhaustive observed values, never a closed enum.",
        "x-unit": "Unit name when explicitly verified; no automatic conversion.",
    }
    return result
