"""Exact task observation through the public CLI, fake CDP and terminal boundary."""

import json
import os
from pathlib import Path

from integration.test_workflow_cli import call, payment_page

pytest_plugins = ["integration.test_leaf_pilots_cli", "test_workflow_attach"]


def isolated_cli(argv):
    # Nested runner invocations must not drain the observer's capture buffer.
    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO

    from dogopencli.cli import main

    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def prepare(run_cli):
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    return call(run_cli, "export", "create", "--plan", plan["id"])


def test_pending_status_is_one_offline_metadata_envelope(run_cli, pilots):
    task = prepare(run_cli)
    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    code, out, err = run_cli(["workflow", "export", "status", "--run", task["id"]])
    assert code == 0, out
    response = json.loads(out)
    assert set(response) == {"data", "meta", "error"}
    assert response["error"] is None
    assert response["data"]["id"] == task["id"]
    assert response["data"]["effective_state"] == "pending"
    assert response["data"]["attempt"] is None
    assert response["data"]["progress"]["source_total_rows"] is None
    assert response["data"]["progress"]["source_total_scope"] is None
    assert (
        response["data"]["progress"]["source_total_scope_reason"]
        == "native_total_unavailable"
    )
    assert response["data"]["observation"]["ownership"] == "inactive"
    assert not pilots.business_requests
    assert not err
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_snapshot_and_text_status_describe_saved_result_without_loading_rows(
    run_cli, pilots
):
    task = prepare(run_cli)
    pilots.business_script.append(payment_page([{"id": "private-business-record"}]))
    exported = call(run_cli, "export", "run", "--run", task["id"])
    requests = len(pilots.business_requests)
    code, out, _ = run_cli(
        ["workflow", "export", "watch", "--run", task["id"], "--snapshot"]
    )
    assert code == 0, out
    assert task["id"] in out and exported["id"] in out
    assert "completed" in out and "exported" in out.lower()
    assert "private-business-record" not in out
    assert "\x1b" not in out
    code, status, _ = run_cli(
        ["workflow", "export", "status", "--run", task["id"], "--format", "text"]
    )
    assert code == 0
    assert task["id"] in status and exported["id"] in status
    assert "private-business-record" not in status
    assert len(pilots.business_requests) == requests


def test_watch_rejects_usage_before_observation_and_preserves_help_formats(
    run_cli, pilots
):
    task = prepare(run_cli)
    command = ["workflow", "export", "watch", "--run", task["id"]]
    for flags in (
        ["--format", "json"],
        ["--format=json"],
        ["--interval", "0"],
        ["--interval", "-1"],
        ["--interval", "1.5"],
        ["--snapshot", "--until-settled"],
        ["--snapshot", "--attach", "pane"],
        ["--until-settled", "--attach", "pane"],
    ):
        code, out, _ = run_cli([*command, *flags])
        assert code == 2, (flags, out)
        # Explicit JSON still receives the machine-readable host error envelope.
        if "json" in " ".join(flags):
            assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
            assert "status" in json.loads(out)["error"]["message"]
    for flags in ([], ["--format", "json"], ["--format", "text"]):
        code, out, _ = run_cli(["workflow", "export", "watch", "--help", *flags])
        assert code == 0, out
        if "text" not in flags:
            assert json.loads(out)["error"] is None
    code, out, _ = run_cli(
        ["workflow", "export", "status", "--run", task["id"], "--snapshot"]
    )
    assert code == 2
    assert not pilots.business_requests


