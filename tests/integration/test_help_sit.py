"""SIT for the DI-style progressive help (Issue #13).

Covers the acceptance matrix
(docs/research/general/2026-09-12-cli-help-acceptance-matrix.md): entry
equivalence, direct-children navigation, leaf contracts, error protocols and
exit codes, format routing, and help isolation from config/cache/browser.
All offline; no network or browser access (autouse fixture).
"""

import json

import pytest

from dogopencli.plugins.payment.channel import SCOPES, STATUSES

ROOT_CHILDREN = [
    "snapshot",
    "payment",
    "refresh",
    "collection",
    "liquidity",
    "fx",
    "describe",
    "auth",
    "login",
    "logout",
]

GROUPS = [
    [],
    ["payment"],
    ["payment", "ptr"],
    ["payment", "ptr", "cases"],
    ["payment", "ptr", "orders"],
    ["payment", "channel"],
    ["payment", "cost"],
    ["payment", "sla"],
    ["payment", "sla", "baselines"],
    ["refresh"],
    ["refresh", "payment"],
    ["refresh", "payment", "ptr"],
    ["collection"],
    ["collection", "account-isolation"],
    ["collection", "cost"],
    ["collection", "sla"],
    ["collection", "sla", "configs"],
    ["collection", "va"],
    ["collection", "va", "rules"],
    ["collection", "va", "capacity"],
    ["refresh", "collection"],
]

GROUP_CHILDREN = {
    (): ROOT_CHILDREN,
    ("payment",): ["ptr", "rules", "channel", "cost", "sla"],
    ("payment", "ptr"): ["cases", "orders"],
    ("payment", "ptr", "orders"): ["list", "prune"],
    ("payment", "ptr", "cases"): ["list", "prune"],
    ("payment", "channel"): ["list", "prune"],
    ("payment", "cost"): ["list", "prune"],
    ("payment", "sla"): ["baselines"],
    ("payment", "sla", "baselines"): ["list", "get", "prune"],
    ("refresh",): ["payment", "collection", "liquidity", "fx"],
    ("refresh", "payment"): ["ptr", "rules", "channel", "cost", "sla"],
    ("refresh", "payment", "ptr"): ["cases", "orders"],
    ("collection",): [
        "clearing-system",
        "card-template",
        "account-isolation",
        "sla",
        "cost",
        "va",
    ],
    ("collection", "account-isolation"): ["list", "prune"],
    ("collection", "sla"): ["configs"],
    ("collection", "sla", "configs"): ["list", "get", "prune"],
    ("collection", "cost"): ["list", "prune"],
    ("collection", "va"): ["rules", "capacity"],
    ("collection", "va", "rules"): ["list", "get", "prune"],
    ("collection", "va", "capacity"): ["list", "prune"],
    ("refresh", "collection"): [
        "clearing-system",
        "card-template",
        "cost",
        "sla",
        "va",
        "account-isolation",
    ],
}

QUERY_LEAVES = [
    ["payment", "channel", "list"],
    ["payment", "cost", "list"],
    ["payment", "sla", "baselines", "list"],
    ["payment", "sla", "baselines", "get"],
]

REFRESH_LEAVES = [
    ["refresh", "payment", "channel"],
    ["refresh", "payment", "cost"],
    ["refresh", "payment", "sla"],
]

BUSINESS_LEAVES = QUERY_LEAVES + REFRESH_LEAVES

DOC_KEYS = [
    "help_version",
    "command",
    "summary",
    "arguments",
    "options",
    "constraints",
    "effects",
    "output",
    "exit_codes",
    "errors",
    "examples",
    "next",
    "children",
]


def help_json(run_cli, argv):
    code, out, err = run_cli(argv)
    assert code == 0, (argv, out, err)
    assert err == "", argv
    assert out.endswith("\n") and out.count("\n") == 1, argv
    return json.loads(out)


def options_by_name(doc):
    return {option["name"]: option for option in doc["options"]}


# --- entry equivalence and navigation (matrix item 1) ---


@pytest.mark.parametrize(
    "argv",
    [[], ["--help"], ["-h"], ["help"]],
)
def test_root_entries_are_the_same_json(run_cli, argv):
    doc = help_json(run_cli, argv)
    baseline = json.loads(run_cli([])[1])
    assert doc == baseline


