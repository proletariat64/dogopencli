"""Help routing: syntactic command resolution before any business environment.

Issue #13: no-argument/bare-group navigation, ``help PATH``, ``PATH --help``
and explicit ``--format text`` all resolve through the one command tree
declared in ``helpspec`` (business) and ``auth/spec`` (authentication), and
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
from typing import Any

from . import __version__
from .auth.spec import SPECS as AUTH_SPECS
from .auth.spec import document as auth_document
from .auth.spec import render_text as auth_render_text
from .errors import EXIT_OK, EXIT_USAGE, INVALID_ARGUMENT
from .helpspec import (
    HELP_FORMATS,
    BizNode,
    document,
    opt,
    render_text,
)
from .helpspec import (
    REFRESH_OUTPUT as _REFRESH_OUTPUT,
)
from .jsonutil import canonical
from .plugins.payment.channel import CHANNEL_LIST_NODE
from .plugins.payment.cost import COST_LIST_NODE
from .plugins.payment.sla import SLA_GET_NODE, SLA_LIST_NODE

_AUTH_PATHS = {("auth",), ("auth", "check"), ("login",), ("logout",)}

# Options that may legally precede the first command word (auth globals and
# help controls); anything else stops the command-word scan.
_PRE_COMMAND_VALUE_OPTIONS = {"--config-dir", "--format"}
_PRE_COMMAND_FLAGS = {"--verbose", "--quiet", "--no-color", "--version", "-h", "--help"}

_REFRESH_EFFECTS_BASE = {
    "mutates": True,
    "network": False,
    "browser_required": False,
    "destructive": False,
}
_REFRESH_SNAPSHOT_VARIANT: dict[str, Any] = {
    "when": "the configured source is a snapshot dataset",
    "summary": "imports the local dataset; no network and no browser",
    "effects": {
        "mutates": True,
        "network": False,
        "browser_required": False,
        "destructive": False,
    },
}
_REFRESH_CDP_VARIANT: dict[str, Any] = {
    "when": "the configured source is cdp",
    "summary": "queries the backend through the existing CDP session and"
    " rebuilds the cache",
    "effects": {
        "mutates": True,
        "network": True,
        "browser_required": True,
        "destructive": False,
    },
}
_REFRESH_CDP_EFFECTS: dict[str, Any] = {
    "mutates": True,
    "network": True,
    "browser_required": True,
    "destructive": False,
}

_REFRESH_CHANNEL_NODE = BizNode(
    ("refresh", "payment", "channel"),
    "Import the configured channel source into the local cache.",
    options=(
        opt(
            "payout_type",
            "Payout scope.",
            "str",
            default="EXTERNAL",
            choices=("EXTERNAL", "LIQUIDITY", "MANUAL", "SETTLEMENT"),
        ),
    ),
    constraints=(
        "The source branch is decided by configuration; both branches are"
        " listed statically in effects_variants.",
        "Progress diagnostics go to stderr; the result envelope goes to stdout.",
    ),
    effects=dict(_REFRESH_EFFECTS_BASE),
    effects_variants=(_REFRESH_SNAPSHOT_VARIANT, _REFRESH_CDP_VARIANT),
    output=dict(_REFRESH_OUTPUT),
    errors=(
        "INVALID_ARGUMENT",
        "CONFIG_ERROR",
        "SOURCE_DATA_MISSING",
        "SOURCE_DATA_INVALID",
        "SOURCE_SCOPE_UNAVAILABLE",
        "INVALID_RESPONSE",
        "AUTH_REQUIRED",
        "BROWSER_UNAVAILABLE",
        "LOCKED",
        "TIMEOUT",
        "BUSINESS_QUERY_FAILED",
    ),
    examples=(
        "dogopencli refresh payment channel",
        "dogopencli refresh payment channel --payout-type EXTERNAL",
    ),
    next=("dogopencli help payment channel list",),
    handler=True,
)

_REFRESH_COST_NODE = BizNode(
    ("refresh", "payment", "cost"),
    "Rebuild the payment cost cache through the existing CDP session.",
    constraints=(
        "Requires the CDP source and an existing authenticated browser session.",
        "Progress diagnostics go to stderr; the result envelope goes to stdout.",
    ),
    effects=dict(_REFRESH_CDP_EFFECTS),
    output=dict(_REFRESH_OUTPUT),
    errors=(
        "INVALID_ARGUMENT",
        "CONFIG_ERROR",
        "INVALID_RESPONSE",
        "AUTH_REQUIRED",
        "BROWSER_UNAVAILABLE",
        "LOCKED",
        "TIMEOUT",
        "BUSINESS_QUERY_FAILED",
    ),
    examples=("dogopencli refresh payment cost",),
    next=("dogopencli help payment cost list",),
    handler=True,
)

_REFRESH_SLA_NODE = BizNode(
    ("refresh", "payment", "sla"),
    "Rebuild the payment SLA baseline cache through the existing CDP session"
    " (full list, then every detail).",
    constraints=(
        "Requires the CDP source and an existing authenticated browser session.",
        "Progress diagnostics go to stderr; the result envelope goes to stdout.",
    ),
    effects=dict(_REFRESH_CDP_EFFECTS),
    output=dict(_REFRESH_OUTPUT),
    errors=(
        "INVALID_ARGUMENT",
        "CONFIG_ERROR",
        "INVALID_RESPONSE",
        "AUTH_REQUIRED",
        "BROWSER_UNAVAILABLE",
        "LOCKED",
        "TIMEOUT",
        "BUSINESS_QUERY_FAILED",
    ),
    examples=("dogopencli refresh payment sla",),
    next=("dogopencli help payment sla baselines list",),
    handler=True,
)

_LEAF_NODES = (
    CHANNEL_LIST_NODE,
    COST_LIST_NODE,
    SLA_LIST_NODE,
    SLA_GET_NODE,
    _REFRESH_CHANNEL_NODE,
    _REFRESH_COST_NODE,
    _REFRESH_SLA_NODE,
)

NODES: dict[tuple[str, ...], BizNode] = {
    (): BizNode(
        (),
        "Inquiry-only, read-only payment operations queries; the default"
        " reads the local cache.",
        children=(
            ("payment", "Payment product queries: channels, costs, and SLA baselines."),
            ("refresh", "Explicitly rebuild local caches; never runs implicitly."),
            ("auth", AUTH_SPECS[("auth",)].summary),
            ("login", AUTH_SPECS[("login",)].summary),
            ("logout", AUTH_SPECS[("logout",)].summary),
        ),
        constraints=(
            "Business queries never modify production business configuration.",
        ),
        errors=("INVALID_ARGUMENT",),
        examples=(
            "dogopencli",
            "dogopencli help payment",
            "dogopencli help payment channel list",
        ),
        next=(
            "dogopencli help payment",
            "dogopencli help refresh",
            "dogopencli --format text",
        ),
    ),
    ("payment",): BizNode(
        ("payment",),
        "Payment product queries: channels, costs, and SLA baselines.",
        children=(
            ("channel", "Payment channel queries."),
            ("cost", "Payment channel cost configuration queries."),
            ("sla", "Payment SLA baseline queries."),
        ),
        examples=("dogopencli payment channel list",),
        next=("dogopencli help payment channel",),
    ),
    ("payment", "channel"): BizNode(
        ("payment", "channel"),
        "Payment channel queries.",
        children=(("list", CHANNEL_LIST_NODE.summary),),
        examples=("dogopencli payment channel list",),
        next=("dogopencli help payment channel list",),
    ),
    ("payment", "cost"): BizNode(
        ("payment", "cost"),
        "Payment channel cost configuration queries.",
        children=(("list", COST_LIST_NODE.summary),),
        examples=("dogopencli payment cost list",),
        next=("dogopencli help payment cost list",),
    ),
    ("payment", "sla"): BizNode(
        ("payment", "sla"),
        "Payment SLA baseline queries.",
        children=(("baselines", "SLA baseline list and detail queries."),),
        examples=("dogopencli payment sla baselines list",),
        next=("dogopencli help payment sla baselines",),
    ),
    ("payment", "sla", "baselines"): BizNode(
        ("payment", "sla", "baselines"),
        "SLA baseline list and detail queries.",
        children=(
            ("list", SLA_LIST_NODE.summary),
            ("get", SLA_GET_NODE.summary),
        ),
        examples=("dogopencli payment sla baselines list",),
        next=(
            "dogopencli help payment sla baselines list",
            "dogopencli help payment sla baselines get",
        ),
    ),
    ("refresh",): BizNode(
        ("refresh",),
        "Explicitly rebuild local caches; never runs implicitly.",
        children=(("payment", "Rebuild payment product caches."),),
        examples=("dogopencli refresh payment channel",),
        next=("dogopencli help refresh payment",),
    ),
    ("refresh", "payment"): BizNode(
        ("refresh", "payment"),
        "Rebuild payment product caches.",
        children=(
            ("channel", _REFRESH_CHANNEL_NODE.summary),
            ("cost", _REFRESH_COST_NODE.summary),
            ("sla", _REFRESH_SLA_NODE.summary),
        ),
        examples=("dogopencli refresh payment channel",),
        next=("dogopencli help refresh payment channel",),
    ),
}
NODES.update({node.path: node for node in _LEAF_NODES})


def leading_command(tokens: list[str]) -> tuple[str | None, int]:
    """First command word and its index; known pre-command options only."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return None, len(tokens)
        if token in _PRE_COMMAND_VALUE_OPTIONS:
            index += 2
            continue
        if token in _PRE_COMMAND_FLAGS:
            index += 1
            continue
        if token.startswith("-"):
            return None, index
        return token, index
    return None, len(tokens)


