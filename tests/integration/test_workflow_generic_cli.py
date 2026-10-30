"""Generic durable exports preserve frozen native scope and local selection."""

import json

from test_workflow_cli import call

pytest_plugins = [
    "integration.leaves.liquidity.test_cash_balances_cli",
    "integration.test_leaf_pilots_cli",
]


def test_history_entity_scope_enumerates_accounts_only_during_export(
    run_cli, installed
):
    from leaves.liquidity.test_cash_balances_cli import (
        directory_page,
        page,
        roster,
        row,
    )

    _, browser, _ = installed
    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.cash.balances",
        "--mode",
        "history",
        "--parameters",
        '{"entity":"ALIPAYGM","from-date":"20260918","to-date":"20260918"}',
    )
    assert not browser.business_requests

    def native(body, _):
        if "bankAccountQueryVO" in body:
            context = json.loads(body["bankAccountQueryVO"])
            return directory_page(
                [roster()][
                    context["rowStart"] : context["rowStart"] + context["pageSize"]
                ]
            )
        return page([row(entity="ALIPAYGM")])

    browser.business_handler = native
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    artifact = call(
        run_cli, "export", "show", "--export", exported["packages"][0]["export_id"]
    )
    assert artifact["records"] == [row(entity="ALIPAYGM")]
    assert artifact["state"] == "complete_nonempty"


def test_any_selection_is_frozen_offline_and_changed_selector_rejected(
    run_cli, installed
):
    import duckdb

    _, browser, config = installed
    database = config / "duckdog.duckdb"
    with duckdb.connect(str(database)) as db:
        db.execute("CREATE TABLE entities(instId VARCHAR)")
        db.execute("INSERT INTO entities VALUES ('ALIPAYGM'), ('OTHER')")
    with (config / "config.toml").open("a") as stream:
        stream.write(
            f'\n[duckdog]\npath="{database}"\n[duckdog.selectors]\n"liquidity/reference/entities"="entities"\n'
        )
    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.cash.balances",
        "--mode",
        "history",
        "--parameters",
        '{"entity":"ANY","from-date":"20260918","to-date":"20260918"}',
    )
    assert plan["parameters"]["_resolved_entities"] == ["ALIPAYGM", "OTHER"]
    assert not browser.business_requests
    with duckdb.connect(str(database)) as db:
        db.execute("DELETE FROM entities WHERE instId='OTHER'")
    code, output, _ = run_cli(
        [
            "workflow",
            "export",
            "run",
            "--run",
            call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        ]
    )
    assert code == 1, output
    status = call(run_cli, "history", "show", "--plan", plan["id"])
    assert (
        "selection" in status["packages"][0]["attempts"][0]["error"]["message"].lower()
    )
    assert not browser.business_requests


def test_local_selection_retains_source_evidence_and_exact_selected_scope(
    run_cli, pilots
):
    from pathlib import Path

    pilots.href = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    source = (
        Path(__file__).resolve().parents[2] / "leaf_packages/liquidity/reference.banks"
    )
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 0, output
    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.reference.banks",
        "--parameters",
        '{"country":"SG"}',
    )
    rows = [
        {"bankId": "selected", "cityCode": "SG"},
        {"bankId": "outside", "cityCode": "US"},
    ]
    pilots.business_script.append(
        {
            "status": 200,
            "body": {"resultFlag": True, "count": 2, "result": {"bankVoList": rows}},
        }
    )
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
    )
    saved = call(run_cli, "export", "show", "--export", exported["id"])
    assert saved["records"] == rows[:1]
    assert saved["metadata"]["scope"] == {
        "native_scope": "",
        "local_filters": {"country": ["SG"]},
    }
    assert saved["metadata"]["source_acquisition"]["reported_total"] == 2
    assert saved["metadata"]["reported_total"] is None
    assert (
        saved["metadata"]["coverage_basis"] == "local_selection_of_native_acquisition"
    )
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    assert (
        call(run_cli, "observation", "show", "--export", exported["id"])["records"]
        == rows[:1]
    )