def test_root_shape(run_cli):
    doc = help_json(run_cli, [])
    assert list(doc.keys()) == DOC_KEYS
    assert doc["help_version"] == 1
    assert doc["command"] == "dogopencli"
    assert "read-only" in doc["summary"]
    assert [child["name"] for child in doc["children"]] == ROOT_CHILDREN
    assert "help" not in [child["name"] for child in doc["children"]]
    assert doc["effects"] == {
        "mutates": False,
        "network": False,
        "browser_required": False,
        "destructive": False,
    }
    assert doc["output"]["help_default_format"] == "json"
    assert doc["output"]["help_formats"] == ["json", "text"]
    assert doc["next"] == [
        "dogopencli help payment",
        "dogopencli help refresh",
        "dogopencli --format text",
    ]


@pytest.mark.parametrize("path", GROUPS[1:], ids=lambda p: " ".join(p))
def test_group_entries_are_the_same_json(run_cli, path):
    docs = [
        help_json(run_cli, path),
        help_json(run_cli, [*path, "--help"]),
        help_json(run_cli, [*path, "-h"]),
        help_json(run_cli, ["help", *path]),
    ]
    assert docs[0] == docs[1] == docs[2] == docs[3]
    assert docs[0]["command"] == "dogopencli " + " ".join(path)
    names = [child["name"] for child in docs[0]["children"]]
    assert names == GROUP_CHILDREN[tuple(path)]
    assert "help" not in names


def test_text_entries_are_equivalent(run_cli):
    code, bare, err = run_cli(["--format", "text"])
    assert code == 0 and err == ""
    for argv in (
        ["help", "--format", "text"],
        ["--format", "text", "payment"],
        ["payment", "--format", "text"],
        ["help", "payment", "--format", "text"],
    ):
        code, out, err = run_cli(argv)
        assert code == 0 and err == "", argv
        assert "\x1b" not in out
    _, payment_text, _ = run_cli(["payment", "--format", "text"])
    _, payment_text_before, _ = run_cli(["--format", "text", "payment"])
    _, payment_text_help, _ = run_cli(["help", "payment", "--format", "text"])
    assert payment_text == payment_text_before == payment_text_help
    assert "dogopencli" in bare and "payment" in bare and "logout" in bare


# --- leaf contracts (matrix items 2 and 3) ---


@pytest.mark.parametrize("path", BUSINESS_LEAVES, ids=lambda p: " ".join(p))
def test_leaf_help_entries_are_the_same_json(run_cli, path):
    docs = [
        help_json(run_cli, [*path, "--help"]),
        help_json(run_cli, [*path, "-h"]),
        help_json(run_cli, ["help", *path]),
    ]
    assert docs[0] == docs[1] == docs[2]
    doc = docs[0]
    assert doc["children"] == []
    assert doc["command"] == "dogopencli " + " ".join(path)
    keys = list(doc.keys())
    assert keys[:7] == DOC_KEYS[:6] + ["effects"]
    if doc.get("effects_variants"):
        assert keys.index("effects_variants") == keys.index("effects") + 1
    assert doc["output"]["help_default_format"] == "json"
    assert doc["output"]["help_formats"] == ["json", "text"]
    assert set(doc["exit_codes"]) == {"0", "1", "2", "130"}
    assert doc["examples"], path
    assert doc["next"], path


def _assert_window_and_format_options(options):
    assert options["limit"]["type"] == "int"
    assert options["limit"]["default"] == 100
    assert options["limit"]["required"] is False
    assert options["offset"]["type"] == "int"
    assert options["offset"]["default"] == 0
    assert "all" not in options
    assert options["format"]["choices"] == ["json", "table"]
    assert options["format"]["default"] == "json"
    assert options["fields"]["type"] == "str"


def _assert_cache_flags(options):
    for name in ("live", "require_fresh", "require_complete"):
        assert options[name]["type"] == "bool"
        assert options[name]["default"] is False


