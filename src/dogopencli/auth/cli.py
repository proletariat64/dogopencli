"""Auth command shell: grammar, help, config, output and errors only.

Ported from DI ``src/di/cli/__init__.py`` and ``errors.py`` at baseline commit
8eb163c6d140554ca167bd50349a85ca224ac342, reduced to the authentication
commands and their exit contract (ADR 0004): 0 success/help/version,
1 argument or runtime failure, 130 interrupted. Global options may appear
before or after the command; option-name abbreviation is disabled; the
deprecated ``browser_context`` positional and hidden ``--json`` alias are
rejected as invalid arguments.
"""

import argparse
import contextlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from .. import __version__
from .. import config as config_mod
from ..browser import environment as environment_mod
from ..browser.errors import (
    AUTH_REQUIRED,
    BROWSER_BUSY,
    BROWSER_UNAVAILABLE,
    CONFIG_INVALID,
    INVALID_ARGUMENTS,
    LOGIN_IN_PROGRESS,
    LOGOUT_UNVERIFIED,
    SERVICE_FAILURE,
    AuthError,
    invalid,
)
from ..browser.login import login
from ..browser.logout import logout
from ..browser.probe import check_authentication
from .output import Result, emit
from .spec import (
    SPECS,
    CommandSpec,
    document,
    globals_parser,
    leaf_parser,
    render_text,
)

CONFIG_DIR_ENV = "DOGOPENCLI_CONFIG_DIR"


def resolve_command(tokens: list[str]) -> tuple[CommandSpec, list[str]]:
    spec = SPECS[()]
    consumed = 0
    for token in tokens:
        candidate = SPECS.get((*spec.path, token))
        if candidate is None:
            break
        consumed += 1
        spec = candidate
    return spec, tokens[consumed:]


def resolve_config_dir(explicit: str | None) -> Path:
    try:
        return config_mod.config_path(explicit).parent
    except config_mod.CliError as exc:
        raise invalid(str(exc)) from exc


def dispatch(spec: CommandSpec, args: argparse.Namespace) -> Result:
    domain = getattr(args, "domain", None) or "payment"
    startup_url = environment_mod.STARTUP_URLS[domain]
    try:
        environment = environment_mod.resolve_environment(config_file=args.config_file)
        if spec.handler in {"login", "auth.check"}:
            environment = replace(environment, startup_url=startup_url)
        if spec.handler == "auth.check":
            return Result(check_authentication(environment))
        if spec.handler == "login":
            return Result(login(environment, timeout_seconds=args.timeout_seconds))
    except AuthError as exc:
        if spec.handler in {"login", "auth.check"}:
            exc.details = {**exc.details, "domain": domain, "startup_url": startup_url}
            if domain != "payment":
                exc.message = exc.message.replace(
                    "dogopencli login", f"dogopencli login --domain {domain}"
                )
        raise
    if spec.handler == "logout":
        return Result(logout(environment))
    raise invalid(f"Unknown auth action: {spec.handler}")


def _next_steps(exc: AuthError, command: str) -> list[str]:
    domain = exc.details.get("domain", "payment")
    selector = f" --domain {domain}" if domain != "payment" else ""
    steps = list(exc.next)
    if steps:
        return steps
    if exc.code == INVALID_ARGUMENTS:
        if command == "dogopencli":
            return ["dogopencli --help"]
        return ["dogopencli " + command.replace(".", " ") + " --help"]
    if exc.code in {AUTH_REQUIRED, BROWSER_UNAVAILABLE}:
        return [
            f"Run dogopencli login{selector} to restore the dedicated "
            f"browser/authentication, then re-run dogopencli auth check{selector}."
        ]
    if exc.code == BROWSER_BUSY:
        return ["Retry after the active data work or browser mutation finishes."]
    if exc.code == LOGIN_IN_PROGRESS:
        return ["Retry after the other dogopencli login operation finishes."]
    if exc.code == LOGOUT_UNVERIFIED:
        return [
            "Retry dogopencli logout; if the session still verifies, re-run "
            "dogopencli login to restore a known session, then log out again."
        ]
    if exc.code == SERVICE_FAILURE:
        return [
            f"Retry dogopencli auth check{selector}; if it persists, "
            f"check the {domain} "
            "platform service state."
        ]
    if exc.code == CONFIG_INVALID:
        return ["Fix the [auth] configuration or CDP endpoint, then retry."]
    return []


def error_dict(exc: Exception, command: str) -> dict[str, Any]:
    if isinstance(exc, AuthError):
        return {
            "code": exc.code,
            "message": exc.message,
            "retryable": bool(exc.retryable),
            "details": exc.details,
            "next": _next_steps(exc, command),
        }
    code = "io_error" if isinstance(exc, OSError) else "command_failed"
    return {
        "code": code,
        "message": str(exc),
        "retryable": False,
        "details": {},
        "next": [],
    }


def main(argv: list[str], command_hint: str | None = None) -> int:
    values = list(argv)
    hint = SPECS.get((command_hint,)) if command_hint else None
    spec = hint if hint is not None else SPECS[()]
    format = "json"
    domain_context = {}
    try:
        global_args, tokens = globals_parser().parse_known_args(values)
        format = global_args.format or "json"
        if global_args.verbose and global_args.quiet:
            raise invalid("--verbose and --quiet are mutually exclusive")
        spec, remainder = resolve_command(tokens)
        if global_args.version:
            emit("version", Result({"version": __version__}), None, format)
            return 0
        if global_args.help or not spec.handler:
            if remainder and not spec.handler:
                if remainder[0].startswith("-"):
                    raise invalid("unrecognized arguments: " + " ".join(remainder))
                raise invalid("Unknown command: " + " ".join(remainder))
            if spec.handler:
                leaf_parser(spec).parse_args(remainder, namespace=global_args)
            sys.stdout.write(
                render_text(spec)
                if format == "text"
                else json.dumps(document(spec), ensure_ascii=False) + "\n"
            )
            return 0
        args = leaf_parser(spec).parse_args(remainder, namespace=global_args)
        if spec.handler in {"login", "auth.check"}:
            domain = args.domain
            domain_context = {
                "domain": domain,
                "startup_url": environment_mod.STARTUP_URLS[domain],
            }
        try:
            args.config_file = config_mod.config_path(args.config_dir)
        except config_mod.CliError as exc:
            raise invalid(str(exc)) from exc
        args.config_dir = args.config_file.parent
        if args.verbose:
            sys.stderr.write(f"dogopencli: {spec.command}; config={args.config_dir}\n")
        if args.quiet:
            with open(os.devnull, "w") as sink, contextlib.redirect_stderr(sink):
                result = dispatch(spec, args)
        else:
            result = dispatch(spec, args)
        emit(spec.command, result, None, format)
        return result.exit_code
    except (AuthError, OSError, ValueError) as exc:
        error = error_dict(exc, spec.command)
        error["details"] = {**error["details"], **domain_context}
        emit(spec.command, Result(exit_code=1), error, format)
        return 1
    except KeyboardInterrupt:
        error = error_dict(
            AuthError("interrupted", "Command interrupted"), spec.command
        )
        error["details"] = {**error["details"], **domain_context}
        emit(spec.command, Result(exit_code=130), error, format)
        return 130
    except Exception as exc:
        error = {
            "code": "internal_error",
            "message": "Unexpected command failure",
            "retryable": False,
            "details": {"exception_type": type(exc).__name__, **domain_context},
            "next": [],
        }
        emit(spec.command, Result(exit_code=1), error, format)
        return 1
