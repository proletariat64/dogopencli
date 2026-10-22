"""Read-only local System information; never initialize or inspect business rows."""

import contextlib
import platform
import sqlite3
import stat
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from . import __version__
from .browser.environment import resolve_environment
from .cache import Cache
from .config import cache_ttl_hours
from .domain_contracts import domain_declarations
from .errors import CliError
from .leaves.registry import Registry
from .temporary_query import is_stale


def _file(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "size_bytes": None}
    try:
        status = path.stat()
        if not stat.S_ISREG(status.st_mode):
            raise OSError
        result.update(state="present", size_bytes=status.st_size)
    except FileNotFoundError:
        result["state"] = "missing"
    except OSError:
        result["state"] = "unavailable"
    return result


def _configuration(config_file: Path) -> dict[str, Any]:
    result = _file(config_file)
    result.update(ttl_hours=None, cdp_url=None, profile=None)
    try:
        result["ttl_hours"] = cache_ttl_hours(config_file)
        browser = resolve_environment(config_file=config_file)
        result.update(cdp_url=browser.cdp_url, profile=str(browser.profile))
    except CliError:
        result.update(state="unavailable", error_code="CONFIG_ERROR")
    return result


def _installation() -> dict[str, Any]:
    try:
        distribution = metadata.distribution("dogopencli")
        package_location = str(distribution.locate_file(""))
    except metadata.PackageNotFoundError:
        package_location = None
    return {
        "version": __version__,
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.system() + " · " + platform.machine(),
        "module_path": str(Path(__file__).resolve().parent),
        "distribution_path": package_location,
    }


def _cache_info(registry: Registry, ttl: float | None, now: datetime) -> dict[str, Any]:
    result = _file(registry.cache_path)
    leaves = [
        leaf
        for leaf in registry.leaves.values()
        if "list" in leaf.manifest["operations"]
    ]
    try:
        snapshots = {
            item.namespace: item for item in Cache(registry.cache_path).snapshots()
        }
    except (CliError, OSError, ValueError, TypeError, IndexError):
        result.update(
            state="unavailable", snapshot_count=None, row_count=None, leaves=[]
        )
        return result
    rows = []
    for leaf in sorted(leaves, key=lambda item: item.id):
        snapshot = snapshots.get(leaf.cache_namespace)
        row: dict[str, Any] = {
            "leaf_id": leaf.id,
            "state": "missing",
            "row_count": None,
            "fetched_at": None,
            "freshness": "unknown",
        }
        if snapshot is not None:
            if type(snapshot.row_count) is not int or snapshot.row_count < 0:
                row["state"] = "unavailable"
            else:
                row.update(
                    state="available",
                    row_count=snapshot.row_count,
                    fetched_at=snapshot.fetched_at,
                    simulated=snapshot.simulated,
                )
                try:
                    if ttl is not None:
                        row["freshness"] = (
                            "stale" if is_stale(snapshot, ttl, now) else "fresh"
                        )
                except (ValueError, TypeError, OverflowError):
                    pass
        rows.append(row)
    result.update(
        snapshot_count=sum(row["state"] == "available" for row in rows),
        row_count=sum(row["row_count"] or 0 for row in rows),
        leaves=rows,
    )
    if any(row["state"] == "unavailable" for row in rows):
        result.update(state="unavailable", snapshot_count=None, row_count=None)
    elif result["state"] == "present":
        result["state"] = "available"
    return result


def _bindings(config_file: Path) -> list[tuple]:
    path = config_file.parent / "leaf-registry.sqlite3"
    if not path.exists():
        return []
    with contextlib.closing(
        sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2)
    ) as database:
        if (
            database.execute(
                "SELECT 1 FROM sqlite_master WHERE name='bindings' AND type='table'"
            ).fetchone()
            is None
        ):
            raise ValueError("binding metadata is unavailable")
        rows = database.execute(
            "SELECT leaf_id, database_path, relation_name, active "
            "FROM bindings ORDER BY database_path, leaf_id"
        ).fetchall()
    for leaf_id, database_path, relation, active in rows:
        if (
            not all(
                isinstance(value, str) and value
                for value in (leaf_id, database_path, relation)
            )
            or not Path(database_path).is_absolute()
            or active not in (0, 1)
        ):
            raise ValueError("binding metadata is invalid")
    return rows


