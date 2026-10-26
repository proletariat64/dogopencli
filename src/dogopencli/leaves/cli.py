"""Manifest-driven action-first public command registration."""

import math
import sys
from typing import Any

from dogopencli import __version__, config
from dogopencli.command_model import Parser
from dogopencli.domain_contracts import domain_declarations
from dogopencli.domains import DomainService
from dogopencli.errors import CliError, diagnostic, error_exit_code, normalize_warnings
from dogopencli.jsonutil import canonical
from dogopencli.rendering import render_text

from .registry import Leaf, Registry
from .runtime import execute


def emit(
    data: Any,
    meta: dict | None = None,
    error: dict | None = None,
    output_format: str = "json",
) -> None:
    if meta is not None and meta.get("warnings"):
        meta = {**meta, "warnings": normalize_warnings(meta["warnings"])}
        for warning in meta["warnings"]:
            print(f"warning: {warning['code']}: {warning['message']}", file=sys.stderr)
    envelope = {"data": data, "meta": meta, "error": error}
    if output_format == "json":
        print(canonical(envelope))
    else:
        sections = []
        if data is not None or error is None:
            sections.append(render_text(data))
        if meta is not None:
            sections.append("Metadata:\n" + render_text(meta, 1))
        if error is not None:
            sections.append("Error:\n" + render_text(error, 1))
        print("\n\n".join(sections))


def _record_execution(
    service: DomainService | None,
    leaf: Leaf | None,
    operation: str | None,
    *,
    started: bool,
    error_code: str | None = None,
    warning: bool = False,
) -> None:
    if (
        not started
        or service is None
        or leaf is None
        or operation not in {"list", "get", "refresh"}
    ):
        return
    try:
        service.record_execution(
            leaf.domain,
            leaf.id,
            outcome="failed" if error_code else "warning" if warning else "success",
            operation=operation,
            error_code=error_code,
        )
    except CliError:
        print("warning: execution observation was not saved", file=sys.stderr)


def _failure_meta(meta: dict | None, operation: str | None) -> dict:
    return {
        **(meta or {}),
        "outcome": "failed",
        "data_quality": (
            "incomplete"
            if meta
            and any(meta.get(key) is False for key in ("complete", "dataset_complete"))
            else "unusable"
        ),
        "publication": {
            "status": "unchanged" if operation == "refresh" else "not_requested",
            "reason": "rejected" if operation == "refresh" else None,
        },
        **({"published": False} if operation == "refresh" else {}),
    }


