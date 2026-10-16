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
from dogopencli.plugins import domain_plugins

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


def _boolean(value: str) -> bool:
    if value.lower() in ("true", "1"):
        return True
    if value.lower() in ("false", "0"):
        return False
    raise argparse.ArgumentTypeError("expected true or false")


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
        if controls.version:
            emit({"version": __version__}, output_format=output_format)
            return 0
        config_file = config.config_path(controls.config_dir)
        if tokens == ["plugins", "install-pilots"]:
            emit(_install(config_file), output_format=output_format)
            return 0
        registry = Registry(config_file).scan()
        domains = {domain.id: domain for domain in domain_plugins()}
        if not tokens or tokens in (["--help"], ["-h"], ["help"]):
            emit(
                {
                    "usage": "dogopencli <domain> <action> <dotted-leaf>",
                    "domains": sorted(domains),
                    "actions": ["list", "get", "refresh", "prune", "help", "describe"],
                    "installation": "plugins install-pilots",
                    "diagnostics": registry.diagnostics,
                },
                output_format=output_format,
            )
            return 0
        if len(tokens) == 1 and tokens[0] in domains:
            emit(
                {
                    "domain": tokens[0],
                    "leaves": [
                        item.name
                        for item in registry.leaves.values()
                        if item.domain == tokens[0]
                    ],
                    "diagnostics": registry.diagnostics,
                },
                output_format=output_format,
            )
            return 0
        if (
            len(tokens) < 3
            or tokens[0] not in domains
            or tokens[1] not in {"list", "get", "refresh", "prune", "help", "describe"}
        ):
            raise CliError(
                "INVALID_ARGUMENT",
                "use <domain> <action> <dotted-leaf-name>",
                exit_code=2,
            )
        domain, operation, name, *remaining = tokens
        leaf = registry.get(domain, name)
        if (
            operation in {"help", "describe"}
            or "--help" in remaining
            or "-h" in remaining
        ):
            if any(token not in {"--help", "-h"} for token in remaining):
                raise CliError(
                    "INVALID_ARGUMENT", "Unsupported documentation option", exit_code=2
                )
            from .documentation import describe, render_text

            document = describe(leaf)
            if output_format == "text":
                print(render_text(document), end="")
            else:
                emit(document, output_format=output_format)
            return 0
        declared_operation = "list" if operation in {"refresh", "prune"} else operation
        if declared_operation not in leaf.manifest["operations"]:
            raise CliError(
                "UNSUPPORTED_CAPABILITY",
                f"{leaf.id} does not support {operation}",
                exit_code=2,
            )
        parser = Parser(
            prog=f"dogopencli {domain} {operation} {name}",
            add_help=False,
            allow_abbrev=False,
        )
        parser.add_argument("--fields")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--require-complete", action="store_true")
        parser.add_argument("--require-fresh", action="store_true")
        parser.add_argument("--live", action="store_true")
        if operation == "get":
            parser.add_argument("detail_identity")
        definitions = (
            leaf.manifest["operations"][declared_operation].get("parameters", [])
            if operation != "prune"
            else []
        )
        types = {"string": str, "integer": int, "number": float, "boolean": _boolean}
        for definition in definitions:
            kwargs = {
                "type": types[definition["type"]],
                "default": definition.get("default"),
            }
            if "choices" in definition:
                kwargs["choices"] = definition["choices"]
            if definition.get("multiple"):
                kwargs["action"] = "append"
            parser.add_argument("--" + definition["name"], **kwargs)
        args = parser.parse_args(remaining)
        if operation in {"get", "prune"}:
            unsupported = {
                "--limit",
                "--offset",
                "--live",
                "--require-fresh",
                "--require-complete",
            }
            if operation == "prune":
                unsupported.add("--fields")
            if any(token.partition("=")[0] in unsupported for token in remaining):
                raise CliError(
                    "INVALID_ARGUMENT",
                    "Option does not apply to this action",
                    exit_code=2,
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
