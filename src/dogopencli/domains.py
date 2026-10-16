"""Shared, offline domain controls and operational observations.

Operational metadata lives beside the effective configuration, never in the
business query cache. Reading a new scope does not create directories or a DB.
"""

import contextlib
import json
import re
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, plugins
from .errors import CliError


def _unknown_execution() -> dict[str, Any]:
    return {
        "outcome": "unknown",
        "updated_at": None,
        "operation": None,
        "error_code": None,
        "diagnostic": None,
    }


class DomainService:
    """Application boundary shared by CLI, auth orchestration and localhost GUI."""

    def __init__(self, config_file: Path | None = None) -> None:
        self.config_file = (config_file or config.config_path()).expanduser().resolve()
        self.state_path = self.config_file.with_name(
            self.config_file.name + ".domains.sqlite3"
        )

    def inventory(self, domain_id: str | None = None) -> list[dict[str, Any]]:
        domains = plugins.domain_plugins()
        if domain_id is not None and not any(d.id == domain_id for d in domains):
            raise CliError("DOMAIN_NOT_FOUND", f"Unknown domain: {domain_id}")
        settings, executions, auth = self._read()
        return [
            {
                "id": domain.id,
                "entry_point": domain.entry_point,
                "enabled": settings.get(domain.id, True),
                "auth": auth.get(domain.id, {"outcome": "unknown", "updated_at": None}),
                "leaves": [
                    {
                        "id": leaf.id,
                        "enabled": leaf.enabled,
                        "effective_enabled": leaf.enabled
                        and settings.get(domain.id, True),
                        "last_execution": executions.get(
                            (domain.id, leaf.id), _unknown_execution()
                        ),
                    }
                    for leaf in domain.leaves
                ],
            }
            for domain in domains
            if domain_id is None or domain.id == domain_id
        ]

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
                if any(value not in (0, 1) for value in settings.values()):
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
            with contextlib.closing(
                sqlite3.connect(self.state_path, timeout=5)
            ) as database:
                database.execute("BEGIN IMMEDIATE")
                try:
                    version = database.execute("PRAGMA user_version").fetchone()[0]
                    if version not in (0, 1):
                        raise ValueError("unsupported schema")
                    if version == 0:
                        # An existing unrelated SQLite file must never be adopted.
                        if database.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchone():
                            raise ValueError("unrecognized schema")
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
                    yield database
                    database.commit()
                except BaseException:
                    database.rollback()
                    raise
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise CliError("DOMAIN_STATE_ERROR", "Cannot persist domain state") from exc

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
            or value.get("outcome") not in outcomes
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
        if outcome not in {"success", "warning", "failed"}:
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
        _, _, auth = self._read()
        with self._write() as database:
            for domain_id, verdict in auth.items():
                if verdict["outcome"] == "authenticated":
                    database.execute(
                        "UPDATE auth SET record=? WHERE domain_id=?",
                        (
                            json.dumps({"outcome": "unknown", "updated_at": None}),
                            domain_id,
                        ),
                    )

    def require_execution(self, path: tuple[str, ...]) -> tuple[str, str] | None:
        """Take one eligibility snapshot before entering the public leaf handler."""
        owner = None
        for domain in plugins.domain_plugins():
            for leaf in domain.leaves:
                if any(
                    node.path == path
                    for node in (*leaf.commands, *leaf.refresh_commands)
                ):
                    owner = (domain.id, leaf.id)
                    break
            if owner is not None:
                break
        if owner is None:
            return None
        domain_id, leaf_id = owner
        row = self.inventory(domain_id)[0]
        if not row["enabled"]:
            raise CliError("DOMAIN_DISABLED", f"Domain is disabled: {domain_id}")
        leaf = next(item for item in row["leaves"] if item["id"] == leaf_id)
        if not leaf["enabled"]:
            raise CliError("LEAF_DISABLED", f"Leaf is disabled: {leaf_id}")
        return owner

    def select_domains(self, selectors: list[str] | None = None) -> tuple[Any, ...]:
        """Validate an entire selection before browser recovery can start."""
        inventory = {row["id"]: row for row in self.inventory()}
        declarations = {domain.id: domain for domain in plugins.domain_plugins()}
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
