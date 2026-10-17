"""Declarative business help: one declaration drives parsing and both formats.

DI-style ``help_version=1`` documents for the business command tree (Issue
#13). The same OptionSpec/BizNode records generate the argparse leaf parsers,
the parent/child navigation, and the JSON/text help renderers, so help can
never drift from the accepted syntax. The auth subtree keeps its ported
declaration in ``auth/spec.py``; ``helptree`` delegates those paths there.

Normative source: docs/research/general/2026-09-12-cli-help-acceptance-matrix.md
"""

import argparse
from dataclasses import dataclass, field, replace
from typing import Any, NoReturn

HELP_VERSION = 1
HELP_FORMATS = ("json", "text")

# Version of the per-option argument_contract object (Issue #127); the
# skeleton carries version plus declared fields and auto-derived aliases.
ARGUMENT_CONTRACT_VERSION = 1

# Role vocabulary for per-mode availability/role/cardinality entries.
ROLE_SCOPE = "scope-selection"  # chooses the cached/acquired dataset scope
ROLE_NATIVE_REQUEST = "native-request"  # sent to the backend as-is
ROLE_ACQUISITION = "acquisition-scope"  # refresh acquisition scope
ROLE_LOCAL_FILTER = "local-filter"  # post-acquisition result filter
ROLE_DISPLAY = "display"  # presentation-only, never sent
ROLE_MODE = "mode-selector"  # selects execution mode
ROLE_CACHE_POLICY = "cache-policy"  # freshness/completeness gating


def _mode(role: str, cardinality: dict[str, Any] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"available": True, "role": role}
    if cardinality is not None:
        entry["cardinality"] = cardinality
    return entry


def _unavailable() -> dict[str, Any]:
    return {"available": False}


SINGLE = {"min": 0, "max": 1}
MULTI = {"min": 0, "max": None}


def scope_modes(cardinality: dict[str, Any] | None = None) -> dict[str, Any]:
    """Modes for acquisition/cache scope options shared by list+refresh."""
    return {
        "cache": _mode(ROLE_SCOPE, cardinality),
        "live": _mode(ROLE_NATIVE_REQUEST, cardinality),
        "refresh": _mode(ROLE_ACQUISITION, cardinality),
    }


def variant_modes(cardinality: dict[str, Any] | None = None) -> dict[str, Any]:
    """Modes for virtual contract-variant selectors: they choose the variant
    and shape scope identity in every mode but are never sent to the backend."""
    return {
        "cache": _mode(ROLE_SCOPE, cardinality),
        "live": _mode("variant-selector", cardinality),
        "refresh": _mode(ROLE_ACQUISITION, cardinality),
    }


def filter_modes(repeatable: bool = True, live_native: bool = True) -> dict[str, Any]:
    """Local exact-match filters.

    ``live_native`` distinguishes payment's verified single-value native
    pass-through from collection/liquidity filters, which stay local (and
    multi-value) even in live mode because the backend request ignores them.
    """
    if live_native:
        live = _mode(ROLE_NATIVE_REQUEST, SINGLE)
    else:
        live = _mode(ROLE_LOCAL_FILTER, MULTI if repeatable else SINGLE)
    return {
        "cache": _mode(ROLE_LOCAL_FILTER, MULTI if repeatable else SINGLE),
        "live": live,
        "refresh": _unavailable(),
    }


def display_modes() -> dict[str, Any]:
    """Presentation-only options; never part of acquisition."""
    return {
        "cache": _mode(ROLE_DISPLAY, SINGLE),
        "live": _mode(ROLE_DISPLAY, SINGLE),
        "refresh": _mode(ROLE_DISPLAY, SINGLE),
    }


def contract(
    value_type: str,
    *,
    preferred_format: str | None = None,
    accepted_formats: tuple[str, ...] = (),
    modes: dict[str, Any] | None = None,
    constraints: tuple[dict[str, Any], ...] = (),
    timezone: str | None = None,
) -> dict[str, Any]:
    """Versioned machine-readable argument contract (Issue #127 decision 6)."""
    result: dict[str, Any] = {"value_type": value_type}
    if preferred_format is not None:
        result["preferred_format"] = preferred_format
    if accepted_formats:
        result["accepted_formats"] = list(accepted_formats)
    if timezone is not None:
        result["timezone"] = timezone
    if modes is not None:
        result["modes"] = modes
    if constraints:
        result["constraints"] = [dict(item) for item in constraints]
    return result