def test_until_settled_distinguishes_execution_failure_from_read_failure(
    run_cli, pilots
):
    task = prepare(run_cli)
    pilots.business_script.append({"status": 500, "body": {}})
    code, _, _ = run_cli(["workflow", "export", "run", "--run", task["id"]])
    assert code == 1
    status = call(run_cli, "export", "status", "--run", task["id"])
    assert status["effective_state"] == "failed"
    assert status["attempt"]["error"]
    for mode, expected in (("--snapshot", 0), ("--until-settled", 1)):
        code, out, _ = run_cli(
            ["workflow", "export", "watch", "--run", task["id"], mode]
        )
        assert code == expected, out
        assert task["id"] in out and "failed" in out
    pilots.business_script.append(payment_page([]))
    call(run_cli, "export", "run", "--run", task["id"])
    code, out, _ = run_cli(
        ["workflow", "export", "watch", "--run", task["id"], "--until-settled"]
    )
    assert code == 0 and "completed" in out
    assert "complete_empty" in out
    code, out, _ = run_cli(["workflow", "export", "status", "--run", "0" * 32])
    assert code == 1
    assert json.loads(out)["error"]["code"] == "WORKFLOW_ERROR"
    code, out, _ = run_cli(["workflow", "export", "status", "--run", "bad"])
    assert code == 2
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_resident_watch_follows_same_task_retry_and_ctrl_c_only_ends_observer(
    run_cli, pilots, monkeypatch
):
    from dogopencli import workflow_watch

    task = prepare(run_cli)
    polls = []

    def tick(interval):
        polls.append(interval)
        if len(polls) == 1:
            pilots.business_script.append({"status": 500, "body": {}})
            code, _, _ = isolated_cli(
                ["workflow", "export", "run", "--run", task["id"]]
            )
            assert code == 1
        elif len(polls) == 2:
            pilots.business_script.append(payment_page([{"id": "saved"}]))
            call(isolated_cli, "export", "run", "--run", task["id"])
        else:
            raise KeyboardInterrupt

    monkeypatch.setattr(workflow_watch, "sleep", tick)
    code, out, err = run_cli(["workflow", "export", "watch", "--run", task["id"]])
    assert code == 130
    assert polls == [3, 3, 3]
    assert "pending" in out and "failed" in out and "completed" in out
    assert "\x1b" not in out
    assert "observer" in err.lower()
    current = call(run_cli, "export", "status", "--run", task["id"])
    assert current["effective_state"] == "completed"
    assert current["attempt_count"] == 2
    assert len(current["recent_attempts"]) == 1
    assert current["last_successful_attempt"]


def test_all_four_stage_status_and_snapshot_routes_use_exact_typed_identity(
    run_cli, pilots
):
    baseline = prepare(run_cli)
    pilots.business_script.append({"status": 500, "body": {}})
    run_cli(["workflow", "export", "run", "--run", baseline["id"]])
    repair = call(run_cli, "repair", "plan", "--run", baseline["id"])
    good = prepare(run_cli)
    pilots.business_script.append(payment_page([]))
    exported = call(run_cli, "export", "run", "--run", good["id"])
    importing = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    target = call(run_cli, "target", "create", "--plan", good["plan_id"])
    execution = call(run_cli, "target", "plan", "--target", target["id"])
    requests = len(pilots.business_requests)
    for kind, flag, task in (
        ("export", "--run", baseline),
        ("repair", "--repair", repair),
        ("import", "--plan", importing),
        ("target", "--execution", execution),
    ):
        status = call(run_cli, kind, "status", flag, task["id"])
        assert status["id"] == task["id"] and status["kind"] == kind
        assert status["effective_state"] == (
            "failed" if kind == "export" else "pending"
        )
        code, out, _ = run_cli(
            ["workflow", kind, "watch", flag, task["id"], "--snapshot"]
        )
        assert code == 0 and task["id"] in out
        code, out, _ = run_cli(["workflow", kind, "status", flag, "0" * 32])
        assert code == 1 and json.loads(out)["error"]
    assert len(pilots.business_requests) == requests


def test_resident_read_failure_retains_aged_frame_and_finite_reads_fail(
    run_cli, pilots, monkeypatch
):
    from dogopencli import workflow_watch

    task = prepare(run_cli)
    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    task_file = root / "workflow" / "runs" / (task["id"] + ".json")
    hidden = task_file.with_suffix(".hidden")
    polls = []
    clock = [0]

    def tick(interval):
        polls.append(interval)
        clock[0] += 7
        if len(polls) == 1:
            task_file.rename(hidden)
            for action, flags in (
                ("status", []),
                ("watch", ["--snapshot"]),
                ("watch", ["--until-settled"]),
            ):
                code, out, _ = isolated_cli(
                    ["workflow", "export", action, "--run", task["id"], *flags]
                )
                assert code == 1, out
        elif len(polls) == 2:
            hidden.rename(task_file)
            pilots.business_script.append(payment_page([]))
            call(isolated_cli, "export", "run", "--run", task["id"])
        else:
            raise KeyboardInterrupt

    monkeypatch.setattr(workflow_watch, "sleep", tick)
    monkeypatch.setattr(workflow_watch, "monotonic", lambda: clock[0])
    code, out, err = run_cli(["workflow", "export", "watch", "--run", task["id"]])
    assert code == 130
    assert "STALE" in out and "7.0" in out
    assert "completed" in out
    assert "WORKFLOW_ERROR" in out and "WORKFLOW_ERROR" in err
    assert "\x1b" not in out


