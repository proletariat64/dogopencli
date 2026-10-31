"""Batch 3 native temporal windows through the public workflow CLI."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def install(run_cli, name):
    code, out, error = run_cli(
        ["plugins", "install", str(ROOT / "leaf_packages/liquidity" / name)]
    )
    assert code == 0, out + error


def plan(run_cli, name, parameters, windows=None, code=0):
    args = [
        "workflow",
        "plan",
        "create",
        "--leaf",
        "liquidity." + name,
        "--mode",
        "history",
        "--parameters",
        json.dumps(parameters),
    ]
    if windows is not None:
        args += ["--windows", json.dumps(windows)]
    status, out, error = run_cli(args)
    assert status == code, out + error
    return json.loads(out)


def test_demands_inclusive_equal_second_has_explicit_beijing_axis(run_cli):
    install(run_cli, "operations.demands")
    result = plan(
        run_cli,
        "operations.demands",
        {
            "from-time": "2026-04-01T00:00:00",
            "to-time": "2026-04-01T00:00:00",
        },
    )["data"]
    assert result["desired_range"] == {
        "from": "2026-03-31T16:00:00.000Z",
        "to": "2026-03-31T16:00:00.000Z",
    }
    assert result["contract"]["time_basis"] == "executeTime"
    assert result["contract"]["timezone"] == "GMT+08:00"
    assert result["native_scope"] == {
        "tntInstId": "GUAPW3SG",
        "source": ["FUND_REQUIRE"],
        "startExecuteTime": "2026-04-01 00:00:00",
        "endExecuteTime": "2026-04-01 00:00:00",
    }


@pytest.mark.parametrize("name", ["risk.anomalies", "risk.events"])
def test_risk_calendar_windows_are_inclusive_beijing_days_on_utc_wire(run_cli, name):
    install(run_cli, name)
    result = plan(
        run_cli,
        name,
        {"from-date": "20261026", "to-date": "20261027"},
        [
            {"from": "2026-10-26", "to": "2026-10-26"},
            {"from": "2026-10-27", "to": "2026-10-27"},
        ],
    )["data"]
    assert result["desired_range"] == {"from": "2026-10-26", "to": "2026-10-27"}
    assert result["contract"]["time_basis"] == "gmtCreate"
    assert result["contract"]["timezone"] == "GMT+08:00"
    assert result["contract"]["cross_range_equivalence"] is False
    first, second = result["packages"]
    assert first["native_scope"] == {
        "tntInstId": "GUAPW3SG",
        "riskMode": "RISK_ALERT" if name.endswith("anomalies") else "RISK_EVENT",
        "timeZone": "GMT+08",
        "startTime": "2026-10-25 16:00:00",
        "endTime": "2026-10-26 15:59:59",
    }
    assert second["native_scope"]["startTime"] == "2026-10-26 16:00:00"
    assert second["native_scope"]["endTime"] == "2026-10-27 15:59:59"


def test_rfqs_start_axis_has_required_inclusive_compact_wire_pair(run_cli):
    install(run_cli, "investment.rfqs")
    result = plan(
        run_cli,
        "investment.rfqs",
        {
            "from-date": "2026-04-15",
            "to-date": "2026-04-15",
        },
    )["data"]
    assert result["desired_range"] == {"from": "2026-04-15", "to": "2026-04-15"}
    assert result["contract"]["time_basis"] == "inquiryStartTime"
    assert result["contract"]["timezone"] == "GMT+08:00"
    assert result["native_scope"] == {
        "inquiryType": "TARGET_RFQ",
        "inquiryStartDate": "20260415",
        "inquiryEndDate": "20260415",
    }
    result = plan(run_cli, "investment.rfqs", {"from-date": "2026-04-15"}, code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "name,parameters",
    [
        (
            "operations.demands",
            {"from-time": "2026-04-01T00:00:00.001", "to-time": "2026-04-01T00:00:01"},
        ),
        (
            "operations.demands",
            {
                "from-time": "2026-04-01T00:00:00+08:00",
                "to-time": "2026-04-01T00:00:01",
            },
        ),
        (
            "operations.demands",
            {"from-time": "2026-04-02T00:00:00", "to-time": "2026-04-01T00:00:01"},
        ),
        (
            "operations.demands",
            {
                "execute-from": "2026-04-01T00:00:00",
                "execute-to": "2026-04-01T00:00:01",
            },
        ),
        ("investment.rfqs", {"from-date": "2026-04-16", "to-date": "2026-04-15"}),
        ("investment.rfqs", {"from-date": "20260415", "to-date": "20260415"}),
        ("risk.anomalies", {"from-date": "20261026", "to-date": "20261025"}),
        ("risk.events", {"from-date": "20260230", "to-date": "20260301"}),
    ],
)
def test_batch3_rejects_invalid_public_ranges_before_execution(
    run_cli, name, parameters
):
    install(run_cli, name)
    result = plan(run_cli, name, parameters, code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "window",
    [
        {"from": "2026-03-31T16:00:00.001Z", "to": "2026-03-31T16:00:01.000Z"},
        {"from": "2026-03-31T16:00:00.000Z", "to": "2026-03-31T16:00:00.999Z"},
        {"from": "2026-04-01T00:00:00.000+08:00", "to": "2026-03-31T16:00:01.000Z"},
        {"from": "2026-03-31T16:00:00Z", "to": "2026-03-31T16:00:01.000Z"},
    ],
)
def test_demands_rejects_noncanonical_or_fractional_native_windows(run_cli, window):
    install(run_cli, "operations.demands")
    result = plan(
        run_cli,
        "operations.demands",
        {
            "from-time": "2026-04-01T00:00:00",
            "to-time": "2026-04-01T00:00:01",
        },
        [window],
        code=2,
    )
    assert result["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("name", ["investment.rfqs", "risk.anomalies", "risk.events"])
@pytest.mark.parametrize(
    "window",
    [
        {"from": "20260415", "to": "20260415"},
        {"from": "2026-04-15T00:00:00.000Z", "to": "2026-04-15T00:00:00.000Z"},
    ],
)
def test_calendar_host_windows_accept_only_iso_dates(run_cli, name, window):
    install(run_cli, name)
    parameters = {
        "from-date": "2026-04-15" if name == "investment.rfqs" else "20260415",
        "to-date": "2026-04-15" if name == "investment.rfqs" else "20260415",
    }
    result = plan(run_cli, name, parameters, [window], code=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("name", ["risk.anomalies", "risk.events"])
@pytest.mark.parametrize(
    "day,lower,upper",
    [
        ("20260308", "2026-03-07 16:00:00", "2026-03-08 15:59:59"),
        ("20251102", "2025-11-01 16:00:00", "2025-11-02 15:59:59"),
    ],
)
def test_risk_query_clock_stays_utc_across_pacific_dst(
    run_cli, name, day, lower, upper
):
    install(run_cli, name)
    result = plan(run_cli, name, {"from-date": day, "to-date": day})["data"]
    assert result["native_scope"]["startTime"] == lower
    assert result["native_scope"]["endTime"] == upper


def test_demands_cross_day_window_preserves_inclusive_seconds(run_cli):
    install(run_cli, "operations.demands")
    result = plan(
        run_cli,
        "operations.demands",
        {
            "from-time": "2026-04-01T23:59:59",
            "to-time": "2026-04-02T00:00:01",
        },
        [{"from": "2026-04-01T16:00:00.000Z", "to": "2026-04-01T16:00:01.000Z"}],
    )["data"]
    assert result["desired_range"] == {
        "from": "2026-04-01T15:59:59.000Z",
        "to": "2026-04-01T16:00:01.000Z",
    }
    package = result["packages"][0]
    assert package["parameters"]["from_time"] == "2026-04-02T00:00:00"
    assert package["parameters"]["to_time"] == "2026-04-02T00:00:01"
    assert package["native_scope"]["source"] == ["FUND_REQUIRE"]


def test_batch3_inventory_preserves_full_and_get_only_package_support():
    from dogopencli.leaves.package import validate_package

    manifests = {}
    for root in (ROOT / "leaf_packages", ROOT / "src/dogopencli/leaf_packages"):
        for source in root.glob("*/*/leaf.json"):
            with validate_package(source.parent) as package:
                value = package.manifest
                manifests[value["domain"] + "." + value["name"]] = value
    temporal = {
        key
        for key, value in manifests.items()
        if "history" in value["operations"].get("list", {})
    }
    full = {
        key
        for key, value in manifests.items()
        if "list" in value["operations"] and key not in temporal
    }
    get_only = {
        key for key, value in manifests.items() if "list" not in value["operations"]
    }
    retained = {
        "liquidity.operations.decisions",
        "liquidity.forecast.accuracy",
        "liquidity.investment.holdings",
    }
    assert len(manifests) == 91
    assert len(temporal) == 31
    assert retained <= full
    assert len(full - retained) == 52
    assert len(get_only) == 5
    assert all(
        "history" not in manifests[key]["operations"].get("get", {}) for key in get_only
    )


@pytest.mark.parametrize(
    "missing", ["start-from", "start-to", "created-from", "created-to"]
)
def test_decisions_still_requires_all_four_native_bounds(run_cli, missing):
    install(run_cli, "operations.decisions")
    parameters = {
        "start-from": "2026-04-01T00:00:00",
        "start-to": "2026-04-02T00:00:00",
        "created-from": "2026-04-01T00:00:00",
        "created-to": "2026-04-02T00:00:00",
    }
    parameters.pop(missing)
    status, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity.operations.decisions",
            "--parameters",
            json.dumps(parameters),
        ]
    )
    assert status == 2, out + error
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "name,parameters,native_field,native_value",
    [
        (
            "forecast.accuracy",
            {"account-alias": "ACCOUNT", "record-date": "2026-03-08"},
            "record_date",
            "2026-03-08",
        ),
        ("investment.holdings", {"date": "2026-10-03"}, "date", "20261003"),
    ],
)
def test_snapshots_remain_single_date_full_observations(
    run_cli, name, parameters, native_field, native_value
):
    install(run_cli, name)
    status, out, error = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity." + name,
            "--parameters",
            json.dumps(parameters),
        ]
    )
    assert status == 0, out + error
    result = json.loads(out)["data"]
    assert result["mode"] == "full"
    assert result["native_scope"][native_field] == native_value
    failed = plan(run_cli, name, parameters, code=2)
    assert failed["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "name,parameters",
    [
        (
            "operations.demands",
            {"from-time": "2026-04-01T00:00:00", "to-time": "2026-04-01T00:00:01"},
        ),
        ("investment.rfqs", {"from-date": "2026-04-15", "to-date": "2026-04-15"}),
        ("risk.anomalies", {"from-date": "20261026", "to-date": "20261026"}),
        ("risk.events", {"from-date": "20261026", "to-date": "20261026"}),
    ],
)
def test_changed_temporal_binding_rejects_saved_plan_without_rewriting_it(
    run_cli,
    tmp_path,
    monkeypatch,
    name,
    parameters,
):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.delenv("DOGOPENCLI_CONFIG_DIR", raising=False)
    install(run_cli, name)
    original = plan(run_cli, name, parameters)["data"]
    status, out, error = run_cli(
        [
            "workflow",
            "export",
            "create",
            "--plan",
            original["id"],
        ]
    )
    assert status == 0, out + error
    export_run = json.loads(out)["data"]
    manifest_path = tmp_path / "plugins/liquidity" / name / "leaf.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["operations"]["list"]["history"]["time_basis"] = "changed_native_axis"
    manifest_path.write_text(json.dumps(manifest))
    status, out, error = run_cli(
        [
            "workflow",
            "export",
            "run",
            "--run",
            export_run["id"],
        ]
    )
    assert status != 0, out + error
    status, out, error = run_cli(
        [
            "workflow",
            "history",
            "show",
            "--plan",
            original["id"],
        ]
    )
    assert status == 0, out + error
    state = json.loads(out)["data"]
    assert state["packages"][0]["attempts"][0]["error"]["message"] == (
        "Native history contract changed; create a new plan"
    )
    status, out, error = run_cli(
        [
            "workflow",
            "plan",
            "show",
            "--plan",
            original["id"],
        ]
    )
    assert status == 0, out + error
    assert json.loads(out)["data"] == original
