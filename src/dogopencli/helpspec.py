"""Declarative business help: one declaration drives parsing and both formats.

DI-style ``help_version=1`` documents for the business command tree (Issue
#13). The same OptionSpec/BizNode records generate the argparse leaf parsers,
the parent/child navigation, and the JSON/text help renderers, so help can
never drift from the accepted syntax. The auth subtree keeps its ported
declaration in ``auth/spec.py``; ``helptree`` delegates those paths there.

Normative source: docs/research/general/2026-09-12-cli-help-acceptance-matrix.md
"""

import argparse
from dataclasses import dataclass, field
from typing import Any

HELP_VERSION = 1
HELP_FORMATS = ("json", "text")

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


@dataclass(frozen=True)
class BizNode:
    """One business command-tree node; handler=False nodes only show help."""

    path: tuple[str, ...]
    summary: str
    children: tuple[tuple[str, str], ...] = ()
    options: tuple[OptionSpec, ...] = ()
    constraints: tuple[str, ...] = ()
    effects: dict[str, Any] = field(default_factory=lambda: dict(NO_EFFECTS))
    effects_variants: tuple[dict[str, Any], ...] = ()
    output: dict[str, Any] = field(default_factory=lambda: dict(GROUP_OUTPUT))
    errors: tuple[str, ...] = ("INVALID_ARGUMENT",)
    examples: tuple[str, ...] = ()
    next: tuple[str, ...] = ()
    handler: bool = False


# Shared query options (declared once, reused by every query leaf).
LIMIT = opt(
    "limit", "Maximum rows to display; a positive integer.", "int", help_default=100
)
OFFSET = opt("offset", "Rows to skip before displaying.", "int", help_default=0)
ALL = opt(
    "all",
    "Display all matched rows; conflicts with explicit --limit/--offset.",
    "bool",
)
FIELDS = opt("fields", "Comma-separated record fields to keep; at least one.", "str")
LIVE = opt(
    "live",
    "Query the backend through the existing CDP session instead of the cache.",
    "bool",
)
REQUIRE_FRESH = opt(
    "require_fresh",
    "Fail when the cached snapshot is older than the TTL (default 72 hours,"
    " configurable).",
    "bool",
)
REQUIRE_COMPLETE = opt(
    "require_complete",
    "Fail when the snapshot or live collection does not cover the complete scope.",
    "bool",
)
FORMAT_TABLE = opt(
    "format", "Result format.", "str", default="json", choices=("json", "table")
)

CACHE_FLAGS = (REQUIRE_FRESH, REQUIRE_COMPLETE)

# Shared query constraints and effects (Issue #13 wording).
FILTER_OR_AND = "Multiple values of one filter field OR; different filter fields AND."
CACHE_SEMANTICS = (
    "Cached read: default TTL 72 hours (configurable); stale and complete are"
    " independent; --require-fresh fails on stale, --require-complete fails on"
    " incomplete."
)
DISPLAY_WINDOW = (
    "Display window: default shows 100 rows (limit=100, offset=0); --all"
    " returns all matched rows and conflicts with explicit --limit/--offset."
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

QUERY_EFFECTS_VARIANTS = (CACHE_INIT_VARIANT, LIVE_VARIANT)


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
            kwargs["default"] = [] if option.default is None else option.default
        else:
            kwargs["default"] = option.default
        if option.choices:
            kwargs["choices"] = option.choices
        if option.required:
            kwargs["required"] = True
        parser.add_argument(option.flag, **kwargs)


def _describe(option: OptionSpec) -> dict[str, Any]:
    value: dict[str, Any] = {
        "name": option.name,
        "summary": option.summary,
        "type": option.kind,
        "required": option.required,
        "default": option.effective_default,
    }
    value["flags"] = [option.flag]
    if option.choices:
        value["choices"] = list(option.choices)
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
    doc["arguments"] = []
    doc["options"] = [_describe(option) for option in node.options]
    doc["constraints"] = list(node.constraints)
    doc["effects"] = dict(node.effects)
    if node.effects_variants:
        doc["effects_variants"] = [
            _copy_variant(variant) for variant in node.effects_variants
        ]
    doc["output"] = dict(node.output)
    doc["exit_codes"] = dict(BUSINESS_EXIT_CODES)
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
    if doc["options"]:
        lines.append("Options:")
        for entry in doc["options"]:
            flags = ", ".join(entry.get("flags", (entry["name"],)))
            metadata = []
            if entry["type"] != "bool":
                flags += " <" + entry["name"].strip("_").upper() + ">"
            if entry["type"] == "append":
                metadata.append("repeatable")
            if entry.get("choices"):
                metadata.append("choices: " + ", ".join(entry["choices"]))
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
