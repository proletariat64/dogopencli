"""Issue #129 account-alias renames: public CLI + fake CDP + real SQLite.

The ten list-command account options take ``--account-alias`` as the
canonical spelling; the previous spellings stay accepted as deprecated
legacy aliases (one stderr diagnostic per logical argument, parseable
stdout). Internal dests, native wire fields, cache scope keys, and request
bodies stay byte-identical; validator errors name canonical flags. All
data synthetic; fully offline (autouse fixture).
"""

import json
from hashlib import sha256

import pytest
from test_liquidity_account_capacity_cli_sit import capacity, response
from test_liquidity_forecast_accuracy import ACCOUNT, ROW, handler

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]

WATERLEVELS = ["cash", "waterlevels"]
WARNING = "warning: --account is deprecated; use --account-alias"


def waterlevel(alias):
    return {
        "aliasName": alias,
        "currency": "USD",
        "valueDate": "20261005",
        "curAvlBal": "10.00",
        "timeZone": "GMT+08",
    }


def waterlevel_page(rows):
    return {
        "status": 200,
        "body": {"success": True, "data": {"data": rows, "totalCount": len(rows)}},
    }


def test_canonical_and_legacy_spellings_emit_identical_requests(setup, run_cli):
    setup.state.business_handler = lambda payload, index: waterlevel_page([])
    base = ["liquidity", *WATERLEVELS, "list", "--live"]
    code, out, err = run_cli([*base, "--account-alias", "A1"])
    assert code == 0, (out, err)
    assert WARNING not in err
    code, out, err = run_cli([*base, "--account", "A1"])
    assert code == 0, (out, err)
    assert WARNING in err
    canonical, legacy = setup.state.business_requests
    assert canonical == legacy
    assert canonical["aliasNameList"] == ["A1"]


def test_equals_form_and_command_word_value(setup, run_cli):
    setup.state.business_handler = lambda payload, index: waterlevel_page([])
    base = ["liquidity", *WATERLEVELS, "list", "--live"]
    code, out, err = run_cli([*base, "--account-alias=A1"])
    assert code == 0, (out, err)
    code, out, err = run_cli([*base, "--account-alias", "list"])
    assert code == 0, (out, err)
    assert setup.state.business_requests[-1]["aliasNameList"] == ["list"]
    code, out, err = run_cli([*base, "--account=A1"])
    assert code == 0, (out, err)
    assert WARNING in err
    assert setup.state.business_requests[-1]["aliasNameList"] == ["A1"]


def test_legacy_spelling_keeps_stdout_parseable(setup, run_cli):
    setup.state.business_handler = lambda payload, index: waterlevel_page(
        [waterlevel("A1")]
    )
    code, out, err = run_cli(["refresh", "liquidity", *WATERLEVELS, "--account", "A1"])
    assert code == 0, (out, err)
    assert WARNING in err
    assert json.loads(out)["data"]["row_count"] == 1
    code, out, err = run_cli(["liquidity", *WATERLEVELS, "list", "--account", "A1"])
    assert code == 0, (out, err)
    assert err == WARNING + "\n"
    assert parse(out)["data"] == [waterlevel("A1")]


@pytest.mark.parametrize("values", [("A1", "A1"), ("A1", "A2")])
def test_mixed_scalar_spellings_rejected_before_transport(setup, run_cli, values):
    base = ["liquidity", *WATERLEVELS, "list", "--live"]
    code, out, err = run_cli(
        [*base, "--account-alias", values[0], "--account", values[1]]
    )
    assert code == 2
    result = parse(out)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert "--account-alias" in result["error"]["message"]
    assert setup.state.transports == []


def test_cache_seeded_via_legacy_spelling_read_via_canonical(setup, run_cli):
    setup.state.business_handler = lambda payload, index: waterlevel_page(
        [waterlevel("A1")]
    )
    code, out, err = run_cli(["refresh", "liquidity", *WATERLEVELS, "--account", "A1"])
    assert code == 0, (out, err)
    seeded = parse(out)
    digest = sha256(setup.cache_path.read_bytes()).hexdigest()
    setup.state.reachable = False
    requests = len(setup.state.business_requests)
    code, out, err = run_cli(
        ["liquidity", *WATERLEVELS, "list", "--account-alias", "A1"]
    )
    assert code == 0, (out, err)
    assert err == ""
    canonical = parse(out)
    assert canonical["data"] == [waterlevel("A1")]
    assert canonical["meta"]["source"] == "cache"
    assert canonical["meta"]["complete"] is True
    assert canonical["meta"]["stale"] is False
    code, out, err = run_cli(["liquidity", *WATERLEVELS, "list", "--account", "A1"])
    assert code == 0, (out, err)
    assert err == WARNING + "\n"
    legacy = parse(out)
    assert legacy["data"] == canonical["data"]
    assert legacy["meta"]["scope"] == canonical["meta"]["scope"]
    assert legacy["meta"]["snapshot_id"] == canonical["meta"]["snapshot_id"]
    assert legacy["meta"]["fetched_at"] == canonical["meta"]["fetched_at"]
    assert seeded["meta"]["published"] is True
    assert len(setup.state.business_requests) == requests
    assert sha256(setup.cache_path.read_bytes()).hexdigest() == digest


