"""Current public commands, projected without activating installed leaf runtimes.

One model supplies navigation, option validation and installed-leaf parsing.
Core declarations remain owned by their execution modules.
"""

import argparse
import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NoReturn

from . import config
from .errors import CliError
from .helpspec import NO_EFFECTS, BizNode, OptionSpec, add_options, opt
from .leaves.operation_rules import known_errors
from .leaves.registry import Leaf, Registry

OUTPUT = {
    "default_format": "json",
    "formats": ["json", "text"],
    "help_default_format": "json",
    "help_formats": ["json", "text"],
}
COMMON = (
    opt("config_dir", "Shared configuration directory."),
    opt("format", "Output format.", default="json", choices=("json", "text")),
    OptionSpec(
        "help", "--help", "Show current command help.", "bool", legacy_flags=("-h",)
    ),
    opt("version", "Show version.", "bool"),
)
WINDOW = (
    opt("fields", "Comma-separated record fields."),
    opt(
        "limit",
        "Maximum displayed rows; 0 means all remaining rows.",
        "int",
        default=100,
    ),
    opt("offset", "Rows to skip.", "int", default=0),
    opt("require_complete", "Require complete results.", "bool"),
    opt("require_fresh", "Require a fresh cached result.", "bool"),
    opt("live", "Query live rather than cached records.", "bool"),
)
WITH_DETAIL = opt(
    "with_detail",
    "With --live, fetch native detail for each selected output row; "
    "return {record, detail}; any detail failure fails the command.",
    "bool",
)


def value_parser(kind: str):
    if kind == "boolean":

        def boolean(value: str) -> bool:
            if value.lower() in ("true", "1", "false", "0"):
                return value.lower() in ("true", "1")
            raise argparse.ArgumentTypeError("expected true or false")

        return boolean
    if kind in {"number", "positive"}:

        def number(value: str) -> float:
            try:
                result = float(value)
            except ValueError as error:
                raise argparse.ArgumentTypeError("expected a number") from error
            if not math.isfinite(result) or (kind == "positive" and result <= 0):
                raise argparse.ArgumentTypeError(
                    "value must be finite"
                    + (" and positive" if kind == "positive" else "")
                )
            return result

        return number
    return {"string": str, "integer": int}[kind]


def parameter_modes(definition: dict, operation: str) -> dict:
    """Project the runtime's acquisition and explicit offline-filter rules."""
    required = definition.get("required", False)
    acquisition = {
        "available": True,
        "role": "acquisition-scope" if operation == "refresh" else "native-request",
        "required": required,
        "cardinality": {
            "min": int(required),
            "max": None if definition.get("multiple") else 1,
        },
    }
    if operation != "list":
        return {operation: acquisition}
    cached = {"available": False}
    if definition.get("local_field"):
        cached = {
            "available": True,
            "role": "local-filter",
            "required": False,
            "cardinality": {"min": 0, "max": None if definition.get("multiple") else 1},
        }
    return {"cache": cached, "live": acquisition}


def host_modes(option: OptionSpec, operation: str) -> OptionSpec:
    modes = ("cache", "live") if operation == "list" else (operation,)
    role = (
        "display"
        if option.name in {"fields", "limit", "offset"}
        else ("mode-selector" if option.name == "live" else "cache-policy")
    )
    entries = {mode: {"available": True, "role": role} for mode in modes}
    # Runtime accepts --require-fresh with --live, but only cached replay
    # checks staleness. Describe the no-op without inventing a rejection.
    if option.name == "require_fresh" and "live" in entries:
        entries["live"]["effective"] = False
    if option.name == "with_detail":
        entries = {
            "cache": {"available": False},
            "live": {
                "available": True,
                "role": "detail-composition",
                "requires": ["live"],
            },
        }
    return replace(option, argument_contract={"modes": entries})