def main(argv: list[str]) -> int:
    output_format = "json"
    operation = None
    leaf = None
    service = None
    started = False
    try:
        common = Parser(add_help=False, allow_abbrev=False)
        common.add_argument("--version", action="store_true")
        common.add_argument("--config-dir")
        common.add_argument("--format", choices=("json", "text"), default="json")
        controls, tokens = common.parse_known_args(argv)
        output_format = controls.format
        from ..command_model import resolve

        # Discover and validate the entire invocation before activating runtime.
        # The same declarations drive public help and this execution parser.
        if len(tokens) >= 2:
            operation = tokens[1]
        try:
            invocation = resolve(argv)
        except CliError:
            # Preserve the established missing-leaf execution error envelope.
            if (
                len(tokens) >= 3
                and tokens[0] in {domain.id for domain in domain_declarations()}
                and tokens[1] in {"list", "get", "refresh", "prune", "describe"}
                and not any(token in {"-h", "--help"} for token in tokens)
            ):
                Registry(config.config_path(controls.config_dir)).discover().get(
                    tokens[0], tokens[2]
                )
            raise
        output_format = invocation.args.format
        config_file = invocation.config_file
        node = invocation.node
        if invocation.args.version:
            emit({"version": __version__}, output_format=output_format)
            return 0
        if invocation.help_requested or node.handler is None:
            from ..command_model import emit_help

            return emit_help(invocation)
        if node.path[:1] == ("plugins",):
            if node.path[1] == "list":
                from .discovery import list_plugins

                data = list_plugins(config_file, registry=invocation.registry)
            else:
                from .lifecycle import install, uninstall

                data = (
                    install(config_file, invocation.args.source)
                    if node.path[1] == "install"
                    else uninstall(config_file, invocation.args.identity)
                )
            emit(data, output_format=output_format)
            return 0
        if len(node.path) != 3:
            raise CliError("INVALID_ARGUMENT", "Use dogopencli --help", exit_code=2)
        domain, operation, name = node.path
        leaf = invocation.registry.get(domain, name)
        if operation == "describe":
            from .documentation import describe, render_text

            document = describe(leaf)
            if output_format == "text":
                print(render_text(document), end="")
            else:
                emit(document, output_format=output_format)
            return 0
        declared_operation = "list" if operation in {"refresh", "prune"} else operation
        definitions = (
            leaf.manifest["operations"][declared_operation].get("parameters", [])
            if operation != "prune"
            else []
        )
        remaining = invocation.remaining
        args = invocation.args
        # Runtime expects all host controls, even where an action does not accept
        # a public spelling. Defaults are applied only after syntax validation.
        for key, value in {
            "fields": None,
            "limit": 100,
            "offset": 0,
            "require_complete": False,
            "require_fresh": False,
            "live": False,
            "with_detail": False,
        }.items():
            if not hasattr(args, key):
                setattr(args, key, value)
        if args.with_detail and not args.live:
            raise CliError(
                "INVALID_ARGUMENT", "--with-detail requires --live", exit_code=2
            )
        args.explicit_parameters = {
            token.partition("=")[0][2:].replace("-", "_")
            for token in remaining
            if token.startswith("--")
        }
        parameters = {
            definition["name"].replace("-", "_"): getattr(
                args, definition["name"].replace("-", "_")
            )
            for definition in definitions
        }
        if operation in {"refresh", "get"} or args.live:
            for definition in definitions:
                if (
                    definition.get("required")
                    and parameters[definition["name"].replace("-", "_")] is None
                ):
                    raise CliError(
                        "INVALID_ARGUMENT",
                        f"--{definition['name']} is required",
                        exit_code=2,
                    )
        parameters = {
            key: value for key, value in parameters.items() if value is not None
        }
        for value in parameters.values():
            values = value if isinstance(value, list) else [value]
            if any(
                isinstance(item, float) and not math.isfinite(item) for item in values
            ):
                raise CliError(
                    "INVALID_ARGUMENT", "numeric parameters must be finite", exit_code=2
                )
        service = DomainService(config_file, registry=invocation.registry)
        domain_row = service.inventory(domain)[0]
        if operation != "prune" and not domain_row["enabled"]:
            raise CliError("DOMAIN_DISABLED", f"Domain is disabled: {domain}")
        registry = Registry(config_file).scan()
        leaf = registry.get(domain, name)
        started = True
        data, meta = execute(leaf, operation, parameters, args, config_file)
        _record_execution(
            service,
            leaf,
            operation,
            started=started,
            warning=bool(meta.get("warnings")),
        )
        emit(data, meta, output_format=output_format)
        return 0
    except CliError as exc:
        _record_execution(
            service, leaf, operation, started=started, error_code=exc.code
        )
        emit(
            None,
            _failure_meta(exc.meta, operation),
            exc.diagnostic(component=leaf.id if leaf else None),
            output_format,
        )
        return error_exit_code(exc.code)
    except KeyboardInterrupt:
        _record_execution(
            service, leaf, operation, started=started, error_code="INTERRUPTED"
        )
        print("interrupted", file=sys.stderr)
        emit(
            None,
            _failure_meta(None, operation),
            diagnostic(
                "INTERRUPTED",
                "Inquiry interrupted",
                retryable=True,
                component=leaf.id if leaf else None,
                consequence="No result was accepted; the previous cache is preserved.",
            ),
            output_format,
        )
        return error_exit_code("INTERRUPTED")
    except Exception:
        _record_execution(
            service, leaf, operation, started=started, error_code="INTERNAL_ERROR"
        )
        emit(
            None,
            _failure_meta(None, operation),
            diagnostic(
                "INTERNAL_ERROR",
                "unexpected command failure",
                retryable=False,
                origin="host",
                stage="execution",
                component=leaf.id if leaf else None,
                consequence="The requested result was not accepted.",
            ),
            output_format,
        )
        return error_exit_code("INTERNAL_ERROR")
