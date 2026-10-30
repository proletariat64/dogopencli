"""Bounded imports and offline metadata inspection at the public CLI seam."""

import os
from pathlib import Path

import pytest
from integration.test_workflow_cli import call, payment_page

pytest_plugins = ["integration.test_leaf_pilots_cli"]


def test_status_does_not_read_retained_export_records(run_cli, pilots, monkeypatch):
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    pilots.business_script.append(payment_page([{"id": "retained"}]))
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    original = Path.read_bytes

    def metadata_only(path):
        if path.name == "records.json" or path.name == exported["id"] + ".json":
            raise AssertionError("Status reread retained records")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", metadata_only)
    status = call(run_cli, "status")
    assert status["exports"][0]["record_count"] == 1
    assert not (Path(os.environ["DOGOPENCLI_CONFIG"]).parent / "unexpected").exists()


@pytest.mark.parametrize(
    "stop",
    [
        "before_batch_commit",
        "after_batch_commit",
        "before_publication_commit",
        "after_publication_commit",
    ],
)
def test_resume_after_durable_batch_before_publication(
    run_cli, pilots, monkeypatch, stop
):
    from dogopencli import workflow_storage
    from dogopencli.workflow_tasks import snapshot

    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    rows = [{"id": str(i), "nested": [None, "1.0000"]} for i in range(25001)]
    for page in range(3):
        response = payment_page(rows[page * 10000 : (page + 1) * 10000])
        response["body"].update(pageNo=page, totalCount=len(rows))
        pilots.business_script.append(response)
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        "--limit",
        "1",
    )
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    original = workflow_storage.stage_checkpoint
    batches = []

    def interrupted(phase, count):
        batches.append((phase, count))
        if phase == stop:
            raise KeyboardInterrupt

    monkeypatch.setattr(workflow_storage, "stage_checkpoint", interrupted)
    result = run_cli(["workflow", "import", "apply", "--plan", prepared["id"]])
    progress = snapshot(
        Path(os.environ["DOGOPENCLI_CONFIG"]), "import", prepared["id"]
    )["progress"]
    assert result[0] != 0, result
    assert batches, result
    assert progress["expected_rows"] == 25001
    assert progress["staged_rows"] == (
        0
        if stop == "before_batch_commit"
        else 10000
        if stop == "after_batch_commit"
        else 25001
    )
    assert progress.get("committed_rows", 0) == (
        25001 if stop == "after_publication_commit" else 0
    )
    before_status = {
        path: path.read_bytes()
        for path in Path(os.environ["DOGOPENCLI_CONFIG"]).parent.rglob("*")
        if path.is_file()
    }
    committed = call(run_cli, "status")["committed_observations"]
    assert len(committed) == (1 if stop == "after_publication_commit" else 0)
    assert all(path.read_bytes() == value for path, value in before_status.items())
    monkeypatch.setattr(workflow_storage, "stage_checkpoint", original)
    applied = call(run_cli, "import", "apply", "--plan", prepared["id"])
    assert applied["inserted_count"] == (
        0 if stop == "after_publication_commit" else 25001
    )
    assert batches[-1][0] == stop
    completed = [count for phase, count in batches if phase == "after_batch_commit"]
    assert all(
        right - left <= 10000
        for left, right in zip([0, *completed], completed, strict=False)
    )
    assert (
        call(run_cli, "observation", "show", "--export", exported["id"])["records"]
        == rows
    )
    assert (
        call(run_cli, "import", "apply", "--plan", prepared["id"])["replayed"] is True
    )