BUSINESS_EXIT_CODES = {
    0: "success",
    1: "runtime failure",
    2: "argument or configuration error",
    130: "interrupted",
}

NO_EFFECTS: dict[str, Any] = {
    "mutates": False,
    "network": False,
    "browser_required": False,
    "destructive": False,
}

GROUP_OUTPUT: dict[str, Any] = {
    "help_default_format": "json",
    "help_formats": ["json", "text"],
}

QUERY_OUTPUT: dict[str, Any] = {
    "default_format": "json",
    "formats": ["json", "table"],
    "help_default_format": "json",
    "help_formats": ["json", "text"],
}

REFRESH_OUTPUT: dict[str, Any] = {
    "default_format": "json",
    "formats": ["json"],
    "help_default_format": "json",
    "help_formats": ["json", "text"],
}

_UNSET = object()


@dataclass(frozen=True)
class OptionSpec:
    """One CLI option shared by the parser and the help document."""

    name: str
    flag: str
    summary: str
    kind: str = "str"  # str | bool | int | append
    required: bool = False
    default: Any = None
    # Effective execution default when the parser sentinel differs (the
    # list window parses None but executes limit=100/offset=0).
    help_default: Any = _UNSET
    choices: tuple[str, ...] = ()
    # Deprecated public spellings bound to the same dest; ``flag`` stays the
    # preferred spelling and ``name`` the stable internal identity (Issue
    # #127 decision 3).
    legacy_flags: tuple[str, ...] = ()
    # Optional versioned machine-readable contract (value_type,
    # preferred_format, accepted_formats, modes, ...); emitted in help JSON
    # as ``argument_contract`` (Issue #127 decision 6).
    argument_contract: dict[str, Any] | None = None
    value_type: str | None = None
    # An explicitly declared empty choice set rejects every supplied value.
    choices_declared: bool = False

    @property
    def flags(self) -> tuple[str, ...]:
        """Every accepted spelling, preferred first, then legacy aliases."""
        return (self.flag, *self.legacy_flags)

    @property
    def effective_default(self) -> Any:
        if self.help_default is not _UNSET:
            return self.help_default
        if self.kind == "bool" and self.default is None:
            return False
        if self.kind == "append" and self.default is None:
            return []
        return self.default


def opt(
    name: str,
    summary: str,
    kind: str = "str",
    **kwargs: Any,
) -> OptionSpec:
    """OptionSpec with the flag derived from the dest name."""
    return OptionSpec(name, "--" + name.replace("_", "-"), summary, kind, **kwargs)


def filter_opt(
    name: str,
    summary: str,
    kind: str = "append",
    *,
    live_native: bool = True,
    **kwargs: Any,
) -> OptionSpec:
    """A local exact-match filter option with its declared contract (#127)."""
    kwargs.setdefault(
        "argument_contract",
        contract(
            "string",
            modes=filter_modes(repeatable=kind == "append", live_native=live_native),
        ),
    )
    return opt(name, summary, kind, **kwargs)


def identity_opt(name: str, summary: str, **kwargs: Any) -> OptionSpec:
    """A required business-object identity selector with its contract (#127)."""
    kwargs.setdefault(
        "argument_contract",
        contract(
            "string",
            preferred_format="nonempty native identifier",
            modes=scope_modes(SINGLE),
        ),
    )
    return opt(name, summary, "str", **kwargs)


def scope_opt(
    name: str,
    summary: str,
    kind: str = "str",
    *,
    value_type: str = "string",
    preferred_format: str | None = None,
    accepted_formats: tuple[str, ...] = (),
    timezone: str | None = None,
    constraints: tuple[dict[str, Any], ...] = (),
    **kwargs: Any,
) -> OptionSpec:
    """An acquisition/cache scope option with its declared contract (#127)."""
    kwargs.setdefault(
        "argument_contract",
        contract(
            value_type,
            preferred_format=preferred_format,
            accepted_formats=accepted_formats,
            modes=scope_modes(None),
            constraints=constraints,
            timezone=timezone,
        ),
    )
    return opt(name, summary, kind, **kwargs)


