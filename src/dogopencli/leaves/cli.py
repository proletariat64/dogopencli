"""Manifest-driven action-first public command registration."""

import argparse
import math
import shutil
import sys
from pathlib import Path
from typing import Any, NoReturn

from dogopencli import __version__, config
from dogopencli.domains import DomainService
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical

from .registry import Leaf, Registry
from .runtime import execute


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CliError("INVALID_ARGUMENT", message, exit_code=2)


def emit(
    data: Any,
    meta: dict | None = None,
    error: dict | None = None,
    output_format: str = "json",
) -> None:
    envelope = {"data": data, "meta": meta, "error": error}
    if output_format == "json":
        print(canonical(envelope))
    else:
        sections = []
        if data is not None or error is None:
            sections.append(_text(data))
        if meta is not None:
            sections.append("Metadata:\n" + _text(meta, 1))
        if error is not None:
            sections.append("Error:\n" + _text(error, 1))
        print("\n\n".join(sections))


def _text(value: Any, depth: int = 0) -> str:
    """Render labeled fields and bullet lists without changing native values."""
    padding = "  " * depth
    if isinstance(value, (dict, list)):
        if not value:
            kind = "object" if isinstance(value, dict) else "list"
            return padding + f"(empty {kind})"
        items = value.items() if isinstance(value, dict) else ((None, v) for v in value)
        lines = []
        for key, item in items:
            label = f"{key}:" if key is not None else "-"
            rendered = _text(item, depth + 1)
            if isinstance(item, (dict, list)) or "\n" in rendered:
                lines.append(padding + label + "\n" + rendered)
            else:
                lines.append(padding + label + " " + rendered[len(padding) + 2 :])
        return "\n".join(lines)
    scalar = value if isinstance(value, str) and value else canonical(value)
    return "\n".join(padding + line for line in scalar.split("\n"))


def _install(config_file: Path) -> dict:
    source = Path(__file__).parents[1] / "leaf_packages"
    target = config_file.parent / "plugins"
    folders = sorted(source.glob("*/*/leaf.json"))
    destinations = [
        (manifest.parent, target / manifest.parent.parent.name / manifest.parent.name)
        for manifest in folders
    ]
    if any(destination.exists() for _, destination in destinations):
        raise CliError(
            "PLUGIN_EXISTS",
            "pilot destination already exists; replace folders explicitly",
        )
    installed = []
    try:
        for origin, destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.mkdir()
            installed.append(destination)
            shutil.copytree(
                origin,
                destination,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                dirs_exist_ok=True,
            )
    except OSError as exc:
        for destination in installed:
            shutil.rmtree(destination)
        raise CliError("IO_ERROR", "pilot installation failed") from exc
    registry = Registry(config_file).scan()
    return {
        "installed": [str(path.relative_to(target)) for path in installed],
        "diagnostics": registry.diagnostics,
    }


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
        if node.path == ("plugins", "install-pilots") and not invocation.help_requested:
            emit(_install(config_file), output_format=output_format)
            return 0
        if invocation.help_requested or node.handler is None:
            from ..helpspec import document

            emit(
                {**document(node), "diagnostics": invocation.registry.diagnostics},
                output_format=output_format,
            )
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
        }.items():
            if not hasattr(args, key):
                setattr(args, key, value)
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
        registry = Registry(config_file).scan()
        leaf = registry.get(domain, name)
        service = DomainService(config_file, registry=registry)
        domain_row = service.inventory(domain)[0]
        if operation != "prune" and not domain_row["enabled"]:
            raise CliError("DOMAIN_DISABLED", f"Domain is disabled: {domain}")
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
        meta = exc.meta
        if operation == "refresh":
            meta = {**(meta or {}), "published": False}
        emit(
            None,
            meta,
            {"code": exc.code, "message": exc.message, "retryable": exc.retryable},
            output_format,
        )
        return exc.exit_code
    except KeyboardInterrupt:
        _record_execution(
            service, leaf, operation, started=started, error_code="INTERRUPTED"
        )
        print("interrupted", file=sys.stderr)
        return 130
    except Exception:
        _record_execution(
            service, leaf, operation, started=started, error_code="INTERNAL_ERROR"
        )
        emit(
            None,
            {"published": False} if operation == "refresh" else None,
            {
                "code": "INTERNAL_ERROR",
                "message": "unexpected command failure",
                "retryable": False,
            },
            output_format,
        )
        return 1
