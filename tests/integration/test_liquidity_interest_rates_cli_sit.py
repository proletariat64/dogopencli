"""Four-source interest inquiries through public CLI and synthetic CDP."""

import copy

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]
ROOT = ["liquidity", "investment", "interest-rates"]
BOUNDS = ["--from-date", "2026-01-01", "--to-date", "2026-01-02"]


def market():
    return {
        "currency": "USD",
        "rateName": "SYN-RATE",
        "ratePeriod": "O/N",
        "effectiveDate": "2026-01-01",
        "rateValue": "-0.1234500",
    }


def page(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {"data": rows, "totalCount": len(rows) if total is None else total},
        },
    }


def test_market_prefix_and_legacy_source_preserve_wire_and_values(setup, run_cli):
    setup.state.business_handler = lambda payload, index: page([market()])
    for args in (
        [*ROOT, "--source", "market", "list", *BOUNDS, "--live"],
        [*ROOT, "list", "--source", "market", *BOUNDS, "--live"],
        [*ROOT, "--source=market", "list", "--source", "market", *BOUNDS, "--live"],
    ):
        code, out, err = run_cli(args)
        assert code == 0, err
        result = parse(out)
        assert result["data"] == [market()]
        assert result["meta"]["kind"] == "runtimes"
        assert setup.state.business_requests[-1]["beginDate"] == "20260101"


def test_source_conflicts_and_invalid_sources_make_no_requests(setup, run_cli):
    for args in (
        [*ROOT, "--source", "market", "list", "--source", "bank", "--live", *BOUNDS],
        [*ROOT, "list", "--source", "unknown", "--live"],
        [*ROOT, "list", "--live"],
    ):
        code, out, _ = run_cli(args)
        assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


def bank(identity="SYN-BANK", product="SYN-PRODUCT"):
    return {
        "bankId": identity,
        "currency": "USD",
        "productTerm": "O/N",
        "productType": product,
        "quoteDate": "20260101",
        "rateValue": "-0.0002500",
        "gmtModified": None,
        "maxPurchaseAmount": "",
        "inquiryAmount": "0",
    }


def test_bank_rows_are_not_group_total_and_strict_preserves_slot(setup, run_cli):
    setup.state.business_handler = lambda payload, index: page([market()])
    assert run_cli(["refresh", *ROOT, "--source", "market", *BOUNDS])[0] == 0
    before = setup.cache_path.read_bytes()
    rows = [bank(product="SYN-A"), bank(product="SYN-B")]
    setup.state.business_handler = lambda payload, index: page(rows, 2)
    args = [*ROOT, "--source", "bank", "list", *BOUNDS, "--live", "--limit", "0"]
    code, out, err = run_cli(args)
    assert code == 0, err
    result = parse(out)
    assert result["data"] == rows
    assert result["meta"]["reported_total"] == 2
    assert result["meta"]["collected_total"] == 2
    assert result["meta"]["complete"] is False
    assert result["meta"]["acquisition"]["total_semantics"] == "quote_date_groups"
    assert setup.state.business_requests[-1]["beginDate"] == "2026-01-01"
    code, out, _ = run_cli(
        ["refresh", *ROOT, "--source", "bank", *BOUNDS, "--require-complete"]
    )
    assert code == 1 and parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before


def test_source_switch_offline_metadata_empty_failure_and_no_live_write(setup, run_cli):
    setup.state.business_handler = lambda payload, index: page([market()])
    assert run_cli(["refresh", *ROOT, "--source", "market", *BOUNDS])[0] == 0
    setup.state.business_handler = lambda payload, index: page([bank()], 1)
    code, out, err = run_cli(["refresh", *ROOT, "--source", "bank", *BOUNDS])
    assert code == 0, err
    saved = parse(out)
    assert saved["meta"]["rate_source"] == "bank"
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli([*ROOT, "list"])
    assert code == 0, err
    assert parse(out)["data"] == [bank()]
    assert parse(out)["meta"]["rate_source"] == "bank"
    assert parse(out)["meta"]["kind"] == "runtimes"
    code, out, _ = run_cli([*ROOT, "list", "--source", "market"])
    assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    for answer in (page([], 0), {"status": 401, "body": {"success": False}}):
        setup.state.business_handler = lambda payload, index, answer=answer: answer
        run_cli(["refresh", *ROOT, "--source", "bank", *BOUNDS])
        assert setup.cache_path.read_bytes() == before
    setup.state.business_handler = lambda payload, index: page([market()])
    assert run_cli([*ROOT, "list", "--source", "market", *BOUNDS, "--live"])[0] == 0
    assert setup.cache_path.read_bytes() == before


