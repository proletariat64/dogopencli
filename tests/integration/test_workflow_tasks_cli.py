"""Stable task selection at the CLI and shared offline snapshot seams."""

import os
from pathlib import Path

from integration.test_workflow_cli import call, payment_page

pytest_plugins = ["integration.test_leaf_pilots_cli"]


def test_export_create_prepares_distinct_pending_runs_without_queries(run_cli, pilots):
    from dogopencli.workflow_tasks import snapshot

    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    first = call(run_cli, "export", "create", "--plan", plan["id"])
    second = call(run_cli, "export", "create", "--plan", plan["id"])
    assert first["id"] != second["id"]
    status = snapshot(Path(os.environ["DOGOPENCLI_CONFIG"]), "export", first["id"])
    assert status["effective_state"] == "pending"
    assert status["attempt"] is None
    assert status["plan_id"] == plan["id"]
    assert not pilots.business_requests


def test_export_retry_keeps_identity_and_fresh_run_never_borrows_results(
    run_cli, pilots
):
    from dogopencli.workflow_tasks import snapshot

    config = Path(os.environ["DOGOPENCLI_CONFIG"])
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    first = call(run_cli, "export", "create", "--plan", plan["id"])
    pilots.business_script.append(payment_page([{"id": "old"}]))
    exported = call(run_cli, "export", "run", "--run", first["id"])
    requests = len(pilots.business_requests)
    replay = call(run_cli, "export", "run", "--run", first["id"])
    assert replay["id"] == exported["id"]
    assert len(pilots.business_requests) == requests
    second = call(run_cli, "export", "create", "--plan", plan["id"])
    pilots.business_script.append(payment_page([]))
    fresh = call(run_cli, "export", "run", "--run", second["id"])
    assert fresh["id"] != exported["id"]
    assert fresh["record_count"] == 0
    status = snapshot(config, "export", first["id"])
    assert status["effective_state"] == "completed"
    assert status["attempt_count"] == 2
    assert status["result"]["export_id"] == exported["id"]
    code, _, _ = run_cli(["workflow", "export", "run", "--plan", plan["id"]])
    assert code == 2


def test_repair_freezes_one_run_even_when_same_plan_has_other_success(run_cli, pilots):
    from dogopencli.workflow_tasks import snapshot

    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    baseline = call(run_cli, "export", "create", "--plan", plan["id"])
    pilots.business_script.append({"status": 500, "body": {}})
    code, _, _ = run_cli(["workflow", "export", "run", "--run", baseline["id"]])
    assert code == 1
    unrelated = call(run_cli, "export", "create", "--plan", plan["id"])
    pilots.business_script.append(payment_page([]))
    call(run_cli, "export", "run", "--run", unrelated["id"])
    repair = call(run_cli, "repair", "plan", "--run", baseline["id"])
    assert repair["baseline_run"] == baseline["id"]
    assert (
        snapshot(Path(os.environ["DOGOPENCLI_CONFIG"]), "repair", repair["id"])[
            "effective_state"
        ]
        == "pending"
    )
    pilots.business_script.append(payment_page([{"id": "repaired"}]))
    fixed = call(run_cli, "repair", "run", "--repair", repair["id"])
    assert fixed["complete"] is True
    assert len(fixed["selected_exports"]) == 1


def test_target_execution_freezes_its_child_runs_and_retries_them(run_cli, pilots):
    from dogopencli.workflow_tasks import snapshot

    config = Path(os.environ["DOGOPENCLI_CONFIG"])
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    target = call(run_cli, "target", "create", "--plan", plan["id"])
    execution = call(run_cli, "target", "plan", "--target", target["id"])
    child = execution["runs"][0]
    assert snapshot(config, "target", execution["id"])["effective_state"] == "pending"
    assert snapshot(config, "export", child)["effective_state"] == "pending"
    pilots.business_script.append({"status": 500, "body": {}})
    code, _, _ = run_cli(["workflow", "target", "run", "--execution", execution["id"]])
    assert code == 1
    pilots.business_script.append(payment_page([]))
    completed = call(run_cli, "target", "run", "--execution", execution["id"])
    assert completed["runs"] == [child]
    assert completed["complete"] is True
    assert snapshot(config, "export", child)["attempt_count"] == 2
    fresh = call(run_cli, "target", "plan", "--target", target["id"])
    assert fresh["runs"][0] != child


