"""Native page metadata survives the installed public CLI and saved replay."""

import json
import runpy
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = """from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.errors import BUSINESS_QUERY_FAILED, CliError
from dogopencli.jsonutil import parse

class Inquiry:
    name = "collection.sample.records.list"
    page_url = "https://leaf-handbook.invalid/app"
    contract = EndpointContract(
        method="POST", host="leaf-handbook.invalid", path="/records/query",
        page_size=2, allowed_page_sizes=(2, 1), one_based=False,
        allowed_body_keys=frozenset({"scope", "rowStart", "pageSize"}),
        fixed_body_values=(("scope", "all"),),
    )
    def page_body(self, scope, position, page_size):
        return {"scope": scope, "rowStart": position, "pageSize": page_size}
    def parse_rows(self, body):
        value = parse(body)
        if not value["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "rejected")
        return value["rows"], value["total"]
    def parse_metadata(self, body):
        return parse(body)["metadata"]
    def parse_page(self, body):
        value = parse(body)
        rows, total = self.parse_rows(body)
        return ParsedPage(rows, value["position"], value["page_size"], total,
                          -(-total // value["page_size"]))

class Adapter:
    def capability(self, parameters):
        return Inquiry()
    def scope(self, parameters):
        return "all"
    def filter(self, records, parameters):
        return records
adapter = Adapter()
"""


@pytest.fixture(params=["directory", "zip"])
def metadata_cli(
    request, paging_mode, include_metadata, run_cli, tmp_path, monkeypatch, capsys
):
    source = tmp_path / "source"
    shutil.copytree(ROOT / "tools/leaf-dev/example", source)
    manifest = json.loads((source / "leaf.json").read_text())
    del manifest["operations"]["get"]
    manifest["collection"]["paging"] = {"mode": "offset", "page_sizes": [2, 1]}
    if paging_mode == "short_page":
        manifest["collection"]["paging"]["termination"] = "short_page"
    elif paging_mode == "clamped":
        manifest["collection"]["paging"] = {
            "mode": "page_number",
            "page_sizes": [2, 1],
            "termination": "short_page",
        }
    elif paging_mode != "offset":
        manifest["collection"]["paging"] = {"mode": paging_mode, "page_sizes": [2]}
    (source / "leaf.json").write_text(json.dumps(manifest))
    adapter = ADAPTER
    if paging_mode == "clamped":
        adapter = adapter.replace("one_based=False", "one_based=True").replace(
            "class Adapter:",
            "    def pagination_terminal(self, page, requested):\n"
            "        return True\n\nclass Adapter:",
        )
    if paging_mode == "single_response":
        adapter = adapter.replace(
            'return value["rows"], value["total"]', 'return value["rows"], None'
        )
    if not include_metadata:
        adapter = adapter.replace("def parse_metadata(", "def unused_metadata(")
    (source / "adapter.py").write_text(adapter)
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    browser = FakeBrowser(href="https://leaf-handbook.invalid/app")
    cdp.set_transport_factory(browser.transport)

    def cli(*args, code=0):
        result, output, error = run_cli(list(args))
        assert result == code, output + error
        return parse(output)

    try:
        if request.param == "zip":
            helper = runpy.run_path(str(ROOT / "tools/leaf-dev/leaf.py"))["main"]
            monkeypatch.setattr(
                "sys.argv",
                [
                    "leaf.py",
                    "pack",
                    str(source),
                    "--output",
                    str(tmp_path / "delivery"),
                ],
            )
            assert helper() == 0
            capsys.readouterr()
            source = tmp_path / "delivery/collection.sample.records.zip"
        cli("plugins", "install", str(source))
        yield cli, browser
    finally:
        cdp.set_transport_factory(None)


@pytest.fixture
def paging_mode(request):
    return getattr(request, "param", "offset")


@pytest.fixture
def include_metadata(request):
    return getattr(request, "param", True)


def response(rows, total, metadata, position=0, page_size=2):
    return {
        "status": 200,
        "body": {
            "success": True,
            "rows": rows,
            "total": total,
            "metadata": metadata,
            "position": position,
            "page_size": page_size,
        },
    }


def clamped_responses(*, invalid_terminal=None):
    return [
        response(
            [{"id": "one"}, {"id": "two"}], 3, {"totalAmount": "first"}, position=1
        ),
        response([{"id": "three"}], 3, {"totalAmount": "last"}, position=2),
        response(
            [{"id": "three"}],
            3,
            []
            if invalid_terminal == 3
            else {"amount": Decimal("3.123456789012345678901")},
            position=2,
        ),
        response(
            [{"id": "three"}],
            3,
            [] if invalid_terminal == 4 else {"native": [None, False, "4.00"]},
            position=2,
        ),
    ]


