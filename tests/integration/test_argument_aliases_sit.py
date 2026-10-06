"""SIT for legacy flag aliases and the argument_contract skeleton (#128).

The shared declaration model accepts deprecated alias spellings onto the
same dest, rejects mixed canonical/legacy scalar spellings, emits one stderr
deprecation diagnostic per affected logical argument per invocation, and
describes aliases plus the optional versioned argument contract in help.
Exercised through the public CLI with a synthetic catalog leaf; no real leaf
declaration changes in this ticket, so baseline help stays byte-identical.
All offline; no network or browser access (autouse fixture).
"""

import argparse
import json
import sys

import pytest

from dogopencli import cli
from dogopencli.catalog import NODES
from dogopencli.helpspec import QUERY_OUTPUT, BizNode, document, opt

WARNING_FROM = "warning: --from is deprecated; use --from-date"
WARNING_LABEL = "warning: --label is deprecated; use --tag"


def _handler(records: list[argparse.Namespace]):
    def run(args: argparse.Namespace) -> int:
        records.append(args)
        payload = {
            "data": {"from_date": args.from_date, "tag": list(args.tag)},
            "error": None,
            "meta": None,
        }
        sys.stdout.write(json.dumps(payload) + "\n")
        return 0

    return run


@pytest.fixture
def alias_leaf(monkeypatch: pytest.MonkeyPatch) -> list:
    """Synthetic leaf with one scalar and one repeatable aliased option."""
    records: list = []
    group = BizNode(("aliastest",), "Synthetic alias contract test group.")
    leaf = BizNode(
        ("aliastest", "list"),
        "Synthetic alias contract test leaf.",
        options=(
            opt(
                "from_date",
                "First day of the inquiry window.",
                legacy_flags=("--from",),
                argument_contract={
                    "value_type": "date",
                    "preferred_format": "YYYY-MM-DD",
                    "accepted_formats": ["YYYY-MM-DD", "YYYYMMDD"],
                },
            ),
            opt("tag", "Tag filter.", kind="append", legacy_flags=("--label",)),
        ),
        output=QUERY_OUTPUT,
        handler="cmd_aliastest_list",
    )
    monkeypatch.setitem(NODES, group.path, group)
    monkeypatch.setitem(NODES, leaf.path, leaf)
    monkeypatch.setattr(cli, "cmd_aliastest_list", _handler(records), raising=False)
    return records


def _help_options(out: str) -> dict:
    doc = json.loads(out)
    assert doc["help_version"] == 1
    return {entry["name"]: entry for entry in doc["options"]}


def test_help_json_lists_preferred_flag_then_legacy_aliases(run_cli, alias_leaf):
    code, out, err = run_cli(["help", "aliastest", "list"])
    assert code == 0
    assert err == ""
    options = _help_options(out)
    assert options["from_date"]["flags"] == ["--from-date", "--from"]
    assert options["tag"]["flags"] == ["--tag", "--label"]


def test_help_json_emits_versioned_argument_contract(run_cli, alias_leaf):
    code, out, err = run_cli(["aliastest", "list", "--help"])
    assert code == 0
    assert err == ""
    options = _help_options(out)
    contract = options["from_date"]["argument_contract"]
    assert next(iter(contract)) == "version"
    assert contract["version"] == 1
    assert contract["value_type"] == "date"
    assert contract["preferred_format"] == "YYYY-MM-DD"
    assert contract["accepted_formats"] == ["YYYY-MM-DD", "YYYYMMDD"]
    assert contract["deprecated_flags"] == ["--from"]
    # Existing fields and their types are preserved.
    assert options["from_date"]["name"] == "from_date"
    assert options["from_date"]["type"] == "str"
    assert options["from_date"]["required"] is False
    assert options["from_date"]["default"] is None
    # Options without a declared contract gain no new key.
    assert "argument_contract" not in options["tag"]


def test_text_help_shows_aliases_preferred_first(run_cli, alias_leaf):
    code, out, err = run_cli(["aliastest", "list", "--format", "text", "--help"])
    assert code == 0
    assert err == ""
    assert "--from-date, --from <FROM_DATE>" in out
    assert "--tag, --label <TAG>" in out


def test_preferred_flag_executes_without_diagnostics(run_cli, alias_leaf):
    code, out, err = run_cli(["aliastest", "list", "--from-date", "2026-01-01"])
    assert code == 0
    assert err == ""
    assert json.loads(out)["data"] == {"from_date": "2026-01-01", "tag": []}


