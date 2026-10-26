# ruff: noqa: F811
"""New leaf behavior through the public CLI and scripted CDP boundary."""

import json
from pathlib import Path

from test_leaf_pilots_cli import pilots  # noqa: F401


def test_legacy_leaf_paths_are_detached(run_cli):
    code, output, _ = run_cli(["payment", "sla", "baselines", "list"])
    assert code == 2
    assert json.loads(output)["error"]["code"] == "INVALID_ARGUMENT"


def test_install_is_explicit_and_default_list_is_offline(
    run_cli, tmp_path, monkeypatch
):
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(tmp_path))
    for identity in (
        "payment.sla.baselines",
        "collection.cost",
        "liquidity.reference.entities",
        "fx.trade",
    ):
        code, output, _ = run_cli(["plugins", "install", "bundled:" + identity])
        assert code == 0, output
    code, output, _ = run_cli(["plugins", "list"])
    assert (
        len(
            [
                row
                for row in json.loads(output)["data"]["plugins"]
                if row["state"] == "installed"
            ]
        )
        == 4
    )
    code, output, _ = run_cli(["payment", "list", "sla.baselines"])
    assert code == 1
    assert json.loads(output)["error"]["code"] == "CACHE_MISS"


def page(rows, *, success=True):
    return {
        "status": 200,
        "body": {
            "success": success,
            "pageNo": 0,
            "pageSize": 10000,
            "totalCount": len(rows),
            "resultDataList": rows,
        },
    }