def test_channel_list_contract(run_cli):
    doc = help_json(run_cli, ["help", "payment", "channel", "list"])
    options = options_by_name(doc)
    assert options["payout_type"]["type"] == "str"
    assert options["payout_type"]["default"] == "EXTERNAL (online only)"
    assert options["payout_type"]["choices"] == list(SCOPES)
    for name in (
        "financial_inst_id",
        "debit_inst_country_code",
        "status",
        "debit_account_name",
        "debit_account_no",
        "clearing_system_name",
        "debit_currency",
        "credit_currency",
    ):
        assert options[name]["type"] == "append", name
        assert options[name]["default"] == [], name
    assert options["status"]["choices"] == list(STATUSES)
    _assert_window_and_format_options(options)
    _assert_cache_flags(options)
    assert doc["output"]["default_format"] == "json"
    assert doc["output"]["formats"] == ["json", "table"]
    joined = " ".join(doc["constraints"])
    assert "72 hours" in joined
    assert "seqid" in joined
    assert "--limit 0" in joined
    assert any("--live" in example for example in doc["examples"])


def test_cost_list_contract(run_cli):
    doc = help_json(run_cli, ["help", "payment", "cost", "list"])
    options = options_by_name(doc)
    for name in (
        "legal_entity_code",
        "financial_inst_code",
        "bank_account",
        "trans_currency_code",
        "charge_bearer",
        "clearing_network_name",
    ):
        assert options[name]["type"] == "append", name
    _assert_window_and_format_options(options)
    _assert_cache_flags(options)
    assert "FUND_OUT_CHANNEL_TRANS_FEE" in " ".join(doc["constraints"])


def test_sla_list_contract(run_cli):
    doc = help_json(run_cli, ["help", "payment", "sla", "baselines", "list"])
    options = options_by_name(doc)
    assert "choices" not in options["status"]
    live_only = options["biz_legal_entity"]
    assert live_only["type"] == "append"
    assert "unverified" in live_only["summary"]
    joined = " ".join(doc["constraints"])
    assert "--biz-legal-entity" in joined and "--live" in joined
    _assert_window_and_format_options(options)
    _assert_cache_flags(options)


def test_sla_get_contract(run_cli):
    doc = help_json(run_cli, ["help", "payment", "sla", "baselines", "get"])
    options = options_by_name(doc)
    assert options["id"]["required"] is True
    assert options["id"]["type"] == "str"
    assert options["id"]["default"] is None
    assert "require_fresh" not in options
    assert options["require_complete"]["type"] == "bool"
    assert options["format"]["choices"] == ["json", "table"]
    assert "limit" not in options and "all" not in options
    assert any("--id BASELINE_ID" in example for example in doc["examples"])


@pytest.mark.parametrize("path", QUERY_LEAVES, ids=lambda p: " ".join(p))
def test_query_leaf_effects(run_cli, path):
    doc = help_json(run_cli, ["help", *path])
    if path[-1] == "get":
        assert doc["effects"]["network"] is True
        assert doc["effects"]["browser_required"] is True
        assert doc.get("effects_variants", []) == []
        return
    assert doc["effects"] == {
        "mutates": False,
        "network": False,
        "browser_required": False,
        "destructive": False,
    }
    variants = doc["effects_variants"]
    cache_init = [v for v in variants if v["effects"]["mutates"] is True]
    live = [v for v in variants if "--live" in v["when"]]
    assert cache_init == []
    assert len(live) == 1
    assert live[0]["effects"] == {
        "mutates": False,
        "network": True,
        "browser_required": True,
        "destructive": False,
    }


def test_refresh_channel_two_static_branches(run_cli):
    doc = help_json(run_cli, ["help", "refresh", "payment", "channel"])
    assert doc["effects"]["mutates"] is True
    variants = doc["effects_variants"]
    assert len(variants) == 2
    snapshot = [v for v in variants if "snapshot" in v["when"]]
    cdp = [v for v in variants if "cdp" in v["when"]]
    assert snapshot[0]["effects"] == {
        "mutates": True,
        "network": False,
        "browser_required": False,
        "destructive": False,
    }
    assert cdp[0]["effects"] == {
        "mutates": True,
        "network": True,
        "browser_required": True,
        "destructive": False,
    }
    options = options_by_name(doc)
    assert options["payout_type"]["choices"] == list(SCOPES)
    assert doc["output"]["formats"] == ["json"]


