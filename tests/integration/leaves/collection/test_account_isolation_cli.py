"""opening-rule List through installed CLI and synthetic native responses."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAF = "account_isolation"
SOURCE = ROOT / "leaf_packages/collection" / LEAF


def row(identity="1000000000000000001", **values):
    return {
        "id": identity,
        "businessCategory": None,
        "businessRegionScope": "GLOBAL",
        "customerTags": "A,B",
        "sceneCode": "SCENE",
        "creditArea": "SG",
        "currency": "USD,EUR",
        "regionType": "CROSS_BORDER",
        "amount": Decimal("0.123456789012345678901"),
        "extension": {"zero": 0, "values": [None, False, "", "1.0000"]},
        **values,
    }


def page(rows, total=None, **echo):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "businessDataList": rows,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": len(rows) if total is None else total,
                "totalPageNo": 0,
                **echo,
            },
        },
    }


@pytest.fixture(params=["directory"])
def installed(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for key in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(key, raising=False)
    browser = FakeBrowser(
        href="https://ifundcontrol.alipay.com/productOperation/collectionProductManagement/networkConstruction/businessAccount"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        result, output, error = run_cli(["collection", action, LEAF, *args])
        assert result == code, output + error
        return parse(output)

    try:
        source = tmp_path / "source"
        shutil.copytree(SOURCE, source)
        if request.param == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(source))
            source = archive_path
        result, output, error = run_cli(["plugins", "install", str(source)])
        assert result == 0, output + error
        if request.param == "directory":
            shutil.rmtree(source)
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_native_values_live_refresh_offline_and_static_help(installed):
    cli, browser, config = installed
    cli("list", "-h")
    cli("describe")
    assert not browser.transports
    assert cli("list", code=1)["error"]["code"] == "CACHE_MISS"
    rows = [row("2"), row("10")]
    browser.business_script.append(page(rows))
    live = cli("list", "--live", "--require-complete", "--limit", "0")
    assert live["data"] == sorted(rows, key=lambda item: item["id"])
    assert live["meta"]["complete"] is True
    assert not (config / "leaf-cache.sqlite3").exists()
    browser.business_script.append(page(rows))
    refreshed = cli("refresh", "--require-complete")
    calls = len(browser.business_requests)
    saved = cli("list", "--limit", "0")
    assert saved["data"] == live["data"]
    assert saved["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert len(browser.business_requests) == calls
    assert browser.business_requests == [{"pageNo": 0, "pageSize": 1000}] * 2
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert all(
        "https://ifundcontrolprodops.alipay.com/api/virtualAccountRuleConfig/search"
        in e
        and 'method: "POST"' in e
        and "application/json" in e
        for e in expressions
    )


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (["--currency", "USD"], []),
        (["--currency", "USD,EUR"], ["1"]),
        (["--customer-group", "A"], []),
        (["--customer-group", "A,B"], ["1", "2"]),
        (["--currency", "*"], ["3"]),
        (["--currency", "usd"], []),
        (
            ["--currency", "USD,EUR", "--currency", "JPY", "--scene-code", "OTHER"],
            ["2"],
        ),
        (["--business-line", "None"], []),
        (["--opening-rule-id", "1", "--collection-region", "SG"], ["1"]),
    ],
)
def test_filters_are_exact_local_or_and_before_projection(installed, flags, expected):
    cli, browser, _ = installed
    rows = [
        row("1"),
        row("2", currency="JPY", sceneCode="OTHER"),
        row("3", currency="*", customerTags="OTHER"),
    ]
    browser.business_script.append(page(rows))
    cli("refresh", "--require-complete")
    result = cli("list", *flags, "--limit", "0", "--fields", "id")
    assert result["data"] == [{"id": value} for value in expected]
    assert browser.business_requests == [{"pageNo": 0, "pageSize": 1000}]


@pytest.mark.parametrize(
    "flag",
    [
        "opening-rule-id",
        "business-line",
        "business-region",
        "customer-group",
        "scene-code",
        "collection-region",
        "currency",
        "transaction-type",
    ],
)
def test_blank_local_filter_refuses_before_browser(installed, flag):
    cli, browser, _ = installed
    result = cli("list", "--live", "--" + flag, " ", code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


@pytest.mark.parametrize(
    "failure",
    [
        "auth",
        "business",
        "marker",
        "data",
        "null_rows",
        "bad_row",
        "id_missing",
        "id_number",
        "id_blank",
        "page",
        "size",
        "bool_total",
        "negative_total",
        "bad_pages",
        "duplicate",
        "short",
        "capacity",
    ],
)
def test_rejected_refresh_preserves_saved_capture(installed, failure):
    cli, browser, _ = installed
    original = [row()]
    browser.business_script.append(page(original))
    before = cli("refresh", "--require-complete")
    candidate = page([row("OTHER")])
    data = candidate["body"]["data"]
    expected = "INVALID_RESPONSE"
    if failure == "auth":
        candidate = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    elif failure == "business":
        candidate["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "marker":
        candidate["body"]["success"] = 1
    elif failure == "data":
        candidate["body"]["data"] = []
    elif failure == "null_rows":
        data["businessDataList"] = None
    elif failure == "bad_row":
        data["businessDataList"] = [None]
    elif failure == "id_missing":
        data["businessDataList"] = [{}]
    elif failure == "id_number":
        data["businessDataList"] = [row(123)]
    elif failure == "id_blank":
        data["businessDataList"] = [row(" ")]
    elif failure == "page":
        data["pageNo"] = 1
    elif failure == "size":
        data["pageSize"] = 10
    elif failure == "bool_total":
        data["totalCount"] = True
    elif failure == "negative_total":
        data["totalCount"] = -1
    elif failure == "bad_pages":
        data["totalPageNo"] = True
    elif failure == "duplicate":
        candidate = page([row("X"), row("X")])
        expected = "INCOMPLETE_RESULT"
    elif failure == "short":
        data["totalCount"] = 2
        expected = "INCOMPLETE_RESULT"
    else:
        candidate = page([row(str(i)) for i in range(1000)], 1001)
        expected = "INCOMPLETE_RESULT"
    browser.business_script.append(candidate)
    failed = cli("refresh", "--require-complete", code=1)
    assert failed["error"]["code"] == expected
    assert failed["meta"]["published"] is False
    after = cli("list", "--limit", "0")
    assert after["data"] == original
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


@pytest.mark.parametrize("count", [0, 1000])
def test_native_empty_and_exact_capacity_with_placeholder_pages(installed, count):
    cli, browser, _ = installed
    rows = [row(str(i)) for i in range(count)]
    browser.business_script.append(page(rows))
    result = cli("list", "--live", "--limit", "0", "--require-complete")
    assert len(result["data"]) == count
    assert result["meta"]["complete"] is True
    assert browser.business_requests == [{"pageNo": 0, "pageSize": 1000}]


def test_request_allowlist_refuses_business_filter_before_fetch(
    installed, run_cli, tmp_path
):
    cli, browser, _ = installed
    result, output, error = run_cli(
        ["plugins", "uninstall", "collection.account_isolation"]
    )
    assert result == 0, output + error
    source = tmp_path / "unverified-request"
    shutil.copytree(SOURCE, source)
    adapter = source / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            'return {"pageNo": 0, "pageSize": PAGE_SIZE}',
            'return {"pageNo": 0, "pageSize": PAGE_SIZE, "currency": "USD"}',
        )
    )
    result, output, error = run_cli(["plugins", "install", str(source)])
    assert result == 0, output + error
    rejected = cli("list", "--live", code=1)
    assert rejected["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests
