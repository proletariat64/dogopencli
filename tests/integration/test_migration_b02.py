"""Installed B02 packages: public CLI, synthetic native responses only."""

import json
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
LEAVES = {
    "risk.thresholds": (
        "/api/risk/benchmark/riskEventBenchmarkQuery.json",
        None,
        1000,
        "benchmarkId",
        None,
    ),
    "rules.realtime": ("/api/realtime/rule/getAll.json", None, 1000, "id", None),
    "rules.operation": (
        "/riskActionRuleListQuery.json",
        "riskActionRuleListQueryVO",
        1000,
        "ruleId",
        ("status", "ACTIVE", "INACTIVE"),
    ),
    "rules.fx_settlement": (
        "/fxBankAccountConfigQuery.json",
        "fxBankAccountPropertyConfigQueryVO",
        5000,
        "id",
        ("currency", "USD", "EUR"),
    ),
    "rules.funding": (
        "/fundRiskActionRelationQuery.json",
        "fundRiskActionRelationQueryVO",
        5000,
        "id",
        None,
    ),
    "rules.action_mapping": (
        "/clientAgreementConfigQuery.json",
        "clientAgreementConfigQueryVO",
        1000,
        "id",
        None,
    ),
}


def rows(identity):
    return [
        {
            identity: 0,
            "amount": Decimal("0.123456789012345678901"),
            "textAmount": "1.0000",
            "unknown": {"null": None, "false": False, "empty": "", "list": [0, "0"]},
            "currency": "USD",
            "ruleStatus": "ACTIVE",
        },
        {identity: "b", "currency": "EUR", "ruleStatus": "INACTIVE"},
        {identity: "c", "currency": "usd", "ruleStatus": "active"},
    ]


def page(leaf, records, total=None):
    total = len(records) if total is None else total
    if LEAVES[leaf][1]:
        body = {"resultFlag": True, "result": {"dataValue": records, "count": total}}
    else:
        body = {"success": True, "data": {"data": records, "totalCount": total}}
    return {"status": 200, "body": body}


@pytest.fixture(params=["directory", "zip"])
def source_format(request):
    return request.param


@pytest.fixture(params=LEAVES)
def installed(request, run_cli, tmp_path, monkeypatch, source_format):
    leaf = request.param
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    browser = FakeBrowser(href=LIQUIDITY_STARTUP_URL)
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        status, output, error = run_cli(list(args))
        assert status == code, output + error
        return parse(output)

    try:
        cli("domain", "enable", "liquidity")
        source = ROOT / "leaf_packages/liquidity" / leaf
        if source_format == "zip":
            package = tmp_path / "leaf.zip"
            with ZipFile(package, "w") as archive:
                for item in source.iterdir():
                    if item.is_file():
                        archive.write(item, item.name)
            source = package
        cli("plugins", "install", str(source))
        yield leaf, cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def test_native_records_live_refresh_offline_and_exact_request(installed):
    leaf, cli, browser, _ = installed
    _, vo, size, identity, _ = LEAVES[leaf]
    records = rows(identity)
    cli("liquidity", "list", leaf, "-h")
    cli("liquidity", "describe", leaf)
    assert not browser.business_requests
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(leaf, records))
    live = cli("liquidity", "list", leaf, "--live", "--limit", "0")
    assert live["data"] == records
    assert live["meta"]["complete"] is True
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"
    browser.business_script.append(page(leaf, records))
    assert cli("liquidity", "refresh", leaf, "--limit", "1")["data"]["row_count"] == 3
    count = len(browser.business_requests)
    assert cli("liquidity", "list", leaf, "--limit", "0")["data"] == records
    assert len(browser.business_requests) == count
    for request in browser.business_requests:
        if vo:
            assert set(request) == {"tntInstId", vo}
            assert request["tntInstId"] == "GUAPW3SG"
            assert json.loads(request[vo]) == {
                "tntInstId": "GUAPW3SG",
                "rowStart": 0,
                "pageSize": size,
            }
        else:
            expected = {"rowStart": 0, "pageSize": size}
            if leaf == "risk.thresholds":
                expected["tntInstId"] = "GUAPW3SG"
            assert request == expected