def test_refresh_preserves_full_candidate_and_empty_failure_leave_saved_capture(
    run_cli, pilots
):
    rows = [
        {"id": "1", "status": "ACTIVE", "native": "0.1000"},
        {"id": "2", "status": "OFFLINE", "native": "0.2000"},
    ]
    pilots.business_script.append(page(rows))
    code, out, _ = run_cli(
        ["payment", "refresh", "sla.baselines", "--limit", "1", "--fields", "id"]
    )
    assert code == 0
    assert json.loads(out)["meta"]["published"] is True
    assert json.loads(out)["data"]["row_count"] == 2
    requests = list(pilots.business_requests)
    code, out, _ = run_cli(["payment", "list", "sla.baselines", "--limit", "0"])
    assert code == 0
    saved = json.loads(out)
    assert saved["data"] == rows
    assert pilots.business_requests == requests
    pilots.business_script.append(page([]))
    code, out, _ = run_cli(["payment", "refresh", "sla.baselines"])
    assert code == 0 and json.loads(out)["meta"]["published"] is False
    pilots.business_script.append(page([], success=False))
    code, out, _ = run_cli(["payment", "refresh", "sla.baselines"])
    assert code == 1 and json.loads(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
    code, out, _ = run_cli(["payment", "list", "sla.baselines", "--limit", "0"])
    assert json.loads(out)["data"] == rows
    assert json.loads(out)["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_live_prune_domain_gate_formats_and_offline_filters(run_cli, pilots):
    rows = [{"id": "1", "status": "ACTIVE"}, {"id": "2", "status": "OFFLINE"}]
    pilots.business_script.append(page(rows))
    assert run_cli(["payment", "list", "sla.baselines", "--live"])[0] == 0
    code, out, _ = run_cli(["payment", "list", "sla.baselines"])
    assert json.loads(out)["error"]["code"] == "CACHE_MISS"
    pilots.business_script.append(page(rows))
    assert run_cli(["payment", "refresh", "sla.baselines"])[0] == 0
    code, out, _ = run_cli(["payment", "list", "sla.baselines", "--status", "ACTIVE"])
    assert code == 0 and json.loads(out)["data"] == rows[:1]
    code, out, _ = run_cli(
        ["payment", "list", "sla.baselines", "--biz-legal-entity", "X"]
    )
    assert code == 2 and json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert run_cli(["payment", "list", "sla.baselines", "--format", "table"])[0] == 2
    code, out, _ = run_cli(["payment", "list", "sla.baselines", "--format", "text"])
    assert code == 0
    assert out.startswith("-\n  id: 1\n  status: ACTIVE\n")
    assert "\nMetadata:\n" in out
    assert "\n  source: cache\n" in out
    assert run_cli(["domain", "disable", "payment"])[0] == 0
    before = list(pilots.business_requests)
    code, out, _ = run_cli(["payment", "list", "sla.baselines", "--live"])
    assert json.loads(out)["error"]["code"] == "DOMAIN_DISABLED"
    assert pilots.business_requests == before
    assert run_cli(["domain", "enable", "payment"])[0] == 0
    assert run_cli(["payment", "prune", "sla.baselines"])[0] == 0
    assert run_cli(["payment", "prune", "sla.baselines"])[0] == 0
    code, out, _ = run_cli(["payment", "list", "sla.baselines"])
    assert json.loads(out)["error"]["code"] == "CACHE_MISS"


def test_stale_strict_and_domain_observations(run_cli, pilots, monkeypatch):
    path = Path(__import__("os").environ["DOGOPENCLI_CONFIG"])
    path.write_text(path.read_text() + "\n[cache]\nttl_hours=0\n")
    pilots.business_script.append(page([{"id": "1", "status": "ACTIVE"}]))
    assert run_cli(["payment", "refresh", "sla.baselines"])[0] == 0
    code, out, _ = run_cli(["payment", "list", "sla.baselines"])
    assert code == 0 and json.loads(out)["meta"]["stale"] is True
    code, out, _ = run_cli(["payment", "list", "sla.baselines", "--require-fresh"])
    assert code == 1 and json.loads(out)["error"]["code"] == "CACHE_STALE"
    _, help_output, _ = run_cli(["payment", "list", "sla.baselines", "-h"])
    assert "CACHE_STALE" in json.loads(help_output)["data"]["errors"]
    _, inventory, _ = run_cli(["domain", "leaves", "payment"])
    observed = json.loads(inventory)["result"]
    assert observed[0]["id"] == "payment.sla.baselines"
    assert observed[0]["last_execution"]["error_code"] == "CACHE_STALE"
    assert run_cli(["payment", "prune", "sla.baselines"])[0] == 0
    _, inventory, _ = run_cli(["domain", "leaves", "payment"])
    assert (
        json.loads(inventory)["result"][0]["last_execution"]
        == observed[0]["last_execution"]
    )


def test_describe_rejects_removed_json_alias(run_cli, pilots):
    code, out, _ = run_cli(["fx", "describe", "trade", "--json"])
    assert code == 2
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_effective_scope_is_saved_and_adapter_updates_require_refresh(run_cli, pilots):
    pilots.business_script.append(page([{"id": "saved", "status": "ACTIVE"}]))
    code, out, _ = run_cli(
        ["payment", "refresh", "sla.baselines", "--status", "ACTIVE"]
    )
    assert code == 0, out
    live = json.loads(out)
    assert live["meta"]["scope"] == {"status": "ACTIVE"}
    code, out, _ = run_cli(["payment", "list", "sla.baselines"])
    assert code == 0 and json.loads(out)["meta"]["scope"] == live["meta"]["scope"]
    path = Path(__import__("os").environ["DOGOPENCLI_CONFIG"]).parent
    adapter = path / "plugins/payment/sla.baselines/adapter.py"
    adapter.write_text(adapter.read_text() + "\n# replacement contract\n")
    code, out, _ = run_cli(["payment", "list", "sla.baselines"])
    assert code == 1 and json.loads(out)["error"]["code"] == "CACHE_CONTRACT_CHANGED"


def test_registry_contention_is_retryable(run_cli, pilots):
    import fcntl
    import os

    path = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    with (path / "leaf-registry.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        code, out, _ = run_cli(["payment", "prune", "sla.baselines"])
    assert code == 1
    assert json.loads(out)["error"]["code"] == "LOCKED"
    assert json.loads(out)["error"]["retryable"] is True


def test_native_get_missing_declared_identity_is_rejected(run_cli, pilots):
    import os

    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    adapter = root / "plugins/payment/sla.baselines/adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            "return parse_detail(response.body, identity)", "return {}"
        )
    )
    pilots.business_script.append(
        {"status": 200, "body": {"success": True, "resultData": {}}}
    )
    code, out, _ = run_cli(["payment", "get", "sla.baselines", "101"])
    assert code == 1
    assert json.loads(out)["data"] is None
    assert json.loads(out)["error"]["code"] == "INVALID_RESPONSE"


def test_qualified_partial_refresh_replaces_capture_unless_strict(run_cli, pilots):
    from test_leaf_pilots_cli import native_page, native_row

    saved_row = native_row("collection", "saved")
    pilots.business_script.append(native_page("collection", [saved_row]))
    code, out, _ = run_cli(["collection", "refresh", "cost", "--require-complete"])
    assert code == 0 and json.loads(out)["meta"]["published"] is True
    _, out, _ = run_cli(["collection", "list", "cost"])
    saved = json.loads(out)
    partial = native_page("collection", [native_row("collection", "partial")])
    partial["body"]["totalCount"] = 1001
    pilots.business_script.append(partial)
    code, out, err = run_cli(["collection", "list", "cost", "--live"])
    assert code == 0 and "INCOMPLETE_RESULT" in err
    assert json.loads(out)["meta"]["complete"] is False
    pilots.business_script.append(partial)
    code, out, _ = run_cli(["collection", "refresh", "cost", "--require-complete"])
    assert code == 1 and json.loads(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert json.loads(out)["meta"]["published"] is False
    _, out, _ = run_cli(["collection", "list", "cost"])
    assert json.loads(out)["data"] == saved["data"]
    assert json.loads(out)["meta"]["fetched_at"] == saved["meta"]["fetched_at"]
    pilots.business_script.append(partial)
    code, out, _ = run_cli(["collection", "refresh", "cost"])
    refreshed = json.loads(out)
    assert code == 0 and refreshed["meta"]["published"] is True
    assert refreshed["meta"]["complete"] is False
    _, out, _ = run_cli(["collection", "list", "cost"])
    replay = json.loads(out)
    assert replay["data"] == [native_row("collection", "partial")]
    assert replay["meta"]["acquisition"] == refreshed["meta"]["acquisition"]
    assert replay["meta"]["warnings"] == refreshed["meta"]["warnings"]


def test_display_formats_preserve_native_decimal_and_string_types(run_cli, pilots):
    from decimal import Decimal

    for output_format in ["json", "text"]:
        pilots.business_script.append(
            page(
                [
                    {
                        "id": "1",
                        "fraction": Decimal("0.1234567890123456789"),
                        "nativeString": "0.1000",
                    }
                ]
            )
        )
        code, out, _ = run_cli(
            ["payment", "list", "sla.baselines", "--live", "--format", output_format]
        )
        assert code == 0
        if output_format == "json":
            result = json.loads(out, parse_float=Decimal)
            assert result["data"][0] == {
                "id": "1",
                "fraction": Decimal("0.1234567890123456789"),
                "nativeString": "0.1000",
            }
        else:
            assert out.startswith(
                "-\n  fraction: 0.1234567890123456789\n"
                "  id: 1\n  nativeString: 0.1000\n\nMetadata:\n"
            )


def test_cache_lock_rejects_refresh_without_query(run_cli, pilots):
    import os

    from dogopencli.cache import Cache

    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    with Cache(root / "leaf-cache.sqlite3").refresh_lock():
        code, out, _ = run_cli(["payment", "refresh", "sla.baselines"])
    assert code == 1
    assert json.loads(out)["error"]["code"] == "LOCKED"
    assert json.loads(out)["error"]["retryable"] is True
    assert pilots.business_requests == []


def test_failed_install_removes_its_partial_folder(run_cli, tmp_path, monkeypatch):
    import shutil

    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(tmp_path))

    def failing_copy(source, destination, **kwargs):
        (destination / "partial").write_text("partial synthetic copy")
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copytree", failing_copy)
    code, out, _ = run_cli(["plugins", "install", "bundled:payment.sla.baselines"])
    assert code == 1 and json.loads(out)["error"]["code"] == "IO_ERROR"
    assert not list((tmp_path / "plugins").glob("*/*"))


def test_publication_failure_rolls_back_previous_rows_and_capture(run_cli, pilots):
    import os
    import sqlite3

    pilots.business_script.append(page([{"id": "saved"}]))
    assert run_cli(["payment", "refresh", "sla.baselines"])[0] == 0
    _, out, _ = run_cli(["payment", "list", "sla.baselines"])
    saved = json.loads(out)
    database_path = Path(os.environ["DOGOPENCLI_CONFIG"]).parent / "leaf-cache.sqlite3"
    with sqlite3.connect(database_path) as database:
        database.execute(
            "CREATE TRIGGER reject_publication BEFORE INSERT ON records "
            "BEGIN SELECT RAISE(ABORT, 'synthetic write failure'); END"
        )
    pilots.business_script.append(page([{"id": "replacement"}]))
    code, out, _ = run_cli(["payment", "refresh", "sla.baselines"])
    assert code == 1 and json.loads(out)["meta"]["published"] is False
    _, out, _ = run_cli(["payment", "list", "sla.baselines"])
    current = json.loads(out)
    assert current["data"] == saved["data"]
    assert current["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_authentication_and_parser_failures_preserve_saved_candidate(run_cli, pilots):
    pilots.business_script.append(page([{"id": "saved"}]))
    assert run_cli(["payment", "refresh", "sla.baselines"])[0] == 0
    _, out, _ = run_cli(["payment", "list", "sla.baselines"])
    saved = json.loads(out)
    failures = [
        ({"status": 401, "body": {}}, "AUTH_REQUIRED"),
        ({"status": 200, "body": "{"}, "INVALID_RESPONSE"),
        (
            page([{"value": "missing native id"}]),
            "INVALID_RESPONSE",
        ),
    ]
    for response, error_code in failures:
        pilots.business_script.append(response)
        code, out, _ = run_cli(["payment", "refresh", "sla.baselines"])
        result = json.loads(out)
        assert code == 1 and result["error"]["code"] == error_code
        assert result["data"] is None and result["meta"]["published"] is False
        _, out, _ = run_cli(["payment", "list", "sla.baselines"])
        current = json.loads(out)
        assert current["data"] == saved["data"]
        assert current["meta"]["fetched_at"] == saved["meta"]["fetched_at"]


def test_disabled_domain_still_allows_offline_prune(run_cli, pilots):
    assert run_cli(["domain", "disable", "payment"])[0] == 0
    code, out, _ = run_cli(["payment", "prune", "sla.baselines"])
    assert code == 0 and json.loads(out)["error"] is None
    assert pilots.business_requests == []


def test_interrupted_query_records_failed_execution_and_preserves_cache(
    run_cli, pilots
):
    pilots.business_script.append(page([{"id": "saved"}]))
    assert run_cli(["payment", "refresh", "sla.baselines"])[0] == 0

    def interrupted(request, index):
        raise KeyboardInterrupt

    pilots.business_handler = interrupted
    code, out, err = run_cli(["payment", "refresh", "sla.baselines"])
    assert code == 130 and "interrupted" in err
    rejected = json.loads(out)
    assert rejected["data"] is None
    assert rejected["error"]["code"] == "INTERRUPTED"
    assert rejected["meta"]["published"] is False
    pilots.business_handler = None
    _, out, _ = run_cli(["domain", "leaves", "payment"])
    observation = json.loads(out)["result"][0]["last_execution"]
    assert observation["outcome"] == "failed"
    assert observation["error_code"] == "INTERRUPTED"
    _, out, _ = run_cli(["payment", "list", "sla.baselines"])
    assert json.loads(out)["data"] == [{"id": "saved"}]


def test_switching_adapter_attribute_invalidates_saved_contract(run_cli, pilots):
    import os

    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    folder = root / "plugins/payment/sla.baselines"
    adapter = folder / "adapter.py"
    adapter.write_text(adapter.read_text() + "\nadapter_alternative = Adapter()\n")
    pilots.business_script.append(page([{"id": "saved"}]))
    assert run_cli(["payment", "refresh", "sla.baselines"])[0] == 0
    path = folder / "leaf.json"
    manifest = json.loads(path.read_text())
    manifest["adapter"] = "adapter.py:adapter_alternative"
    path.write_text(json.dumps(manifest))
    code, out, _ = run_cli(["payment", "list", "sla.baselines"])
    assert code == 1
    assert json.loads(out)["error"]["code"] == "CACHE_CONTRACT_CHANGED"


def test_identical_numeric_parameter_roundtrip_keeps_coverage(run_cli, pilots):
    import os
    from decimal import Decimal

    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    path = root / "plugins/payment/sla.baselines/leaf.json"
    manifest = json.loads(path.read_text())
    manifest["operations"]["list"]["parameters"].append(
        {
            "name": "rate",
            "type": "number",
            "required": False,
            "local_field": "rate",
            "description": "Synthetic local selection",
        }
    )
    path.write_text(json.dumps(manifest))
    pilots.business_script.append(page([{"id": "1", "rate": Decimal("0.1")}]))
    assert run_cli(["payment", "refresh", "sla.baselines", "--rate", "0.1"])[0] == 0
    code, out, _ = run_cli(
        ["payment", "list", "sla.baselines", "--rate", "0.1", "--require-complete"]
    )
    assert code == 0
    assert json.loads(out)["meta"]["complete"] is True


def test_cache_fingerprint_uses_the_adapter_bytes_that_were_loaded(run_cli, pilots):
    import os

    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    source = root / "plugins/payment/sla.baselines/adapter.py"
    source.write_text(
        source.read_text()
        + """
_original_capability = Adapter.capability
def replace_source_after_loading(self, parameters):
    from pathlib import Path
    source = Path(__file__)
    source.write_text(source.read_text().replace('# revision-one', '# revision-two'))
    return _original_capability(self, parameters)
Adapter.capability = replace_source_after_loading
# revision-one
"""
    )
    pilots.business_script.append(page([{"id": "loaded-before-replacement"}]))
    code, output, _ = run_cli(["payment", "refresh", "sla.baselines"])
    assert code == 0 and json.loads(output)["meta"]["published"]
    code, output, _ = run_cli(["payment", "list", "sla.baselines"])
    assert code == 1
    assert json.loads(output)["error"]["code"] == "CACHE_CONTRACT_CHANGED"
