"""Following reuses only coverage inside its frozen finite interval."""

import json
import shutil
from pathlib import Path

import pytest
from test_workflow_cli import call
from test_workflow_generic_cli import SYNTHETIC_ADAPTER, SYNTHETIC_HISTORY

pytest_plugins = ["integration.test_leaf_pilots_cli"]


@pytest.mark.parametrize(
    "windows,expected",
    [
        (
            [{"from": "2026-10-31", "to": "2026-11-01"}],
            [{"from": "2026-10-01", "to": "2026-10-29"}],
        ),
        (
            [{"from": "2026-10-28", "to": "2026-11-01"}],
            [{"from": "2026-10-01", "to": "2026-10-27"}],
        ),
        (
            [
                {"from": "2026-10-01", "to": "2026-10-29"},
                {"from": "2026-10-31", "to": "2026-11-01"},
            ],
            [],
        ),
        (
            [
                {"from": "2026-10-01", "to": "2026-10-10"},
                {"from": "2026-10-20", "to": "2026-11-01"},
            ],
            [{"from": "2026-10-11", "to": "2026-10-19"}],
        ),
        (
            [
                {"from": "2026-10-01", "to": "2026-10-10"},
                {"from": "2026-10-05", "to": "2026-10-15"},
                {"from": "2026-10-20", "to": "2026-11-01"},
            ],
            [{"from": "2026-10-16", "to": "2026-10-19"}],
        ),
    ],
)
def test_retained_future_coverage_cannot_extend_following_cutoff(
    run_cli, pilots, tmp_path, monkeypatch, windows, expected
):
    from dogopencli import workflow

    monkeypatch.setattr(workflow, "now", lambda: "2026-10-29T12:00:00+00:00")
    pilots.href = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    source = tmp_path / "synthetic"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "leaf_packages/liquidity/reference.banks",
        source,
    )
    manifest = json.loads((source / "leaf.json").read_text())
    manifest["name"] = "synthetic.observations"
    manifest["dataset"]["relation"] = "synthetic_observations"
    manifest["operations"]["list"]["history"] = SYNTHETIC_HISTORY
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
    seed = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.synthetic.observations",
        "--mode",
        "history",
        "--parameters",
        '{"from-date":"20261001","to-date":"20261101"}',
        "--windows",
        json.dumps(windows),
    )
    empty = {
        "status": 200,
        "body": {"resultFlag": True, "count": 0, "result": {"bankVoList": []}},
    }
    pilots.business_script.extend([empty] * len(windows))
    code, _, _ = run_cli(["workflow", "export", "run", "--plan", seed["id"]])
    assert code == 1  # Unplanned seed days remain visible.
    retained = call(run_cli, "history", "show", "--plan", seed["id"])
    assert all(item["state"] == "complete_empty" for item in retained["packages"])
    target = call(
        run_cli,
        "target",
        "create",
        "--plan",
        seed["id"],
        "--policy",
        "following",
        "--timezone",
        "UTC",
    )
    previous_requests = len(pilots.business_requests)
    frozen = call(run_cli, "target", "plan", "--target", target["id"])
    assert frozen["cutoff"] == "2026-10-29"
    planned = [
        call(run_cli, "plan", "show", "--plan", item) for item in frozen["plans"]
    ]
    assert [item["desired_range"] for item in planned] == expected
    assert len(pilots.business_requests) == previous_requests
    pilots.business_script.extend([empty] * len(planned))
    assert call(run_cli, "target", "run", "--execution", frozen["id"])["complete"]
    assert [
        {"from": item["from_date"], "to": item["to_date"]}
        for item in pilots.business_requests[previous_requests:]
    ] == [
        {"from": item["from"].replace("-", ""), "to": item["to"].replace("-", "")}
        for item in expected
    ]
    assert call(run_cli, "history", "show", "--plan", seed["id"]) == retained

    if windows == [{"from": "2026-10-31", "to": "2026-11-01"}]:
        repair = call(run_cli, "repair", "plan", "--plan", seed["id"])
        assert repair["packages"][0]["range"] == {
            "from": "2026-10-01",
            "to": "2026-10-30",
        }
        assert repair["packages"][0]["parameters"] == {
            "from_date": "20261001",
            "to_date": "20261030",
        }