def test_unrelated_synthetic_variant_uses_common_full_and_range_import(
    run_cli, pilots, tmp_path
):
    import shutil
    from pathlib import Path

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
            "description": "Synthetic date bound.",
        }
        for name in ("from-date", "to-date")
    ]
    (source / "leaf.json").write_text(json.dumps(manifest))
    with (source / "adapter.py").open("a") as stream:
        stream.write(SYNTHETIC_ADAPTER)
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 0, output
    rows = [
        {
            "bankId": "event",
            "nested": [False, {"x": None}],
            "amount": "0.000000000000000001",
        }
    ]
    for mode, parameters in [
        ("full", {}),
        ("history", {"from-date": "20260918", "to-date": "20260920"}),
    ]:
        plan = call(
            run_cli,
            "plan",
            "create",
            "--leaf",
            "liquidity.synthetic.observations",
            "--mode",
            mode,
            "--parameters",
            json.dumps(parameters),
        )
        pilots.business_script.append(
            {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": 1,
                    "result": {"bankVoList": rows},
                },
            }
        )
        exported = call(
            run_cli,
            "export",
            "run",
            "--run",
            call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        )
        identity = (
            exported["packages"][0]["export_id"]
            if mode == "history"
            else exported["id"]
        )
        prepared = call(
            run_cli, "import", "plan", "--export", identity, "--action", "preserve"
        )
        call(run_cli, "import", "apply", "--plan", prepared["id"])
        assert (
            call(run_cli, "observation", "show", "--export", identity)["records"]
            == rows
        )
        if mode == "history":
            assert pilots.business_requests[-1]["from_date"] == "20260918"
            assert pilots.business_requests[-1]["to_date"] == "20260920"
            assert exported["current_history_effect"] == "separate_observations"


def test_declared_custom_get_components_are_durable_without_extra_queries(
    run_cli, pilots
):
    from pathlib import Path

    from leaves.liquidity.test_investment_products_cli import detail, history, row

    from dogopencli.jsonutil import parse

    pilots.href = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    source = (
        Path(__file__).resolve().parents[2]
        / "leaf_packages/liquidity/investment.products"
    )
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 0, output
    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.investment.products",
        "--operation",
        "get",
        "--identity",
        "PHYSICAL-1",
    )
    versions = [row("OLDER", version=1)]
    pilots.business_script.extend([detail(), history(versions)])
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        "--fields",
        "detail",
    )
    prepared = call(
        run_cli, "import", "plan", "--export", exported["id"], "--action", "preserve"
    )
    call(run_cli, "import", "apply", "--plan", prepared["id"])
    code, output, _ = run_cli(
        ["workflow", "observation", "show", "--export", exported["id"]]
    )
    assert code == 0, output
    assert parse(output)["data"]["records"] == [
        {"detail": detail()["body"]["data"], "history": versions}
    ]
    assert len(pilots.business_requests) == 2


def test_get_only_leaf_cannot_be_enrolled_as_dataset(run_cli, pilots):
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "leaf_packages/liquidity/network.route_quotas"
    )
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 0, output
    code, output, _ = run_cli(
        [
            "workflow",
            "plan",
            "create",
            "--leaf",
            "liquidity.network.route_quotas",
        ]
    )
    assert code == 2, output
    assert "operation" in json.loads(output)["error"]["message"]
    assert not pilots.business_requests


SYNTHETIC_ADAPTER = r"""
from dataclasses import replace
from dogopencli.jsonutil import canonical


class SyntheticInquiry(BankInquiry):
    def __init__(self):
        object.__setattr__(
            self,
            "contract",
            replace(
                CAPABILITY.contract,
                path="/syntheticObservations.json",
                allowed_body_keys=CAPABILITY.contract.allowed_body_keys
                | {"from_date", "to_date"},
            ),
        )

    def page_body(self, scope, row_start, page_size):
        return {**super().page_body("", row_start, page_size), **parse(scope)}


class SyntheticAdapter(Adapter):
    def capability(self, parameters):
        return SyntheticInquiry()

    def scope(self, parameters):
        return canonical(
            {
                key: parameters[key]
                for key in ("from_date", "to_date")
                if key in parameters
            }
        )

    def history_contract(self, parameters):
        return {
            "time_basis": "eventDate",
            "interpretation": "calendar_date",
            "format": "%Y%m%d",
            "boundary": "inclusive",
            "timezone": None,
            "from_parameter": "from_date",
            "to_parameter": "to_date",
            "from": parameters["from_date"],
            "to": parameters["to_date"],
            "splitting": "explicit_windows",
            "cross_range_equivalence": False,
        }


adapter = SyntheticAdapter()
"""