@dataclass(frozen=True)
class BizNode:
    """One business command-tree node; handler=None nodes only show help."""

    path: tuple[str, ...]
    summary: str
    children: tuple[tuple[str, str], ...] = ()
    options: tuple[OptionSpec, ...] = ()
    constraints: tuple[str, ...] = ()
    effects: dict[str, Any] = field(default_factory=lambda: dict(NO_EFFECTS))
    effects_variants: tuple[dict[str, Any], ...] = ()
    output: dict[str, Any] = field(default_factory=lambda: dict(GROUP_OUTPUT))
    # Optional business classification; plugins own their vocabulary and
    # decide which leaves require it. Infrastructure nodes leave it unset.
    kind: str | None = None
    errors: tuple[str, ...] = ("INVALID_ARGUMENT",)
    examples: tuple[str, ...] = ()
    next: tuple[str, ...] = ()
    # Execution binding in cli.py; kept static so help needs no runtime setup.
    handler: str | None = None
    # Optional explicit cache owner for shared refresh controls registered
    # outside a domain plugin. This is an internal discovery association.
    cache_capability: str | None = None
    # Positional input metadata for commands with their own parser (management).
    arguments: tuple[dict[str, Any], ...] = ()
    exit_codes: dict[int, str] = field(
        default_factory=lambda: dict(BUSINESS_EXIT_CODES)
    )


# Shared query options (declared once, reused by every query leaf).
LIMIT = opt(
    "limit",
    "Maximum rows to display; 0 displays all remaining rows.",
    "int",
    help_default=100,
    argument_contract=contract(
        "integer",
        preferred_format="nonnegative integer",
        modes=display_modes(),
    ),
)
OFFSET = opt(
    "offset",
    "Rows to skip before displaying.",
    "int",
    help_default=0,
    argument_contract=contract(
        "integer",
        preferred_format="nonnegative integer",
        modes=display_modes(),
    ),
)
ALL = opt(
    "all",
    "Display all matched rows; conflicts with explicit --limit/--offset.",
    "bool",
    argument_contract=contract(
        "boolean",
        modes=display_modes(),
        constraints=({"kind": "conflicts", "arguments": ["limit", "offset"]},),
    ),
)
FIELDS = opt(
    "fields",
    "Comma-separated record fields to keep; at least one.",
    "str",
    argument_contract=contract(
        "string",
        preferred_format="comma-separated field names",
        modes=display_modes(),
    ),
)
LIVE = opt(
    "live",
    "Query the backend through the existing CDP session instead of the cache.",
    "bool",
    argument_contract=contract(
        "boolean",
        modes={
            "cache": _unavailable(),
            "live": _mode(ROLE_MODE),
            "refresh": _unavailable(),
        },
    ),
)
REQUIRE_FRESH = opt(
    "require_fresh",
    "Fail when the cached snapshot is older than the TTL (default 72 hours,"
    " configurable).",
    "bool",
    argument_contract=contract(
        "boolean",
        modes={
            "cache": _mode(ROLE_CACHE_POLICY),
            "live": _unavailable(),
            "refresh": _unavailable(),
        },
    ),
)
REQUIRE_COMPLETE = opt(
    "require_complete",
    "Require complete scope and required details; incomplete refresh is not"
    " published. Default usable partial results warn and exit 0.",
    "bool",
    argument_contract=contract(
        "boolean",
        modes={
            "cache": _mode(ROLE_CACHE_POLICY),
            "live": _mode(ROLE_CACHE_POLICY),
            "refresh": _mode(ROLE_CACHE_POLICY),
        },
    ),
)
FORMAT_TABLE = opt(
    "format",
    "Result format.",
    "str",
    default="json",
    choices=("json", "table"),
    argument_contract=contract(
        "enum",
        modes=display_modes(),
    ),
)