@pytest.mark.skipif(
    os.environ.get("DOGOPENCLI_RUN_SCALE") != "1",
    reason="Explicit million-row measurement; separate from native UAT",
)
def test_million_row_synthetic_history_measurement(
    run_cli, pilots, tmp_path, monkeypatch
):
    """Opt-in reproducible measurement; no production queries or source profiles."""
    import gc
    import json
    import resource
    import shutil
    import time

    import duckdb
    from integration.test_workflow_generic_cli import SYNTHETIC_ADAPTER

    from dogopencli import workflow, workflow_storage

    monkeypatch.setattr(workflow, "now", lambda: "2026-10-29T00:00:00+00:00")
    pilots.href = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    source = tmp_path / "synthetic"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "leaf_packages/liquidity/reference.banks",
        source,
    )
    manifest = json.loads((source / "leaf.json").read_text())
    manifest["name"] = "synthetic.observations"
    manifest["dataset"]["relation"] = "synthetic_observations"
    manifest["operations"]["list"]["parameters"] = [
        {
            "name": name,
            "type": "string",
            "required": False,
            "description": "Synthetic native date bound.",
        }
        for name in ("from-date", "to-date")
    ]
    (source / "leaf.json").write_text(json.dumps(manifest))
    with (source / "adapter.py").open("a") as stream:
        stream.write(SYNTHETIC_ADAPTER)
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 0, output
    total = 1000000

    def page(body, _):
        query = json.loads(body["paraBankVO"])
        start, size = query["rowStart"], query["pageSize"]
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": total,
                "result": {
                    "bankVoList": [
                        {
                            "bankId": str(i),
                            "amount": "0.000000000000000001",
                            "nested": [False, {"x": None}],
                        }
                        for i in range(start, min(start + size, total))
                    ]
                },
            },
        }

    pilots.business_handler = page
    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.synthetic.observations",
        "--mode",
        "history",
        "--parameters",
        '{"from-date":"20260918","to-date":"20260920"}',
    )
    started = time.perf_counter()
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        "--limit",
        "1",
    )
    export_seconds = time.perf_counter() - started
    identity = exported["packages"][0]["export_id"]
    prepared = call(
        run_cli, "import", "plan", "--export", identity, "--action", "preserve"
    )
    assert "input" not in prepared
    requests = len(pilots.business_requests)
    pilots.business_handler = lambda *_: pytest.fail("Offline import queried source")
    gc.collect()
    before_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    batches = []
    monkeypatch.setattr(
        workflow_storage,
        "stage_checkpoint",
        lambda phase, count: (
            batches.append(count) if phase == "after_batch_commit" else None
        ),
    )
    started = time.perf_counter()
    receipt = call(run_cli, "import", "apply", "--plan", prepared["id"])
    import_seconds = time.perf_counter() - started
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert receipt["inserted_count"] == total
    assert len(batches) == 100 and batches == list(range(10000, 1000001, 10000))
    # Replay after reloading CLI/config state trusts committed DB receipts.
    started = time.perf_counter()
    assert (
        call(run_cli, "import", "apply", "--plan", prepared["id"])["replayed"] is True
    )
    replay_seconds = time.perf_counter() - started
    database = Path(os.environ["DOGOPENCLI_CONFIG"]).parent / "duckdog.duckdb"
    with duckdb.connect(str(database), read_only=True) as db:
        readback = db.execute(
            "SELECT count(*), count(DISTINCT ordinal), "
            "count(DISTINCT json_extract_string(_record, '$.bankId')), "
            "min(CAST(json_extract_string(_record, '$.bankId') AS BIGINT)), "
            "max(CAST(json_extract_string(_record, '$.bankId') AS BIGINT)), "
            "count(*) FILTER (WHERE json_extract_string(_record, '$.amount') "
            "= '0.000000000000000001' AND "
            "json_extract(_record, '$.nested') = '[false,{\"x\":null}]') "
            "FROM _dogopencli_observation_rows WHERE export_id=?",
            [identity],
        ).fetchone()
    assert readback == (1000000, 1000000, 1000000, 0, 999999, 1000000)
    original = Path.read_bytes
    opened = []

    def metadata_only(path):
        opened.append(str(path))
        if path.name == "records.json" and path.parent.name == identity:
            raise AssertionError("Incremental planning/status reread retained corpus")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", metadata_only)
    started = time.perf_counter()
    status = call(run_cli, "status")
    coverage = call(run_cli, "history", "show", "--plan", plan["id"])
    incremental_seconds = time.perf_counter() - started
    assert coverage["complete"] is True
    assert status["committed_observations"][0]["record_count"] == total
    assert len(pilots.business_requests) == requests
    offline_requests = len(pilots.business_requests) - requests
    million_batch_commits = len(batches)
    # A subsequent one-row native package imports without opening the retained
    # million-row artifact, even while exact new input checks remain enabled.
    total = 1
    pilots.business_handler = page
    started = time.perf_counter()
    next_plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.synthetic.observations",
        "--mode",
        "history",
        "--parameters",
        '{"from-date":"20260921","to-date":"20260921"}',
    )
    next_export = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", next_plan["id"])["id"],
        "--limit",
        "1",
    )
    next_identity = next_export["packages"][0]["export_id"]
    next_import = call(
        run_cli, "import", "plan", "--export", next_identity, "--action", "preserve"
    )
    next_requests = len(pilots.business_requests)
    pilots.business_handler = lambda *_: pytest.fail(
        "Incremental import queried source"
    )
    assert (
        call(run_cli, "import", "apply", "--plan", next_import["id"])["inserted_count"]
        == 1
    )
    assert len(pilots.business_requests) == next_requests
    incremental_package_seconds = time.perf_counter() - started
    evidence = {
        "rows": 1000000,
        "readback": list(readback),
        "incremental_package_seconds": incremental_package_seconds,
        "incremental_package_rows": 1,
        "action": "preserve",
        "mode": "history",
        "export_id": identity,
        "import_plan_id": prepared["id"],
        "export_seconds": export_seconds,
        "import_seconds": import_seconds,
        "replay_seconds": replay_seconds,
        "incremental_status_seconds": incremental_seconds,
        "rss_before_import_kib": before_rss,
        "peak_rss_after_import_kib": peak_rss,
        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "batch_rows_max": 10000,
        "batch_commits": million_batch_commits,
        "retained_record_files_read_by_status": 0,
        "requests_during_import_replay_status": offline_requests,
        "measurement": "Synthetic installed leaf/fake CDP; not native UAT",
    }
    output = Path(
        os.environ.get("DOGOPENCLI_SCALE_EVIDENCE", str(tmp_path / "scale.json"))
    )
    output.write_text(json.dumps(evidence, indent=2))