def test_attach_cli_validates_task_then_emits_only_confirmed_startup_receipt(
    run_cli, pilots, herdr, monkeypatch
):
    import shlex

    import pytest

    from dogopencli import workflow_watch

    task = prepare(run_cli)
    monkeypatch.setattr(
        workflow_watch, "sleep", lambda _: pytest.fail("attach must be finite")
    )
    code, out, _ = run_cli(
        [
            "workflow",
            "export",
            "watch",
            "--run",
            task["id"],
            "--attach",
            herdr.target,
            "--interval",
            "4",
        ]
    )
    assert code == 0, out
    assert task["id"] in out and herdr.target in out
    command = shlex.split(herdr.launched)
    assert command[-8:] == [
        "workflow",
        "export",
        "watch",
        "--run",
        task["id"],
        "--interval",
        "4",
        "--format=text",
    ]
    assert "--attach" not in command
    launches = len(herdr.calls)
    code, out, _ = run_cli(
        ["workflow", "export", "watch", "--run", "0" * 32, "--attach", herdr.target]
    )
    assert code == 1
    assert len(herdr.calls) == launches


def observer_process(task_id, *, stdout=None):
    import multiprocessing
    from contextlib import redirect_stderr, redirect_stdout

    from dogopencli.cli import main

    reader, writer = os.pipe() if stdout is None else (None, stdout)
    error_reader, error_writer = os.pipe()

    def observe():
        with os.fdopen(os.dup(writer), "w") as out, os.fdopen(error_writer, "w") as err:
            with redirect_stdout(out), redirect_stderr(err):
                code = main(
                    ["workflow", "export", "watch", "--run", task_id, "--interval", "1"]
                )
        raise SystemExit(code)

    process = multiprocessing.get_context("fork").Process(target=observe)
    process.start()
    if stdout is None:
        os.close(writer)
    os.close(error_writer)
    return process, reader, error_reader


def test_tty_updates_panel_in_place_and_ctrl_c_does_not_write_task_state(
    run_cli, pilots
):
    import select
    import signal
    import time

    task = prepare(run_cli)
    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    reader, terminal = os.openpty()
    process, _, errors = observer_process(task["id"], stdout=terminal)
    os.close(terminal)
    output = b""
    try:
        deadline = time.monotonic() + 8
        while b"\x1b[" not in output and time.monotonic() < deadline:
            if select.select([reader], [], [], 0.2)[0]:
                output += os.read(reader, 65536)
        assert b"\x1b[" in output
        assert output.count(task["id"].encode()) >= 2
        os.kill(process.pid, signal.SIGINT)
        process.join(5)
        assert process.exitcode == 130
        assert b"Observer" in os.read(errors, 65536)
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
        os.close(errors)
        os.close(reader)
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_independent_observer_ctrl_c_leaves_live_runner_and_final_result_intact(
    run_cli, pilots
):
    import multiprocessing
    import signal

    task = prepare(run_cli)
    context = multiprocessing.get_context("fork")
    entered, release = context.Event(), context.Event()
    result = context.Queue()

    def blocked(_body, _request):
        entered.set()
        assert release.wait(15)
        return payment_page([{"id": "runner-owned-result"}])

    def execute():
        result.put(isolated_cli(["workflow", "export", "run", "--run", task["id"]]))

    pilots.business_handler = blocked
    runner = context.Process(target=execute)
    runner.start()
    observer = None
    observer_output = observer_errors = None
    try:
        assert entered.wait(10)
        observer, observer_output, observer_errors = observer_process(task["id"])
        # First panel is flushed before the observer sleeps.
        with os.fdopen(os.dup(observer_output), "rb") as observed:
            assert task["id"].encode() in observed.readline()
        os.kill(observer.pid, signal.SIGINT)
        observer.join(5)
        assert observer.exitcode == 130
        assert b"\x1b" not in os.read(observer_output, 65536)
        assert runner.is_alive()
        release.set()
        runner.join(10)
        assert runner.exitcode == 0
        code, out, err = result.get(timeout=2)
        assert code == 0, out
        assert task["id"] in err
        assert "attempt" in err.lower()
        saved = json.loads(out)["data"]
        assert saved["record_count"] == 1
        status = call(run_cli, "export", "status", "--run", task["id"])
        assert status["effective_state"] == "completed"
        assert status["result"]["export_id"] == saved["id"]
    finally:
        release.set()
        if observer is not None:
            if observer.is_alive():
                observer.kill()
            observer.join(5)
        for fd in (observer_output, observer_errors):
            if fd is not None:
                os.close(fd)
        if runner.is_alive():
            runner.terminate()
        runner.join(5)