CACHE_FLAGS = (REQUIRE_FRESH, REQUIRE_COMPLETE)

# Shared query constraints and effects (Issue #13 wording).
FILTER_OR_AND = "Multiple values of one filter field OR; different filter fields AND."
CACHE_SEMANTICS = (
    "Cached read: default TTL 72 hours (configurable); stale and complete are"
    " independent; --require-fresh fails on stale, --require-complete fails on"
    " incomplete."
    " Usable incomplete live/cache results warn and exit 0 by default."
)
DISPLAY_WINDOW = (
    "Display window: default shows 100 rows (limit=100, offset=0); --limit 0"
    " returns all remaining matched rows after offset."
)
SEQID_UNSTABLE = "seqid is a local cache position and is not stable across datasets."
LIVE_SINGLE_VALUE = "--live accepts a single value per filter."

CACHE_INIT_VARIANT: dict[str, Any] = {
    "when": "first use initializes the cache or migrates a legacy cache database",
    "summary": "local cache initialization or migration writes local files",
    "effects": {
        "mutates": True,
        "network": False,
        "browser_required": False,
        "destructive": False,
    },
}
LIVE_VARIANT: dict[str, Any] = {
    "when": "--live is given",
    "summary": "reads the backend through the existing CDP session; never"
    " launches a browser or refreshes the cache",
    "effects": {
        "mutates": False,
        "network": True,
        "browser_required": True,
        "destructive": False,
    },
}

QUERY_EFFECTS_VARIANTS = (LIVE_VARIANT,)


def add_options(
    parser: argparse.ArgumentParser, options: tuple[OptionSpec, ...]
) -> None:
    """Generate argparse arguments from the shared declarations."""
    for option in options:
        kwargs: dict[str, Any] = {"help": option.summary, "dest": option.name}
        if option.kind == "bool":
            kwargs["action"] = "store_true"
            kwargs["default"] = bool(option.default)
        elif option.kind == "int":
            kwargs["type"] = int
            kwargs["default"] = option.default
        elif option.kind == "append":
            kwargs["action"] = "append"
            kwargs["default"] = (
                option.default
                if option.value_type is not None
                else []
                if option.default is None
                else option.default
            )
        else:
            kwargs["default"] = option.default
        if option.value_type is not None:
            from .command_model import value_parser

            kwargs["type"] = value_parser(option.value_type)
        if option.choices or option.choices_declared:
            kwargs["choices"] = option.choices
        if option.required:
            kwargs["required"] = True
        parser.add_argument(*option.flags, **kwargs)


class HelpParser(argparse.ArgumentParser):
    """Validate help syntax without printing or exiting the public CLI."""

    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def validate_help_options(tokens: list[str], options: tuple[OptionSpec, ...]) -> None:
    parser = HelpParser(add_help=False, allow_abbrev=False)
    add_options(
        parser,
        tuple(
            replace(option, required=False)
            for option in options
            if option.name != "format"
        ),
    )
    parser.add_argument("--format", choices=HELP_FORMATS)
    parser.add_argument("--help", "-h", action="store_true")
    parser.parse_args(tokens)


def _describe(option: OptionSpec) -> dict[str, Any]:
    value: dict[str, Any] = {
        "name": option.name,
        "summary": option.summary,
        "type": option.value_type or option.kind,
        "repeatable": option.kind == "append",
        "required": option.required,
        "default": option.effective_default,
    }
    value["flags"] = list(option.flags)
    if option.choices or option.choices_declared:
        value["choices"] = list(option.choices)
    if option.argument_contract is not None:
        contract: dict[str, Any] = {
            "version": ARGUMENT_CONTRACT_VERSION,
            **option.argument_contract,
        }
        if option.legacy_flags:
            contract.setdefault("deprecated_flags", list(option.legacy_flags))
        value["argument_contract"] = contract
    return value


def _copy_variant(variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "when": variant["when"],
        "summary": variant["summary"],
        "effects": dict(variant["effects"]),
    }