@pytest.mark.parametrize("path", REFRESH_LEAVES[1:], ids=lambda p: " ".join(p))
def test_refresh_cdp_leaf_effects(run_cli, path):
    doc = help_json(run_cli, ["help", *path])
    assert doc["effects"] == {
        "mutates": True,
        "network": True,
        "browser_required": True,
        "destructive": False,
    }
    assert doc["output"]["formats"] == ["json"]


def test_leaf_text_matches_json(run_cli):
    _, text_a, _ = run_cli(
        ["payment", "sla", "baselines", "get", "--help", "--format", "text"]
    )
    _, text_b, _ = run_cli(
        ["help", "payment", "sla", "baselines", "get", "--format", "text"]
    )
    assert text_a == text_b
    assert "\x1b" not in text_a
    assert "--id" in text_a and "required" in text_a
    _, channel_text, _ = run_cli(
        ["payment", "channel", "list", "--help", "--format", "text"]
    )
    assert "default: 100" in channel_text
    assert "repeatable" in channel_text
    assert "choices: ENABLE, DISABLE, GRAY, TEST, INIT" in channel_text
    assert "--live" in channel_text and "Effects" in channel_text
    assert "Exit codes" in channel_text and "Next" in channel_text


# --- bare leaves still execute (matrix items 3 and 18) ---


def test_bare_leaf_executes_query(
    run_cli, dataset_factory, config_factory, sample_channel_rows, envelope
):
    config_factory(dataset_factory(sample_channel_rows))
    code, out, _ = run_cli(["payment", "channel", "list"])
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_MISS"


def test_bare_sla_get_missing_id_is_argument_error(run_cli):
    code, out, err = run_cli(["payment", "sla", "baselines", "get"])
    assert code == 2
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert err == ""
    code, out, _ = run_cli(["payment", "sla", "baselines", "get", "--help"])
    assert code == 0
    assert json.loads(out)["command"] == "dogopencli payment sla baselines get"


# --- auth paths (matrix item 4) ---


def test_auth_help_unchanged_and_routed(run_cli):
    _, auth_bare, _ = run_cli(["auth"])
    _, auth_help, _ = run_cli(["help", "auth"])
    assert auth_bare == auth_help
    assert json.loads(auth_bare)["children"] == [
        {"name": "check", "summary": json.loads(auth_bare)["children"][0]["summary"]}
    ]
    for argv in (
        ["login", "--help"],
        ["logout", "--help"],
        ["auth", "check", "--help"],
    ):
        code, out, _ = run_cli(argv)
        assert code == 0
        assert json.loads(out)["help_version"] == 1
    _, login_help, _ = run_cli(["login", "--help"])
    _, help_login, _ = run_cli(["help", "login"])
    assert login_help == help_login
    _, logout_help, _ = run_cli(["logout", "--help"])
    _, help_logout, _ = run_cli(["help", "logout"])
    assert logout_help == help_logout


def test_auth_help_never_dispatches(run_cli, monkeypatch):
    def broken(*args, **kwargs):
        raise AssertionError("auth dispatch must not run for help")

    monkeypatch.setattr("dogopencli.auth.cli.dispatch", broken)
    for argv in (
        ["help", "login"],
        ["help", "logout"],
        ["help", "auth", "check"],
        ["login", "--help"],
    ):
        code, _, _ = run_cli(argv)
        assert code == 0, argv


def test_auth_argument_error_protocol(run_cli):
    code, out, _ = run_cli(["help", "login", "bogus"])
    assert code == 1
    envelope = json.loads(out)
    assert envelope["output_version"] == 1
    assert envelope["error"]["code"] == "invalid_arguments"
    assert envelope["error"]["next"] == ["dogopencli login --help"]
    code, out, _ = run_cli(["help", "auth", "bogus"])
    assert code == 1
    assert json.loads(out)["error"]["code"] == "invalid_arguments"


# --- meta command and error routing (matrix item 5) ---


def test_help_alone_is_root(run_cli):
    assert json.loads(run_cli(["help"])[1]) == json.loads(run_cli([])[1])


@pytest.mark.parametrize(
    "argv,hint",
    [
        (["bogus"], "dogopencli --help"),
        (["payment", "bogus"], "dogopencli help payment"),
        (["help", "bogus"], "dogopencli --help"),
        (["help", "payment", "bogus"], "dogopencli help payment"),
    ],
)
def test_unknown_command_fails_without_fallback(run_cli, envelope, argv, hint):
    code, out, err = run_cli(argv)
    assert code == 2
    assert err == ""
    error = envelope(out)["error"]
    assert error["code"] == "INVALID_ARGUMENT"
    assert hint in error["message"]
    assert "help_version" not in out