def leaf_options(leaf: Leaf, operation: str) -> tuple[OptionSpec, ...]:
    host = (
        WINDOW
        if operation == "list"
        else WINDOW[:4]
        if operation == "refresh"
        else WINDOW[:1]
        if operation == "get"
        else ()
    )
    if (
        operation == "get"
        and leaf.manifest["operations"]["get"].get("execution") == "custom"
    ):
        host = (*host, WINDOW[3])
    if operation == "list" and leaf.manifest["operations"].get("get", {}).get(
        "list_binding"
    ):
        host = (*host, WITH_DETAIL)
    declared = "list" if operation == "refresh" else operation
    definitions = leaf.manifest["operations"].get(declared, {}).get("parameters", [])
    parameters = tuple(
        OptionSpec(
            item["name"].replace("-", "_"),
            "--" + item["name"],
            item["description"],
            "append" if item.get("multiple") else "str",
            default=item.get("default"),
            help_default=item.get("default"),
            choices=tuple(item.get("choices", ())),
            choices_declared="choices" in item,
            value_type=item["type"],
            required=item.get("required", False) and operation in {"get", "refresh"},
            argument_contract={
                "value_type": item["type"],
                "required_for_acquisition": item.get("required", False),
                "modes": parameter_modes(item, operation),
            },
        )
        for item in definitions
    )
    return (*(host_modes(option, operation) for option in host), *parameters, *COMMON)