def document(node: BizNode) -> dict[str, Any]:
    """help_version=1 document; key order is part of the contract."""
    doc: dict[str, Any] = {}
    doc["help_version"] = HELP_VERSION
    doc["command"] = "dogopencli" + "".join(" " + part for part in node.path)
    doc["summary"] = node.summary
    if node.kind is not None:
        doc["kind"] = node.kind
    doc["arguments"] = [dict(argument) for argument in node.arguments]
    doc["options"] = [_describe(option) for option in node.options]
    doc["constraints"] = list(node.constraints)
    doc["effects"] = dict(node.effects)
    if node.effects_variants:
        doc["effects_variants"] = [
            _copy_variant(variant) for variant in node.effects_variants
        ]
    doc["output"] = dict(node.output)
    doc["exit_codes"] = {
        str(code): summary for code, summary in node.exit_codes.items()
    }
    doc["errors"] = list(node.errors)
    doc["examples"] = list(node.examples)
    doc["next"] = list(node.next)
    doc["children"] = [
        {"name": name, "summary": summary} for name, summary in node.children
    ]
    return doc


def render_text(node: BizNode) -> str:
    """Human rendering of the same document; no ANSI, pager, or TTY logic."""
    doc = document(node)
    lines = [doc["command"], doc["summary"], ""]
    if doc["children"]:
        lines.append("Children:")
        for entry in doc["children"]:
            lines.append(f"  {entry['name']}  {entry['summary']}")
    if doc["arguments"]:
        lines.append("Arguments:")
        for entry in doc["arguments"]:
            suffix = " [required]" if entry.get("required") else ""
            lines.append(f"  {entry['name']}  {entry.get('summary', '')}{suffix}")
    if doc["options"]:
        lines.append("Options:")
        for entry in doc["options"]:
            flags = ", ".join(entry.get("flags", (entry["name"],)))
            metadata = []
            if entry["type"] != "bool":
                flags += " <" + entry["name"].strip("_").upper() + ">"
            if entry.get("repeatable") or entry["type"] == "append":
                metadata.append("repeatable")
            if entry.get("choices"):
                metadata.append(
                    "choices: " + ", ".join(str(choice) for choice in entry["choices"])
                )
            if entry["required"]:
                metadata.append("required")
            if entry.get("default") is not None:
                metadata.append("default: " + str(entry["default"]))
            suffix = " [" + "; ".join(metadata) + "]" if metadata else ""
            lines.append(f"  {flags}  {entry['summary']}{suffix}")
    for key in ("constraints", "examples", "next"):
        if doc[key]:
            lines.append(key.capitalize() + ":")
            lines.extend("  " + item for item in doc[key])
    if node.handler:
        lines.append("Effects: " + str(doc["effects"]))
        for variant in doc.get("effects_variants", []):
            lines.append("Effects variant:")
            lines.append(f"  when: {variant['when']}")
            lines.append(f"  {variant['summary']}")
            lines.append(f"  effects: {variant['effects']}")
        lines.append("Errors: " + ", ".join(doc["errors"]))
        lines.append(
            "Exit codes: "
            + "; ".join(f"{code} {text}" for code, text in doc["exit_codes"].items())
        )
        output = doc["output"]
        lines.append(
            "Default output: "
            + str(output["default_format"])
            + "; formats: "
            + ", ".join(output["formats"])
        )
    lines.append("Help formats: " + ", ".join(doc["output"]["help_formats"]))
    return "\n".join(lines) + "\n"


REFRESH_CDP_EFFECTS = {
    "mutates": True,
    "network": True,
    "browser_required": True,
    "destructive": False,
}
REFRESH_CDP_CONSTRAINTS = (
    "Requires the CDP source and an existing authenticated browser session.",
    "Progress diagnostics go to stderr; the result envelope goes to stdout.",
    "Validated partial data is published with quality warnings by default;"
    " --require-complete rejects before publication and preserves the old cache.",
)
REFRESH_CDP_ERRORS = (
    "INCOMPLETE_RESULT",
    "INVALID_ARGUMENT",
    "CONFIG_ERROR",
    "INVALID_RESPONSE",
    "AUTH_REQUIRED",
    "BROWSER_UNAVAILABLE",
    "LOCKED",
    "TIMEOUT",
    "BUSINESS_QUERY_FAILED",
)
