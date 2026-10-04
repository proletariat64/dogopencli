"""Issue #89 discovery and refusal through the public CLI, without CDP."""

import sqlite3
from pathlib import Path

import pytest

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

TARGETS = [
    ("investment", "benchmark-values", ("valueDate", "timeZone", "unit")),
    ("pricing", "valuations", ("fee-order", "semantics", "naming")),
    ("pricing", "bills", ("DEPOSIT", "currency", "period")),
]


@pytest.fixture
def disconnected_batch_c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache = tmp_path / "cache.sqlite3"
    with sqlite3.connect(cache) as connection:
        connection.execute("CREATE TABLE previous_capture (value TEXT)")
        connection.execute("INSERT INTO previous_capture VALUES ('preserve')")
    config = tmp_path / "config.toml"
    config.write_text(
        f'[cache]\npath = "{cache}"\n'
        f'[auth]\nprofile = "{tmp_path / "profile"}"\n'
        'cdp_url = "http://127.0.0.1:9222"\n'
        '[sources.liquidity]\nkind = "cdp"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))

    def reject_browser(*args, **kwargs):
        pytest.fail("unreleased batch C command contacted CDP")

    cdp.set_transport_factory(reject_browser)
    try:
        yield cache, cache.read_bytes()
    finally:
        cdp.set_transport_factory(None)


@pytest.mark.parametrize("group,leaf,missing", TARGETS)
@pytest.mark.parametrize("command", ["help", "describe"])
def test_batch_c_discovery_explains_first_release_evidence(
    disconnected_batch_c, run_cli, group, leaf, missing, command
):
    cache, before = disconnected_batch_c
    code, out, err = run_cli([command, "liquidity", group, leaf, "list"])
    assert code == 0, err
    document = parse(out)
    if command == "help":
        assert document["kind"] == "runtimes"
        assert document["errors"] == ["UNSUPPORTED_CAPABILITY"]
        assert document["effects"]["network"] is False
        assert document["effects"]["browser_required"] is False
        reason = document["summary"]
    else:
        guide = document["read_guide"]
        assert guide["kind"] == "runtimes"
        assert guide["release_status"] == "deferred"
        assert (
            guide["evidence_status"]
            == {
                "benchmark-values": "identity-unavailable",
                "valuations": "naming-conflict",
                "bills": "empty-scope",
            }[leaf]
        )
        assert not document["data_schema"].get("properties")
        reason = guide["reason"]
    for term in (*missing, "#89", "non-empty", "complete", "UAT"):
        assert term in reason
    assert cache.read_bytes() == before


@pytest.mark.parametrize("group,leaf,missing", TARGETS)
@pytest.mark.parametrize("mode", ["cached", "live", "strict", "refresh"])
def test_batch_c_refuses_execution_and_preserves_previous_cache(
    disconnected_batch_c, run_cli, group, leaf, missing, mode
):
    cache, before = disconnected_batch_c
    args = ["liquidity", group, leaf, "list"]
    if mode == "refresh":
        args = ["refresh", "liquidity", group, leaf]
    elif mode == "live":
        args += ["--live"]
    elif mode == "strict":
        args += ["--require-complete"]
    code, out, _ = run_cli(args)
    document = parse(out)
    assert code in (1, 2)
    assert document["data"] is None
    if mode == "cached":
        assert document["error"]["code"] == "UNSUPPORTED_CAPABILITY"
        assert document["error"]["retryable"] is False
    else:
        assert document["error"]["code"] in (
            "INVALID_ARGUMENT",
            "UNSUPPORTED_CAPABILITY",
        )
    assert cache.read_bytes() == before
