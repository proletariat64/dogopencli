"""Issue #82 release refusal stays offline until native evidence exists."""

from pathlib import Path

import pytest

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse


@pytest.fixture
def disconnected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache = tmp_path / "cache.sqlite3"
    cache.write_bytes(b"previous capture must stay untouched")
    config = tmp_path / "config.toml"
    config.write_text(
        f'[cache]\npath = "{cache}"\n'
        f'[auth]\nprofile = "{tmp_path / "profile"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
        '[sources.liquidity]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))

    def reject_browser(*args, **kwargs):
        pytest.fail("deferred investable-funds command contacted CDP")

    cdp.set_transport_factory(reject_browser)
    yield cache, cache.read_bytes()
    cdp.set_transport_factory(None)


@pytest.mark.parametrize("command", ["help", "describe"])
def test_investable_funds_discovery_exposes_unresolved_release_gate(
    disconnected, run_cli, command
):
    cache, before = disconnected
    code, out, err = run_cli(
        [command, "liquidity", "investment", "investable-funds", "list"]
    )
    assert code == 0, err
    document = parse(out)
    if command == "help":
        assert document["kind"] == "runtimes"
        assert document["errors"] == ["UNSUPPORTED_CAPABILITY"]
        assert document["summary"]
        assert document["effects"]["network"] is False
        assert document["effects"]["browser_required"] is False
    else:
        guide = document["read_guide"]
        assert guide["kind"] == "runtimes"
        assert guide["release_status"] == "deferred"
        assert guide["evidence_status"] == "empty-scope"
        assert not document["data_schema"].get("properties")
        assert guide["reason"]
    assert cache.read_bytes() == before


def test_investable_funds_list_refuses_without_reading_or_replacing_cache(
    disconnected, run_cli
):
    cache, before = disconnected
    code, out, _ = run_cli(["liquidity", "investment", "investable-funds", "list"])
    envelope = parse(out)
    assert code == 1
    assert envelope["data"] is None
    assert envelope["error"]["code"] == "LEAF_DISABLED"
    assert envelope["error"]["retryable"] is False
    assert cache.read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        ["liquidity", "investment", "investable-funds", "list", "--live"],
        ["refresh", "liquidity", "investment", "investable-funds"],
        ["liquidity", "investment", "investable-funds", "get"],
    ],
)
def test_unreleased_investable_funds_live_refresh_and_get_cannot_execute(
    disconnected, run_cli, args
):
    cache, before = disconnected
    code, out, _ = run_cli(args)
    envelope = parse(out)
    assert code in (1, 2)
    assert envelope["data"] is None
    assert envelope["error"]["code"] in (
        "INVALID_ARGUMENT",
        "LEAF_DISABLED",
    )
    assert cache.read_bytes() == before