def current_nodes(registry: Registry) -> dict[tuple[str, ...], BizNode]:
    from .auth.spec import COMMANDS, EXIT_CODES, GLOBALS
    from .domain_contracts import domain_declarations
    from .management import DECLARATIONS

    nodes = {
        (): BizNode((), "Discover inquiry commands and local controls.", options=COMMON)
    }
    for spec in COMMANDS:
        if not spec.path:
            continue
        options = tuple(
            OptionSpec(
                a.name,
                a.flags[0],
                a.summary,
                a.kind if a.kind != "positive" else "str",
                default=a.default,
                help_default=a.default,
                choices=tuple(domain.id for domain in domain_declarations())
                if a.name == "domain"
                else a.choices,
                legacy_flags=a.flags[1:],
                value_type="positive" if a.kind == "positive" else None,
            )
            for a in (*spec.options, *GLOBALS)
        )
        nodes[spec.path] = BizNode(
            spec.path,
            spec.summary,
            options=options,
            handler=spec.handler,
            constraints=(
                "--verbose and --quiet are mutually exclusive.",
                *spec.constraints,
            ),
            effects=spec.effects,
            errors=("invalid_arguments", *spec.errors),
            examples=spec.examples,
            next=spec.next,
            exit_codes=EXIT_CODES,
        )
    for node in DECLARATIONS:
        options = (
            *node.options,
            *(o for o in COMMON if o.name not in {x.name for x in node.options}),
        )
        nodes[node.path] = replace(
            node,
            handler=None if node.path == ("domain",) else node.handler,
            options=options,
        )
    nodes[("plugins",)] = BizNode(
        ("plugins",), "Manage local leaf installations.", options=COMMON
    )
    nodes[("plugins", "install")] = BizNode(
        ("plugins", "install"),
        "Install one leaf from a directory, ZIP, HTTP(S) ZIP URL or bundled identity.",
        options=COMMON,
        arguments=(
            {
                "name": "source",
                "type": "string",
                "required": True,
                "summary": "Directory, ZIP, HTTP(S) ZIP URL or bundled:identity.",
            },
        ),
        handler="plugin-install",
        effects={**NO_EFFECTS, "mutates": True},
        effects_variants=(
            {
                "when": "source is an HTTP(S) URL",
                "summary": "Downloads one bounded ZIP into temporary storage.",
                "effects": {**NO_EFFECTS, "mutates": True, "network": True},
            },
        ),
        constraints=(
            "One leaf per invocation; existing installations are never overwritten.",
            "Domain must already be enabled; installation does not authenticate "
            "or query business data.",
        ),
        examples=("dogopencli plugins install bundled:collection.cost",),
        next=("dogopencli plugins list",),
    )
    nodes[("plugins", "uninstall")] = BizNode(
        ("plugins", "uninstall"),
        "Remove one installed leaf and its temporary query cache; retain Duckdog data.",
        options=COMMON,
        arguments=(
            {
                "name": "identity",
                "type": "string",
                "required": True,
                "summary": "Global identity: domain.dotted-leaf.",
            },
        ),
        handler="plugin-uninstall",
        effects={**NO_EFFECTS, "mutates": True, "destructive": True},
        constraints=(
            "No prompt; truly absent installations succeed idempotently.",
            "Retains Duckdog data, binding history, credentials and source packages.",
        ),
        examples=("dogopencli plugins uninstall collection.cost",),
        next=("dogopencli plugins list",),
    )
    nodes[("plugins", "list")] = BizNode(
        ("plugins", "list"),
        "List bundled availability, installed declarations and diagnostics "
        "without executing adapters.",
        options=COMMON,
        handler="plugin-list",
        effects=NO_EFFECTS,
        constraints=(
            "Availability is not installation; installation is not "
            "production qualification.",
        ),
        next=(
            "dogopencli plugins install --help",
            "dogopencli plugins uninstall --help",
        ),
    )
    for domain in domain_declarations():
        nodes[(domain.id,)] = BizNode(
            (domain.id,), "Discover " + domain.id + " inquiries.", options=COMMON
        )
    for leaf in registry.leaves.values():
        for operation in (
            *leaf.manifest["operations"],
            *(("refresh", "prune") if "list" in leaf.manifest["operations"] else ()),
            "describe",
        ):
            path = (leaf.domain, operation, leaf.name)
            parent = path[:-1]
            nodes.setdefault(
                parent,
                BizNode(
                    parent,
                    operation.capitalize() + " installed leaves.",
                    options=COMMON,
                ),
            )
            arguments = (
                (
                    {
                        "name": "detail_identity",
                        "type": "string",
                        "required": True,
                        "summary": leaf.manifest["operations"]["get"]["lookup"][
                            "description"
                        ],
                        "lookup_name": leaf.manifest["operations"]["get"]["lookup"][
                            "name"
                        ],
                    },
                )
                if operation == "get"
                else ()
            )
            summary = (
                leaf.manifest["operations"].get(operation, {}).get("description")
                or f"{operation.capitalize()} {leaf.id}."
            )
            invocation = "dogopencli " + " ".join(path)
            detail = leaf.manifest["operations"].get("get", {})
            binding = detail.get("list_binding")
            detail_constraints = ()
            if operation == "get":
                result_identity = detail["result_identity"]
                identity_names = result_identity.get(
                    "request_fields", result_identity.get("fields")
                )
                if identity_names is None:
                    identity_names = [
                        json.dumps(path, ensure_ascii=False)
                        for path in result_identity["paths"]
                    ]
                shape = detail.get("result_shape", "object")
                detail_constraints = (
                    f"Live-only native root {shape}; "
                    + (
                        "request context identity: "
                        if "request_fields" in result_identity
                        else "returned identity: "
                    )
                    + ", ".join(identity_names)
                    + ". "
                    + result_identity["description"],
                    "Separate histories, logs and child pages are not acquired; "
                    "a root response does not establish their completeness.",
                )
                if shape == "array":
                    detail_constraints += (
                        "A qualified successful empty array stays empty. --fields "
                        "projects each member; returned_count is the actual member "
                        "count. No List paging or --with-detail binding applies.",
                    )
            elif operation == "list" and binding:
                detail_constraints = (
                    "--with-detail requires --live. Local filtering and offset/limit "
                    "select the output window before detail inquiries; limit 0 means "
                    "all remaining rows. Empty windows make no detail inquiries.",
                    "Each entry is {record, detail}; --fields projects only record. "
                    "Any detail or binding failure fails the whole command. "
                    "List coverage is retained; separate histories, logs and child "
                    "pages are not acquired. No combined result is cached or imported.",
                    "Lookup "
                    + detail["lookup"]["name"]
                    + " comes from List field "
                    + binding["identity_field"]
                    + "; context mappings: "
                    + (
                        ", ".join(
                            name + "=" + field
                            for name, field in binding.get("parameters", {}).items()
                        )
                        or "none"
                    )
                    + ". Unmapped Get parameters use their declared defaults.",
                )
            nodes[path] = BizNode(
                path,
                summary,
                handler="leaf",
                errors=known_errors(
                    operation, has_list="list" in leaf.manifest["operations"]
                ),
                options=leaf_options(leaf, operation),
                arguments=arguments,
                effects={
                    "mutates": operation != "describe",
                    "network": operation in {"get", "refresh"},
                    "browser_required": operation in {"get", "refresh"},
                    "destructive": operation == "prune",
                },
                effects_variants=(
                    {
                        "when": "--live is given",
                        "summary": "Reads the backend through the authenticated CDP "
                        "session without publishing a cache snapshot.",
                        "effects": {
                            **NO_EFFECTS,
                            "mutates": True,
                            "network": True,
                            "browser_required": True,
                        },
                    },
                )
                if operation == "list"
                else (),
                constraints=detail_constraints
                + (
                    (
                        "Required business parameters apply to get, refresh and live "
                        "acquisition; help permits missing values.",
                        "Execution can initialize local storage, reconcile removed "
                        "installations and record local observations; help does none "
                        "of these activities.",
                    )
                    if operation in {"list", "refresh", "get"}
                    else ()
                ),
                examples=(
                    invocation
                    + (
                        " DETAIL_ID"
                        + "".join(
                            " --" + item["name"] + " VALUE"
                            for item in detail.get("parameters", [])
                            if item.get("required") and "default" not in item
                        )
                        if operation == "get"
                        else ""
                    ),
                    *(
                        (invocation + " --live --with-detail --offset 0 --limit 10",)
                        if operation == "list" and binding
                        else ()
                    ),
                ),
                next=("dogopencli " + leaf.domain + " describe " + leaf.name,)
                if operation != "describe"
                else (),
            )
    for path, node in list(nodes.items()):
        children = tuple(
            (p[-1], n.summary)
            for p, n in sorted(nodes.items())
            if p[:-1] == path and len(p) == len(path) + 1
        )
        next_steps = []
        for step in node.next:
            words = step.split()
            if words[:2] == ["dogopencli", "help"]:
                words = [words[0], *words[2:], "--help"]
            target = tuple(word for word in words[1:] if not word.startswith("-"))
            if target in nodes:
                next_steps.append(" ".join(words))
        nodes[path] = replace(
            node,
            children=children,
            output=OUTPUT,
            next=tuple(next_steps)
            or tuple(
                "dogopencli " + " ".join((*path, name)) + " --help"
                for name, _ in children
            )
            or ("dogopencli --help",),
        )
    return nodes


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse echoes rejected values; source URLs can carry credentials.
        message = re.sub(r"https?://\S+", "[HTTP(S) URL]", message, flags=re.IGNORECASE)
        raise CliError("INVALID_ARGUMENT", message, exit_code=2)