@pytest.mark.parametrize("paging_mode", ["clamped"], indirect=True)
def test_numbered_clamped_terminal_metadata_is_kept_with_requested_positions(
    metadata_cli,
):
    cli, browser = metadata_cli
    browser.business_script.extend(clamped_responses())
    refreshed = cli("collection", "refresh", "sample.records")
    assert [body["rowStart"] for body in browser.business_requests] == [1, 2, 3, 4]
    expected = [
        {"position": 1, "page_size": 2, "metadata": {"totalAmount": "first"}},
        {"position": 2, "page_size": 2, "metadata": {"totalAmount": "last"}},
        {
            "position": 3,
            "page_size": 2,
            "metadata": {"amount": Decimal("3.123456789012345678901")},
        },
        {"position": 4, "page_size": 2, "metadata": {"native": [None, False, "4.00"]}},
    ]
    assert refreshed["meta"]["acquisition"]["native_metadata"] == expected
    assert refreshed["meta"]["complete"] is True
    assert (
        refreshed["meta"]["acquisition"]["attempts"][-1]["termination_reason"]
        == "two_clamped_batches"
    )
    saved = cli("collection", "list", "sample.records", "--limit", "0")
    assert saved["data"] == [{"id": "one"}, {"id": "two"}, {"id": "three"}]
    assert saved["meta"]["source_acquisition"]["native_metadata"] == expected
    assert saved["meta"]["acquisition"]["native_metadata"] == expected


@pytest.mark.parametrize("paging_mode", ["clamped"], indirect=True)
@pytest.mark.parametrize("invalid_terminal", [3, 4])
def test_invalid_clamped_terminal_metadata_preserves_previous_capture(
    metadata_cli, invalid_terminal
):
    cli, browser = metadata_cli
    browser.business_script.extend(clamped_responses())
    cli("collection", "refresh", "sample.records")
    before = cli("collection", "list", "sample.records", "--limit", "0")
    browser.business_script.extend(clamped_responses(invalid_terminal=invalid_terminal))
    rejected = cli("collection", "refresh", "sample.records", code=1)
    assert rejected["error"]["code"] == "INVALID_RESPONSE"
    after = cli("collection", "list", "sample.records", "--limit", "0")
    assert after["data"] == before["data"]
    assert after["meta"]["source_acquisition"] == before["meta"]["source_acquisition"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]


def test_live_retains_native_metadata_for_each_page(metadata_cli):
    cli, browser = metadata_cli
    browser.business_script.extend(
        [
            response(
                [{"id": "one"}, {"id": "two"}],
                3,
                {
                    "totalAmount": "10.0000",
                    "nested": [None, False, Decimal("0.123456789012345678901")],
                },
            ),
            response([{"id": "three"}], 3, {"totalAmount": 12, "currency": None}),
        ]
    )
    result = cli("collection", "list", "sample.records", "--live", "--limit", "0")
    assert result["data"] == [{"id": "one"}, {"id": "two"}, {"id": "three"}]
    assert result["meta"]["acquisition"]["native_metadata"] == [
        {
            "position": 0,
            "page_size": 2,
            "metadata": {
                "totalAmount": "10.0000",
                "nested": [None, False, Decimal("0.123456789012345678901")],
            },
        },
        {
            "position": 2,
            "page_size": 2,
            "metadata": {"totalAmount": 12, "currency": None},
        },
    ]
    assert (
        cli("collection", "list", "sample.records", code=1)["error"]["code"]
        == "CACHE_MISS"
    )


def test_refresh_offline_and_live_keep_metadata_with_its_capture(metadata_cli):
    cli, browser = metadata_cli
    browser.business_script.append(
        response(
            [{"id": "saved"}],
            1,
            {
                "totalAmount": Decimal("123456789.1234567890123456789"),
                "native": {"items": [2, None, "2.00"]},
            },
        )
    )
    refreshed = cli("collection", "refresh", "sample.records")
    saved = cli("collection", "list", "sample.records", "--limit", "0")
    assert saved["meta"]["source_acquisition"]["native_metadata"] == [
        {
            "position": 0,
            "page_size": 2,
            "metadata": {
                "totalAmount": Decimal("123456789.1234567890123456789"),
                "native": {"items": [2, None, "2.00"]},
            },
        }
    ]
    assert (
        saved["meta"]["acquisition"]["native_metadata"]
        == refreshed["meta"]["acquisition"]["native_metadata"]
    )
    browser.business_script.append(
        response([{"id": "live"}], 1, {"totalAmount": "different"})
    )
    live = cli("collection", "list", "sample.records", "--live")
    assert live["meta"]["acquisition"]["native_metadata"][0]["metadata"] == {
        "totalAmount": "different"
    }
    after = cli("collection", "list", "sample.records", "--limit", "0")
    assert after["data"] == saved["data"]
    assert after["meta"]["source_acquisition"] == saved["meta"]["source_acquisition"]
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


