"""Shared command declarations, help documents and deterministic text rendering.

The current command model projects core and installed-leaf declarations into
help_version=1 documents. Parsing and both output formats share these contracts.
"""

import argparse
from dataclasses import dataclass, field
from typing import Any

HELP_VERSION = 1

# Version of the per-option argument_contract object (Issue #127); the
# skeleton carries the version and declared fields.
ARGUMENT_CONTRACT_VERSION = 1


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
    # Conventional short flags, such as -h, share the long flag's destination.
    short_flags: tuple[str, ...] = ()
    # Optional versioned machine-readable contract (value_type,
    # preferred_format, accepted_formats, modes, ...); emitted in help JSON
    # as ``argument_contract`` (Issue #127 decision 6).
    argument_contract: dict[str, Any] | None = None
    value_type: str | None = None
    # An explicitly declared empty choice set rejects every supplied value.
    choices_declared: bool = False

    @property
    def flags(self) -> tuple[str, ...]:
        """The long flag followed by its declared short forms."""
        return (self.flag, *self.short_flags)

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
    # Positional input metadata for commands with their own parser (management).
    arguments: tuple[dict[str, Any], ...] = ()
    exit_codes: dict[int, str] = field(
        default_factory=lambda: dict(BUSINESS_EXIT_CODES)
    )


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


def _width(text: str) -> int:
    import unicodedata

    return sum(
        0
        if unicodedata.combining(char)
        else 2
        if unicodedata.east_asian_width(char) in {"W", "F"}
        else 1
        for char in text
    )


def _wrap(
    text: str, width: int, indent: str = "", *, break_cjk: bool = True
) -> list[str]:
    """Keep Latin tokens intact; permit natural breaks between CJK characters."""
    import re

    lines = []
    for paragraph in text.splitlines() or [""]:
        line = indent
        separator = ""
        words = []
        for token in re.findall(r"\s+|\S+", paragraph):
            if not break_cjk or any(
                marker in token for marker in ("/", "\\", "--", ".", "=")
            ):
                words.append(token)
            else:
                words.extend(re.findall(r"[\u3400-\u9fff]|[^\u3400-\u9fff]+", token))
        for word in words:
            if word.isspace():
                separator = " " if line != indent else ""
                continue
            if line != indent and _width(line + separator + word) > width:
                lines.append(line)
                line = indent
                separator = ""
            line += separator + word
            separator = ""
        lines.append(line)
    return lines


def _mode_text(modes: dict[str, Any]) -> str:
    descriptions = []
    for name, mode in modes.items():
        if not mode.get("available"):
            descriptions.append(name + ": unavailable")
            continue
        role = str(mode.get("role", "available")).replace("-", " ")
        detail = name + ": " + role
        if mode.get("effective") is False:
            detail += ", no effect"
        if mode.get("required"):
            detail += ", required"
        cardinality = mode.get("cardinality", {})
        if cardinality.get("max", 1) is None:
            detail += ", repeatable"
        descriptions.append(detail)
    return "; ".join(descriptions)