def test_watch_boolean_flags_do_not_hide_later_explicit_configuration(
    run_cli, pilots, monkeypatch, tmp_path
):
    task = prepare(run_cli)
    selected = Path(os.environ["DOGOPENCLI_CONFIG"])
    # Explicit --config-dir must select the original config despite a conflicting env.
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "elsewhere" / "config.toml"))
    code, out, _ = run_cli(
        [
            "workflow",
            "export",
            "watch",
            "--run",
            task["id"],
            "--snapshot",
            "--config-dir",
            str(selected.parent),
        ]
    )
    assert code == 0, out
    assert task["id"] in out and "pending" in out
    code, out, _ = run_cli(["workflow", "export", "watch", "--help"])
    assert code == 0
    output = json.loads(out)["data"]["output"]
    assert output["default_format"] == "text"
    assert output["formats"] == ["text"]
    assert output["help_default_format"] == "json"


def test_usable_incomplete_export_keeps_native_units_and_until_settled_fails(
    run_cli, pilots
):
    inquiry = call(run_cli, "plan", "create", "--leaf", "collection.cost")
    task = call(run_cli, "export", "create", "--plan", inquiry["id"])
    response = payment_page(
        [{"itemId": "one", "itemType": "FUND_IN_CHANNEL_TRANS_FEE"}]
    )
    response["body"]["pageSize"] = 1000
    response["body"]["totalCount"] = 1001
    pilots.business_script.append(response)
    exported = call(run_cli, "export", "run", "--run", task["id"], "--limit", "0")
    status = call(run_cli, "export", "status", "--run", task["id"])
    assert status["effective_state"] == "incomplete"
    assert status["progress"]["source_pages"] == 1
    assert status["progress"]["request_attempts"] == 1
    assert status["progress"]["source_rows_received"] == 1
    assert status["progress"]["source_rows_selected"] == 1
    assert status["progress"]["source_total_rows"] == 1001
    assert (
        status["progress"]["source_total_scope"]
        == "native_query_before_local_selection"
    )
    assert status["progress"]["source_total_scope_reason"] is None
    assert status["progress"]["exported_rows"] == exported["record_count"] == 1
    code, out, _ = run_cli(
        ["workflow", "export", "watch", "--run", task["id"], "--until-settled"]
    )
    assert code == 1 and "incomplete" in out
    assert "100%" not in out


def test_legacy_import_without_bounded_header_is_degraded_and_cannot_wait_for_success(
    run_cli, pilots
):
    task = prepare(run_cli)
    pilots.business_script.append(payment_page([{"id": "retained-row"}]))
    exported = call(run_cli, "export", "run", "--run", task["id"])
    importing = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    (root / "workflow" / "import_headers" / (importing["id"] + ".json")).unlink()
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    status = call(run_cli, "import", "status", "--plan", importing["id"])
    assert status["effective_state"] == "unknown"
    assert status["observation"]["quality"] == "degraded"
    assert status["progress"]["staged_rows"] is None
    assert status["progress"]["committed_rows"] is None
    assert "retained-row" not in json.dumps(status)
    code, out, _ = run_cli(
        ["workflow", "import", "watch", "--plan", importing["id"], "--until-settled"]
    )
    assert code == 1
    assert "unknown" in out and "WORKFLOW_ERROR" in out
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_status_uses_metadata_even_when_adapters_and_retained_rows_are_unreadable(
    run_cli, pilots, monkeypatch
):
    task = prepare(run_cli)
    pilots.business_script.append(payment_page([{"id": "retained-secret"}]))
    exported = call(run_cli, "export", "run", "--run", task["id"])
    importing = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    adapter = root / "plugins" / "payment" / "sla.baselines" / "adapter.py"
    adapter.write_text('raise RuntimeError("adapter must not load during observation")')
    blocked = {
        root / "workflow" / "exports" / exported["id"] / "records.json",
        root / "workflow" / "imports" / (importing["id"] + ".json"),
    }
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    original_read = Path.read_bytes

    def metadata_only(path):
        if path in blocked:
            raise AssertionError("task observation must not read retained row arrays")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", metadata_only)
    for kind, flag, identity in (
        ("export", "--run", task["id"]),
        ("import", "--plan", importing["id"]),
    ):
        status = call(run_cli, kind, "status", flag, identity)
        assert status["id"] == identity
        assert "retained-secret" not in json.dumps(status)
        code, out, _ = run_cli(
            ["workflow", kind, "watch", flag, identity, "--snapshot"]
        )
        assert code == 0, out
    assert {p: original_read(p) for p in root.rglob("*") if p.is_file()} == before