def test_synthetic_get_only_export_is_durable_without_dataset_binding(
    run_cli, pilots, tmp_path
):
    import shutil
    from pathlib import Path

    from leaves.liquidity.test_investment_products_cli import detail, history, row

    from dogopencli.browser import cdp
    from dogopencli.jsonutil import parse

    pilots.href = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    source = tmp_path / "get-only"
    shutil.copytree(
        Path(__file__).resolve().parents[2]
        / "leaf_packages/liquidity/investment.products",
        source,
    )
    manifest = json.loads((source / "leaf.json").read_text())
    manifest["name"] = "synthetic.get_only"
    manifest["operations"].pop("list")
    manifest["operations"]["get"].pop("list_binding", None)
    for key in ("dataset", "collection"):
        manifest.pop(key, None)
    (source / "leaf.json").write_text(json.dumps(manifest))
    code, output, _ = run_cli(["plugins", "install", str(source)])
    assert code == 0, output
    plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.synthetic.get_only",
        "--operation",
        "get",
        "--identity",
        "PHYSICAL-1",
    )
    assert plan["binding"] is None
    versions = [row("OLDER", version=1)]
    pilots.business_script.extend([detail(), history(versions)])
    exported = call(
        run_cli,
        "export",
        "run",
        "--run",
        call(run_cli, "export", "create", "--plan", plan["id"])["id"],
        "--fields",
        "detail",
    )
    assert exported["binding"] is None
    assert len(pilots.business_requests) == 2

    def offline(*args, **kwargs):
        raise AssertionError("inspect/import must remain offline")

    # A failed unbound Get can be repaired as an exact inquiry, without
    # acquiring a dataset destination as a side effect.
    failed_plan = call(
        run_cli,
        "plan",
        "create",
        "--leaf",
        "liquidity.synthetic.get_only",
        "--operation",
        "get",
        "--identity",
        "PHYSICAL-1",
    )
    pilots.business_script.append({"status": 500, "body": {}})
    failed_plan_run = call(run_cli, "export", "create", "--plan", failed_plan["id"])
    code, _, _ = run_cli(["workflow", "export", "run", "--run", failed_plan_run["id"]])
    assert code == 1
    repair = call(run_cli, "repair", "plan", "--run", failed_plan_run["id"])
    pilots.business_script.extend([detail(), history(versions)])
    repaired = call(run_cli, "repair", "run", "--repair", repair["id"])
    assert repaired["complete"] is True
    code, output, _ = run_cli(
        ["workflow", "import", "plan", "--repair", repair["id"], "--action", "preserve"]
    )
    assert code == 1, output
    assert "registered dataset destination" in json.loads(output)["error"]["message"]
    enrolled = call(run_cli, "target", "enroll")
    assert all(
        call(run_cli, "plan", "show", "--plan", identity)["leaf"]
        != "liquidity.synthetic.get_only"
        for identity in enrolled["plans"]
    )

    cdp.set_transport_factory(offline)
    code, output, _ = run_cli(
        ["workflow", "export", "show", "--export", exported["id"]]
    )
    assert code == 0, output
    assert parse(output)["data"]["records"] == [
        {"detail": detail()["body"]["data"], "history": versions}
    ]
    status = call(run_cli, "status")
    assert (
        status["last_successful_export"]["id"] == repaired["packages"][0]["export_id"]
    )
    for action in ("preserve", "replace-full", "replace-range", "keyed"):
        code, output, _ = run_cli(
            [
                "workflow",
                "import",
                "plan",
                "--export",
                exported["id"],
                "--action",
                action,
            ]
        )
        assert code == 1, output
        assert (
            "registered dataset destination" in json.loads(output)["error"]["message"]
        )
    for command in ("current", "observation"):
        code, output, _ = run_cli(
            ["workflow", command, "show", "--export", exported["id"]]
        )
        assert code == 1, output
        assert (
            "registered dataset destination" in json.loads(output)["error"]["message"]
        )
    code, output, _ = run_cli(
        ["workflow", "plan", "create", "--leaf", "liquidity.synthetic.get_only"]
    )
    assert code == 2, output
    assert "operation" in json.loads(output)["error"]["message"]
