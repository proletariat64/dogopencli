"""Help routing: syntactic command resolution before any business environment.

Issue #13: no-argument/bare-group navigation, ``help PATH``, ``PATH --help``
and explicit ``--format text`` all resolve through the one command tree
assembled in ``catalog`` from business and authentication declarations, and
every help response is produced before config parsing, auth dispatch, cache
construction, or CDP initialization. Help never reads config, cache,
browser, or network state.

Error protocols (ADR 0004): root/business navigation argument errors are the
business envelope INVALID_ARGUMENT, exit 2; errors on paths already resolved
to authentication keep the auth envelope invalid_arguments, exit 1. Help
success always exits 0 with an empty stderr.
"""

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import __version__
from .auth.spec import SPECS as AUTH_SPECS
from .auth.spec import document as auth_document
from .auth.spec import render_text as auth_render_text
from .catalog import AUTH_PATHS as _AUTH_PATHS
from .catalog import NODES
from .catalog import resolve_child as _resolve_child
from .errors import EXIT_OK, EXIT_USAGE, INVALID_ARGUMENT
from .helpspec import (
    HELP_FORMATS,
    BizNode,
    document,
    render_text,
    validate_help_options,
)
from .jsonutil import canonical

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


def _document_for(path: tuple[str, ...]) -> dict[str, Any]:
    if path in _AUTH_PATHS:
        return auth_document(AUTH_SPECS[path])
    return document(NODES[path])


def _text_for(path: tuple[str, ...]) -> str:
    if path in _AUTH_PATHS:
        return auth_render_text(AUTH_SPECS[path])
    return render_text(NODES[path])


def _emit_help(path: tuple[str, ...], format: str) -> int:
    if format == "text":
        sys.stdout.write(_text_for(path))
    else:
        sys.stdout.write(json.dumps(_document_for(path), ensure_ascii=False) + "\n")
    return EXIT_OK


def _hint(path: tuple[str, ...]) -> str:
    if not path:
        return "dogopencli --help"
    return "dogopencli help " + " ".join(path)


def _business_error(message: str, path: tuple[str, ...], format: str) -> int:
    full = f"{message}; run: {_hint(path)}"
    if format == "text":
        sys.stderr.write(f"error: {INVALID_ARGUMENT}: {full}\n")
    else:
        sys.stdout.write(
            canonical(
                {
                    "data": None,
                    "error": {
                        "code": INVALID_ARGUMENT,
                        "message": full,
                        "retryable": False,
                    },
                    "meta": None,
                }
            )
            + "\n"
        )
    return EXIT_USAGE


def _auth_error(message: str, path: tuple[str, ...], format: str) -> int:
    from .auth.cli import error_dict
    from .auth.output import Result, emit
    from .browser.errors import invalid

    command = ".".join(path)
    error = invalid(message)
    emit(command, Result(exit_code=1), error_dict(error, command), format)
    return 1


@dataclass
class _Route:
    path: tuple[str, ...] = ()
    word_indices: set[int] = field(default_factory=set)
    options: list[str] = field(default_factory=list)
    help_position: int | None = None
    version_position: int | None = None
    format: str = "json"
    pre_path_format: bool = False
    unknown_word: str | None = None


def _scan(tokens: list[str], *, explicit_help: bool) -> _Route:
    """Resolve paths and consume option values once for both help entrances.

    Keep original option tokens for the declaration-driven syntax validator.
    Continue scanning after a bad path so trailing presentation flags apply
    to errors too. Values and tokens after -- never become command words.
    """
    route = _Route()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            route.options.extend(tokens[index:])
            break
        if token.startswith("-"):
            flag, separator, inline = token.partition("=")
            node = NODES.get(route.path)
            takes_value = flag == "--format"
            if not explicit_help and node is not None:
                takes_value |= any(
                    option.flag == flag and option.kind != "bool"
                    for option in node.options
                )
            route.options.append(token)
            value = inline if separator else None
            consumed = 1
            if takes_value and not separator and index + 1 < len(tokens):
                following = tokens[index + 1]
                # Negative numbers remain argument values, not command words.
                negative = following.startswith("-") and following[1:2].isdigit()
                if not following.startswith("-") or negative:
                    value = following
                    route.options.append(following)
                    consumed = 2
            if flag == "--format":
                if not route.word_indices:
                    route.pre_path_format = True
                route.format = value if value in HELP_FORMATS else "json"
            if token in ("--help", "-h") and route.help_position is None:
                route.help_position = index
            if token == "--version" and route.version_position is None:
                route.version_position = index
            index += consumed
            continue
        resolved = (
            _resolve_child(route.path, token) if route.unknown_word is None else None
        )
        if resolved is None:
            if route.unknown_word is None:
                route.unknown_word = token
        else:
            route.path = resolved
            route.word_indices.add(index)
        index += 1
    return route


def _show_route_help(
    route: _Route, *, explicit_help: bool, error_format: str | None = None
) -> int:
    fail = _auth_error if route.path in _AUTH_PATHS else _business_error
    error_format = error_format or route.format
    if route.unknown_word is not None:
        return fail(f"unknown command: {route.unknown_word}", route.path, error_format)
    node = NODES.get(route.path)
    options = node.options if node is not None and not explicit_help else ()
    try:
        validate_help_options(route.options, options)
    except ValueError as error:
        return fail(str(error), route.path, error_format)
    return _emit_help(route.path, route.format)


def help_main(tokens: list[str]) -> int:
    """Explicit help accepts path words and help controls only."""
    return _show_route_help(_scan(tokens, explicit_help=True), explicit_help=True)


def business_entry(
    values: list[str],
    execute: Callable[[BizNode, list[str], set[int]], int],
) -> int:
    route = _scan(values, explicit_help=False)
    if (
        route.version_position is not None
        and not route.word_indices
        and (
            route.help_position is None or route.version_position < route.help_position
        )
    ):
        # Preserve the root version action's existing protocol.
        print(f"dogopencli {__version__}")
        raise SystemExit(EXIT_OK)
    if route.path in _AUTH_PATHS:
        # Valid auth prefixes route to the auth shell in main. An invalid
        # prefix must produce its protocol's error, never index the biz tree.
        return _auth_error(
            "unrecognized options before authentication command",
            route.path,
            route.format,
        )
    node = NODES[route.path]
    if node.handler and route.help_position is None:
        if route.unknown_word is not None:
            return _business_error(
                f"unrecognized arguments: {route.unknown_word}", node.path, "json"
            )
        if route.pre_path_format:
            return _business_error(
                "unrecognized option before the command path: --format",
                node.path,
                "json",
            )
        if route.version_position is not None:
            return _business_error("unrecognized option: --version", node.path, "json")
        return execute(node, values, route.word_indices)
    # Invalid describe execution remains business JSON; explicit help uses
    # the requested help format. Bare groups still navigate in that format.
    error_format = (
        "json"
        if route.path[:1] == ("describe",) and route.help_position is None
        else route.format
    )
    return _show_route_help(route, explicit_help=False, error_format=error_format)


__all__ = ["NODES", "business_entry", "help_main", "leading_command"]
