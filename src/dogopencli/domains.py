"""Shared, offline domain controls and operational observations.

Operational metadata lives beside the effective configuration, never in the
business query cache. Reading a new scope does not create directories or a DB.
"""

import contextlib
import json
import os
import re
import sqlite3
import tempfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .domain_contracts import DomainDeclaration, domain_declarations
from .errors import CliError


def _unknown_execution() -> dict[str, Any]:
    return {
        "outcome": "unknown",
        "updated_at": None,
        "operation": None,
        "error_code": None,
        "diagnostic": None,
    }


def _sdk_info(manifest: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Describe the host SDK selected by each statically validated operation."""
    result = {}
    for operation, specification in manifest["operations"].items():
        if specification.get("execution") == "custom":
            result[operation] = {"name": "Custom query SDK"}
        elif operation == "list":
            result[operation] = {
                "name": "List SDK",
                "provider": manifest["collection"]["provider"],
            }
        else:
            result[operation] = {"name": "Get SDK"}
    return result


class DomainService:
    """Application boundary shared by CLI, auth orchestration and localhost GUI."""

    def __init__(self, config_file: Path | None = None, *, registry=None) -> None:
        self.config_file = (config_file or config.config_path()).expanduser().resolve()
        self._registry = registry
        self.state_path = self.config_file.with_name(
            self.config_file.name + ".domains.sqlite3"
        )

    def inventory(self, domain_id: str | None = None) -> list[dict[str, Any]]:
        domains = domain_declarations()
        if domain_id is not None and not any(d.id == domain_id for d in domains):
            raise CliError("DOMAIN_NOT_FOUND", f"Unknown domain: {domain_id}")
        settings, executions, auth = self._read()
        from .leaves.registry import Registry

        registry = self._registry
        if registry is None:
            registry = Registry(self.config_file).discover()
        return [
            {
                "id": domain.id,
                "entry_point": domain.entry_point,
                "enabled": settings.get(domain.id, True),
                "auth": auth.get(domain.id, {"outcome": "unknown", "updated_at": None}),
                "leaves": [
                    {
                        "id": leaf.id,
                        "enabled": True,
                        "effective_enabled": settings.get(domain.id, True),
                        "name": leaf.name,
                        "summary": leaf.manifest["summary"],
                        "operations": list(leaf.manifest["operations"]),
                        "sdks": _sdk_info(leaf.manifest),
                        "last_execution": executions.get(
                            (domain.id, leaf.id), _unknown_execution()
                        ),
                    }
                    for leaf in registry.leaves.values()
                    if leaf.domain == domain.id
                ],
                "diagnostics": [
                    item
                    for item in registry.diagnostics
                    if item.get("id") in {"plugins", domain.id}
                    or item.get("id", "").startswith(domain.id + ".")
                ],
            }
            for domain in domains
            if domain_id is None or domain.id == domain_id
        ]

    def overview(self) -> list[dict[str, Any]]:
        """Enrich GUI cards without making command gates depend on cache reads."""
        from .leaves.runtime import cache_for

        inventory = self.inventory()
        cache = cache_for(self.config_file)
        cache_error: str | None = None

        def saved_data(leaf_id: str) -> dict[str, Any]:
            nonlocal cache_error
            if cache_error is None:
                try:
                    snapshot = cache.current("leaf:" + leaf_id)
                except CliError as error:
                    # All leaves share one database. Avoid repeating a busy
                    # timeout or failed read for every card in this inventory.
                    cache_error = error.code
                else:
                    if snapshot is None:
                        return {"state": "empty"}
                    return {
                        "state": "available",
                        "row_count": snapshot.row_count,
                        "fetched_at": snapshot.fetched_at,
                        "simulated": snapshot.simulated,
                    }
            return {"state": "unavailable", "error_code": cache_error}

        for domain in inventory:
            for leaf in domain["leaves"]:
                leaf["saved_data"] = saved_data(leaf["id"])
        return inventory

    def _read(self) -> tuple[dict, dict, dict]:
        if not self.state_path.exists():
            return {}, {}, {}
        try:
            with contextlib.closing(
                sqlite3.connect(
                    self.state_path.as_uri() + "?mode=ro", uri=True, timeout=5
                )
            ) as database:
                if database.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValueError("unsupported schema")
                settings = dict(
                    database.execute("SELECT domain_id, enabled FROM settings")
                )
                if any(
                    type(value) is not int or value not in (0, 1)
                    for value in settings.values()
                ):
                    raise ValueError("invalid enabled state")
                executions = {
                    (domain, leaf): self._decode(record, execution=True)
                    for domain, leaf, record in database.execute(
                        "SELECT domain_id, leaf_id, record FROM executions"
                    )
                }
                auth = {
                    domain: self._decode(record, execution=False)
                    for domain, record in database.execute(
                        "SELECT domain_id, record FROM auth"
                    )
                }
                return (
                    {key: bool(value) for key, value in settings.items()},
                    executions,
                    auth,
                )
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise CliError(
                "DOMAIN_STATE_ERROR", "Cannot read valid domain state"
            ) from exc

    @contextlib.contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
            with contextlib.closing(
                sqlite3.connect(
                    self.state_path.as_uri() + "?mode=rw", uri=True, timeout=5
                )
            ) as database:
                database.execute("BEGIN IMMEDIATE")
                try:
                    if database.execute("PRAGMA user_version").fetchone()[0] != 1:
                        raise ValueError("unsupported schema")
                    yield database
                    database.commit()
                except BaseException:
                    database.rollback()
                    raise
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise CliError("DOMAIN_STATE_ERROR", "Cannot persist domain state") from exc

    def _initialize(self) -> None:
        """Publish a complete empty schema atomically before any reader sees it."""
        if self.state_path.exists():
            return
        with tempfile.NamedTemporaryFile(
            dir=self.state_path.parent, prefix=".domain-state-", delete=False
        ) as temporary:
            staging = Path(temporary.name)
        try:
            with contextlib.closing(sqlite3.connect(staging)) as database:
                with database:
                    database.execute(
                        "CREATE TABLE settings (domain_id TEXT PRIMARY KEY, "
                        "enabled INTEGER NOT NULL CHECK(enabled IN (0,1)))"
                    )
                    database.execute(
                        "CREATE TABLE executions (domain_id TEXT, leaf_id TEXT, "
                        "record TEXT NOT NULL, PRIMARY KEY(domain_id, leaf_id))"
                    )
                    database.execute(
                        "CREATE TABLE auth (domain_id TEXT PRIMARY KEY, "
                        "record TEXT NOT NULL)"
                    )
                    database.execute("PRAGMA user_version=1")
            try:
                os.link(staging, self.state_path)
            except FileExistsError:
                # A concurrent writer already published its complete schema.
                pass
        finally:
            staging.unlink(missing_ok=True)

    def set_enabled(self, domain_id: str, enabled: bool) -> dict[str, Any]:
        self.inventory(domain_id)
        if type(enabled) is not bool:
            raise CliError("INVALID_ARGUMENT", "enabled must be a boolean", exit_code=2)
        with self._write() as database:
            database.execute(
                "INSERT INTO settings(domain_id, enabled) VALUES (?, ?) "
                "ON CONFLICT(domain_id) DO UPDATE SET enabled=excluded.enabled",
                (domain_id, int(enabled)),
            )
        return self.inventory(domain_id)[0]

    @staticmethod
    def _decode(raw: str, *, execution: bool) -> dict[str, Any]:
        value = json.loads(raw)
        outcomes = (
            {"success", "warning", "failed"}
            if execution
            else {"unknown", "authenticated", "unauthenticated", "failed"}
        )
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("outcome"), str)
            or value["outcome"] not in outcomes
            or "updated_at" not in value
        ):
            raise ValueError("invalid observation")
        timestamp = value["updated_at"]
        if timestamp is not None:
            if not isinstance(timestamp, str):
                raise ValueError("invalid timestamp")
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif execution or value["outcome"] != "unknown":
            raise ValueError("missing timestamp")
        if execution and (
            not isinstance(value.get("operation"), str) or not value["operation"]
        ):
            raise ValueError("invalid operation")
        return value

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _code(value: str | None) -> str | None:
        # Codes are identifiers, never request/response text or arbitrary messages.
        if value is None:
            return None
        if not isinstance(value, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]{0,79}", value
        ):
            return "EXECUTION_FAILED"
        return value

    def record_execution(
        self,
        domain_id: str,
        leaf_id: str,
        *,
        outcome: str,
        operation: str,
        error_code: str | None = None,
        diagnostic: str | None = None,
    ) -> None:
        domain = self.inventory(domain_id)[0]
        if not any(leaf["id"] == leaf_id for leaf in domain["leaves"]):
            raise CliError("LEAF_NOT_FOUND", "Unknown registered leaf")
        if not isinstance(outcome, str) or outcome not in {
            "success",
            "warning",
            "failed",
        }:
            raise CliError("INVALID_ARGUMENT", "Invalid execution outcome", exit_code=2)
        if not isinstance(operation, str) or operation not in {
            "list",
            "get",
            "refresh",
        }:
            raise CliError(
                "INVALID_ARGUMENT", "Invalid execution operation", exit_code=2
            )
        code = self._code(error_code)
        if outcome == "failed" and code is None:
            code = "EXECUTION_FAILED"
        record = {
            "outcome": outcome,
            "operation": operation,
            "updated_at": self._timestamp(),
            "error_code": code,
            "diagnostic": f"Execution {outcome}" + (f" ({code})" if code else "")
            if diagnostic is not None or outcome != "success"
            else None,
        }
        with self._write() as database:
            database.execute(
                "INSERT INTO executions(domain_id, leaf_id, record) VALUES (?, ?, ?) "
                "ON CONFLICT(domain_id, leaf_id) DO UPDATE SET record=excluded.record",
                (domain_id, leaf_id, json.dumps(record)),
            )

    def record_auth(self, domain_id: str, verdict: dict[str, Any]) -> None:
        self.inventory(domain_id)
        explicit_outcome = verdict.get("outcome")
        authenticated = verdict.get("authenticated")
        if explicit_outcome == "unknown":
            outcome = "unknown"
        elif authenticated is True:
            outcome = "authenticated"
        elif authenticated is False:
            outcome = "unauthenticated"
        else:
            outcome = "failed"
        record = {
            "outcome": outcome,
            "updated_at": None if outcome == "unknown" else self._timestamp(),
        }
        if outcome != "unknown":
            code = self._code(verdict.get("error_code"))
            if code:
                record["error_code"] = code
                record["diagnostic"] = f"Authentication check failed ({code})"
        with self._write() as database:
            database.execute(
                "INSERT INTO auth(domain_id, record) VALUES (?, ?) "
                "ON CONFLICT(domain_id) DO UPDATE SET record=excluded.record",
                (domain_id, json.dumps(record)),
            )

    def invalidate_auth(self) -> None:
        if not self.state_path.exists():
            return
        self._read()
        with self._write() as database:
            rows = list(database.execute("SELECT domain_id, record FROM auth"))
            for domain_id, raw in rows:
                if self._decode(raw, execution=False)["outcome"] == "authenticated":
                    database.execute(
                        "UPDATE auth SET record=? WHERE domain_id=?",
                        (
                            json.dumps({"outcome": "unknown", "updated_at": None}),
                            domain_id,
                        ),
                    )

    def select_domains(
        self, selectors: list[str] | None = None
    ) -> tuple[DomainDeclaration, ...]:
        """Validate an entire selection before browser recovery can start."""
        inventory = {row["id"]: row for row in self.inventory()}
        declarations = {domain.id: domain for domain in domain_declarations()}
        if selectors is not None:
            selected = tuple(dict.fromkeys(selectors))
            for domain_id in selected:
                if domain_id not in inventory:
                    raise CliError("DOMAIN_NOT_FOUND", f"Unknown domain: {domain_id}")
                if not inventory[domain_id]["enabled"]:
                    raise CliError(
                        "DOMAIN_DISABLED", f"Domain is disabled: {domain_id}"
                    )
        else:
            selected = tuple(key for key, row in inventory.items() if row["enabled"])
        if not selected:
            raise CliError("DOMAIN_SELECTION_ERROR", "No enabled domains selected")
        return tuple(declarations[key] for key in selected)
