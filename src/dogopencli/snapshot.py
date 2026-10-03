"""Offline command-tree report; every renderer consumes the same inventory."""

import argparse
import json
import math
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from . import __version__, config
from .auth.spec import SPECS as AUTH_SPECS
from .catalog import NODES
from .errors import CliError
from .plugins import cache_bindings
from .plugins.liquidity.capability import (
    LiquidityDetailCapability,
    LiquidityListCapability,
)
from .plugins.liquidity.leaves import DEFERRED_BY_PATH, LIST_LEAVES
from .plugins.liquidity.store import INDEX_SCOPE, _owning_variant
from .snapshot_cache import Inventory, capture


class ArgumentError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ArgumentError(message)


def bindings() -> dict[tuple[str, ...], Any]:
    discovered = cache_bindings()
    # The oldest shared refresh declarations predate plugin registration.
    # Their help links identify their inquiry without duplicating inventory.
    for path, node in NODES.items():
        if path[:1] == ("refresh",) and node.handler and path not in discovered:
            for hint in node.next:
                prefix = "dogopencli help "
                if hint.startswith(prefix):
                    owner = discovered.get(tuple(hint[len(prefix) :].split()))
                    if owner is not None:
                        discovered[path] = owner
                        break
    return discovered


def overview(
    captures: list[dict[str, Any]], *, applicable: bool = True
) -> dict[str, Any]:
    if not applicable or not captures:
        status = "not_applicable" if not applicable else "missing"
        return {
            "status": status,
            "summary": status.replace("_", " "),
            "complete": None,
            "freshness": None,
            "oldest_updated": None,
            "captures": [],
        }
    qualities = {(item["complete"], item["freshness"]) for item in captures}
    complete_values = {item["complete"] for item in captures}
    freshness_values = {item["freshness"] for item in captures}
    complete = next(iter(complete_values)) if len(complete_values) == 1 else None
    freshness = next(iter(freshness_values)) if len(freshness_values) == 1 else None
    if len(qualities) > 1:
        summary = f"mixed · {len(captures)} captures"
        status = "mixed"
    else:
        summary = (
            "complete"
            if complete
            else ("incomplete" if complete is False else "present · quality unknown")
        )
        summary += " · " + (freshness or "freshness unknown")
        status = "present"
    times = [item["updated"] for item in captures if item["updated"] is not None]
    return {
        "status": status,
        "summary": summary,
        "complete": complete,
        "freshness": freshness,
        "oldest_updated": min(times, key=_time) if times else None,
        "captures": captures,
    }


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def inspect(
    owner: Any, path: tuple[str, ...], inventory: Inventory, ttl: float, now: datetime
) -> list[dict[str, Any]]:
    if isinstance(owner, LiquidityListCapability):
        entries = inventory.entries(owner.name)
        if entries is None:
            return []
        results = []
        for entry in entries:
            meta = inventory.metadata.get(entry.namespace)
            if (
                meta is None
                or isinstance(meta, Exception)
                or meta.capability != owner.name
            ):
                raise ValueError("published capture is missing")
            item = capture(meta, inventory.count(meta.namespace), ttl, now, entry=entry)
            declared = owner.descriptor
            variants = LIST_LEAVES[declared.path].variants
            item["profile"] = entry.profile
            if len(variants) > 1:
                variant = _owning_variant(declared, entry)
                item["contract_variant"] = (
                    "/".join(
                        option.match
                        for option in variant.scope_options
                        if option.virtual and option.match
                    )
                    or f"contract-{variants.index(variant) + 1}"
                )
            results.append(item)
        return results
    if isinstance(owner, LiquidityDetailCapability):
        from .plugins.liquidity.details import details_namespace

        retained = inventory.metadata.get(details_namespace(owner.name))
        if isinstance(retained, Exception):
            raise ValueError("invalid detail metadata")
        results = []
        for meta in [retained] if retained is not None else []:
            if meta.scope != "detail" or meta.source_kind != "cdp":
                continue
            objects = inventory.details(meta)
            if len(objects) != meta.row_count or len(
                {key for key, _ in objects}
            ) != len(objects):
                raise ValueError("detail storage count mismatch")
            if not objects:
                results.append(capture(meta, 0, ttl, now, detail=True))
            for key, updated in objects:
                results.append(
                    capture(
                        meta,
                        1,
                        ttl,
                        now,
                        key=key,
                        fetched_at=updated or "",
                        detail=True,
                    )
                )
        return results
    metas = inventory.metas(owner.name)
    results = []
    paired_detail = path[-1:] == ("get",) and any(
        node.path[-1:] == ("list",) and node.path[:-1] == path[:-1]
        for node in NODES.values()
    )
    for meta in metas:
        if meta.scope == INDEX_SCOPE:
            continue
        count = inventory.count(meta.namespace)
        item = capture(meta, count, ttl, now)
        if paired_detail:
            detail_count = inventory.detail_count(meta)
            item["rows"] = detail_count
            item["variant"] = "paired_native_document"
            if detail_count != count:
                item["complete"] = False
                item["reasons"].append("DETAIL_COVERAGE_GAP")
        results.append(item)
    return results