def rule(category, identity="SYN-RULE"):
    return {
        "ruleId": identity,
        "ruleStatus": "INVALID",
        "ruleValue": "-0.0025000",
        "rateCategory": category,
        "currency": "USD",
        "effectiveDate": "20260101",
        "expireDate": "21260101",
        "version": "1",
    }


def test_rule_sources_settings_native_templates_and_single_slot(setup, run_cli):
    for source, category in (
        ("expectation-rule", "CUSTOMER_TYPE"),
        ("expection", "FINANCIAL_INST_TYPE"),
    ):
        rows = [rule(category)]
        setup.state.business_handler = lambda payload, index, rows=rows: page(rows)
        code, out, err = run_cli(["refresh", *ROOT, "--source", source])
        assert code == 0, err
        assert parse(out)["meta"]["kind"] == "settings"
        body = setup.state.business_requests[-1]
        assert body["rateCategory"] == category
        assert "source" not in body
        assert body["rowStart"] == 0 and body["pageSize"] == 1000
        if source == "expectation-rule":
            assert body["beginDate"] == body["endDate"] == ""
            assert body["currentArea"] == "1" and body["timeZone"] == "GMT+08"
        else:
            assert body["ruleStatus"] == ""
            assert "beginDate" not in body and "tntInstId" not in body
        code, out, err = run_cli([*ROOT, "list"])
        assert code == 0, err
        result = parse(out)
        assert result["data"] == rows
        assert result["meta"]["rate_source"] == source
        assert result["meta"]["kind"] == "settings"
        code, out, _ = run_cli([*ROOT, "--source", source, "list", *BOUNDS, "--live"])
        assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"


def external_detail():
    return {
        **rule("FINANCIAL_INST_TYPE"),
        "approveState": "SYN-APPROVED",
        "customizedMarketRateName": "SYN-NAME",
        "effectDateList": {"20260101": "-0.0025000"},
        "expectedRateProvider": "SYN-PROVIDER",
        "financialInstFiles": [],
        "financialInstFilesMap": {"SYN-FILE": {"name": "synthetic"}},
        "gmtCreate": "20260101",
        "gmtModify": None,
        "lastOperator": "SYN-OPERATOR",
        "oldIncrementFinancialRateRuleDetail": {
            "ruleValue": "",
            "effectDateList": None,
        },
        "operationLogDetailList": [{"operation": "SYN-LOG", "value": "0"}],
        "operator": "SYN-OPERATOR",
        "processId": None,
        "rateBasicType": "SYN-TYPE",
        "ratePeriod": "O/N",
        "rateProvideCode": "SYN-CODE",
        "rateType": "SYN-TYPE",
        "reason": "SYNTHETIC TEST",
        "ruleType": "SYN-FIXED",
    }


def test_external_get_preserves_all_nested_fields_and_query_identity(setup, run_cli):
    record = external_detail()
    assert len(record) == 27
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": record},
    }
    code, out, err = run_cli(
        [*ROOT, "--source", "expection", "get", "--id", "SYN-RULE"]
    )
    assert code == 0, err
    assert parse(out)["data"] == record
    assert parse(out)["meta"]["rate_source"] == "expection"
    assert parse(out)["meta"]["kind"] == "settings"
    assert not setup.cache_path.exists()
    expressions = [
        e for t in setup.state.transports for e in t.expressions if "fetch(" in e
    ]
    assert len(expressions) == 1
    assert "queryFinancialInstRateRuleDetail.json" in expressions[0]
    assert "URLSearchParams(payload)" in expressions[0]
    assert 'method: "POST"' in expressions[0]
    assert 'body: ""' in expressions[0]
    assert setup.state.business_requests == [
        {"id": "SYN-RULE", "_output_charset": "utf-8"}
    ]


def test_other_get_sources_refused_and_missing_source_invalid_without_requests(
    setup, run_cli
):
    for source in ("market", "bank", "expectation-rule"):
        code, out, _ = run_cli([*ROOT, "--source", source, "get", "--id", "SYN-RULE"])
        assert code == 1 and parse(out)["error"]["code"] == "UNSUPPORTED_CAPABILITY"
    code, out, _ = run_cli([*ROOT, "get", "--id", "SYN-RULE"])
    assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