def _resolve_child(path: tuple[str, ...], word: str) -> tuple[str, ...] | None:
    if path == ():
        if word in ("payment", "refresh", "auth", "login", "logout"):
            return (word,)
        return None
    if path == ("auth",):
        return ("auth", "check") if word == "check" else None
    node = NODES.get(path)
    if node is None:
        return None
    for name, _summary in node.children:
        if name == word:
            return (*path, word)
    return None


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


def _option_arity(node: BizNode, flag: str) -> int | None:
    for option in node.options:
        if option.flag == flag:
            return 0 if option.kind == "bool" else 1
    return None


def help_main(tokens: list[str]) -> int:
    """``dogopencli help [PATH]``: path words plus help control options only."""
    try:
        cut = tokens.index("--")
        pre, post = tokens[:cut], tokens[cut + 1 :]
    except ValueError:
        pre, post = tokens, []
    path: tuple[str, ...] = ()
    format_value: str | None = None
    format_missing = False
    unknown_option: str | None = None
    unknown_word: str | None = None
    index = 0
    while index < len(pre):
        token = pre[index]
        if token in ("-h", "--help"):
            index += 1
            continue
        if token == "--format":
            following = pre[index + 1] if index + 1 < len(pre) else None
            if following is None or following.startswith("-"):
                format_missing = True
                index += 1
            else:
                format_value = following
                index += 2
            continue
        if token.startswith("-"):
            unknown_option = token
            break
        resolved = _resolve_child(path, token)
        if resolved is None:
            unknown_word = token
            break
        path = resolved
        index += 1
    fail = _auth_error if path in _AUTH_PATHS else _business_error
    if format_missing:
        return fail("option --format requires a value", path, "json")
    if format_value is not None and format_value not in HELP_FORMATS:
        return fail(
            f"invalid help format: {format_value!r}; expected json or text",
            path,
            "json",
        )
    if unknown_word is not None:
        return fail(f"unknown command: {unknown_word}", path, format_value or "json")
    if unknown_option is not None:
        return fail(
            f"unrecognized option: {unknown_option}", path, format_value or "json"
        )
    if post:
        return fail(
            "unrecognized arguments: " + " ".join(post), path, format_value or "json"
        )
    return _emit_help(path, format_value or "json")