def test_import_status_separates_durable_staging_from_receipt_and_replay(
    run_cli, pilots, monkeypatch
):
    from dogopencli import workflow_storage

    task = prepare(run_cli)
    pilots.business_script.append(payment_page([{"id": "saved-row"}]))
    exported = call(run_cli, "export", "run", "--run", task["id"])
    importing = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )

    def interrupted(phase, count):
        if phase == "after_batch_commit":
            raise RuntimeError("interrupted after durable staging")

    monkeypatch.setattr(workflow_storage, "stage_checkpoint", interrupted)
    code, _, _ = run_cli(["workflow", "import", "apply", "--plan", importing["id"]])
    assert code == 1
    status = call(run_cli, "import", "status", "--plan", importing["id"])
    assert status["progress"]["expected_rows"] == 1
    assert status["progress"]["staged_rows"] == 1
    assert status["progress"]["committed_rows"] == 0
    assert status["result"]["action_completed"] is False
    assert status["effective_state"] == "failed"
    monkeypatch.setattr(workflow_storage, "stage_checkpoint", lambda *args: None)
    call(run_cli, "import", "apply", "--plan", importing["id"])
    status = call(run_cli, "import", "status", "--plan", importing["id"])
    assert status["effective_state"] == "completed"
    assert status["result"]["action_completed"] is True
    assert status["progress"]["committed_rows"] == 1
    call(run_cli, "import", "apply", "--plan", importing["id"])
    status = call(run_cli, "import", "status", "--plan", importing["id"])
    assert status["result"]["replayed"] is True
    assert status["progress"]["committed_rows"] == 1
    code, out, _ = run_cli(
        ["workflow", "import", "watch", "--plan", importing["id"], "--until-settled"]
    )
    assert code == 0, out
    assert "staged" in out.lower() and "committed" in out.lower()


def test_until_settled_waits_for_pending_task_and_uses_custom_interval(
    run_cli, pilots, monkeypatch
):
    from dogopencli import workflow_watch

    task = prepare(run_cli)
    polls = []

    def tick(interval):
        polls.append(interval)
        assert len(polls) == 1
        pilots.business_script.append(payment_page([]))
        call(isolated_cli, "export", "run", "--run", task["id"])

    monkeypatch.setattr(workflow_watch, "sleep", tick)
    code, out, _ = run_cli(
        [
            "workflow",
            "export",
            "watch",
            "--run",
            task["id"],
            "--interval",
            "4",
            "--until-settled",
        ]
    )
    assert code == 0, out
    assert polls == [4]
    assert "pending" in out and "completed" in out


def test_get_and_list_detail_observation_keep_root_detail_and_saved_units_separate(
    run_cli, pilots
):
    inquiry = call(
        run_cli, "plan", "create", "--leaf", "payment.sla.baselines", "--with-detail"
    )
    task = call(run_cli, "export", "create", "--plan", inquiry["id"])
    pilots.business_script.extend(
        [
            payment_page([{"id": "one"}, {"id": "two"}]),
            {"status": 200, "body": {"success": True, "resultData": {"id": "one"}}},
            {"status": 200, "body": {"success": True, "resultData": {"id": "two"}}},
        ]
    )
    exported = call(run_cli, "export", "run", "--run", task["id"])
    status = call(run_cli, "export", "status", "--run", task["id"])
    assert status["progress"]["exported_rows"] == exported["record_count"] == 2
    assert status["progress"]["root_rows_received"] == 1
    assert status["progress"]["detail_rows_completed"] == 2
    assert status["progress"]["detail_rows_expected"] == 2
    inquiry = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "payment.sla.baselines",
        "--operation",
        "get",
        "--identity",
        "one",
    )
    task = call(run_cli, "export", "create", "--plan", inquiry["id"])
    pilots.business_script.append(
        {"status": 200, "body": {"success": True, "resultData": {"id": "one"}}}
    )
    call(run_cli, "export", "run", "--run", task["id"])
    status = call(run_cli, "export", "status", "--run", task["id"])
    assert status["operation"] == "get"
    assert status["progress"]["source_pages"] is None
    assert status["progress"]["root_rows_received"] == 1
    assert status["progress"]["exported_rows"] == 1