def test_all_offset_pages_precede_display_limit(installed):
    leaf, cli, browser, _ = installed
    _, vo, size, identity, _ = LEAVES[leaf]
    records = [{identity: n} for n in range(size + 1)]
    browser.business_script.extend(
        [page(leaf, records[:size], size + 1), page(leaf, records[size:], size + 1)]
    )
    result = cli("liquidity", "list", leaf, "--live", "--limit", "1")
    assert result["data"] == records[:1]
    assert result["meta"]["complete"] is True
    assert result["meta"]["collected_total"] == size + 1
    native = [
        json.loads(request[vo]) if vo else request
        for request in browser.business_requests
    ]
    assert [request["rowStart"] for request in native] == [0, size]


@pytest.mark.parametrize("bad", [None, "", "   ", True, {}, [], 1.5])
def test_invalid_native_identity_is_rejected(installed, bad):
    leaf, cli, browser, _ = installed
    identity = LEAVES[leaf][3]
    browser.business_script.append(page(leaf, [{identity: bad}]))
    assert (
        cli("liquidity", "list", leaf, "--live", code=1)["error"]["code"]
        == "INVALID_RESPONSE"
    )


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "business",
        "nested-business",
        "success-type",
        "shape",
        "missing-rows",
        "total-type",
        "total-bool",
        "total-negative",
        "changed-total",
        "early-empty",
        "overfull",
        "duplicate-strict",
        "conflict",
        "auth",
        "transport",
    ],
)
def test_rejected_refresh_preserves_records_and_capture(
    installed, failure, monkeypatch
):
    leaf, cli, browser, _ = installed
    _, vo, size, identity, _ = LEAVES[leaf]
    records = rows(identity)
    browser.business_script.append(page(leaf, records))
    cli("liquidity", "refresh", leaf)
    before = cli("liquidity", "list", leaf, "--limit", "0")
    expected, flags = "INVALID_RESPONSE", []
    response = page(leaf, records)
    container = response["body"]["result" if vo else "data"]
    if failure == "empty":
        response, expected = page(leaf, []), None
    elif failure == "business":
        response["body"]["resultFlag" if vo else "success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "nested-business":
        container["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "success-type":
        response["body"]["resultFlag" if vo else "success"] = 1
    elif failure == "shape":
        container["dataValue" if vo else "data"] = {}
    elif failure == "missing-rows":
        del container["dataValue" if vo else "data"]
    elif failure.startswith("total-"):
        container["count" if vo else "totalCount"] = {
            "total-type": "3",
            "total-bool": True,
            "total-negative": -1,
        }[failure]
    elif failure in {"changed-total", "early-empty"}:
        browser.business_script.append(
            page(leaf, [{identity: n} for n in range(size)], size + 1)
        )
        response = page(leaf, [], size + (2 if failure == "changed-total" else 1))
        if failure == "early-empty":
            expected = "INCOMPLETE_RESULT"
    elif failure == "overfull":
        response = page(leaf, [{identity: n} for n in range(size + 1)])
    elif failure == "duplicate-strict":
        response = page(leaf, [records[0], records[0]])
        expected, flags = "INCOMPLETE_RESULT", ["--require-complete"]
    elif failure == "conflict":
        response = page(leaf, [records[0], {**records[0], "amount": "different"}])
        expected = "INCOMPLETE_RESULT"
    elif failure == "auth":
        response, expected = {"status": 401, "body": {}}, "AUTH_REQUIRED"
    elif failure == "transport":
        monkeypatch.setattr("dogopencli.collect._sleep", lambda _: None)
        browser.business_script.extend([{"status": 503, "body": {}}] * 2)
        response, expected = {"status": 503, "body": {}}, "BUSINESS_QUERY_FAILED"
    browser.business_script.append(response)
    result = cli("liquidity", "refresh", leaf, *flags, code=1 if expected else 0)
    if expected:
        assert result["error"]["code"] == expected
    else:
        assert result["meta"]["published"] is False
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"] == records
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


def test_identical_duplicates_remain_incomplete(installed):
    leaf, cli, browser, _ = installed
    record = rows(LEAVES[leaf][3])[0]
    browser.business_script.append(page(leaf, [record, record]))
    result = cli("liquidity", "list", leaf, "--live", "--limit", "0")
    assert result["data"] == [record]
    assert result["meta"]["complete"] is False


def test_sdk_cross_page_conflict_keeps_last_arrival_and_prior_cache(installed):
    leaf, cli, browser, _ = installed
    _, vo, size, identity, _ = LEAVES[leaf]
    first = [{identity: n, "value": "original"} for n in range(size)]
    changed = {**first[0], "value": "changed"}
    browser.business_script.append(page(leaf, [first[0]]))
    cli("liquidity", "refresh", leaf)
    before = cli("liquidity", "list", leaf, "--limit", "0")

    def queue_conflict():
        browser.business_script.extend(
            [page(leaf, first, size + 1), page(leaf, [changed], size + 1)]
        )

    queue_conflict()
    partial = cli("liquidity", "list", leaf, "--live", "--limit", "0")
    assert partial["data"] == [changed, *first[1:]]
    assert partial["meta"]["complete"] is False
    assert partial["meta"]["duplicate_count"] == 1
    attempt = partial["meta"]["acquisition"]["attempts"][0]
    assert attempt["conflict_count"] == 1 and attempt["pages"] == 2
    assert "LAST_ARRIVAL_WINS" in attempt["reasons"]
    requests = browser.business_requests[-2:]
    native = [json.loads(item[vo]) if vo else item for item in requests]
    assert [item["rowStart"] for item in native] == [0, size]
    queue_conflict()
    strict = cli("liquidity", "list", leaf, "--live", "--require-complete", code=1)
    assert strict["error"]["code"] == "INCOMPLETE_RESULT"
    queue_conflict()
    rejected = cli("liquidity", "refresh", leaf, code=1)
    assert rejected["error"]["code"] == "INCOMPLETE_RESULT"
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


def test_sdk_short_interior_page_retains_explicit_partial_result(installed):
    leaf, cli, browser, _ = installed
    identity, size = LEAVES[leaf][3], LEAVES[leaf][2]
    first, last = {identity: 0}, {identity: size}
    browser.business_script.extend(
        [page(leaf, [first], size + 1), page(leaf, [last], size + 1)]
    )
    result = cli("liquidity", "list", leaf, "--live", "--limit", "0")
    assert result["data"] == [first, last]
    assert result["meta"]["complete"] is False
    assert "SHORT_NATIVE_PAGE" in result["meta"]["acquisition"]["reasons"]
    assert result["meta"]["reported_total"] == size + 1


@pytest.mark.parametrize("mutation", ["extra", "tenant", "size"])
def test_unverified_native_request_is_blocked(installed, tmp_path, mutation):
    import shutil

    leaf, cli, browser, _ = installed
    cli("plugins", "uninstall", "liquidity." + leaf)
    source = tmp_path / "mutated"
    shutil.copytree(ROOT / "leaf_packages/liquidity" / leaf, source)
    path = source / "adapter.py"
    code = path.read_text()
    start = code.index("    def page_body")
    head, tail = code[:start], code[start:]
    if mutation == "extra":
        tail = tail.replace(
            '"rowStart": row_start', '"unverified": True, "rowStart": row_start', 1
        )
    elif mutation == "tenant":
        if LEAVES[leaf][1] or leaf == "risk.thresholds":
            tail = tail.replace('"tntInstId": TENANT', '"tntInstId": "WRONG"')
        else:
            tail = tail.replace(
                '"rowStart": row_start',
                '"tntInstId": "GUAPW3SG", "rowStart": row_start',
                1,
            )
    else:
        tail = tail.replace('"pageSize": PAGE_SIZE', '"pageSize": 100', 1)
    path.write_text(head + tail)
    cli("plugins", "install", str(source))
    result = cli("liquidity", "list", leaf, "--live", code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests


def test_repeated_local_filters_and_full_scope_refresh(installed):
    leaf, cli, browser, _ = installed
    _, _, _, identity, local = LEAVES[leaf]
    if local is None:
        pytest.skip("leaf has no local selector")
    flag, first, second = local
    records = rows(identity)
    flags = ["--" + flag, first, "--" + flag, second, "--" + flag, first]
    browser.business_script.append(page(leaf, records))
    result = cli("liquidity", "list", leaf, "--live", "--limit", "0", *flags)
    assert result["data"] == records[:2]
    browser.business_script.append(page(leaf, records))
    assert (
        cli("liquidity", "refresh", leaf, "--" + flag, first)["data"]["row_count"] == 3
    )
    count = len(browser.business_requests)
    assert cli("liquidity", "list", leaf, "--limit", "0")["data"] == records
    assert cli("liquidity", "list", leaf, "--limit", "0", *flags)["data"] == records[:2]
    assert cli("liquidity", "list", leaf, "--limit", "0", "--" + flag, second)[
        "data"
    ] == [records[1]]
    assert len(browser.business_requests) == count


DETAILS = {
    "rules.operation": (
        "/riskActionRuleDetail.json",
        "GET",
        "query",
        "ruleId",
        "ruleId",
    ),
    "rules.realtime": ("/api/realtime/rule/getDetail.json", "POST", "json", "Id", "id"),
    "risk.thresholds": (
        "/api/risk/benchmark/riskEventBenchmarkDetailDetail.json",
        "POST",
        "form",
        "benchmarkId",
        "benchmarkId",
    ),
}


def detail_response(leaf, record):
    body = (
        {"resultFlag": True, "result": {"data": record}}
        if leaf == "rules.operation"
        else {"success": True, "data": record}
    )
    return {"status": 200, "body": body}


def test_native_detail_preserves_types_exact_request_and_saved_list(installed):
    leaf, cli, browser, _ = installed
    if leaf not in DETAILS:
        pytest.skip("list only")
    endpoint, method, encoding, request_key, echo = DETAILS[leaf]
    records = rows(echo)
    browser.business_script.append(page(leaf, records))
    cli("liquidity", "refresh", leaf)
    before = cli("liquidity", "list", leaf, "--limit", "0")
    detail = {
        **records[0],
        "detailOnly": [
            True,
            None,
            {"decimal": Decimal("123456789.123456789123456789")},
        ],
    }
    browser.business_script.append(detail_response(leaf, detail))
    result = cli("liquidity", "get", leaf, "0")
    assert result["data"] == detail
    expected = {request_key: "0"}
    if leaf == "rules.operation":
        expected["tntInstId"] = "GUAPW3SG"
    assert browser.business_requests[-1] == expected
    expressions = [
        expression
        for transport in browser.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    expression = expressions[-1]
    assert endpoint in expression
    assert method in expression
    if encoding == "form":
        assert "application/x-www-form-urlencoded" in expression
    elif encoding == "json":
        assert "application/json" in expression
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


@pytest.mark.parametrize("bad", [None, True, {}, [], "", "   ", "wrong", 0.5])
def test_native_detail_rejects_invalid_echo_without_storage(installed, bad):
    leaf, cli, browser, _ = installed
    if leaf not in DETAILS:
        pytest.skip("list only")
    echo = DETAILS[leaf][4]
    browser.business_script.append(detail_response(leaf, {echo: bad}))
    assert (
        cli("liquidity", "get", leaf, "0", code=1)["error"]["code"]
        == "INVALID_RESPONSE"
    )
    assert cli("liquidity", "list", leaf, code=1)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize(
    "failure",
    ["business", "success-type", "missing", "container", "missing-id", "auth"],
)
def test_native_detail_failures_preserve_saved_capture(installed, failure):
    leaf, cli, browser, _ = installed
    if leaf not in DETAILS:
        pytest.skip("list only")
    identity = LEAVES[leaf][3]
    browser.business_script.append(page(leaf, rows(identity)))
    cli("liquidity", "refresh", leaf)
    before = cli("liquidity", "list", leaf, "--limit", "0")
    response = detail_response(leaf, {identity: 0})
    expected = "INVALID_RESPONSE"
    if failure == "business":
        response["body"]["resultFlag" if leaf == "rules.operation" else "success"] = (
            False
        )
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "success-type":
        response["body"]["resultFlag" if leaf == "rules.operation" else "success"] = (
            "true"
        )
    elif failure in {"missing", "container", "missing-id"}:
        response = detail_response(
            leaf,
            {"missing": 0}
            if failure == "missing-id"
            else ([] if failure == "container" else None),
        )
    else:
        response, expected = {"status": 401, "body": {}}, "AUTH_REQUIRED"
    browser.business_script.append(response)
    assert cli("liquidity", "get", leaf, "0", code=1)["error"]["code"] == expected
    after = cli("liquidity", "list", leaf, "--limit", "0")
    assert after["data"] == before["data"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]