def test_import_status_requires_requested_action_and_recognizes_commit_before_failure(
    run_cli, pilots, monkeypatch
):
    from dogopencli import workflow_storage
    from dogopencli.workflow_tasks import snapshot

    config = Path(os.environ["DOGOPENCLI_CONFIG"])
    inquiry = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    run = call(run_cli, "export", "create", "--plan", inquiry["id"])
    pilots.business_script.append(payment_page([{"id": "committed"}]))
    exported = call(run_cli, "export", "run", "--run", run["id"])
    preserve = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    call(run_cli, "import", "apply", "--plan", preserve["id"])
    publication = call(
        run_cli,
        "import",
        "plan",
        "--export",
        exported["id"],
        "--action",
        "replace-full",
    )
    pending = snapshot(config, "import", publication["id"])
    assert pending["effective_state"] == "pending"
    assert pending["result"]["action_completed"] is False
    assert pending["progress"]["committed_rows"] == 0

    def fail_after_commit(phase, count):
        if phase == "after_publication_commit":
            raise RuntimeError("response lost after commit")

    monkeypatch.setattr(workflow_storage, "stage_checkpoint", fail_after_commit)
    code, _, _ = run_cli(["workflow", "import", "apply", "--plan", publication["id"]])
    assert code == 1
    recovered = snapshot(config, "import", publication["id"])
    assert recovered["effective_state"] == "completed"
    assert recovered["attempt"]["state"] == "failed"
    assert recovered["result"]["action_completed"] is True
    assert recovered["progress"]["committed_rows"] == 1
    assert (
        recovered["observation"]["completion_verification"]["source"]
        == "database_receipts"
    )


def test_exact_task_lock_rejects_competitor_and_hard_exit_is_interrupted(
    run_cli, pilots, monkeypatch
):
    import json
    import multiprocessing

    from dogopencli.workflow_tasks import snapshot

    config = Path(os.environ["DOGOPENCLI_CONFIG"])
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    task = call(run_cli, "export", "create", "--plan", plan["id"])
    context = multiprocessing.get_context("fork")
    requested = context.Event()

    def blocked_request(body, _):
        requested.set()
        import time

        time.sleep(30)
        return payment_page([])

    pilots.business_handler = blocked_request
    process = context.Process(
        target=lambda: run_cli(["workflow", "export", "run", "--run", task["id"]])
    )
    process.start()
    try:
        assert requested.wait(10)
        live = snapshot(config, "export", task["id"])
        assert live["effective_state"] == "running"
        assert live["observation"]["ownership"] == "verified"
        original_read = Path.read_text

        def unavailable_proc(path, *args, **kwargs):
            if str(path).startswith("/proc/"):
                raise PermissionError("controlled ownership read failure")
            return original_read(path, *args, **kwargs)

        with monkeypatch.context() as unavailable:
            unavailable.setattr(Path, "read_text", unavailable_proc)
            uncertain = snapshot(config, "export", task["id"])
            assert uncertain["effective_state"] == "unknown"
            assert uncertain["observation"]["ownership"] == "unknown"
        for hidden in ("missing", "mismatched"):

            def hidden_proc(path, *args, _visibility=hidden, **kwargs):
                if str(path).startswith("/proc/") and path.name == "stat":
                    if _visibility == "missing":
                        raise FileNotFoundError("process outside observer namespace")
                    prefix, fields = original_read(path, *args, **kwargs).rsplit(")", 1)
                    fields = fields.split()
                    fields[19] = str(int(fields[19]) + 1)
                    return prefix + ") " + " ".join(fields)
                return original_read(path, *args, **kwargs)

            with monkeypatch.context() as invisible:
                invisible.setattr(Path, "read_text", hidden_proc)
                uncertain = snapshot(config, "export", task["id"])
                assert uncertain["effective_state"] == "unknown", hidden
                assert uncertain["observation"]["ownership"] == "unknown", hidden
        unrelated = config.parent / "unrelated-lock"
        unrelated.touch()
        unrelated_stat = unrelated.stat()
        original_stat = Path.stat

        def wrong_descriptor(path, *args, **kwargs):
            if str(path).startswith("/proc/") and "/fd/" in str(path):
                return unrelated_stat
            return original_stat(path, *args, **kwargs)

        with monkeypatch.context() as other_lock:
            other_lock.setattr(Path, "stat", wrong_descriptor)
            assert (
                snapshot(config, "export", task["id"])["effective_state"] == "unknown"
            )
        code, output, error = run_cli(
            ["workflow", "export", "run", "--run", task["id"]]
        )
        assert code == 1
        assert json.loads(output)["error"]["code"] == "WORKFLOW_BUSY"
        assert "attempt " not in error
        process.kill()
        process.join(10)
        lost = snapshot(config, "export", task["id"])
        assert lost["effective_state"] == "interrupted"
        assert lost["attempt"]["state"] == "running"
        pilots.business_handler = None
        pilots.business_script.append(payment_page([]))
        call(run_cli, "export", "run", "--run", task["id"])
        retried = snapshot(config, "export", task["id"])
        assert retried["effective_state"] == "completed"
        assert retried["recent_attempts"][-1]["state"] == "interrupted"
    finally:
        if process.is_alive():
            process.kill()
        process.join(10)