def _database_info(path: Path, rows: list[tuple], installed: set[str]) -> dict:
    result = _file(path)
    datasets = [
        {
            "leaf_id": leaf_id,
            "relation": relation,
            "association": "installed"
            if leaf_id in installed
            else "retained"
            if not active
            else "unavailable",
            "estimated_rows": None,
            "state": "unavailable",
        }
        for leaf_id, _, relation, active in rows
    ]
    result["datasets"] = datasets
    if result["state"] != "present":
        return result
    if not rows:
        result["state"] = "not_inspected"
        return result
    import duckdb

    try:
        with duckdb.connect(
            str(path),
            read_only=True,
            config={
                "enable_external_access": False,
                "autoload_known_extensions": False,
                "autoinstall_known_extensions": False,
            },
        ) as database:
            database.execute("BEGIN TRANSACTION")
            tables = dict(
                database.execute(
                    "SELECT table_name, estimated_size FROM duckdb_tables() "
                    "WHERE schema_name='main' AND NOT internal"
                ).fetchall()
            )
            if "_dogopencli_leaf_ownership" not in tables:
                raise ValueError("ownership metadata is unavailable")
            for dataset in datasets:
                relation = dataset["relation"]
                if relation not in tables or relation.lower().startswith("_dogopencli"):
                    continue
                owner = database.execute(
                    "SELECT leaf_id FROM _dogopencli_leaf_ownership "
                    "WHERE relation_name=?",
                    [relation],
                ).fetchall()
                if owner != [(dataset["leaf_id"],)]:
                    continue
                dataset.update(state="available", estimated_rows=tables[relation])
            database.execute("ROLLBACK")
        result["state"] = (
            "available"
            if all(d["state"] == "available" for d in datasets)
            else "unavailable"
        )
    except (duckdb.Error, ValueError, OSError) as error:
        message = str(error).lower()
        result["state"] = (
            "busy"
            if "lock" in message or "different configuration" in message
            else "unavailable"
        )
        for dataset in datasets:
            dataset.update(state="unavailable", estimated_rows=None)
    return result


def _duckdog_info(registry: Registry) -> dict[str, Any]:
    try:
        rows = _bindings(registry.config_file)
        configured = registry.database_path()
    except (sqlite3.Error, OSError, ValueError, CliError):
        return {"state": "unavailable", "databases": [], "dataset_count": None}
    groups: dict[Path, list[tuple]] = {configured: []}
    for row in rows:
        groups.setdefault(Path(row[1]), []).append(row)
    databases = [
        _database_info(path, group, set(registry.leaves))
        for path, group in groups.items()
    ]
    return {
        "state": "unavailable"
        if any(db["state"] in {"unavailable", "busy"} for db in databases)
        else "available",
        "dataset_count": len(rows),
        "databases": databases,
    }


def read_system_info(config_file: Path) -> dict[str, Any]:
    """Return allowlisted metadata only; no auth, adapters or business transport."""
    config_file = config_file.expanduser().resolve()
    registry = Registry(config_file).discover()
    now = datetime.now(timezone.utc)
    configuration = _configuration(config_file)
    return {
        "observed_at": now.isoformat(),
        "configuration": configuration,
        "installation": _installation(),
        "domain_count": len(domain_declarations()),
        "leaf_count": len(registry.leaves),
        "declaration_issues": len(registry.diagnostics),
        "cache": _cache_info(registry, configuration["ttl_hours"], now),
        "duckdog": _duckdog_info(registry),
    }