def render_text(doc: dict[str, Any], width: int = 88) -> str:
    """Render an already assembled help document; no discovery or IO."""
    width = max(1, width)
    arguments = "".join(
        " <" + entry["name"] + ">"
        if entry.get("required")
        else " [" + entry["name"] + "]"
        for entry in doc.get("arguments", [])
    )
    usage = "Usage: " + doc["command"] + arguments
    if doc.get("children"):
        usage += " <command>"
    if doc.get("options"):
        usage += " [options]"
    lines = _wrap(usage, width, break_cjk=False)
    lines.extend(_wrap(doc["summary"], width))

    def section(title: str, items: list[str]) -> None:
        if items:
            lines.extend(["", title + ":"])
            for item in items:
                lines.extend(
                    _wrap(
                        item, width, "  ", break_cjk=title not in {"Examples", "Next"}
                    )
                )

    def rows(title: str, entries: list[tuple[str, str]]) -> None:
        if not entries:
            return
        lines.extend(["", title + ":"])
        column = min(max(_width(label) for label, _ in entries), 30)
        for label, description in entries:
            description_width = max(1, width - column - 4)
            wrapped = _wrap(description, description_width)
            if (
                width < 60
                or _width(label) > column
                or any(_width(line) > description_width for line in wrapped)
            ):
                # An intact token can fit the terminal but exceed the narrower
                # description column. Give it the normal stacked-row width.
                lines.extend(_wrap(label, width, "  ", break_cjk=False))
                lines.extend(_wrap(description, width, "    "))
            else:
                prefix = "  " + label + " " * (column - _width(label) + 2)
                lines.append(prefix + wrapped[0])
                lines.extend(" " * (column + 4) + line for line in wrapped[1:])

    rows("Commands", [(c["name"], c["summary"]) for c in doc.get("children", [])])
    rows(
        "Arguments",
        [
            (
                entry["name"],
                entry.get("summary", "")
                + (" [required]" if entry.get("required") else ""),
            )
            for entry in doc.get("arguments", [])
        ],
    )
    options = []
    for entry in doc.get("options", []):
        label = ", ".join(entry.get("flags", [entry["name"]]))
        if entry["type"] != "bool":
            label += " <" + entry["name"].strip("_").upper() + ">"
        metadata = []
        if entry.get("required"):
            metadata.append("required")
        if entry.get("repeatable"):
            metadata.append("repeatable")
        if "choices" in entry:
            metadata.append(
                "choices: "
                + (
                    ", ".join(str(choice) for choice in entry["choices"])
                    or "none (no supplied value accepted)"
                )
            )
        default = entry.get("default")
        if (
            default is not None
            and default != []
            and not (entry["type"] == "bool" and default is False)
        ):
            metadata.append("default: " + str(default))
        contract = entry.get("argument_contract", {})
        if contract.get("modes"):
            metadata.append(_mode_text(contract["modes"]))
        description = entry["summary"]
        if metadata:
            description += " [" + "; ".join(metadata) + "]"
        options.append((label, description))
    rows("Options", options)
    section("Constraints", doc.get("constraints", []))
    section("Examples", doc.get("examples", []))
    next_steps = doc.get("next", [])
    generated = [
        doc["command"] + " " + child["name"] + " --help"
        for child in doc.get("children", [])
    ]
    if generated and next_steps == generated:
        next_steps = [doc["command"] + " <command> --help --format text"]
    section("Next", next_steps)
    effect_names = {
        "mutates": "writes local state",
        "network": "accesses network",
        "browser_required": "requires browser",
        "destructive": "destructive",
    }

    def effects(value: dict[str, Any]) -> str:
        active = [effect_names.get(key, key) for key, flag in value.items() if flag]
        if not active:
            return "No side effects."
        if value.get("network") is False:
            active.append("no network")
        return "; ".join(active)

    if not doc.get("children"):
        effect_rows = [effects(doc.get("effects", {}))]
        effect_rows.extend(
            variant["when"]
            + ": "
            + variant["summary"]
            + " "
            + effects(variant["effects"])
            for variant in doc.get("effects_variants", [])
        )
        section("Effects", effect_rows)
        section("Errors", [", ".join(doc["errors"])] if doc.get("errors") else [])
        section(
            "Exit codes",
            [
                code + ": " + description
                for code, description in doc.get("exit_codes", {}).items()
            ],
        )
        output = doc.get("output", {})
        section(
            "Output",
            [
                "Default: "
                + output["default_format"]
                + "; formats: "
                + ", ".join(output["formats"])
            ]
            if "default_format" in output
            else [],
        )
    diagnostics = []
    for entry in doc.get("diagnostics", []):
        diagnostics.append(
            "; ".join(str(key) + ": " + str(value) for key, value in entry.items())
            if isinstance(entry, dict)
            else str(entry)
        )
    section("Diagnostics", diagnostics)
    return "\n".join(lines) + "\n"