def test_bank_group_paging_complete_products_and_boundary_overlap(setup, run_cli):
    from datetime import date, timedelta

    days = [(date(2026, 1, 2) - timedelta(days=i)).isoformat() for i in range(1001)]
    rows = [
        dict(bank(product=p), quoteDate=d.replace("-", ""))
        for d in days
        for p in ("SYN-A", "SYN-B")
    ]
    setup.state.business_handler = lambda payload, index: page(
        rows[payload["rowStart"] * 2 : (payload["rowStart"] + 1000) * 2], 1001
    )
    bounds = ["--from-date", days[-1], "--to-date", days[0]]
    args = [*ROOT, "--source", "bank", "list", *bounds, "--live", "--limit", "0"]
    code, out, err = run_cli([*args, "--require-complete"])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == rows
    assert result["meta"]["complete"] is True
    assert result["meta"]["reported_total"] == 1001
    assert result["meta"]["collected_total"] == 2002
    assert result["meta"]["missing_count"] is None
    assert [body["rowStart"] for body in setup.state.business_requests] == [0, 1000]
    setup.state.business_requests.clear()
    setup.state.business_handler = lambda payload, index: page(rows[:2000], 1001)
    code, out, err = run_cli(args)
    assert code == 0 and parse(out)["meta"]["complete"] is False
    assert len(parse(out)["data"]) == 2000
    assert "BANK_GROUP_OVERLAP" in parse(out)["meta"]["acquisition"]["reasons"]


def test_describe_exposes_each_source_kind_identity_and_raw_units(setup, run_cli):
    code, out, _ = run_cli(["describe", *ROOT, "list"])
    assert code == 0
    variants = parse(out)["read_guide"]["variants"]
    assert {item["selectors"]["source"]: item["kind"] for item in variants} == {
        "market": "runtimes",
        "bank": "runtimes",
        "expectation-rule": "settings",
        "expection": "settings",
    }
    for item in variants:
        value = "ruleValue" if item["kind"] == "settings" else "rateValue"
        assert (
            item["data_schema"]["properties"][value]["x-unit"]
            == "unknown; raw value preserved"
        )
    code, out, _ = run_cli(["describe", *ROOT, "get"])
    assert code == 0
    description = parse(out)
    assert set(description["data_schema"]["properties"]) == set(external_detail())
    assert description["read_guide"]["rate_source"] == "expection"
    assert setup.state.transports == []


@pytest.mark.parametrize("source", ["market", "bank", "expectation-rule", "expection"])
@pytest.mark.parametrize(
    "argument", ["missing", "unknown", "conflict", "date", "timezone"]
)
def test_invalid_source_arguments_do_not_open_browser(setup, run_cli, source, argument):
    flags = ["--source", source]
    extra = []
    if argument == "missing":
        flags = []
    elif argument == "unknown":
        flags = ["--source", "expectation"]
    elif argument == "conflict":
        extra = ["--source", "bank" if source != "bank" else "market"]
    elif argument == "date":
        extra = ["--from-date", "2026-02-30", "--to-date", "2026-01-01"]
    else:
        extra = ["--timezone", "GMT-08"]
    code, out, _ = run_cli([*ROOT, *flags, "list", "--live", *extra])
    assert code == 2 and parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []


@pytest.mark.parametrize(
    "defect",
    ["identity", "category", "tenant", "refusal", "container", "missing-success"],
)
def test_external_detail_hard_failures_never_fallback_or_write(setup, run_cli, defect):
    setup.state.business_handler = lambda payload, index: page(
        [rule("FINANCIAL_INST_TYPE")]
    )
    assert run_cli(["refresh", *ROOT, "--source", "expection"])[0] == 0
    before = setup.cache_path.read_bytes()
    record = external_detail()
    body = {"success": True, "data": record}
    if defect == "identity":
        record["ruleId"] = "SYN-OTHER"
    elif defect == "category":
        record["rateCategory"] = "CUSTOMER_TYPE"
    elif defect == "tenant":
        record["tntInstId"] = "SYN-OTHER-TENANT"
    elif defect == "refusal":
        body["success"] = False
    elif defect == "container":
        body["data"] = [record]
    else:
        del body["success"]
    setup.state.business_handler = lambda payload, index: {"status": 200, "body": body}
    code, out, _ = run_cli([*ROOT, "--source", "expection", "get", "--id", "SYN-RULE"])
    assert code == 1 and parse(out)["data"] is None
    assert setup.cache_path.read_bytes() == before


