"""Declarative auth command tree, strict parsers and both help formats.

Ported from DI ``src/di/cli/spec.py``, ``arguments.py`` (GLOBALS), ``parser.py``
and ``help.py`` at baseline commit 8eb163c6d140554ca167bd50349a85ca224ac342,
reduced to the authentication commands. The parser never owns exit codes:
every parse failure becomes ``invalid_arguments`` for the auth envelope.
"""

import argparse
import math
from dataclasses import dataclass, field
from typing import Any, NoReturn

from ..browser.errors import invalid

EXIT_CODES = {
    0: "success / help / version",
    1: "argument or runtime failure",
    130: "interrupted",
}

FORMATS = ("json", "text")


@dataclass(frozen=True)
class ArgumentSpec:
    name: str
    summary: str
    flags: tuple[str, ...] = ()
    kind: str = "str"
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandSpec:
    path: tuple[str, ...]
    summary: str
    options: tuple[ArgumentSpec, ...] = ()
    effects: dict[str, Any] = field(
        default_factory=lambda: {
            "mutates": False,
            "network": False,
            "browser_required": False,
            "destructive": False,
        }
    )
    errors: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    next: tuple[str, ...] = ()
    handler: str | None = None
    constraints: tuple[str, ...] = ()

    @property
    def command(self) -> str:
        return ".".join(self.path) or "dogopencli"


def _option(
    name: str,
    summary: str,
    *,
    kind: str = "str",
    default: Any = None,
    choices: tuple[str, ...] = (),
) -> ArgumentSpec:
    if kind == "bool" and default is None:
        default = False
    return ArgumentSpec(
        name.replace("-", "_"), summary, ("--" + name,), kind, False, default, choices
    )


def _positive(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("value must be a finite positive number")
    return result


GLOBALS = (
    _option(
        "config-dir",
        "Configuration: --config-dir > DOGOPENCLI_CONFIG_DIR > ~/.config/dogopencli.",
    ),
    _option(
        "format",
        "Output format; auth results and help default to json.",
        choices=FORMATS,
    ),
    _option("verbose", "Enable detailed diagnostics on stderr.", kind="bool"),
    _option("quiet", "Suppress progress diagnostics.", kind="bool"),
    _option("no-color", "Disable terminal colors.", kind="bool"),
    ArgumentSpec(
        "help",
        "Show help for this command and its direct children.",
        ("--help", "-h"),
        "bool",
        default=False,
    ),
    _option("version", "Show the dogopencli version.", kind="bool"),
)

TIMEOUT_SECONDS = _option(
    "timeout-seconds",
    "Maximum seconds to wait for the human company SSO.",
    kind="positive",
    default=600.0,
)

COMMANDS = (
    CommandSpec((), "Inquiry-only CLI for the payment product operations platform."),
    CommandSpec(
        ("auth",),
        "Verify dedicated browser authentication; dogopencli login owns recovery.",
    ),
    CommandSpec(
        ("auth", "check"),
        "Bounded verified-authentication probe of the dedicated browser "
        "environment; never launches, switches, or repairs Chrome. The "
        "verdict names the domain actually checked; one domain's session "
        "does not prove another domain's authorization.",
        options=(
            _option(
                "domain",
                "Domain to probe; repeat for a subset, omit for all enabled domains.",
                kind="append",
            ),
        ),
        effects={
            "mutates": True,
            "network": True,
            "browser_required": True,
            "destructive": False,
        },
        errors=(
            "auth_required",
            "browser_unavailable",
            "browser_busy",
            "service_failure",
        ),
        examples=(
            "dogopencli auth check",
            "dogopencli auth check --domain liquidity --format text",
        ),
        next=("dogopencli help login", "dogopencli help payment"),
        handler="auth.check",
        constraints=(
            "Writes local domain auth observations; never mutates production "
            "business configuration or recovers the browser session.",
        ),
    ),
    CommandSpec(
        ("login",),
        "Restore the dedicated login: verify headless authentication; on "
        "expiry in the selected domain, open headed Chrome for the human company "
        "SSO, wait for "
        "verified completion, then switch back to headless and re-verify.",
        options=(
            _option(
                "domain",
                "Domain to restore; repeat for a subset, omit for all enabled domains.",
                kind="append",
            ),
            TIMEOUT_SECONDS,
        ),
        effects={
            "mutates": True,
            "network": True,
            "browser_required": False,
            "destructive": False,
        },
        errors=(
            "auth_required",
            "browser_unavailable",
            "browser_busy",
            "login_in_progress",
            "service_failure",
        ),
        handler="login",
        examples=(
            "dogopencli login",
            "dogopencli login --domain liquidity",
            "dogopencli login --timeout-seconds 600",
        ),
        next=("dogopencli auth check", "dogopencli help refresh"),
    ),
    CommandSpec(
        ("logout",),
        "Clear and verify the dedicated local authentication through the "
        "reachable CDP endpoint; company-wide SSO, business caches, and other "
        "browser profiles stay unchanged. Never starts or switches Chrome.",
        effects={
            "mutates": True,
            "network": True,
            "browser_required": True,
            "destructive": False,
        },
        errors=(
            "browser_unavailable",
            "browser_busy",
            "login_in_progress",
            "logout_unverified",
            "service_failure",
        ),
        handler="logout",
        examples=("dogopencli logout",),
        next=("dogopencli auth check", "dogopencli help login"),
    ),
)

SPECS = {spec.path: spec for spec in COMMANDS}


def children(spec: CommandSpec) -> tuple[CommandSpec, ...]:
    return tuple(
        child
        for child in COMMANDS
        if child.path[:-1] == spec.path and len(child.path) == len(spec.path) + 1
    )


class Parser(argparse.ArgumentParser):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(add_help=False, allow_abbrev=False, **kwargs)

    def error(self, message: str) -> NoReturn:
        raise invalid(message)


def _add_argument(parser: argparse.ArgumentParser, spec: ArgumentSpec) -> None:
    kwargs: dict[str, Any] = {"help": spec.summary, "default": spec.default}
    kwargs["dest"] = spec.name
    if spec.kind == "bool":
        kwargs["action"] = "store_true"
        kwargs["default"] = bool(spec.default)
    elif spec.kind == "positive":
        kwargs["type"] = _positive
    elif spec.kind == "append":
        kwargs["action"] = "append"
    if spec.choices:
        kwargs["choices"] = spec.choices
    parser.add_argument(*spec.flags, **kwargs)


def globals_parser() -> Parser:
    parser = Parser(prog="dogopencli")
    for argument in GLOBALS:
        _add_argument(parser, argument)
    return parser


def leaf_parser(spec: CommandSpec) -> Parser:
    parser = Parser(prog="dogopencli " + " ".join(spec.path), description=spec.summary)
    for argument in spec.options:
        _add_argument(parser, argument)
    return parser