@pytest.mark.parametrize(
    "stop",
    ["after_batch_commit", "before_publication_commit", "after_publication_commit"],
)
def test_full_current_stays_atomic_across_durable_staging(
    run_cli, pilots, monkeypatch, stop
):
    from dogopencli import workflow_storage

    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    pilots.business_script.append(payment_page([{"id": "previous"}]))
    first = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    initial = call(
        run_cli, "import", "plan", "--export", first["id"], "--action", "replace-full"
    )
    call(run_cli, "import", "apply", "--plan", initial["id"])
    rows = [{"id": str(i)} for i in range(10001)]
    for page in range(2):
        response = payment_page(rows[page * 10000 : (page + 1) * 10000])
        response["body"].update(pageNo=page, totalCount=len(rows))
        pilots.business_script.append(response)
    second = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        "--limit",
        "1",
    )
    replacement = call(
        run_cli, "import", "plan", "--export", second["id"], "--action", "replace-full"
    )
    original = workflow_storage.stage_checkpoint

    def interrupted(phase, _):
        if phase == stop:
            raise KeyboardInterrupt

    monkeypatch.setattr(workflow_storage, "stage_checkpoint", interrupted)
    code, _, _ = run_cli(["workflow", "import", "apply", "--plan", replacement["id"]])
    assert code != 0
    current = call(run_cli, "current", "show", "--export", first["id"])
    assert current["records"] == (
        rows if stop == "after_publication_commit" else [{"id": "previous"}]
    )
    monkeypatch.setattr(workflow_storage, "stage_checkpoint", original)
    applied = call(run_cli, "import", "apply", "--plan", replacement["id"])
    assert applied["replayed"] is (stop == "after_publication_commit")
    assert call(run_cli, "current", "show", "--export", first["id"])["records"] == rows
    assert call(run_cli, "observation", "show", "--export", first["id"])["records"] == [
        {"id": "previous"}
    ]


def test_uninstall_retains_imported_history_and_unrelated_data(run_cli, pilots):
    import duckdb

    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    pilots.business_script.append(payment_page([{"id": "retained"}]))
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    binding = exported["binding"]
    with duckdb.connect(binding["database"]) as db:
        db.execute("CREATE TABLE unrelated_data(value VARCHAR)")
        db.execute("INSERT INTO unrelated_data VALUES ('keep')")
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    code, output, _ = run_cli(["plugins", "uninstall", "payment.sla.baselines"])
    assert code == 0, output
    with duckdb.connect(binding["database"]) as db:
        assert db.execute("SELECT * FROM unrelated_data").fetchall() == [("keep",)]
        assert db.execute(
            "SELECT _record FROM _dogopencli_observation_rows WHERE export_id=?",
            [exported["id"]],
        ).fetchall() == [('{"id":"retained"}',)]
        assert db.execute(
            "SELECT count(*) FROM _dogopencli_observations WHERE export_id=?",
            [exported["id"]],
        ).fetchone() == (1,)
    import json

    assert json.loads(output)["data"]["data_retained"] is True
    import sqlite3

    with sqlite3.connect(
        Path(os.environ["DOGOPENCLI_CONFIG"]).parent / "leaf-registry.sqlite3"
    ) as registry:
        assert registry.execute(
            "SELECT active FROM bindings WHERE leaf_id=?", [binding["leaf"]]
        ).fetchone() == (0,)