def test_external_get_and_projection_do_not_change_saved_list(setup, run_cli):
    rows = [rule("FINANCIAL_INST_TYPE", "SYN-A"), rule("FINANCIAL_INST_TYPE", "SYN-B")]
    setup.state.business_handler = lambda payload, index: page(rows)
    assert run_cli(["refresh", *ROOT, "--source", "expection"])[0] == 0
    assert len(setup.state.business_requests) == 1
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(
        [*ROOT, "list", "--fields", "ruleValue", "--limit", "1", "--offset", "1"]
    )
    assert code == 0, err
    result = parse(out)
    assert result["data"] == [{"ruleValue": "-0.0025000"}]
    assert result["meta"]["rate_source"] == "expection"
    assert result["meta"]["collected_total"] == 2
    assert result["meta"]["returned_count"] == 1
    record = external_detail()
    record["financialInstFilesMap"] = None
    record["oldIncrementFinancialRateRuleDetail"] = None
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {"success": True, "data": record},
    }
    code, out, err = run_cli(
        [*ROOT, "--source", "expection", "get", "--id", "SYN-RULE"]
    )
    assert code == 0, err
    assert parse(out)["data"] == record
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize(
    "dates", [["2026-01-01", "2026-01-02"], ["20260101", "20260102"]]
)
def test_bank_iso_request_compact_native_response_and_offline_filter(
    setup, run_cli, dates
):
    setup.state.business_handler = lambda payload, index: page([bank()], 1)
    args = [
        "refresh",
        *ROOT,
        "--source",
        "bank",
        "--from-date",
        dates[0],
        "--to-date",
        dates[1],
    ]
    code, out, err = run_cli(args)
    assert code == 0, err
    assert setup.state.business_requests[-1]["beginDate"] == "2026-01-01"
    assert setup.state.business_requests[-1]["endDate"] == "2026-01-02"
    code, out, err = run_cli([*ROOT, "list", "--source", "bank", *BOUNDS])
    assert code == 0, err
    assert parse(out)["data"] == [bank()]
    assert parse(out)["meta"]["complete"] is True


@pytest.mark.parametrize(
    "defect", ["identity", "total-change", "order", "scope", "empty"]
)
def test_bank_collection_failures_preserve_slot_and_partial_is_honest(
    setup, run_cli, defect
):
    from datetime import date, timedelta

    setup.state.business_handler = lambda payload, index: page([market()])
    assert run_cli(["refresh", *ROOT, "--source", "market", *BOUNDS])[0] == 0
    before = setup.cache_path.read_bytes()
    dates = [
        (date(2026, 1, 2) - timedelta(days=i)).strftime("%Y%m%d") for i in range(1001)
    ]
    rows = [dict(bank(), quoteDate=day) for day in dates]

    def answer(payload, index):
        native = copy.deepcopy(rows[payload["rowStart"] : payload["rowStart"] + 1000])
        total = 1001
        if defect == "identity":
            native.append({**native[0], "rateValue": "conflict"})
        elif defect == "total-change" and payload["rowStart"]:
            total = 1002
        elif defect == "order":
            native.reverse()
        elif defect == "scope":
            native[0]["quoteDate"] = "20300101"
        elif defect == "empty" and payload["rowStart"]:
            native = []
        return page(native, total)

    setup.state.business_handler = answer
    bounds = ["--from-date", dates[-1], "--to-date", dates[0]]
    code, out, _ = run_cli(
        ["refresh", *ROOT, "--source", "bank", *bounds, "--require-complete"]
    )
    assert code == 1 and parse(out)["data"] is None
    assert setup.cache_path.read_bytes() == before
    if defect in ("order", "empty"):
        code, out, err = run_cli([*ROOT, "--source", "bank", "list", *bounds, "--live"])
        assert code == 0 and parse(out)["meta"]["complete"] is False
        assert "INCOMPLETE_RESULT" in err


@pytest.mark.parametrize("source", ["market", None, "bank"])
def test_legacy_market_saved_source_requires_trustworthy_identity(
    setup, run_cli, source
):
    from dogopencli.cache import Cache
    from dogopencli.result_policy import AcquisitionEvidence
    from dogopencli.temporary_query import publish_slot

    query = {"beginDate": "20260101", "endDate": "20260102", "timeZone": "GMT+08"}
    if source is not None:
        query["source"] = source
    publish_slot(
        Cache(setup.cache_path),
        "liquidity.investment.interest-rates",
        [market()],
        capability="liquidity.investment.interest-rates.list",
        scope=query,
        evidence=AcquisitionEvidence.for_collection(
            complete=True, reported_total=1, collected_total=1
        ),
        fetched_at="2026-01-01T00:00:00+00:00",
        variant="/incrementBaseRateList.json",
    )
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli([*ROOT, "list"])
    if source == "market":
        assert code == 0, err
        assert parse(out)["data"] == [market()]
    else:
        assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.state.transports == []
    assert setup.cache_path.read_bytes() == before
