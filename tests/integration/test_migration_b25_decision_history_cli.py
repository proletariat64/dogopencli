"""Installed decision history keeps native versions bound to current lineage."""

import shutil
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "leaf_packages/liquidity/operations.decisions.history"
FLAGS = ["--id", "123"]


def root(**extra):
    return {
        "id": 123,
        "reportId": "REPORT",
        "groupId": "GROUP",
        "tntInstId": "GUAPW3SG",
        "version": 9,
        **extra,
    }


def row(identity=9, **extra):
    return {
        **root(),
        "id": identity,
        "version": 2,
        "amount": Decimal("123.450000000000000000001"),
        "unknown": {"native": [None, False, ""]},
        **extra,
    }


def response(data):
    return {"status": 200, "body": {"success": True, "data": data}}


@pytest.fixture(params=["directory", "zip"])
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
        href="https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        result, output, error = run_cli(
            ["liquidity", action, "operations.decisions.history", *args]
        )
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


def test_native_versions_order_refresh_offline_and_exact_binding(installed):
    cli, browser, config = installed
    cli("list", "--help")
    cli("describe")
    assert not browser.transports
    versions = [row(9), row(2, version=1)]
    browser.business_script.extend([response(root()), response(versions)])
    live = cli("list", "--live", *FLAGS, "--require-complete", "--limit", "0")
    assert live["data"] == versions
    assert all(r["id"] != 123 for r in live["data"])
    assert live["meta"]["complete"] is True
    assert live["meta"]["acquisition"]["reported_total"] is None
    assert live["meta"]["acquisition"]["coverage_basis"] == "qualified_single_response"
    assert not (config / "leaf-cache.sqlite3").exists()
    assert browser.business_requests == [{"id": 123, "tntInstId": "GUAPW3SG"}] * 2
    expressions = [
        expression
        for transport in browser.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]
    for endpoint in ("getDetail.json", "getHistory.json"):
        assert sum(endpoint in expression for expression in expressions) == 1
    browser.business_script.extend([response(root()), response(versions)])
    saved = cli("refresh", *FLAGS, "--require-complete")
    assert saved["meta"]["published"] is True
    count = len(browser.business_requests)
    browser.running = False
    offline = cli("list", "--require-complete", "--limit", "0")
    assert offline["data"] == versions
    assert offline["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    assert len(browser.business_requests) == count


@pytest.mark.parametrize(
    "failure",
    [
        "root_id",
        "root_id_bool",
        "root_lineage",
        "root_tenant",
        "root_shape",
        "history_shape",
        "history_id",
        "history_version",
        "report",
        "group",
        "tenant",
        "duplicate",
        "business",
        "success_type",
        "auth",
    ],
)
def test_context_and_native_failures_keep_previous_snapshot(installed, failure):
    cli, browser, _ = installed
    versions = [row()]
    browser.business_script.extend([response(root()), response(versions)])
    saved = cli("refresh", *FLAGS, "--require-complete")
    current, history = response(root()), response([row(2)])
    expected = "INVALID_RESPONSE"
    if failure == "root_id":
        current["body"]["data"]["id"] = 124
    elif failure == "root_id_bool":
        current["body"]["data"]["id"] = True
    elif failure == "root_lineage":
        current["body"]["data"]["reportId"] = ""
    elif failure == "root_tenant":
        current["body"]["data"]["tntInstId"] = "OTHER"
    elif failure == "root_shape":
        current["body"]["data"] = []
    elif failure == "history_shape":
        history["body"]["data"] = {}
    elif failure == "history_id":
        history["body"]["data"][0]["id"] = "2"
    elif failure == "history_version":
        history["body"]["data"][0]["version"] = True
    elif failure in {"report", "group", "tenant"}:
        field = {"report": "reportId", "group": "groupId", "tenant": "tntInstId"}[
            failure
        ]
        history["body"]["data"][0][field] = "OTHER"
    elif failure == "duplicate":
        history["body"]["data"] = [row(2), row(2)]
    elif failure == "business":
        history["body"]["success"] = False
        expected = "BUSINESS_QUERY_FAILED"
    elif failure == "success_type":
        history["body"]["success"] = "true"
    elif failure == "auth":
        history = {"status": 401, "body": {}}
        expected = "AUTH_REQUIRED"
    browser.business_script.extend([current, history])
    before = len(browser.business_requests)
    result = cli("refresh", *FLAGS, "--require-complete", code=1)
    assert result["error"]["code"] == expected
    assert result["meta"]["published"] is False
    assert len(browser.business_requests) - before == (
        1 if failure.startswith("root_") else 2
    )
    assert cli("list")["data"] == versions
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_empty_history_does_not_append_current_or_replace_saved_capture(installed):
    cli, browser, _ = installed
    browser.business_script.extend([response(root()), response([row()])])
    saved = cli("refresh", *FLAGS, "--require-complete")
    browser.business_script.extend([response(root()), response([])])
    live = cli("list", "--live", *FLAGS, "--require-complete", "--limit", "0")
    assert live["data"] == [] and live["meta"]["complete"] is True
    browser.business_script.extend([response(root()), response([])])
    refreshed = cli("refresh", *FLAGS, "--require-complete")
    assert refreshed["meta"]["published"] is False
    assert cli("list")["data"] == [row()]
    assert cli("list")["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize("flags", [[], ["--id", "not-a-number"], ["--id", "1.5"]])
def test_required_integer_scope_is_validated_before_browser(installed, flags):
    cli, browser, _ = installed
    assert cli("list", "--live", *flags, code=2)["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.transports


def test_undeclared_request_field_rejected_before_business_fetch(
    installed, run_cli, tmp_path
):
    cli, browser, _ = installed
    code, output, error = run_cli(
        ["plugins", "uninstall", "liquidity.operations.decisions.history"]
    )
    assert code == 0, output + error
    source = tmp_path / "badrequest"
    shutil.copytree(SOURCE, source)
    path = source / "adapter.py"
    text = path.read_text()
    original = 'return {"tntInstId": TENANT, "id": selected}'
    assert original in text
    path.write_text(text.replace(original, original[:-1] + ', "mutation": True}'))
    code, output, error = run_cli(["plugins", "install", str(source)])
    assert code == 0, output + error
    result = cli("list", "--live", *FLAGS, code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert not browser.business_requests
