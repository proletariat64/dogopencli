"""Execute the handbook's standard leaf against fake CDP and real local stores."""

import json
import runpy
import shutil
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse
from dogopencli.leaves.package import validate_package

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools/leaf-dev/example"
ROWS = [
    {
        "id": "one",
        "amount": "0.1234567890123456789",
        "extra": {"native": True, "rate": Decimal("0.1234567890123456789")},
    },
    {"id": "two", "amount": "2.00"},
    {"id": "three", "amount": "3.00"},
]


def page(rows, *, number=0, total=None, success=True):
    return {
        "status": 200,
        "body": {
            "success": success,
            "rows": rows,
            "pageNo": number,
            "pageSize": 2,
            "total": len(rows) if total is None else total,
        },
    }


def queue_full(browser):
    browser.business_script.extend(
        [page(ROWS[:2], total=3), page(ROWS[2:], number=1, total=3)]
    )


@pytest.fixture(params=["directory", "zip"])
def handbook(request, run_cli, tmp_path, monkeypatch, capsys):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    # Every session and fetch is fake; integration conftest also blocks sockets
    # and process launches. No manual authentication or network is required.
    browser = FakeBrowser(href="https://leaf-handbook.invalid/app")
    cdp.set_transport_factory(browser.transport)
    try:
        source = SOURCE
        helper = runpy.run_path(str(ROOT / "tools/leaf-dev/leaf.py"))["main"]

        def helper_cli(*args):
            monkeypatch.setattr("sys.argv", ["plugin_helper.py", *map(str, args)])
            assert helper() == 0
            return json.loads(capsys.readouterr().out)

        assert helper_cli("verify", source)["state"] == "verified"
        if request.param == "zip":
            source = tmp_path / "delivery/collection.sample.records.zip"
            assert (
                helper_cli("pack", SOURCE, "--output", source.parent)["state"]
                == "packed"
            )
            assert helper_cli("verify", source)["state"] == "verified"

        def cli(*args, code=0):
            result, output, error = run_cli(list(args))
            assert result == code, output + error
            return parse(output)

        cli("plugins", "install", str(source))
        assert browser.business_requests == []
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def test_handbook_end_to_end(handbook):
    cli, browser, config = handbook
    for args in (
        ("collection", "-h"),
        ("collection", "list", "-h"),
        ("collection", "list", "sample.records", "-h"),
        ("collection", "describe", "sample.records"),
        ("plugins", "list"),
    ):
        cli(*args)
    assert browser.business_requests == []
    assert not (config / "leaf-cache.sqlite3").exists()
    miss = cli("collection", "list", "sample.records", code=1)
    assert miss["error"]["code"] == "CACHE_MISS"

    queue_full(browser)
    live = cli("collection", "list", "sample.records", "--live", "--limit", "0")
    assert live["data"] == ROWS and live["meta"]["complete"] is True
    assert browser.business_requests == [
        {"scope": "all", "pageNo": 0, "pageSize": 2},
        {"scope": "all", "pageNo": 1, "pageSize": 2},
    ]
    assert cli("collection", "list", "sample.records", code=1)["error"]["code"] == (
        "CACHE_MISS"
    )
    queue_full(browser)
    refreshed = cli(
        "collection", "refresh", "sample.records", "--limit", "1", "--fields", "id"
    )
    assert refreshed["data"]["row_count"] == 3
    assert refreshed["meta"]["published"] is True
    before = len(browser.business_requests)
    cached = cli("collection", "list", "sample.records", "--limit", "0")
    assert cached["data"] == ROWS
    assert len(browser.business_requests) == before
    with duckdb.connect(str(config / "duckdog.duckdb"), read_only=True) as db:
        assert db.execute(
            "SELECT count(*) FROM collection_sample_records"
        ).fetchone() == (0,)
    cli("plugins", "uninstall", "collection.sample.records")
    assert (
        cli("plugins", "uninstall", "collection.sample.records")["data"]["removed"]
        is False
    )


@pytest.mark.parametrize(
    "failure", ["empty", "business", "shape", "identity", "strict", "auth"]
)
def test_handbook_failed_refresh_preserves_full_snapshot(handbook, failure):
    cli, browser, _ = handbook
    queue_full(browser)
    cli("collection", "refresh", "sample.records")
    before = cli("collection", "list", "sample.records", "--limit", "0")
    flags = []
    expected = None
    if failure == "empty":
        response = page([])
    elif failure == "business":
        response, expected = page([], success=False), "BUSINESS_QUERY_FAILED"
    elif failure == "shape":
        response, expected = page([{"amount": "1"}]), "INVALID_RESPONSE"
    elif failure == "identity":
        response = page([ROWS[0], {"id": "one", "amount": "different"}])
        # Opted-in SDK retains the last row, but rejects incomplete refresh.
        expected = "INCOMPLETE_RESULT"
    elif failure == "strict":
        response = page([ROWS[0], ROWS[0]])
        expected = "INCOMPLETE_RESULT"
        flags = ["--require-complete"]
    else:
        response, expected = {"status": 401, "body": {}}, "AUTH_REQUIRED"
    browser.business_script.append(response)
    result = cli(
        "collection", "refresh", "sample.records", *flags, code=1 if expected else 0
    )
    if expected:
        assert result["error"]["code"] == expected
    else:
        assert result["meta"]["published"] is False
    after = cli("collection", "list", "sample.records", "--limit", "0")
    assert after["data"] == before["data"] == ROWS
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


def test_handbook_resource_is_loaded_from_installed_snapshot(handbook, tmp_path):
    cli, browser, _ = handbook
    cli("plugins", "uninstall", "collection.sample.records")
    source = tmp_path / "resource-source"
    shutil.copytree(SOURCE, source)
    (source / "resources").mkdir()
    (source / "resources/scope.txt").write_text("all\n")
    adapter = source / "adapter.py"
    adapter.write_text(
        "from pathlib import Path\n"
        + adapter.read_text().replace(
            'return "all"',
            'return (Path(__file__).parent / "resources/scope.txt")'
            ".read_text().strip()",
        )
    )
    cli("plugins", "install", str(source))
    shutil.rmtree(source)
    queue_full(browser)
    result = cli("collection", "list", "sample.records", "--live", "--limit", "0")
    assert result["data"] == ROWS


def test_handbook_bare_sibling_import_is_not_a_package_loader(handbook, tmp_path):
    cli, browser, config = handbook
    cli("plugins", "uninstall", "collection.sample.records")
    source = tmp_path / "module-source"
    shutil.copytree(SOURCE, source)
    (source / "handbook_sibling_unique.py").write_text("VALUE = 'all'\n")
    adapter = source / "adapter.py"
    adapter.write_text("import handbook_sibling_unique\n" + adapter.read_text())
    with validate_package(source):
        pass  # Static package checks deliberately do not import Python code.
    result = cli("plugins", "install", str(source), code=1)
    assert result["error"]["code"] == "INVALID_LEAF"
    assert not (config / "plugins/collection/sample.records").exists()
    assert browser.business_requests == []


def test_handbook_request_allowlist_rejects_extra_field(handbook, tmp_path):
    cli, browser, _ = handbook
    cli("plugins", "uninstall", "collection.sample.records")
    source = tmp_path / "invalid-request-source"
    shutil.copytree(SOURCE, source)
    adapter = source / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            'return {"scope": scope,', 'return {"unverified": True, "scope": scope,'
        )
    )
    cli("plugins", "install", str(source))
    result = cli("collection", "list", "sample.records", "--live", code=1)
    assert result["error"]["code"] == "REQUEST_NOT_ALLOWED"
    assert browser.business_requests == []