def business_entry(
    values: list[str],
    execute: Callable[[BizNode, list[str], set[int]], int],
) -> int:
    """Business/root routing: help and navigation errors, else execution.

    ``execute`` receives the resolved leaf node, the original argv, and the
    indices of the path-word tokens to strip before argparse parsing.
    """
    try:
        cut = values.index("--")
        pre, post = values[:cut], values[cut + 1 :]
    except ValueError:
        pre, post = values, []
    node = NODES[()]
    word_indices: set[int] = set()
    help_flag = False
    help_pos = -1
    version_flag = False
    version_pos = -1
    format_value: str | None = None
    format_missing = False
    pre_path_format = False
    unknown_option: str | None = None
    unknown_word: str | None = None
    index = 0
    while index < len(pre):
        token = pre[index]
        if token in ("-h", "--help"):
            if not help_flag:
                help_pos = index
            help_flag = True
            index += 1
            continue
        if token == "--version":
            if not version_flag:
                version_pos = index
            version_flag = True
            index += 1
            continue
        if token == "--format":
            following = pre[index + 1] if index + 1 < len(pre) else None
            if following is None or following.startswith("-"):
                format_missing = True
                index += 1
            else:
                if not word_indices:
                    pre_path_format = True
                format_value = following
                index += 2
            continue
        if token.startswith("-"):
            arity = _option_arity(node, token) if node.handler else None
            if arity is None:
                if unknown_option is None:
                    unknown_option = token
                index += 1
            elif arity == 0:
                index += 1
            else:
                following = pre[index + 1] if index + 1 < len(pre) else None
                if following is None or following.startswith("-"):
                    index += 1
                else:
                    index += 2
            continue
        if node.handler:
            unknown_word = token
            break
        resolved = _resolve_child(node.path, token)
        if resolved is None:
            unknown_word = token
            break
        node = NODES[resolved]
        word_indices.add(index)
        index += 1
    if version_flag and not word_indices and (not help_flag or version_pos < help_pos):
        # argparse version-action compatibility: print and exit 0.
        print(f"dogopencli {__version__}")
        raise SystemExit(EXIT_OK)
    if node.handler and not help_flag:
        if unknown_word is not None:
            return _business_error(
                f"unrecognized arguments: {unknown_word}", node.path, "json"
            )
        if pre_path_format:
            return _business_error(
                "unrecognized option before the command path: --format",
                node.path,
                "json",
            )
        if version_flag:
            return _business_error("unrecognized option: --version", node.path, "json")
        return execute(node, values, word_indices)
    if version_flag and unknown_option is None:
        unknown_option = "--version"
    if format_missing:
        return _business_error("option --format requires a value", node.path, "json")
    if format_value is not None and format_value not in HELP_FORMATS:
        return _business_error(
            f"invalid help format: {format_value!r}; expected json or text",
            node.path,
            "json",
        )
    if unknown_word is not None:
        return _business_error(
            f"unknown command: {unknown_word}", node.path, format_value or "json"
        )
    if unknown_option is not None:
        return _business_error(
            f"unrecognized option: {unknown_option}", node.path, format_value or "json"
        )
    if post:
        return _business_error(
            "unrecognized arguments: " + " ".join(post),
            node.path,
            format_value or "json",
        )
    return _emit_help(node.path, format_value or "json")


__all__ = [
    "NODES",
    "business_entry",
    "help_main",
    "leading_command",
]
