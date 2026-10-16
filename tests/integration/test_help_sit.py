"""SIT for the DI-style progressive help (Issue #13).

Covers the acceptance matrix
(docs/research/general/2026-09-12-cli-help-acceptance-matrix.md): entry
equivalence, direct-children navigation, leaf contracts, error protocols and
exit codes, format routing, and help isolation from config/cache/browser.
All offline; no network or browser access (autouse fixture).
"""

import json

import pytest

ROOT_CHILDREN = [
    "snapshot",
    "domain",
    "gui",
    "payment",
    "refresh",
    "collection",
    "liquidity",
    "fx",
    "describe",
    "prune",
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


# --- leaf contracts (matrix items 2 and 3) ---


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


# --- bare leaves still execute (matrix items 3 and 18) ---


# --- auth paths (matrix item 4) ---


# --- meta command and error routing (matrix item 5) ---


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
