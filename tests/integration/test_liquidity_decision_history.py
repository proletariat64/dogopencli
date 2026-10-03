"""Decision history keeps native versions and verifies their source lineage."""

from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

LIQUIDITY_URL = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
QUERY = ["liquidity", "operations", "decisions", "history", "--id", "7"]
REFRESH = [
    "refresh",
    "liquidity",
    "operations",
    "decisions",
    "detail",
    "history",
    "--id",
    "7",
]


@pytest.fixture
def history_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[cache]\n"
        f'path = "{tmp_path / "cache.sqlite3"}"\n'
        "ttl_hours = 72\n"
        "[auth]\n"
        f'profile = "{tmp_path / "chrome-profile"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
        "[sources.liquidity]\n"
        'kind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config_path))
    state = FakeBrowser(href=LIQUIDITY_URL)
    cdp.set_transport_factory(state.transport)
    yield state
    cdp.set_transport_factory(None)


def parent():
    return {
        "id": 7,
        "reportId": "report-a",
        "groupId": "group-a",
        "tntInstId": "GUAPW3SG",
    }


def versions():
    return [dict(parent(), id=6, version=2), dict(parent(), id=5, version=1)]


def script(state, rows, current=None):
    from collections import deque

    state.business_script = deque(
        {"status": 200, "body": {"success": True, "data": data}}
        for data in (parent() if current is None else current, rows)
    )


def test_history_live_refresh_offline_keeps_native_versions(history_source, run_cli):
    state = history_source
    rows = versions()
    script(state, rows)
    code, out, err = run_cli([*QUERY, "--live"])
    assert code == 0, err
    result = parse(out)
    assert result["data"] == rows
    assert result["meta"]["complete"] is True
    assert result["meta"]["returned_count"] == 1  # One native history document.
    assert len(state.business_requests) == 2
    assert all(request == {"id": 7} for request in state.business_requests)
    expressions = [
        expression
        for transport in state.transports
        for expression in transport.expressions
    ]
    assert any("getDetail.json" in expression for expression in expressions)
    assert any("getHistory.json" in expression for expression in expressions)
    code, out, _ = run_cli(QUERY)
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    script(state, rows)
    code, out, err = run_cli(REFRESH)
    assert code == 0, err
    published = parse(out)

    def disconnected(url):
        raise AssertionError("offline history contacted CDP")

    cdp.set_transport_factory(disconnected)
    code, out, err = run_cli(QUERY)
    assert code == 0, err
    result = parse(out)
    assert result["data"] == rows
    assert result["meta"]["snapshot_id"] == published["meta"]["snapshot_id"]


@pytest.mark.parametrize("field", ["reportId", "groupId", "tntInstId"])
@pytest.mark.parametrize("value", [None, "", "unrelated", 1, True])
def test_history_rejects_unrelated_or_untyped_lineage(
    history_source, run_cli, field, value
):
    rows = versions()
    rows[1][field] = value
    script(history_source, rows)
    code, out, _ = run_cli(REFRESH)
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    code, out, _ = run_cli(QUERY)
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize("rows", [None, {}, [1], [None], [{"id": 6}]])
def test_history_rejects_malformed_native_documents(history_source, run_cli, rows):
    script(history_source, rows)
    code, out, _ = run_cli([*QUERY, "--live"])
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"


@pytest.mark.parametrize("field", ["id", "version"])
@pytest.mark.parametrize("value", [None, "1", True])
def test_history_version_identity_remains_typed(history_source, run_cli, field, value):
    rows = versions()
    rows[0][field] = value
    script(history_source, rows)
    code, out, _ = run_cli([*QUERY, "--live"])
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"


def test_history_empty_native_list_is_valid(history_source, run_cli):
    script(history_source, [])
    code, out, err = run_cli([*QUERY, "--live"])
    assert code == 0, err
    assert parse(out)["data"] == []
    assert len(history_source.business_requests) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 8),
        ("id", "7"),
        ("reportId", ""),
        ("groupId", None),
        ("tntInstId", "OTHER"),
    ],
)
def test_history_rejects_invalid_sibling_before_history_request(
    history_source, run_cli, field, value
):
    current = parent()
    current[field] = value
    script(history_source, versions(), current)
    code, out, _ = run_cli([*QUERY, "--live"])
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert len(history_source.business_requests) == 1


def test_failed_history_refresh_retains_previous_native_document(
    history_source, run_cli
):
    rows = versions()
    script(history_source, rows)
    code, out, err = run_cli(REFRESH)
    assert code == 0, err
    snapshot = parse(out)["meta"]["snapshot_id"]
    broken = versions()
    broken[0]["reportId"] = "different-report"
    script(history_source, broken)
    code, out, _ = run_cli(REFRESH)
    assert code == 1 and parse(out)["error"]["code"] == "INVALID_RESPONSE"
    code, out, err = run_cli(QUERY)
    assert code == 0, err
    result = parse(out)
    assert result["data"] == rows
    assert result["meta"]["snapshot_id"] == snapshot


def test_history_corrected_contract_does_not_read_legacy_objects(
    history_source, tmp_path, run_cli
):
    from dogopencli.cache import Cache
    from dogopencli.plugins.liquidity import details
    from dogopencli.plugins.liquidity.leaves import detail_leaf

    detail = detail_leaf(("operations", "decisions", "history")).spec
    details.upsert_detail(
        Cache(tmp_path / "cache.sqlite3"),
        detail.name,
        details.detail_key({"id": "7"}, detail.identity),
        parent(),
        "2026-10-03T00:00:00+00:00",
        "2026-10-03T00:00:00+00:00",
    )
    code, out, _ = run_cli(QUERY)
    assert code == 1 and parse(out)["error"]["code"] == "CACHE_MISS"
    assert history_source.business_requests == []
