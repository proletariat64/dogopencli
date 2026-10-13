"""PTR public CLI with synthetic CDP responses and real private SQLite."""

import pytest
from test_sla_cli_sit import list_page, sla_setup  # noqa: F401


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.payment_ptr_cases]\nkind = "cdp"\n')
    return sla_setup


def case(identity="CASE-01", **changes):
    return {
        "id": identity,
        "caseName": "Expected rejection",
        "caseType": "NEGATIVE",
        "verifyResult": True,
        "fundOutAbilityBaselineVO": {
            "financialInstCode": "SYNTHETIC-BANK",
            "debtorCurrency": "USD",
        },
        **changes,
    }


def refresh(run_cli):
    return run_cli(["refresh", "payment", "ptr", "cases"])


def listing(run_cli, *flags):
    return run_cli(["payment", "ptr", "cases", "list", *flags])


def test_refresh_confirms_complete_cases_then_reads_offline(run_cli, envelope, setup):
    rows = [case("CASE-02"), case()]
    setup.state.business_script.extend([list_page(rows), list_page(rows[::-1])])
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    assert setup.state.business_requests == [
        {"pageNo": 0, "pageSize": 5000},
        {"pageNo": 0, "pageSize": 5000},
    ]
    setup.state.running = False
    code, out, _ = listing(run_cli)
    assert code == 0, out
    assert envelope(out)["data"] == rows[::-1]
    assert envelope(out)["meta"]["complete"] is True


def test_live_omits_sensitive_fields_without_replacing_cache(run_cli, envelope, setup):
    old = case(caseName="Cached")
    setup.state.business_script.extend([list_page([old]), list_page([old])])
    assert refresh(run_cli)[0] == 0
    raw = case(
        caseName="Live",
        oboName="SYNTHETIC-PERSON",
        userIban="SYNTHETIC-IBAN",
        futureSecret={"account": "SYNTHETIC-SECRET"},
        fundOutAbilityBaselineVO={
            "financialInstCode": "BANK",
            "debtorAccountNo": "SECRET",
        },
    )
    setup.state.business_script.extend([list_page([raw]), list_page([raw])])
    code, out, err = listing(run_cli, "--live")
    assert code == 0, out
    assert envelope(out)["data"] == [
        case(caseName="Live", fundOutAbilityBaselineVO={"financialInstCode": "BANK"})
    ]
    assert "SECRET" not in out + err
    assert "SYNTHETIC-PERSON" not in out + err
    setup.state.running = False
    assert envelope(listing(run_cli)[1])["data"] == [old]


@pytest.mark.parametrize(
    "failure",
    ["drift", "duplicate", "truncated", "echo", "refusal", "identity", "direction"],
)
def test_failed_refresh_and_live_preserve_old_snapshot(
    run_cli, envelope, setup, failure
):
    old = case(caseName="Old")
    setup.state.business_script.extend([list_page([old]), list_page([old])])
    assert refresh(run_cli)[0] == 0
    bad = {
        "drift": list_page([case(caseName="Changed")]),
        "duplicate": list_page([case(), case()]),
        "truncated": list_page([case()], total_count=2),
        "echo": list_page([case()], page_no=1),
        "refusal": list_page([], success=False),
        "identity": list_page([case(None)]),
        "direction": list_page([case(fundOutAbilityBaselineVO=None)]),
    }[failure]
    for command in (lambda: refresh(run_cli), lambda: listing(run_cli, "--live")):
        setup.state.business_script.extend([list_page([case()]), bad])
        code, out, _ = command()
        assert code == 1, out
        assert envelope(out)["data"] is None
    setup.state.running = False
    assert envelope(listing(run_cli)[1])["data"] == [old]


@pytest.mark.parametrize(
    "flag,path",
    [
        ("id", "id"),
        ("name", "caseName"),
        ("case-type", "caseType"),
        ("channel", "fundOutAbilityBaselineVO.financialInstCode"),
        ("debtor-account", "fundOutAbilityBaselineVO.debtorAccountAliasName"),
        ("debtor-currency", "fundOutAbilityBaselineVO.debtorCurrency"),
        ("creditor-currency", "creditorCurrency"),
        ("clearing-system", "fundOutAbilityBaselineVO.clearingSystemName"),
        ("obo", "obo"),
        ("fvt", "fvt"),
        ("baseline-id", "baselineId"),
        ("creditor-account-alias", "creditorAccountAliasName"),
    ],
)
def test_each_local_filter_matches_whole_value(run_cli, envelope, setup, flag, path):
    rows = [case("A"), case("B")]
    for row, value in zip(rows, ["A", "B"], strict=True):
        if "." in path:
            parent, field = path.split(".")
            row[parent][field] = value
        else:
            row[path] = value
    setup.state.business_script.extend([list_page(rows), list_page(rows)])
    assert refresh(run_cli)[0] == 0
    for live in ([], ["--live"]):
        if live:
            setup.state.business_script.extend([list_page(rows), list_page(rows)])
        code, out, _ = listing(run_cli, *live, f"--{flag}", "A")
        assert code == 0, out
        assert envelope(out)["data"] == [rows[0]]
    assert (
        envelope(listing(run_cli, f"--{flag}", "A", f"--{flag}", "B")[1])["data"]
        == rows
    )
    assert envelope(listing(run_cli, f"--{flag}", "a")[1])["data"] == []
    assert envelope(listing(run_cli, f"--{flag}", "*")[1])["data"] == []
    assert listing(run_cli, f"--{flag}", " ")[0] == 2