def test_help_names_canonical_flag_and_keeps_identity(run_cli):
    for path in (
        ["help", "liquidity", *WATERLEVELS, "list"],
        ["help", "refresh", "liquidity", *WATERLEVELS],
    ):
        code, out, err = run_cli(path)
        assert code == 0 and err == ""
        options = {option["name"]: option for option in json.loads(out)["options"]}
        assert options["account"]["flags"] == ["--account-alias", "--account"]
        assert options["account"]["required"] is (path[0] == "refresh")
    code, out, err = run_cli(
        ["help", "liquidity", *WATERLEVELS, "list", "--format", "text"]
    )
    assert code == 0 and err == ""
    assert "--account-alias" in out


# --- liquidity risk account-capacity: repeatable sorted set -------------------

CAPACITY = ["risk", "account-capacity"]


def test_capacity_mixed_repeatable_spellings_combine_into_sorted_scope(setup, run_cli):
    setup.state.business_handler = lambda payload, index: response(
        capacity(payload["aliasName"])
    )
    code, out, err = run_cli(
        [
            "refresh",
            "liquidity",
            *CAPACITY,
            "--account-alias",
            "SYN-B",
            "--account",
            "SYN-A",
            "--account-alias",
            "SYN-C",
        ]
    )
    assert code == 0, (out, err)
    assert err.count(WARNING) == 1  # one diagnostic per logical argument
    assert setup.state.business_requests == [
        {"aliasName": alias} for alias in ("SYN-A", "SYN-B", "SYN-C")
    ]
    setup.state.reachable = False
    requests = len(setup.state.business_requests)
    code, out, err = run_cli(
        [
            "liquidity",
            *CAPACITY,
            "list",
            "--account-alias",
            "SYN-C",
            "--account-alias",
            "SYN-A",
            "--account-alias",
            "SYN-B",
            "--limit",
            "0",
        ]
    )
    assert code == 0, (out, err)
    assert err == ""
    assert [row["aliasName"] for row in parse(out)["data"]] == [
        "SYN-A",
        "SYN-B",
        "SYN-C",
    ]
    assert len(setup.state.business_requests) == requests


@pytest.mark.parametrize(
    "spellings",
    [
        ["--account-alias", "SYN-A", "--account", "SYN-A"],
        ["--account-alias", "SYN-A", "--account-alias", "SYN-A"],
        [part for index in range(11) for part in ("--account-alias", f"SYN-{index}")],
    ],
)
def test_capacity_set_rules_rejected_naming_canonical_flag(setup, run_cli, spellings):
    for command in (
        ["liquidity", *CAPACITY, "list", "--live", *spellings],
        ["refresh", "liquidity", *CAPACITY, *spellings],
    ):
        code, out, _ = run_cli(command)
        result = parse(out)
        assert code == 2 and result["error"]["code"] == "INVALID_ARGUMENT"
        assert "--account-alias" in result["error"]["message"]
    assert setup.state.transports == []


# --- liquidity forecast accuracy: exactly one alias ----------------------------

ACCURACY = ["forecast", "accuracy"]


