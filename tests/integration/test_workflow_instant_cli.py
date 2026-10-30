"""Instant observations use discrete milliseconds through public workflow stages."""

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytest_plugins = ["integration.test_leaf_handbook"]


@pytest.fixture
def sample_source(tmp_path, request):
    source = tmp_path / "instant-sample"
    shutil.copytree(ROOT / "tools/leaf-dev/example-history", source)
    manifest = json.loads((source / "leaf.json").read_text())
    manifest["name"] = "sample.instant"
    manifest["dataset"]["relation"] = "sample_instants"
    operation = manifest["operations"]["list"]
    for parameter in operation["parameters"]:
        parameter["name"] = parameter["name"].replace("-date", "-time")
        parameter["temporal_role"] = (
            "history_from" if parameter["name"] == "from-time" else "history_to"
        )
    operation["history"].update(
        interpretation="instant",
        from_parameter="from-time",
        to_parameter="to-time",
        precision="millisecond",
    )
    if getattr(request, "param", None) == "freeze":
        operation["freeze_parameters"] = True
        for parameter in operation["parameters"]:
            parameter["required"] = False
    (source / "leaf.json").write_text(json.dumps(manifest))
    with (source / "adapter.py").open("a") as stream:
        stream.write("""
from dogopencli.temporal import normalize_utc_milliseconds

class InstantAdapter(Adapter):
    def history_bounds(self, parameters):
        return {"from": normalize_utc_milliseconds(parameters["from_time"]),
                "to": normalize_utc_milliseconds(parameters["to_time"])}
    def history_parameters(self, bounds):
        return {"from_time": bounds["from"], "to_time": bounds["to"]}
    def capability(self, parameters):
        bounds = self.history_bounds(parameters)
        if bounds["from"] > bounds["to"]:
            raise CliError(INVALID_ARGUMENT, "Reversed instant range", exit_code=2)
        return CAPABILITY
    def scope(self, parameters):
        return canonical({"fromDate": parameters["from_time"],
                          "toDate": parameters["to_time"]})
adapter = InstantAdapter()
""")
    if getattr(request, "param", None) == "freeze":
        with (source / "adapter.py").open("a") as stream:
            stream.write("""
def freeze(parameters):
    from dogopencli.workflow import now
    result = dict(parameters)
    result.setdefault("from_time", now()[:10] + "T00:00:00.000Z")
    result.setdefault("to_time", now()[:10] + "T23:59:59.999Z")
    return result

def filter_records(records, parameters):
    left, right = parameters.get("from_time"), parameters.get("to_time")
    return [row for row in records if
            (not left or row["eventTime"] >= left)
            and (not right or row["eventTime"] <= right)]
adapter.freeze_parameters = freeze
adapter.filter = filter_records
""")
    return source


def plan(cli, windows=None):
    flags = ["--windows", json.dumps(windows)] if windows is not None else []
    return cli(
        "workflow",
        "plan",
        "create",
        "--leaf",
        "collection.sample.instant",
        "--mode",
        "history",
        "--parameters",
        '{"from-time":"2026-10-16T23:59:59.998Z","to-time":"2026-10-17T00:00:00.002Z"}',
        *flags,
    )["data"]


def response(rows):
    return {
        "status": 200,
        "body": {
            "success": True,
            "rows": rows,
            "pageNo": 0,
            "pageSize": 2,
            "total": len(rows),
        },
    }


def test_instant_gap_repair_and_preserve_import_keep_one_millisecond(handbook):
    cli, browser, _ = handbook
    frozen = plan(
        cli,
        [
            {"from": "2026-10-16T23:59:59.998Z", "to": "2026-10-16T23:59:59.999Z"},
            {"from": "2026-10-17T00:00:00.001Z", "to": "2026-10-17T00:00:00.002Z"},
        ],
    )
    assert frozen["contract"]["interpretation"] == "instant"
    assert frozen["contract"]["precision"] == "millisecond"
    assert "format" not in frozen["contract"]
    browser.business_script.extend([response([]), response([])])
    cli("workflow", "export", "run", "--plan", frozen["id"], code=1)
    status = cli("workflow", "history", "show", "--plan", frozen["id"])["data"]
    missing = [{"from": "2026-10-17T00:00:00.000Z", "to": "2026-10-17T00:00:00.000Z"}]
    assert status["uncovered_ranges"] == missing
    assert status["overlapping_packages"] == []
    repair = cli("workflow", "repair", "plan", "--plan", frozen["id"])["data"]
    assert [item["range"] for item in repair["packages"]] == missing
    rows = [
        {"id": "midnight", "eventTime": "2026-10-17T00:00:00.000Z", "amount": "0.000"}
    ]
    browser.business_script.append(response(rows))
    assert (
        cli("workflow", "export", "run", "--plan", repair["id"])["data"]["complete"]
        is True
    )
    artifact_id = cli("workflow", "repair", "show", "--repair", repair["id"])["data"][
        "packages"
    ][0]["export_id"]
    prepared = cli(
        "workflow", "import", "plan", "--export", artifact_id, "--action", "preserve"
    )["data"]
    count = len(browser.business_requests)
    cli("workflow", "import", "apply", "--plan", prepared["id"])
    assert (
        cli("workflow", "observation", "show", "--export", artifact_id)["data"][
            "records"
        ]
        == rows
    )
    assert len(browser.business_requests) == count
    assert browser.business_requests[-1]["fromDate"] == "2026-10-17T00:00:00.000Z"