def parse_options(
    node: BizNode, tokens: list[str], *, help_requested: bool = False
) -> argparse.Namespace:
    parser = Parser(
        prog="dogopencli " + " ".join(node.path), add_help=False, allow_abbrev=False
    )
    options = node.options
    if help_requested:
        options = tuple(replace(option, required=False) for option in options)
    elif node.handler == "leaf":
        # Required acquisition values are checked by the execution owner so
        # cached lists can omit them and semantic errors retain their contract.
        options = tuple(replace(option, required=False) for option in options)
    elif node.path[:1] in (("login",), ("logout",), ("auth",)):
        # Authentication retains domain_not_found as a semantic execution
        # failure. Help validates supplied choices without entering that service.
        options = tuple(
            replace(option, choices=()) if option.name == "domain" else option
            for option in options
        )
    add_options(parser, options)
    for argument in node.arguments:
        parser.add_argument(
            argument["name"],
            nargs="?" if help_requested or not argument.get("required") else None,
        )
    args = parser.parse_args(tokens)
    if (
        node.path[:1] in (("login",), ("logout",), ("auth",))
        and getattr(args, "verbose", False)
        and getattr(args, "quiet", False)
    ):
        raise CliError(
            "INVALID_ARGUMENT",
            "--verbose and --quiet are mutually exclusive",
            exit_code=2,
        )
    for name in ("limit", "offset"):
        if getattr(args, name, 0) < 0:
            raise CliError(
                "INVALID_ARGUMENT", f"--{name} must be nonnegative", exit_code=2
            )
    if node.path == ("gui",) and not 0 <= args.port <= 65535:
        raise CliError(
            "INVALID_ARGUMENT", "port must be between 0 and 65535", exit_code=2
        )
    return args


@dataclass
class Invocation:
    node: BizNode
    args: argparse.Namespace
    registry: Registry
    config_file: Path
    remaining: list[str]
    help_requested: bool


