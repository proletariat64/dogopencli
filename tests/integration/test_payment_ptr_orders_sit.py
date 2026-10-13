"""Bounded PTR order inquiries through public CLI and synthetic CDP."""

from datetime import datetime

import pytest
from test_sla_cli_sit import list_page, sla_setup  # noqa: F401

START = "2025-01-01T00:00:00+08:00"
END = "2025-01-02T00:00:00+08:00"
START_MS = int(datetime.fromisoformat(START).timestamp()) * 1000
END_MS = int(datetime.fromisoformat(END).timestamp()) * 1000
WINDOW = ["--updated-from", START, "--updated-to", END]


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.payment_ptr_orders]\nkind = "cdp"\n')
    return sla_setup


def order(identity, modified, **changes):
    return {
        "ptrOrderId": identity,
        "gmtModified": modified,
        "orderStatus": "FAILED",
        "verifyStatus": "VERIFIED",
        "ptrFinalResult": "PASS",
        "productionTrialRunFundOutAbilityVO": {"financialInstCode": "SYNTHETIC"},
        **changes,
    }


def page(rows, **changes):
    return list_page(rows, page_size=500, **changes)


def refresh(run_cli, window=WINDOW):
    return run_cli(["refresh", "payment", "ptr", "orders", *window])


def listing(run_cli, *flags, window=WINDOW):
    return run_cli(["payment", "ptr", "orders", "list", *window, *flags])


def test_padded_acquisition_publishes_only_exact_half_open_scope(
    run_cli, envelope, setup
):
    rows = [
        order("BEFORE", START_MS - 1),
        order("START", START_MS),
        order("INSIDE", START_MS + 1),
        order("LAST", END_MS - 1),
        order("END", END_MS),
    ]
    setup.state.business_script.extend([page(rows), page(rows[::-1])])
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    assert (
        setup.state.business_requests
        == [
            {
                "pageNo": 0,
                "pageSize": 500,
                "modifiedTimeBegin": "2024-12-31 23:59:59",
                "modifiedTimeEnd": "2025-01-02 00:00:01",
            }
        ]
        * 2
    )
    setup.state.running = False
    code, out, _ = listing(run_cli, "--limit", "0")
    assert code == 0, out
    assert envelope(out)["data"] == [rows[2], rows[3], rows[1]]
    assert envelope(out)["meta"]["complete"] is True


def test_exact_windows_have_independent_snapshots(run_cli, envelope, setup):
    first = order("FIRST", START_MS + 500)
    setup.state.business_script.extend([page([first]), page([first])])
    assert refresh(run_cli)[0] == 0
    next_window = ["--updated-from", END, "--updated-to", "2025-01-03T00:00:00+08:00"]
    unmatched = envelope(listing(run_cli, window=next_window)[1])
    assert unmatched["data"] == []
    assert unmatched["meta"]["requested_coverage"] is False
    second = order("SECOND", END_MS + 500)
    setup.state.business_script.extend([page([second]), page([second])])
    assert refresh(run_cli, next_window)[0] == 0
    setup.state.running = False
    assert envelope(listing(run_cli)[1])["data"] == []
    assert envelope(run_cli(["payment", "ptr", "orders", "list"])[1])["data"] == [
        second
    ]
    assert envelope(listing(run_cli, window=next_window)[1])["data"] == [second]