def test_unknown_option_fails(run_cli, envelope):
    code, out, _ = run_cli(["payment", "--bogus"])
    assert code == 2
    assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    code, out, _ = run_cli(["help", "payment", "channel", "list", "--limit", "3"])
    assert code == 2
    assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "argv",
    [
        ["--format", "table"],
        ["--format", "markdown"],
        ["help", "payment", "--format", "table"],
        ["payment", "channel", "--format", "markdown"],
    ],
)
def test_help_rejects_table_and_markdown(run_cli, envelope, argv):
    code, out, _ = run_cli(argv)
    assert code == 2
    assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert "help_version" not in out


def test_text_error_goes_to_stderr_only(run_cli):
    code, out, err = run_cli(["--format", "text", "bogus"])
    assert code == 2
    assert out == ""
    assert "INVALID_ARGUMENT" in err


def test_no_abbreviations(run_cli, envelope):
    code, out, _ = run_cli(["payment", "--h"])
    assert code == 2
    assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"
    code, out, err = run_cli(["payment", "channel", "list", "--hel"])
    assert code == 2
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert err == ""


def test_double_dash_is_not_a_help_switch(run_cli, envelope):
    code, out, err = run_cli(["payment", "channel", "list", "--", "--help"])
    assert code == 2
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert err == ""
    code, out, _ = run_cli(["help", "--", "payment"])
    assert code == 2
    assert envelope(out)["error"]["code"] == "INVALID_ARGUMENT"


def test_option_values_never_misroute(
    run_cli, envelope, dataset_factory, config_factory, sample_channel_rows
):
    config_factory(dataset_factory(sample_channel_rows))
    code, out, _ = run_cli(["payment", "sla", "baselines", "get", "--id", "login"])
    assert code == 2
    body = envelope(out)
    assert body["error"]["code"] == "CONFIG_ERROR"
    assert "output_version" not in body
    code, out, err = run_cli(["payment", "channel", "list", "--status", "login"])
    assert code == 2
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert err == ""


def test_help_with_known_leaf_options_still_shows_help(run_cli):
    code, out, err = run_cli(
        ["payment", "channel", "list", "--status", "ENABLE", "--help"]
    )
    assert code == 0 and err == ""
    assert json.loads(out)["command"] == "dogopencli payment channel list"


# --- isolation (matrix item 6) ---


@pytest.fixture
def environment_entry_points_fail(monkeypatch):
    def broken(*args, **kwargs):
        raise AssertionError("help must not touch config/cache/browser")

    monkeypatch.setattr("dogopencli.cli.config_mod.load", broken)
    monkeypatch.setattr("dogopencli.cli.Cache", broken)
    monkeypatch.setattr("dogopencli.cached_query.Cache", broken)
    monkeypatch.setattr("dogopencli.inquiry.resolve_environment", broken)
    monkeypatch.setattr("dogopencli.inquiry.make_transport", broken)
    monkeypatch.setattr("dogopencli.inquiry.acquire_browser_control", broken)
    monkeypatch.setattr("dogopencli.inquiry.check_authentication", broken)
    monkeypatch.setattr("dogopencli.auth.cli.dispatch", broken)


def test_help_never_touches_environment(run_cli, environment_entry_points_fail):
    for path in GROUPS:
        assert run_cli(path)[0] == 0, path
        assert run_cli(["help", *path])[0] == 0, path
    for path in BUSINESS_LEAVES:
        assert run_cli([*path, "--help"])[0] == 0, path
        assert run_cli(["help", *path])[0] == 0, path
    for argv in (["auth"], ["help", "login"], ["help", "logout"]):
        assert run_cli(argv)[0] == 0, argv


def test_help_works_with_missing_and_corrupt_config(run_cli, monkeypatch, tmp_path):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "missing.toml"))
    assert run_cli([])[0] == 0
    assert run_cli(["help", "payment", "channel", "list"])[0] == 0
    corrupt = tmp_path / "corrupt.toml"
    corrupt.write_text("not [ valid toml")
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(corrupt))
    assert run_cli(["payment", "--format", "text"])[0] == 0
    assert run_cli(["help", "login"])[0] == 0


