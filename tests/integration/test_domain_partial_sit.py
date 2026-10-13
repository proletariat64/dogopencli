"""Real CLI/SQLite acceptance for all fixed-list families and VA capacity."""

import importlib

import pytest
from test_sla_cli_sit import sla_setup  # noqa: F401

CASES = (
    (
        "collection_cost_cli",
        "collection_cost",
        ("collection", "cost", "list"),
        ("refresh", "collection", "cost"),
    ),
    (
        "collection_sla_cli",
        "collection_sla",
        ("collection", "sla", "configs", "list"),
        ("refresh", "collection", "sla"),
    ),
    (
        "collection_va_rule_cli",
        "collection_va",
        ("collection", "va", "rules", "list"),
        ("refresh", "collection", "va"),
    ),
    (
        "collection_va_capacity_cli",
        "collection_va_capacity",
        ("collection", "va", "capacity", "list"),
        ("refresh", "collection", "va", "capacity"),
    ),
    (
        "collection_account_isolation",
        "collection_account_isolation",
        ("collection", "account-isolation", "list"),
        ("refresh", "collection", "account-isolation"),
    ),
    *(
        (
            "collection_network_config",
            "collection_" + slug.replace("-", "_"),
            ("collection", slug, "list"),
            ("refresh", "collection", slug),
        )
        for slug in ("clearing-system", "card-template")
    ),
    *(
        (
            "payment_rules",
            "payment_rules_" + slug.replace("-", "_"),
            ("payment", "rules", slug, "list"),
            ("refresh", "payment", "rules", slug),
        )
        for slug in ("same-bank-transfer", "cost-reduction", "retry", "bank-switch")
    ),
)


@pytest.mark.parametrize("module_name,source_key,list_path,refresh_path", CASES)
def test_partial_refresh_replaces_latest_and_offline_quality_is_preserved(  # noqa: F811
    run_cli,
    envelope,
    sla_setup,  # noqa: F811
    module_name,
    source_key,
    list_path,
    refresh_path,
):
    module = importlib.import_module("test_" + module_name + "_sit")
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write(f'\n[sources.{source_key}]\nkind = "cdp"\n')
    state = sla_setup.state
    if module_name == "payment_rules":
        record = module.simple_row(list_path[2])

        def outcome(total):
            response = module.page([record], list_path[2])
            data = response["body"][
                "resultObj" if list_path[2] == "same-bank-transfer" else "data"
            ]
            data["totalCount"] = total
            if list_path[2] == "same-bank-transfer":
                data["totalPages"] = -(-total // 1000)
            return response
    else:
        record = module.row()

        def outcome(total):
            if module_name == "collection_cost_cli":
                return module.page([record], total_count=total)
            return module.page([record], totalCount=total)

    def script(total):
        state.business_script.append(outcome(total))

    script(1)
    assert run_cli(list(refresh_path))[0] == 0
    # Identical row content still publishes changed completeness evidence.
    script(1001)
    code, out, err = run_cli(list(refresh_path))
    assert code == 0, out
    result = envelope(out)
    assert result["error"] is None
    assert result["meta"]["published"] is True
    assert result["data"]["published"] is True
    assert result["meta"]["complete"] is False
    assert result["meta"]["reported_total"] == 1001
    assert result["meta"]["missing_count"] == 1000
    assert result["meta"]["collected_total"] == 1
    assert "INCOMPLETE_RESULT" in err
    before = sla_setup.cache_path.read_bytes()
    requests = len(state.business_requests)
    state.running = False
    for flags in ((), ("--fields", next(iter(record))), ("--format", "table")):
        code, out, err = run_cli([*list_path, *flags])
        assert code == 0, out
        assert "INCOMPLETE_RESULT" in err
        if "table" not in flags:
            meta = envelope(out)["meta"]
            assert meta["complete"] is False
            assert meta["acquisition"]["reasons"] == ["COUNT_SHORTFALL"]
    code, out, _ = run_cli([*list_path, "--require-complete"])
    assert code == 1
    assert envelope(out)["data"] is None
    assert envelope(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert len(state.business_requests) == requests
    assert sla_setup.cache_path.read_bytes() == before