@pytest.mark.parametrize(
    "paging_mode", ["page_number", "single", "single_response"], indirect=True
)
def test_other_standard_paging_modes_retain_metadata(metadata_cli):
    cli, browser = metadata_cli
    browser.business_script.append(
        response([{"id": "one"}], 1, {"totalAmount": "10.00"})
    )
    cli("collection", "refresh", "sample.records")
    saved = cli("collection", "list", "sample.records")
    assert saved["meta"]["source_acquisition"]["native_metadata"] == [
        {"position": 0, "page_size": 2, "metadata": {"totalAmount": "10.00"}}
    ]


@pytest.mark.parametrize("include_metadata", [False], indirect=True)
def test_absent_hook_preserves_existing_envelope(metadata_cli):
    cli, browser = metadata_cli
    browser.business_script.append(response([{"id": "one"}], 1, {"unused": True}))
    refreshed = cli("collection", "refresh", "sample.records")
    saved = cli("collection", "list", "sample.records")
    assert "native_metadata" not in refreshed["meta"]["acquisition"]
    assert "native_metadata" not in saved["meta"]["source_acquisition"]


@pytest.mark.parametrize("paging_mode", ["short_page"], indirect=True)
def test_short_page_acquisition_retains_successful_native_page_metadata(metadata_cli):
    cli, browser = metadata_cli
    browser.business_script.extend(
        [
            response([{"id": "one"}, {"id": "two"}], 0, {"totalAmount": "10.00"}),
            response([], 0, {"terminal": "first"}),
            response([], 0, {"terminal": "second"}),
        ]
    )
    from dogopencli.progress import observe

    progress = {}
    with observe(lambda facts: progress.update(facts)):
        result = cli("collection", "refresh", "sample.records")
    assert progress["source_pages"] == 3
    assert progress["source_rows_received"] == 2
    assert progress["source_total_rows"] is None
    assert result["meta"]["acquisition"]["native_metadata"] == [
        {"position": 0, "page_size": 2, "metadata": {"totalAmount": "10.00"}},
        {"position": 2, "page_size": 2, "metadata": {"terminal": "first"}},
        {"position": 4, "page_size": 2, "metadata": {"terminal": "second"}},
    ]


def test_width_fallback_discards_rejected_candidate_metadata(metadata_cli):
    cli, browser = metadata_cli
    browser.business_script.extend(
        [
            response([{"id": "one"}], 2, {"totalAmount": "rejected-width"}),
            response([{"id": "one"}], 2, {"totalAmount": "accepted-first"}),
            response([{"id": "two"}], 2, {"totalAmount": "accepted-second"}),
        ]
    )
    from dogopencli.progress import observe

    progress = {}
    with observe(lambda facts: progress.update(facts)):
        result = cli("collection", "refresh", "sample.records")
    assert progress["candidate"] == 2
    assert progress["request_attempts"] == 2
    assert progress["source_pages"] == 2
    assert progress["source_rows_received"] == 2
    assert progress["source_total_rows"] == 2
    assert result["meta"]["acquisition"]["native_metadata"] == [
        {"position": 0, "page_size": 1, "metadata": {"totalAmount": "accepted-first"}},
        {"position": 1, "page_size": 1, "metadata": {"totalAmount": "accepted-second"}},
    ]
    saved = cli("collection", "list", "sample.records", "--limit", "0")
    assert (
        saved["meta"]["source_acquisition"]["native_metadata"]
        == result["meta"]["acquisition"]["native_metadata"]
    )


@pytest.mark.parametrize("failure", ["empty", "business", "incomplete", "metadata"])
def test_rejected_refresh_preserves_rows_metadata_and_capture_time(
    metadata_cli, failure
):
    cli, browser = metadata_cli
    browser.business_script.append(
        response([{"id": "saved"}], 1, {"totalAmount": "saved"})
    )
    cli("collection", "refresh", "sample.records")
    saved = cli("collection", "list", "sample.records", "--limit", "0")
    if failure == "empty":
        browser.business_script.append(response([], 0, {"totalAmount": "empty"}))
        rejected = cli("collection", "refresh", "sample.records")
        assert rejected["meta"]["published"] is False
    else:
        if failure == "business":
            browser.business_script.append({"status": 200, "body": {"success": False}})
            expected = "BUSINESS_QUERY_FAILED"
        elif failure == "incomplete":
            browser.business_script.extend(
                [
                    response([], 1, {"totalAmount": "bad-first-width"}),
                    response([], 1, {"totalAmount": "bad-second-width"}),
                ]
            )
            expected = "INCOMPLETE_RESULT"
        else:
            browser.business_script.append(response([{"id": "bad"}], 1, []))
            expected = "INVALID_RESPONSE"
        rejected = cli(
            "collection", "refresh", "sample.records", "--require-complete", code=1
        )
        assert rejected["error"]["code"] == expected
    after = cli("collection", "list", "sample.records", "--limit", "0")
    assert after["data"] == saved["data"]
    assert after["meta"]["source_acquisition"] == saved["meta"]["source_acquisition"]
    assert after["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