def resolve(argv: list[str]) -> Invocation:
    # Locate global configuration while respecting all declared option arities.
    # Manifest options cannot use reserved host names, so their unknown arity is
    # one value; core flag spellings come directly from their declarations.
    from .auth.spec import GLOBALS

    host_flags = {
        flag
        for option in (*COMMON, *WINDOW, WITH_DETAIL)
        if option.kind == "bool"
        for flag in option.flags
    }
    auth_flags = {
        flag for option in GLOBALS if option.kind == "bool" for flag in option.flags
    }
    config_dir = None
    command_root = None
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            break
        flag, equal, value = token.partition("=")
        if (
            flag.startswith("-")
            and flag
            not in (
                host_flags
                | (
                    auth_flags
                    if command_root in {None, "login", "logout", "auth"}
                    else set()
                )
            )
            and not equal
        ):
            index += 1
            value = argv[index] if index < len(argv) else None
        if not flag.startswith("-") and command_root is None:
            command_root = flag
        if flag == "--config-dir":
            config_dir = value
        index += 1
    config_error = None
    try:
        config_file = config.config_path(config_dir)
    except CliError as error:
        # Invalid environment location must not prevent core discovery. Do not
        # silently inspect a different user configuration or execute there.
        config_error = error
        config_file = config.DEFAULT_CONFIG
    registry = Registry(config_file)
    if config_error is None:
        registry.discover()
    nodes = current_nodes(registry)
    global_names = {option.name for option in GLOBALS}
    globals_by_flag = {
        flag: option
        for option in nodes[("login",)].options
        if option.name in global_names
        for flag in option.flags
    }
    path: tuple[str, ...] = ()
    remaining = []
    help_requested = False
    index = 0
    while index < len(argv):
        token = argv[index]
        node = nodes[path]
        if token == "--":
            remaining.extend(argv[index:])
            break
        if token.startswith("-"):
            flag, equal, value = token.partition("=")
            spellings = {
                spelling: option for option in node.options for spelling in option.flags
            }
            option = spellings.get(flag) or (
                globals_by_flag.get(flag) if not path else None
            )
            if option is None:
                raise CliError(
                    "INVALID_ARGUMENT",
                    f"Unknown option {flag}; use "
                    + " ".join(("dogopencli", *path, "--help")),
                    exit_code=2,
                    command_path=path,
                )
            if option.kind != "bool" and not equal:
                index += 1
                if index == len(argv):
                    raise CliError(
                        "INVALID_ARGUMENT",
                        f"{flag} expected one argument",
                        exit_code=2,
                        command_path=path,
                    )
                value = argv[index]
                equal = "="
            remaining.append(flag + equal + value)
            if option.name == "help" and not equal:
                help_requested = True
        elif (*path, token) in nodes:
            path = (*path, token)
        elif node.handler is not None and node.arguments:
            remaining.append(token)
        else:
            raise CliError(
                "INVALID_ARGUMENT",
                f"Unknown command {token}; use dogopencli {chr(32).join(path)} --help",
                exit_code=2,
                command_path=path,
            )
        index += 1
    node = nodes[path]
    try:
        args = parse_options(
            node, remaining, help_requested=help_requested or node.handler is None
        )
    except CliError as error:
        error.message += "; use " + " ".join(("dogopencli", *path, "--help"))
        error.command_path = path
        raise
    if (
        config_error is not None
        and not help_requested
        and not args.version
        and node.handler is not None
    ):
        config_error.command_path = path
        raise config_error
    return Invocation(node, args, registry, config_file, remaining, help_requested)


# Options that may legally precede the first command word (auth globals and
# help controls); anything else stops the command-word scan.
_PRE_COMMAND_VALUE_OPTIONS = {"--config-dir", "--format"}
_PRE_COMMAND_FLAGS = {"--verbose", "--quiet", "--no-color", "--version", "-h", "--help"}


def leading_command(tokens: list[str]) -> tuple[str | None, int]:
    """First command word and its index; known pre-command options only."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return None, len(tokens)
        flag, separator, _value = token.partition("=")
        if flag in _PRE_COMMAND_VALUE_OPTIONS:
            index += 1 if separator else 2
            continue
        if token in _PRE_COMMAND_FLAGS:
            index += 1
            continue
        if token.startswith("-"):
            return None, index
        return token, index
    return None, len(tokens)


def emit_help(invocation: Invocation) -> int:
    import os
    import sys

    from .helpspec import document, render_text
    from .leaves.cli import emit

    doc = document(invocation.node)
    doc["diagnostics"] = invocation.registry.diagnostics
    if invocation.args.format == "text":
        width = 88
        try:
            if sys.stdout.isatty():
                width = os.get_terminal_size(sys.stdout.fileno()).columns
                if width <= 0:
                    width = 88
        except (OSError, ValueError):
            pass
        sys.stdout.write(render_text(doc, width))
    else:
        emit(doc, output_format="json")
    return 0