def test_help_creates_no_files(run_cli, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(tmp_path / "cfg"))
    for argv in (
        [],
        ["help", "payment"],
        ["payment", "channel", "list", "--help"],
        ["help", "auth"],
    ):
        assert run_cli(argv)[0] == 0, argv
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("option", ["--format=json", "--config-dir=elsewhere"])
@pytest.mark.parametrize("path", [["auth"], ["login"], ["logout"], ["auth", "check"]])
def test_auth_help_accepts_equals_globals(
    run_cli, environment_entry_points_fail, option, path
):
    assert help_json(run_cli, [option, *path, "--help"]) == help_json(
        run_cli, [*path, "--help"]
    )


@pytest.mark.parametrize(
    "path", [[], ["payment"], ["login"], ["payment", "channel", "list"]]
)
def test_help_prefix_format_is_preserved(run_cli, path):
    expected = run_cli(["help", *path, "--format", "text"])
    assert run_cli(["--format", "text", "help", *path]) == expected
    assert run_cli(["--format=text", "help", *path]) == expected


@pytest.mark.parametrize("prefix", [["help", "payment"], ["payment"], ["help", "auth"]])
def test_trailing_text_format_applies_to_errors(run_cli, prefix):
    code, out, err = run_cli([*prefix, "bogus", "--format", "text"])
    assert code in (1, 2)
    assert out == ""
    assert "bogus" in err


@pytest.mark.parametrize(
    "options",
    [
        ["--limit"],
        ["--limit", "bad"],
        ["--status", "BAD"],
        ["--status=BAD"],
        ["--liv"],
        ["--live=true"],
    ],
)
def test_leaf_help_validates_supplied_syntax(
    run_cli, options, environment_entry_points_fail
):
    code, out, err = run_cli(["payment", "channel", "list", *options, "--help"])
    assert code == 2
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert err == ""


@pytest.mark.parametrize("path", [["login"], ["logout"], ["auth", "check"]])
def test_auth_help_rejects_unknown_options_and_has_navigation(run_cli, path):
    for args in ([*path, "--help", "--bad"], ["help", *path, "--bad"]):
        code, out, err = run_cli(args)
        assert code == 1
        assert json.loads(out)["error"]["code"] == "invalid_arguments"
        assert err == ""
    doc = help_json(run_cli, ["help", *path])
    assert doc["examples"]
    assert doc["next"]


def test_leaf_help_equals_values_do_not_become_controls(run_cli):
    doc = help_json(
        run_cli, ["payment", "sla", "baselines", "get", "--id=--help", "--help"]
    )
    assert doc["command"] == "dogopencli payment sla baselines get"
    code, out, err = run_cli(
        ["payment", "channel", "list", "--status=ENABLE", "--help", "--format=text"]
    )
    assert code == 0 and not err
    assert out.startswith("dogopencli payment channel list\n")


def test_unknown_prefix_cannot_crash_auth_route(run_cli):
    code, out, err = run_cli(["--bogus", "auth", "--help"])
    assert code in (1, 2)
    assert json.loads(out)["error"]
    assert not err


@pytest.mark.parametrize("path", BUSINESS_LEAVES)
def test_leaf_unknown_option_uses_business_envelope(run_cli, monkeypatch, path):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid arguments reached configuration")

    monkeypatch.setattr("dogopencli.cli.config_mod.load", forbidden)
    code, out, err = run_cli([*path, "--unknown-option"])
    assert code == 2
    body = json.loads(out)
    assert body["data"] is None and body["meta"] is None
    assert body["error"]["code"] == "INVALID_ARGUMENT"
    assert body["error"]["retryable"] is False
    assert err == ""


@pytest.mark.parametrize(
    "options",
    [
        ["--limit", "not-an-int"],
        ["--limit"],
        ["--limit", "-1"],
        ["--lim", "1"],
        ["--format", "bogus"],
    ],
)
def test_leaf_invalid_options_use_business_envelope(run_cli, options):
    code, out, err = run_cli(["payment", "channel", "list", *options])
    assert code == 2
    assert json.loads(out)["error"]["code"] == "INVALID_ARGUMENT"
    assert err == ""