def test_two_native_pages_keep_comparable_rate_and_saved_count_beyond_preview(
    run_cli, pilots
):
    from integration.test_leaf_pilots_cli import fx_page

    from dogopencli.domain_contracts import FX_STARTUP_URL

    pilots.href = FX_STARTUP_URL
    inquiry = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "fx.trade",
        "--parameters",
        '{"trade-id":["TEST"]}',
    )
    task = call(run_cli, "export", "create", "--plan", inquiry["id"])
    rows = [{"uniqueId": str(i)} for i in range(1002)]
    pilots.business_script.extend(
        [
            fx_page(rows[:1000], total=1002),
            fx_page(rows[1000:], number=1, total=1002),
        ]
    )
    exported = call(run_cli, "export", "run", "--run", task["id"], "--limit", "1")
    assert len(exported["records"]) == 1
    status = call(run_cli, "export", "status", "--run", task["id"])
    assert status["progress"]["source_pages"] == 2
    assert status["progress"]["request_attempts"] == 2
    assert status["progress"]["source_rows_received"] == 1002
    assert status["progress"]["source_rows_selected"] == 1002
    assert status["progress"]["source_total_rows"] == 1002
    assert status["progress"]["exported_rows"] == 1002
    assert status["progress"]["row_rate_per_second"] > 0
    assert status["progress"]["eta_seconds"] is None
    assert status["progress"]["eta_reason"] == "task_not_running"


def test_settled_incomplete_source_keeps_last_rate_without_forward_eta(run_cli, pilots):
    from integration.test_leaf_pilots_cli import fx_page

    from dogopencli.domain_contracts import FX_STARTUP_URL

    pilots.href = FX_STARTUP_URL
    inquiry = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "fx.trade",
        "--parameters",
        '{"trade-id":["TEST"]}',
    )
    task = call(run_cli, "export", "create", "--plan", inquiry["id"])
    rows = [{"uniqueId": str(i)} for i in range(2000)]
    active = []

    def native_page(payload, index):
        if index == 2:
            import time

            deadline = time.monotonic() + 5
            while True:
                current = call(isolated_cli, "export", "status", "--run", task["id"])
                if current["progress"].get("source_rows_received") == 2000:
                    break
                assert time.monotonic() < deadline, "Heartbeat did not publish pages"
                time.sleep(0.05)
            assert current["effective_state"] == "running"
            assert current["progress"]["eta_seconds"] > 0
            active.append(current)
        return fx_page(
            rows[index * 1000 : (index + 1) * 1000], number=index, total=2001
        )

    pilots.business_handler = native_page
    call(run_cli, "export", "run", "--run", task["id"])
    assert active
    root = Path(os.environ["DOGOPENCLI_CONFIG"]).parent
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    settled = call(run_cli, "export", "status", "--run", task["id"])
    assert settled["effective_state"] == "incomplete"
    assert settled["progress"]["source_rows_received"] == 2000
    assert settled["progress"]["source_total_rows"] == 2001
    assert settled["progress"]["row_rate_per_second"] > 0
    assert settled["progress"]["eta_seconds"] is None
    assert settled["progress"]["eta_reason"] == "task_not_running"
    code, text, _ = run_cli(
        ["workflow", "export", "status", "--run", task["id"], "--format", "text"]
    )
    assert code == 0
    assert "Last source row rate:" in text
    assert "ETA: not applicable" in text
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_watch_errors_keep_default_text_and_explicit_json_envelopes(run_cli, pilots):
    task = prepare(run_cli)
    command = ["workflow", "export", "watch", "--run", task["id"]]
    for flags in (["--interval", "0"], ["--snapshot", "--until-settled"]):
        code, out, err = run_cli([*command, *flags])
        assert code == 2
        assert "Error:\n" in out
        assert "INVALID_ARGUMENT" in out
        code, out, _ = run_cli([*command, *flags, "--format", "json"])
        assert code == 2
        assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    code, out, err = run_cli(
        ["workflow", "export", "watch", "--run", "0" * 32, "--snapshot"]
    )
    assert code == 1
    assert "Error:\n" in out
    assert "WORKFLOW_ERROR" in out