def test_independent_reader_uses_durable_stage_summary_and_reconciles_killed_commit(
    run_cli, pilots, monkeypatch
):
    import multiprocessing
    import time

    from dogopencli import workflow_storage
    from dogopencli.workflow_tasks import snapshot

    config = Path(os.environ["DOGOPENCLI_CONFIG"])
    inquiry = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    run = call(run_cli, "export", "create", "--plan", inquiry["id"])
    pilots.business_script.append(payment_page([{"id": "durable"}]))
    exported = call(run_cli, "export", "run", "--run", run["id"])
    plan = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    context = multiprocessing.get_context("fork")
    staged = context.Event()
    committed = context.Event()
    release = config.parent / "release-writer"

    def checkpoints(phase, count):
        if phase == "after_batch_commit":
            staged.set()
            deadline = time.monotonic() + 20
            while not release.exists():
                if time.monotonic() > deadline:
                    raise TimeoutError("controlled writer barrier expired")
                time.sleep(0.01)
        if phase == "after_publication_commit":
            committed.set()
            time.sleep(30)

    monkeypatch.setattr(workflow_storage, "stage_checkpoint", checkpoints)
    process = context.Process(
        target=lambda: run_cli(["workflow", "import", "apply", "--plan", plan["id"]])
    )
    process.start()
    try:
        assert staged.wait(10)
        received, sent = context.Pipe(duplex=False)

        def independent_read():
            sent.send(snapshot(config, "import", plan["id"]))
            sent.close()

        reader = context.Process(target=independent_read)
        reader.start()
        sent.close()
        try:
            assert received.poll(10), "Independent observer did not respond"
            active = received.recv()
            reader.join(10)
            assert reader.exitcode == 0
        finally:
            received.close()
            if reader.is_alive():
                reader.kill()
            reader.join(10)
        assert active["effective_state"] == "running"
        assert active["progress"]["staged_rows"] == 1
        assert active["result"]["action_completed"] is None
        assert active["observation"]["completion_verification"]["source"] is None
        release.touch()
        assert committed.wait(10)
        process.kill()
        process.join(10)
        reconciled = snapshot(config, "import", plan["id"])
        assert reconciled["effective_state"] == "completed"
        assert reconciled["progress"]["committed_rows"] == 1
        assert reconciled["attempt"]["state"] == "running"
    finally:
        if process.is_alive():
            process.kill()
        process.join(10)


def test_import_polling_reads_bounded_metadata_without_changing_files(
    run_cli, pilots, monkeypatch
):
    from dogopencli.workflow_tasks import snapshot

    config = Path(os.environ["DOGOPENCLI_CONFIG"])
    inquiry = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    run = call(run_cli, "export", "create", "--plan", inquiry["id"])
    pilots.business_script.append(payment_page([{"id": "retained"}]))
    exported = call(run_cli, "export", "run", "--run", run["id"])
    plan = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    before = {p: p.read_bytes() for p in config.parent.rglob("*") if p.is_file()}
    original = Path.read_bytes

    def metadata_only(path):
        assert path.name != "records.json"
        assert path.parent.name != "imports"
        return original(path)

    unrelated = config.parent / "workflow" / "exports" / ("f" * 32)
    unrelated.mkdir()
    (unrelated / "metadata.json").write_text("corrupt unrelated artifact")
    monkeypatch.setattr(Path, "read_bytes", metadata_only)
    assert snapshot(config, "import", plan["id"])["effective_state"] == "pending"
    assert snapshot(config, "export", run["id"])["progress"]["exported_rows"] == 1
    assert all(original(p) == content for p, content in before.items())


def test_runner_emits_actual_identity_and_safe_progress_only_on_stderr(run_cli, pilots):
    import json

    from dogopencli.workflow_tasks import snapshot

    config = Path(os.environ["DOGOPENCLI_CONFIG"])
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    task = call(run_cli, "export", "create", "--plan", plan["id"])
    pilots.business_script.append(payment_page([{"id": "private-business-row"}]))
    code, output, error = run_cli(["workflow", "export", "run", "--run", task["id"]])
    assert code == 0
    assert json.loads(output)["error"] is None
    current = snapshot(config, "export", task["id"])["attempt"]
    assert f"export {task['id']} attempt {current['number']} {current['id']}" in error
    assert "phase=" in error
    assert "private-business-row" not in error