def test_accuracy_canonical_flag_end_to_end(setup, run_cli):
    setup.state.business_handler = handler([ROW])
    code, out, err = run_cli(
        [
            "refresh",
            "liquidity",
            *ACCURACY,
            "--account-alias",
            ACCOUNT,
            "--record-date",
            "2026-10-05",
            "--require-complete",
        ]
    )
    assert code == 0, (out, err)
    digest = sha256(setup.cache_path.read_bytes()).hexdigest()
    setup.state.reachable = False
    code, out, err = run_cli(
        [
            "liquidity",
            *ACCURACY,
            "list",
            "--account-alias",
            ACCOUNT,
            "--limit",
            "0",
        ]
    )
    assert code == 0, (out, err)
    assert err == ""
    assert parse(out)["data"][0]["id"] == ROW["id"]
    assert sha256(setup.cache_path.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize(
    "spellings",
    [
        ["--account-alias", ACCOUNT, "--account", "OTHER"],
        ["--account-alias", ACCOUNT, "--account-alias", "OTHER"],
    ],
)
def test_accuracy_single_alias_rule_names_canonical_flag(setup, run_cli, spellings):
    code, out, _ = run_cli(
        [
            "liquidity",
            *ACCURACY,
            "list",
            "--live",
            *spellings,
            "--record-date",
            "2026-10-05",
        ]
    )
    result = parse(out)
    assert code == 2 and result["error"]["code"] == "INVALID_ARGUMENT"
    assert "--account-alias" in result["error"]["message"]
    assert setup.state.transports == []


def test_capacity_and_accuracy_help_list_canonical_flag(run_cli):
    for path in (
        ["help", "liquidity", *CAPACITY, "list"],
        ["help", "liquidity", *ACCURACY, "list"],
        ["help", "refresh", "liquidity", *ACCURACY],
    ):
        code, out, err = run_cli(path)
        assert code == 0 and err == ""
        options = {option["name"]: option for option in json.loads(out)["options"]}
        assert options["account"]["flags"] == ["--account-alias", "--account"]


# --- liquidity cash accounts: local-only result filter -------------------------

ACCOUNTS = ["cash", "accounts"]
ALIAS_WARNING = "warning: --alias is deprecated; use --account-alias"
ACCOUNT_ROWS = [
    {"id": "0", "aliasName": "ALIAS001", "currency": "USD"},
    {"id": "1", "aliasName": "ALIAS002", "currency": "USD"},
    {"id": "2", "aliasName": "ALIAS001", "currency": "EUR"},
]


def seed_accounts(setup, run_cli) -> None:
    setup.state.business_handler = lambda payload, index: {
        "status": 200,
        "body": {
            "resultFlag": True,
            "result": {"bankAccountPropertyVOList": ACCOUNT_ROWS},
            "count": len(ACCOUNT_ROWS),
        },
    }
    code, out, err = run_cli(["refresh", "liquidity", *ACCOUNTS])
    assert code == 0, (out, err)
    setup.state.reachable = False


def test_accounts_canonical_filter_or_within_and_and_across(setup, run_cli):
    seed_accounts(setup, run_cli)
    base = ["liquidity", *ACCOUNTS, "list"]
    code, out, err = run_cli(
        [
            *base,
            "--account-alias",
            "ALIAS001",
            "--account-alias",
            "ALIAS002",
            "--require-complete",
        ]
    )
    assert code == 0, (out, err)
    assert err == ""
    result = parse(out)
    assert result["meta"]["complete"] is True
    assert result["meta"]["requested_scope_covered"] is True
    assert result["meta"]["matched_total"] == 3
    code, out, err = run_cli(
        [
            *base,
            "--account-alias",
            "ALIAS001",
            "--currency",
            "USD",
            "--require-complete",
        ]
    )
    assert code == 0, (out, err)
    assert err == ""
    result = parse(out)
    assert result["meta"]["complete"] is True
    assert result["meta"]["requested_scope_covered"] is True
    assert result["meta"]["matched_total"] == 1
    assert result["data"] == [ACCOUNT_ROWS[0]]


def test_accounts_legacy_alias_filter_warns_and_matches_canonical(setup, run_cli):
    seed_accounts(setup, run_cli)
    base = ["liquidity", *ACCOUNTS, "list"]
    code, out, err = run_cli([*base, "--account-alias", "ALIAS001"])
    assert code == 0, (out, err)
    canonical = parse(out)
    code, out, err = run_cli([*base, "--alias", "ALIAS001"])
    assert code == 0, (out, err)
    assert err.startswith(ALIAS_WARNING + "\n")
    assert parse(out)["data"] == canonical["data"]
    assert parse(out)["meta"]["matched_total"] == 2


def test_accounts_filter_stays_off_refresh(setup, run_cli):
    code, out, _ = run_cli(
        ["refresh", "liquidity", *ACCOUNTS, "--account-alias", "ALIAS001"]
    )
    assert code == 2
    assert parse(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert setup.state.transports == []
    assert not setup.cache_path.exists()


def test_accounts_help_lists_canonical_filter_flag(run_cli):
    code, out, err = run_cli(["help", "liquidity", *ACCOUNTS, "list"])
    assert code == 0 and err == ""
    options = {option["name"]: option for option in json.loads(out)["options"]}
    assert options["alias"]["flags"] == ["--account-alias", "--alias"]
    code, out, err = run_cli(["help", "refresh", "liquidity", *ACCOUNTS])
    assert code == 0 and err == ""
    names = {option["name"] for option in json.loads(out)["options"]}
    assert "alias" not in names and "account" not in names