def build_report(
    path: tuple[str, ...] = (), *, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    nodes = {**NODES, **{p: n for p, n in AUTH_SPECS.items() if p}}
    if path != ("help",) and path not in nodes:
        raise ArgumentError("unknown command path")
    report: dict[str, Any] = {
        "snapshot_version": 1,
        "generated_at": now.isoformat(),
        "application_version": __version__,
        "inspection_complete": True,
        "inspection_errors": [],
    }
    ownership = bindings()
    leaves: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    def tree(selected: tuple[str, ...]) -> dict[str, Any]:
        node = nodes.get(selected)
        result: dict[str, Any] = {
            "command": "dogopencli" + (" " + " ".join(selected) if selected else ""),
            "children": [],
        }
        executable = selected == ("help",) or (
            node is not None and bool(getattr(node, "handler", None))
        )
        if selected in AUTH_SPECS and not getattr(node, "children", ()):
            executable = True
        if executable:
            deferred = (
                DEFERRED_BY_PATH.get(selected[1:])
                if selected[:1] == ("liquidity",)
                else None
            )
            result.update(
                availability="unsupported" if deferred else "supported",
                availability_reason=deferred.reason if deferred else None,
                cache=overview(
                    [], applicable=selected in ownership and deferred is None
                ),
                rows=None,
                updated=None,
                reason=None,
            )
            leaves.append((selected, result))
        for candidate in nodes:
            if candidate and candidate[:-1] == selected:
                result["children"].append(tree(candidate))
        if not selected:
            result["children"].append(tree(("help",)))
        return result

    report["tree"] = tree(path)
    applicable = [
        (p, leaf) for p, leaf in leaves if leaf["cache"]["status"] != "not_applicable"
    ]
    if not applicable:
        return report

    def fail(leaf: dict[str, Any], code: str, message: str) -> None:
        leaf["cache"] = {
            **overview([]),
            "status": "read_error",
            "summary": "read error",
        }
        leaf["reason"] = message
        report["inspection_complete"] = False
        error = {"code": code, "message": message, "command": leaf["command"]}
        report["inspection_errors"].append(error)

    try:
        configured = config.load([])
        if not math.isfinite(configured.ttl_hours):
            raise ValueError("invalid freshness policy")
        timedelta(hours=configured.ttl_hours)
    except (CliError, OSError, ValueError, OverflowError):
        for _, leaf in applicable:
            fail(leaf, "CONFIG_ERROR", "configuration could not be inspected")
        return report
    try:
        with Inventory(configured.cache_path) as inventory:
            for command, leaf in applicable:
                try:
                    captures = inspect(
                        ownership[command],
                        command,
                        inventory,
                        configured.ttl_hours,
                        now,
                    )
                    leaf["cache"] = overview(captures)
                    if captures:
                        leaf["rows"] = sum(item["rows"] for item in captures)
                        times = [
                            item["updated"]
                            for item in captures
                            if item["updated"] is not None
                        ]
                        leaf["updated"] = max(times, key=_time) if times else None
                        reasons = list(
                            dict.fromkeys(
                                reason
                                for item in captures
                                for reason in item["reasons"]
                            )
                        )
                        if len({item["scope_id"] for item in captures}) > 1:
                            reasons.append(
                                "multiple retained scopes; completeness is per"
                                " acquired scope"
                            )
                        if any(item["updated"] is None for item in captures):
                            reasons.append(
                                "acquisition timestamp unknown for one or more captures"
                            )
                        leaf["reason"] = "; ".join(reasons) or None
                except (
                    sqlite3.Error,
                    CliError,
                    ValueError,
                    TypeError,
                    KeyError,
                    OverflowError,
                ):
                    fail(
                        leaf,
                        "CACHE_ERROR",
                        "published cache metadata could not be inspected",
                    )
    except (sqlite3.Error, OSError, CliError, ValueError, TypeError):
        for _, leaf in applicable:
            fail(leaf, "CACHE_ERROR", "cache database could not be inspected")
    return report


def _leaves(node: dict[str, Any]) -> list[dict[str, Any]]:
    return ([node] if "availability" in node else []) + [
        leaf for child in node["children"] for leaf in _leaves(child)
    ]


def render(report: dict[str, Any], format: str) -> str:
    if format == "json":
        return json.dumps(report, ensure_ascii=False, allow_nan=False) + "\n"
    if format == "table":
        columns = ("command", "availability", "cache", "rows", "updated", "reason")
        rows = []
        for leaf in _leaves(report["tree"]):
            rows.append(
                [
                    leaf["command"],
                    leaf["availability"],
                    leaf["cache"]["summary"],
                    str(leaf["rows"]) if leaf["rows"] is not None else "—",
                    leaf["updated"] or "—",
                    leaf["availability_reason"] or leaf["reason"] or "—",
                ]
            )
        widths = [
            max([len(name), *(len(row[i]) for row in rows)])
            for i, name in enumerate(columns)
        ]
        return (
            "\n".join(
                "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
                for row in [list(columns), *rows]
            )
            + "\n"
        )
    lines: list[str] = []

    def visit(node: dict[str, Any], prefix: str, connector: str) -> None:
        line = prefix + connector + node["command"].split()[-1]
        if "availability" in node:
            rows = str(node["rows"]) + " rows" if node["rows"] is not None else "—"
            line += (
                f"  {node['availability']}  {node['cache']['summary']}"
                f"  {rows}  {node['updated'] or '—'}"
            )
        lines.append(line)
        indentation = prefix + (
            "   " if connector == "└─ " else "│  " if connector else ""
        )
        if "availability" in node:
            reason = node["availability_reason"] or node["reason"]
            if reason:
                lines.append(indentation + "reason: " + reason)
        for index, child in enumerate(node["children"]):
            visit(
                child,
                indentation,
                "└─ " if index == len(node["children"]) - 1 else "├─ ",
            )

    visit(report["tree"], "", "")
    return "\n".join(lines) + "\n"


def main(tokens: list[str]) -> int:
    parser = Parser(prog="dogopencli snapshot", add_help=False, allow_abbrev=False)
    parser.add_argument("path", nargs="*")
    parser.add_argument("--format", choices=("json", "text", "table"), default="text")
    try:
        args = parser.parse_intermixed_args(tokens)
        report = build_report(tuple(args.path))
    except ArgumentError:
        print(
            "error: INVALID_ARGUMENT: invalid snapshot path or options;"
            " run: dogopencli help snapshot",
            file=sys.stderr,
        )
        return 2
    sys.stdout.write(render(report, args.format))
    for error in report["inspection_errors"]:
        print(
            f"error: {error['code']}: {error['command']}: {error['message']}",
            file=sys.stderr,
        )
    return 0 if report["inspection_complete"] else 1
