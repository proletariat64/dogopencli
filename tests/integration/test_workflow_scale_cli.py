"""Bounded imports and offline metadata inspection at the public CLI seam."""

import os
from pathlib import Path

import pytest
from integration.test_workflow_cli import call, payment_page

pytest_plugins = ["integration.test_leaf_pilots_cli"]


def test_status_does_not_read_retained_export_records(run_cli, pilots, monkeypatch):
    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    pilots.business_script.append(payment_page([{"id": "retained"}]))
    exported = call(run_cli, "export", "run", "--plan", plan["id"])
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

    plan = call(run_cli, "plan", "create", "--leaf", "payment.sla.baselines")
    rows = [{"id": str(i), "nested": [None, "1.0000"]} for i in range(25001)]
    for page in range(3):
        response = payment_page(rows[page * 10000 : (page + 1) * 10000])
        response["body"].update(pageNo=page, totalCount=len(rows))
        pilots.business_script.append(response)
    exported = call(run_cli, "export", "run", "--plan", plan["id"], "--limit", "1")
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
    assert result[0] != 0, result
    assert batches, result
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