def test_empty_complete_library_and_no_detail_or_mutations(run_cli, envelope, setup):
    setup.state.business_script.extend([list_page([]), list_page([])])
    assert refresh(run_cli)[0] == 0
    assert envelope(listing(run_cli)[1])["error"]["code"] == "CACHE_MISS"
    for verb in ("get", "run", "approve", "edit", "verify", "export"):
        assert run_cli(["payment", "ptr", "cases", verb])[0] == 2


def test_help_describe_and_window_are_offline(run_cli, envelope, setup):
    import json

    from jsonschema import validate

    rows = [case("A"), case("B"), case("C")]
    setup.state.business_script.extend([list_page(rows), list_page(rows)])
    assert refresh(run_cli)[0] == 0
    setup.state.running = False
    code, out, _ = run_cli(["describe", "payment", "ptr", "cases", "list"])
    assert code == 0, out
    described = json.loads(out)
    validate(rows, described["data_schema"])
    for path in (
        ["payment", "ptr"],
        ["payment", "ptr", "cases", "list"],
        ["refresh", "payment", "ptr", "cases"],
    ):
        assert run_cli(["help", *path])[0] == 0
    result = envelope(
        listing(
            run_cli,
            "--offset",
            "1",
            "--limit",
            "1",
            "--fields",
            "id",
            "--require-complete",
            "--require-fresh",
        )[1]
    )
    assert result["data"] == [{"id": "B"}]
    assert result["meta"]["complete"] is True
    assert result["meta"]["has_more"] is True
    assert listing(run_cli, "--format", "table", "--limit", "1")[0] == 0
    for flags in (
        ("--all", "--limit", "1"),
        ("--limit", "-1"),
        ("--offset", "-1"),
        ("--fields", " "),
    ):
        assert listing(run_cli, *flags)[0] == 2
    for resource in (
        "networks",
        "beneficiary-accounts",
        "patrol-rules",
        "patrol-batches",
        "automation-batches",
    ):
        assert run_cli(["payment", "ptr", resource, "list"])[0] == 2


def test_missing_cache_and_unavailable_browser_never_fallback(run_cli, envelope, setup):
    code, out, _ = listing(run_cli)
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_MISS"
    setup.state.business_script.extend([list_page([case()]), list_page([case()])])
    assert refresh(run_cli)[0] == 0
    setup.state.running = False
    code, out, _ = listing(run_cli, "--live")
    assert code == 1
    assert envelope(out)["data"] is None
    assert envelope(listing(run_cli)[1])["data"] == [case()]


def test_auth_expiry_and_freshness_are_independent_of_cached_coverage(
    run_cli, envelope, setup, monkeypatch
):
    from datetime import datetime, timedelta, timezone

    from fake_cdp import SSO_URL

    from dogopencli import cli

    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    monkeypatch.setattr(cli, "_now", lambda: now)
    setup.state.business_script.extend([list_page([case()]), list_page([case()])])
    assert refresh(run_cli)[0] == 0
    setup.state.href = SSO_URL
    code, out, _ = listing(run_cli, "--live")
    assert code == 1
    assert envelope(out)["error"]["code"] == "AUTH_REQUIRED"
    monkeypatch.setattr(cli, "_now", lambda: now + timedelta(hours=73))
    body = envelope(listing(run_cli, "--require-complete")[1])
    assert body["data"] == [case()]
    assert body["meta"]["stale"] is True
    code, out, _ = listing(run_cli, "--require-fresh")
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_STALE"


def test_unrelated_configuration_snapshot_cannot_satisfy_ptr_cache(
    run_cli, envelope, setup
):
    from test_payment_rules_sit import page

    with (setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.payment_rules_same_bank_transfer]\nkind = "cdp"\n')
    setup.state.business_script.append(page([{"ruleId": 1}]))
    assert run_cli(["refresh", "payment", "rules", "same-bank-transfer"])[0] == 0
    assert envelope(listing(run_cli)[1])["error"]["code"] == "CACHE_MISS"
    setup.state.business_script.extend([list_page([case()]), list_page([case()])])
    assert refresh(run_cli)[0] == 0
    body = envelope(run_cli(["payment", "rules", "same-bank-transfer", "list"])[1])
    assert body["data"] == [{"ruleId": 1}]