@pytest.mark.parametrize(
    "spelling",
    [["--from", "2026-01-01"], ["--from=2026-01-01"]],
)
def test_legacy_flag_binds_same_dest_and_warns_on_stderr(run_cli, alias_leaf, spelling):
    code, out, err = run_cli(["aliastest", "list", *spelling])
    assert code == 0
    assert json.loads(out)["data"]["from_date"] == "2026-01-01"
    assert err == WARNING_FROM + "\n"


@pytest.mark.parametrize("legacy_value", ["2026-01-01", "2026-02-02"])
def test_mixed_scalar_spellings_rejected_even_when_equal(
    run_cli, alias_leaf, legacy_value
):
    code, out, err = run_cli(
        ["aliastest", "list", "--from-date", "2026-01-01", "--from", legacy_value]
    )
    assert code == 2
    assert err == ""
    envelope = json.loads(out)
    assert envelope["error"]["code"] == "INVALID_ARGUMENT"
    assert "--from-date" in envelope["error"]["message"]
    assert envelope["data"] is None
    assert alias_leaf == []  # the handler never ran


def test_mixed_scalar_spellings_rejected_with_equals_form(run_cli, alias_leaf):
    code, out, _err = run_cli(
        ["aliastest", "list", "--from-date=2026-01-01", "--from=2026-01-01"]
    )
    assert code == 2
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert alias_leaf == []


def test_repeatable_option_mixes_spellings_freely(run_cli, alias_leaf):
    code, out, err = run_cli(["aliastest", "list", "--tag", "a", "--label", "b"])
    assert code == 0
    assert json.loads(out)["data"]["tag"] == ["a", "b"]
    assert err == WARNING_LABEL + "\n"


def test_one_diagnostic_per_argument_and_repeated_scalar_last_wins(run_cli, alias_leaf):
    code, out, err = run_cli(
        [
            "aliastest",
            "list",
            "--from",
            "2026-01-01",
            "--from",
            "2026-02-02",
            "--label",
            "x",
            "--label",
            "y",
        ]
    )
    assert code == 0
    # Repeated occurrences of one unchanged scalar spelling keep argparse
    # last-wins behavior; repeatable options keep ordered multi-values.
    assert json.loads(out)["data"] == {"from_date": "2026-02-02", "tag": ["x", "y"]}
    assert err.splitlines() == [WARNING_FROM, WARNING_LABEL]


def test_value_resembling_command_word_after_legacy_flag_is_consumed(
    run_cli, alias_leaf
):
    code, out, _err = run_cli(["aliastest", "list", "--from", "list"])
    assert code == 0
    assert json.loads(out)["data"]["from_date"] == "list"


def test_help_paths_never_emit_deprecation(run_cli, alias_leaf):
    code, out, err = run_cli(["aliastest", "list", "--from", "2026-01-01", "--help"])
    assert code == 0
    assert err == ""
    assert json.loads(out)["help_version"] == 1


def test_abbreviations_of_aliased_flags_remain_rejected(run_cli, alias_leaf):
    code, out, _err = run_cli(["aliastest", "list", "--from-d", "2026-01-01"])
    assert code == 2
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert alias_leaf == []


# Options legitimately renamed by ticket #130 (dest -> (preferred, legacy)).
# rule-status trigger_from/trigger_to keep their own flags (full datetimes),
# so the preferred-flag match below disambiguates them from strategy-results.
RENAMED_OPTIONS_130 = {
    "from": ("--from-date", ("--from",)),
    "to": ("--to-date", ("--to",)),
    "transaction_from": ("--from-date", ("--transaction-from",)),
    "transaction_to": ("--to-date", ("--transaction-to",)),
    "trade_from": ("--from-date", ("--trade-from",)),
    "trade_to": ("--to-date", ("--trade-to",)),
    "trigger_from": ("--from-date", ("--trigger-from",)),
    "trigger_to": ("--to-date", ("--trigger-to",)),
}


def test_baseline_declarations_keep_single_flag_and_no_contract():
    """Beyond the #130 date renames, declarations keep single-flag help."""
    for node in NODES.values():
        entries = {entry["name"]: entry for entry in document(node)["options"]}
        for option in node.options:
            renamed = RENAMED_OPTIONS_130.get(option.name)
            entry = entries[option.name]
            if renamed is not None and option.flag == renamed[0]:
                preferred, legacy = renamed
                assert option.legacy_flags == legacy
                assert entry["flags"] == [preferred, *legacy]
            else:
                assert option.legacy_flags == ()
                assert option.argument_contract is None
                assert entry["flags"] == [option.flag]
                assert "argument_contract" not in entry