def test_instant_overlap_and_following_rejection(
    handbook,
):
    cli, browser, _ = handbook
    frozen = plan(
        cli,
        [
            {"from": "2026-10-16T23:59:59.998Z", "to": "2026-10-17T00:00:00.001Z"},
            {"from": "2026-10-17T00:00:00.001Z", "to": "2026-10-17T00:00:00.002Z"},
        ],
    )
    status = cli("workflow", "history", "show", "--plan", frozen["id"])["data"]
    assert status["overlapping_packages"] == [
        [item["id"] for item in frozen["packages"]]
    ]
    rejected = cli(
        "workflow",
        "target",
        "create",
        "--plan",
        frozen["id"],
        "--policy",
        "following",
        "--timezone",
        "UTC",
        code=2,
    )
    assert "Following instant history is not supported" in rejected["error"]["message"]
    assert not browser.business_requests


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-17",
        "2026-10-17T00:00:00Z",
        "2026-10-17T00:00:00.0000Z",
        "2026-10-17T08:00:00.000+08:00",
    ],
)
def test_instant_windows_reject_noncanonical_bounds_without_transport(handbook, value):
    cli, browser, _ = handbook
    rejected = cli(
        "workflow",
        "plan",
        "create",
        "--leaf",
        "collection.sample.instant",
        "--mode",
        "history",
        "--parameters",
        '{"from-time":"2026-10-16T23:59:59.998Z","to-time":"2026-10-17T00:00:00.002Z"}',
        "--windows",
        json.dumps([{"from": value, "to": "2026-10-17T00:00:00.002Z"}]),
        code=2,
    )
    assert rejected["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests


@pytest.mark.parametrize("sample_source", ["freeze"], indirect=True)
def test_plan_pins_leaf_defaults_and_bare_cache_replay_does_not_freeze(
    handbook, monkeypatch
):
    from dogopencli import workflow

    cli, browser, _ = handbook
    monkeypatch.setattr(workflow, "now", lambda: "2026-10-16T12:00:00+00:00")
    frozen = cli("workflow", "plan", "create", "--leaf", "collection.sample.instant")[
        "data"
    ]
    assert frozen["parameters"] == {
        "from_time": "2026-10-16T00:00:00.000Z",
        "to_time": "2026-10-16T23:59:59.999Z",
    }
    monkeypatch.setattr(workflow, "now", lambda: "2026-10-17T12:00:00+00:00")
    rows = [{"id": "one", "eventTime": "2026-10-16T01:00:00.000Z"}]
    browser.business_script.append(response(rows))
    exported = cli("workflow", "export", "run", "--plan", frozen["id"])["data"]
    assert exported["records"] == rows
    assert browser.business_requests[-1]["fromDate"] == "2026-10-16T00:00:00.000Z"
    explicit = cli(
        "workflow",
        "plan",
        "create",
        "--leaf",
        "collection.sample.instant",
        "--parameters",
        '{"from-time":"2026-10-15T00:00:00.000Z","to-time":"2026-10-15T00:00:00.001Z"}',
    )["data"]
    assert explicit["parameters"]["from_time"] == "2026-10-15T00:00:00.000Z"
    monkeypatch.setattr(workflow, "now", lambda: "2026-10-16T12:00:00+00:00")
    browser.business_script.append(response(rows))
    cli("collection", "refresh", "sample.instant")
    monkeypatch.setattr(workflow, "now", lambda: "2026-10-17T12:00:00+00:00")
    before = len(browser.business_requests)
    assert cli("collection", "list", "sample.instant")["data"] == rows
    assert len(browser.business_requests) == before


def test_instant_conversion_rejects_unrepresentable_windows(handbook):
    cli, browser, config = handbook
    adapter = config / "plugins/collection/sample.instant/adapter.py"
    adapter.write_text(
        adapter.read_text()
        + """
def rounded(bounds):
    return {"from_time": bounds["from"][:19] + "Z",
            "to_time": bounds["to"][:19] + "Z"}
adapter.history_parameters = rounded
"""
    )
    rejected = cli(
        "workflow",
        "plan",
        "create",
        "--leaf",
        "collection.sample.instant",
        "--mode",
        "history",
        "--parameters",
        '{"from-time":"2026-10-16T01:00:00.123Z","to-time":"2026-10-16T01:00:00.124Z"}',
        code=2,
    )
    assert "does not preserve the requested range" in rejected["error"]["message"]
    assert not browser.business_requests


@pytest.mark.parametrize("sample_source", ["freeze"], indirect=True)
@pytest.mark.parametrize(
    "body",
    [
        'return {**parameters, "unknown": "value"}',
        'parameters["from_time"] = "2026-10-15T00:00:00.000Z"; return parameters',
        'return {**parameters, "from_time": "2026-10-15T00:00:00.000Z"}',
        'return {**parameters, "to_time": 1}',
    ],
)
def test_default_freezing_rejects_mutation_unknown_keys_and_wrong_types(handbook, body):
    cli, browser, config = handbook
    adapter = config / "plugins/collection/sample.instant/adapter.py"
    adapter.write_text(
        adapter.read_text()
        + f"\ndef bad_freeze(parameters):\n    {body}\n"
        + "adapter.freeze_parameters = bad_freeze\n"
    )
    rejected = cli(
        "workflow",
        "plan",
        "create",
        "--leaf",
        "collection.sample.instant",
        "--parameters",
        '{"from-time":"2026-10-16T00:00:00.000Z"}',
        code=2,
    )
    assert rejected["error"]["code"] == "INVALID_ARGUMENT"
    assert not browser.business_requests