@pytest.mark.parametrize(
    "bad_from,bad_to",
    [
        ("2025-01-01", END),
        ("2025-01-01T00:00:00Z", END),
        ("2025-01-01T00:00:00.001+08:00", END),
        (START, START),
        (END, START),
        (START, "2025-02-02T00:00:00+08:00"),
        ("9998-01-01T00:00:00+08:00", "9998-01-02T00:00:00+08:00"),
    ],
)
def test_invalid_bounds_fail_before_browser_or_source_access(
    run_cli, envelope, setup, bad_from, bad_to
):
    window = ["--updated-from", bad_from, "--updated-to", bad_to]
    setup.state.running = False
    for result in (refresh(run_cli, window), listing(run_cli, "--live", window=window)):
        assert result[0] == 2
        assert envelope(result[1])["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.business_requests == []


@pytest.mark.parametrize(
    "failure", ["drift", "padding-drift", "overflow", "outside", "duplicate", "refusal"]
)
def test_failed_full_padded_acquisition_preserves_window(
    run_cli, envelope, setup, failure
):
    old = order("OLD", START_MS + 1)
    setup.state.business_script.extend([page([old]), page([old])])
    assert refresh(run_cli)[0] == 0
    inside = order("NEW", START_MS + 2)
    padding = order("PADDING", START_MS - 500)
    bad = {
        "drift": page([order("NEW", START_MS + 2, ptrFinalResult="N"), padding]),
        "padding-drift": page(
            [inside, order("PADDING", START_MS - 500, ptrFinalResult="N")]
        ),
        "overflow": page([inside, padding], total_count=501),
        "outside": page([inside, order("OUTSIDE", START_MS - 1001)]),
        "duplicate": page([inside, inside]),
        "refusal": page([], success=False),
    }[failure]
    for command in (lambda: refresh(run_cli), lambda: listing(run_cli, "--live")):
        setup.state.business_script.extend([page([inside, padding]), bad])
        code, out, _ = command()
        assert code == 1, out
        assert envelope(out)["data"] is None
    setup.state.running = False
    assert envelope(listing(run_cli)[1])["data"] == [old]


@pytest.mark.parametrize(
    "flag,path",
    [
        ("id", "ptrOrderId"),
        ("case-id", "caseId"),
        ("channel", "productionTrialRunFundOutAbilityVO.financialInstCode"),
        ("debtor-account", "productionTrialRunFundOutAbilityVO.debtorAccountAliasName"),
        ("clearing-system", "productionTrialRunFundOutAbilityVO.clearingSystemName"),
        ("debtor-currency", "debtorAmount.currencyCode"),
        ("creditor-currency", "creditorCurrency"),
        ("order-status", "orderStatus"),
        ("verify-status", "verifyStatus"),
        ("final-result", "ptrFinalResult"),
    ],
)
def test_each_business_filter_has_live_and_cache_equivalence(
    run_cli, envelope, setup, flag, path
):
    rows = [order("A", START_MS + 1), order("B", START_MS + 2)]
    for row, value in zip(rows, ["A", "B"], strict=True):
        if "." in path:
            parent, field = path.split(".")
            row.setdefault(parent, {})[field] = value
        else:
            row[path] = value
    setup.state.business_script.extend([page(rows), page(rows)])
    assert refresh(run_cli)[0] == 0
    for live in ([], ["--live"]):
        if live:
            setup.state.business_script.extend([page(rows), page(rows)])
        code, out, _ = listing(run_cli, *live, f"--{flag}", "A")
        assert code == 0, out
        assert envelope(out)["data"] == [rows[0]]
    assert (
        envelope(listing(run_cli, f"--{flag}", "A", f"--{flag}", "B")[1])["data"]
        == rows
    )
    assert envelope(listing(run_cli, f"--{flag}", "a")[1])["data"] == []
    assert listing(run_cli, f"--{flag}", " ")[0] == 2


def test_live_does_not_publish_and_structured_personal_fields_are_omitted(
    run_cli, envelope, setup
):
    raw = order(
        "A",
        START_MS + 1,
        failureReason="Synthetic operational text",
        creditorAccountNo="SYNTHETIC-PRIVATE",
        oboName="SYNTHETIC-NAME",
    )
    setup.state.business_script.extend([page([raw]), page([raw])])
    code, out, err = listing(run_cli, "--live")
    assert code == 0, out
    assert "SYNTHETIC-PRIVATE" not in out + err
    assert "SYNTHETIC-NAME" not in out + err
    assert envelope(out)["data"][0]["failureReason"] == "Synthetic operational text"
    assert envelope(listing(run_cli)[1])["error"]["code"] == "CACHE_MISS"


def test_empty_scope_and_required_bounds_in_offline_help(run_cli, envelope, setup):
    import json

    from jsonschema import validate

    setup.state.business_script.extend([page([]), page([])])
    assert refresh(run_cli)[0] == 0
    assert envelope(listing(run_cli)[1])["error"]["code"] == "CACHE_MISS"
    setup.state.running = False
    code, out, _ = run_cli(["describe", "payment", "ptr", "orders", "list"])
    assert code == 0
    validate([order("A", START_MS + 1)], json.loads(out)["data_schema"])
    for path in (
        ["payment", "ptr", "orders", "list"],
        ["refresh", "payment", "ptr", "orders"],
    ):
        help_doc = json.loads(run_cli(["help", *path])[1])
        required = {o["name"] for o in help_doc["options"] if o["required"]}
        assert required == set()
        assert run_cli(path)[0] == (2 if path[0] == "refresh" else 1)
    for verb in ("get", "approve", "verify", "retry", "export"):
        assert run_cli(["payment", "ptr", "orders", verb])[0] == 2


def test_equivalent_numeric_offsets_share_the_baseline_scope_and_cache(
    run_cli, envelope, setup
):
    rows = [order("A", START_MS + 1)]
    setup.state.business_script.extend([page(rows), page(rows)])
    assert refresh(run_cli)[0] == 0
    baseline_requests = list(setup.state.business_requests)
    setup.state.running = False
    # 2024-12-31T16:00:00+00:00 is the same instant as the +08:00 baseline.
    equivalent = [
        "--updated-from",
        "2024-12-31T16:00:00+00:00",
        "--updated-to",
        "2025-01-01T16:00:00+00:00",
    ]
    code, out, _ = listing(run_cli, "--limit", "0", window=equivalent)
    assert code == 0, out
    assert envelope(out)["data"] == rows
    # The equivalent refresh emits byte-identical padded native requests.
    setup.state.running = True
    setup.state.business_script.extend([page(rows), page(rows)])
    assert refresh(run_cli, equivalent)[0] == 0
    assert setup.state.business_requests[-2:] == baseline_requests


def test_equivalent_offset_refresh_hint_uses_the_normalized_window(
    run_cli, envelope, setup
):
    equivalent = [
        "--updated-from",
        "2024-12-31T16:00:00+00:00",
        "--updated-to",
        "2025-01-01T16:00:00+00:00",
    ]
    missing = envelope(listing(run_cli, window=equivalent)[1])["error"]
    assert missing["code"] == "CACHE_MISS"
    assert f"--updated-from {START}" in missing["message"]
    assert f"--updated-to {END}" in missing["message"]


@pytest.mark.parametrize(
    "bad",
    [
        "2025-01-01T00:00:00-00:00",  # unknown-offset form
        "2025-01-01T00:00:00",  # missing offset
        "2025-01-01T00:00:00+0800",  # compact offset
    ],
)
def test_offset_form_rejections_precede_browser_and_source(
    run_cli, envelope, setup, bad
):
    window = ["--updated-from", bad, "--updated-to", END]
    for result in (refresh(run_cli, window), listing(run_cli, "--live", window=window)):
        assert result[0] == 2
        assert envelope(result[1])["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.business_requests == []


def test_help_declares_offset_normalization(run_cli, envelope, setup):
    import json

    for path in (
        ["payment", "ptr", "orders", "list"],
        ["refresh", "payment", "ptr", "orders"],
    ):
        code, out, _ = run_cli(["help", *path])
        assert code == 0
        help_doc = json.loads(out)
        options = {o["name"]: o for o in help_doc["options"]}
        for name in ("updated_from", "updated_to"):
            assert "+08:00" in options[name]["summary"]
        constraints = " ".join(help_doc.get("constraints", []))
        assert "equivalent" in constraints and "+08:00" in constraints
