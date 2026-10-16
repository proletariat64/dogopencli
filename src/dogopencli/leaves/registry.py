"""Configuration-scoped installed leaves and conservative storage ownership.

Scanning is local. Missing or malformed storage never triggers business acquisition,
repair or deletion of DuckDB data. Ownership records survive folder removal.
"""

import fcntl
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..cache import Cache
from ..config import tomllib
from ..errors import CONFIG_ERROR, LOCKED, CliError

_NAME = r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*"
_PARAMETER = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
_TYPES = ["string", "integer", "number", "boolean"]
_RESERVED = {
    "format",
    "fields",
    "limit",
    "offset",
    "live",
    "strict",
    "fresh-only",
    "config-dir",
    "help",
    "progress",
    "require-complete",
    "require-fresh",
    "detail-identity",
    "explicit-parameters",
}

PARAMETER_SCHEMA = {
    "type": "object",
    "required": ["name", "type", "required", "description"],
    "properties": {
        "name": {"type": "string", "pattern": f"^{_PARAMETER}$"},
        "type": {"enum": _TYPES},
        "required": {"type": "boolean"},
        "description": {"type": "string"},
        "default": {},
        "choices": {"type": "array"},
        "multiple": {"type": "boolean"},
        "local_field": {"type": "string"},
    },
}
MANIFEST_SCHEMA = {
    "type": "object",
    "required": [
        "domain",
        "name",
        "operations",
        "adapter",
        "fields",
        "identity",
        "summary",
        "purpose",
        "identity_description",
        "limitations",
        "examples",
    ],
    "properties": {
        "domain": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "name": {"type": "string", "pattern": f"^{_NAME}$"},
        "adapter": {"type": "string"},
        "operations": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": False,
            "properties": {
                op: {
                    "type": "object",
                    "required": ["description", "parameters"],
                    "properties": {
                        "description": {"type": "string"},
                        "parameters": {"type": "array", "items": PARAMETER_SCHEMA},
                    },
                }
                for op in ("list", "get")
            },
        },
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "type", "meaning"],
                "properties": {
                    key: {"type": "string"}
                    for key in ("name", "type", "meaning", "unit")
                },
            },
        },
        "identity": {"type": "array", "items": {"type": "string"}},
        **{
            key: {"type": "string"}
            for key in ("summary", "purpose", "identity_description")
        },
        "limitations": {"type": "array", "items": {"type": "string"}},
        "examples": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "command"],
                "properties": {
                    "title": {"type": "string"},
                    "command": {"type": "string"},
                },
            },
        },
        "dataset": {
            "type": "object",
            "required": ["relation"],
            "properties": {
                "relation": {"type": "string", "pattern": "^[a-zA-Z_][a-zA-Z0-9_]*$"},
            },
        },
    },
}


def _invalid(message: str) -> CliError:
    return CliError("INVALID_LEAF", message)


def _validate(value: Any, schema: dict, path: str) -> None:
    """The basic shared schema vocabulary; no optional validator dependency."""
    kind = schema.get("type")
    valid = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
    }
    if kind and not valid.get(kind, False):
        raise _invalid(f"{path} must be {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise _invalid(f"{path} has unsupported value")
    if kind == "string" and "pattern" in schema:
        if re.fullmatch(schema["pattern"], value) is None:
            raise _invalid(f"{path} has invalid spelling")
    if kind == "object":
        for key in schema.get("required", []):
            if key not in value:
                raise _invalid(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if (
            schema.get("additionalProperties") is False
            and set(value) - properties.keys()
        ):
            raise _invalid(f"{path} has unsupported entries")
        if len(value) < schema.get("minProperties", 0):
            raise _invalid(f"{path} cannot be empty")
        for key, item in value.items():
            if key in properties:
                _validate(item, properties[key], f"{path}.{key}")
    if kind == "array" and "items" in schema:
        for index, item in enumerate(value):
            _validate(item, schema["items"], f"{path}[{index}]")


def _typed(value: Any, kind: str) -> bool:
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    return isinstance(value, str)


def validate_manifest(value: Any) -> None:
    _validate(value, MANIFEST_SCHEMA, "leaf")
    for operation in value["operations"].values():
        names = set()
        for parameter in operation["parameters"]:
            name = parameter["name"]
            if name in names or name in _RESERVED:
                raise _invalid(f"duplicate or reserved parameter: {name}")
            names.add(name)
            for choice in parameter.get("choices", []):
                if not _typed(choice, parameter["type"]):
                    raise _invalid(f"parameter {name} choice has wrong type")
            if "default" in parameter:
                default = parameter["default"]
                values = default if parameter.get("multiple") else [default]
                if not isinstance(values, list) or any(
                    not _typed(item, parameter["type"]) for item in values
                ):
                    raise _invalid(f"parameter {name} default has wrong type")
                if "choices" in parameter and any(
                    item not in parameter["choices"] for item in values
                ):
                    raise _invalid(f"parameter {name} default is outside choices")
    names = [field["name"] for field in value["fields"]]
    if len(names) != len(set(names)):
        raise _invalid("duplicate field names")
    if "list" in value["operations"]:
        if "dataset" not in value:
            raise _invalid("list requires dataset relation")
    elif "dataset" in value:
        raise _invalid("get-only leaf cannot declare a dataset")


@dataclass(frozen=True)
class Leaf:
    domain: str
    name: str
    path: Path
    manifest: dict
    adapter: Any

    @property
    def id(self) -> str:
        return f"{self.domain}.{self.name}"

    @property
    def cache_namespace(self) -> str:
        return f"leaf:{self.id}"


class Registry:
    def __init__(self, config_file: Path) -> None:
        self.config_file = config_file.resolve()
        self.root = self.config_file.parent / "plugins"
        self.cache_path = self.config_file.parent / "leaf-cache.sqlite3"
        self.leaves: dict[str, Leaf] = {}
        self.diagnostics: list[dict] = []

    def get(self, domain: str, name: str) -> Leaf:
        identity = f"{domain}.{name}"
        if identity not in self.leaves:
            detail = next((d for d in self.diagnostics if d["id"] == identity), None)
            if detail:
                raise CliError(detail["code"], detail["message"])
            global_error = next(
                (d for d in self.diagnostics if d["id"] == "plugins"), None
            )
            if global_error:
                raise CliError(
                    global_error["code"],
                    global_error["message"],
                    retryable=global_error["code"] == LOCKED,
                )
            raise CliError("LEAF_NOT_FOUND", f"Leaf is not installed: {identity}")
        return self.leaves[identity]

    def _error(self, identity: str, error: Exception) -> None:
        self.diagnostics.append(
            {
                "id": identity,
                "code": getattr(error, "code", "LEAF_LOAD_ERROR"),
                "message": str(error),
            }
        )

    def _database(self) -> Path:
        document = {}
        if self.config_file.exists():
            try:
                document = tomllib.loads(self.config_file.read_text(encoding="utf-8"))
            except (ValueError, OSError) as error:
                raise CliError(
                    CONFIG_ERROR, "Cannot read valid configuration"
                ) from error
        section = document.get("duckdog", {})
        if not isinstance(section, dict):
            raise CliError(CONFIG_ERROR, "duckdog must be a configuration table")
        raw = section.get("path", "duckdog.duckdb")
        if not isinstance(raw, str) or not raw.strip():
            raise CliError(CONFIG_ERROR, "duckdog.path must be a nonempty path")
        path = Path(raw).expanduser()
        return (self.config_file.parent / path).resolve()

    def _load(self, folder: Path) -> Leaf:
        if folder.is_symlink() or folder.parent.is_symlink():
            raise _invalid("domain and leaf folders must be direct local directories")
        if not folder.is_dir():
            raise _invalid("leaf installation must be a directory")
        manifest_path = folder / "leaf.json"
        if manifest_path.is_symlink():
            raise _invalid("leaf.json must be a local file")
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_manifest(value)
        if value["domain"] != folder.parent.name or value["name"] != folder.name:
            raise _invalid("manifest identity must match domain and leaf folder")
        from ..plugins import domain_plugins

        if value["domain"] not in {domain.id for domain in domain_plugins()}:
            raise _invalid("unknown domain")
        binding = value["adapter"]
        if not isinstance(binding, str) or binding.count(":") != 1:
            raise _invalid("adapter must bind local-file.py:attribute")
        filename, attribute = binding.split(":")
        location = (folder / filename).resolve()
        if (
            location.parent != folder.resolve()
            or location.suffix != ".py"
            or not attribute.isidentifier()
            or not location.is_file()
        ):
            raise _invalid("adapter must resolve to a Python file inside its leaf")
        # Execute fresh source rather than timestamp-based bytecode: a replacement
        # with equal size and timestamp must still take effect next invocation.
        module_name = "_dogopencli_leaf_" + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(module_name, location)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            exec(compile(location.read_bytes(), str(location), "exec"), module.__dict__)
            adapter = getattr(module, attribute)
            required = {"get", "capability"} if "get" in value["operations"] else set()
            if "list" in value["operations"]:
                required |= {"capability", "scope", "collector", "filter"}
            if any(not callable(getattr(adapter, name, None)) for name in required):
                raise _invalid("adapter does not implement declared operations")
        finally:
            sys.modules.pop(module_name, None)
        return Leaf(value["domain"], value["name"], folder, value, adapter)

    def _storage(self, leaf: Leaf, state: sqlite3.Connection) -> None:
        if "list" not in leaf.manifest["operations"]:
            return
        database = self._database()
        relation = leaf.manifest["dataset"]["relation"]
        if relation.lower().startswith("_dogopencli"):
            raise _invalid("dataset relation uses a reserved host name")
        previous = state.execute(
            "SELECT database_path, relation_name FROM bindings WHERE leaf_id=?",
            (leaf.id,),
        ).fetchone()
        if previous and previous != (str(database), relation.lower()):
            raise _invalid("registered Duckdog binding cannot change implicitly")
        collision = state.execute(
            "SELECT leaf_id FROM bindings WHERE database_path=? AND relation_name=?",
            (str(database), relation.lower()),
        ).fetchone()
        if collision and collision[0] != leaf.id:
            raise _invalid("Duckdog relation is owned by another leaf")
        try:
            import duckdb
        except ImportError as error:
            raise CliError(
                "DATASET_ERROR", "DuckDB support is required for list leaves"
            ) from error
        if previous and not database.is_file():
            raise CliError("DATASET_ERROR", "Registered Duckdog database is missing")
        database.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(database), read_only=bool(previous)) as db:
            db.execute("BEGIN TRANSACTION")
            exists = db.execute(
                "SELECT table_type FROM information_schema.tables "
                "WHERE table_schema='main' AND lower(table_name)=lower(?)",
                [relation],
            ).fetchone()
            owner_table = db.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='main' "
                "AND table_name='_dogopencli_leaf_ownership'"
            ).fetchone()
            owner = None
            if owner_table:
                owner = db.execute(
                    "SELECT leaf_id FROM _dogopencli_leaf_ownership "
                    "WHERE relation_name=?",
                    [relation.lower()],
                ).fetchone()
            if previous or owner:
                if owner != (leaf.id,) or exists != ("BASE TABLE",):
                    raise CliError(
                        "DATASET_ERROR", "Registered Duckdog ownership/table is missing"
                    )
            elif exists:
                raise CliError(
                    "DATASET_ERROR", "Refusing to adopt an unowned Duckdog relation"
                )
            else:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS _dogopencli_leaf_ownership "
                    "(relation_name VARCHAR PRIMARY KEY, "
                    "leaf_id VARCHAR UNIQUE NOT NULL)"
                )
                db.execute(f'CREATE TABLE "{relation}" (_record VARCHAR)')
                db.execute(
                    "INSERT INTO _dogopencli_leaf_ownership VALUES (?, ?)",
                    [relation.lower(), leaf.id],
                )
            columns = db.execute(f'PRAGMA table_info("{relation}")').fetchall()
            if [(row[1], row[2]) for row in columns] != [("_record", "VARCHAR")]:
                raise CliError(
                    "DATASET_ERROR", "Registered Duckdog table has incompatible columns"
                )
            db.execute("COMMIT")
        state.execute(
            "INSERT OR IGNORE INTO bindings VALUES (?, ?, ?, 1)",
            (leaf.id, str(database), relation.lower()),
        )
        state.execute("UPDATE bindings SET active=1 WHERE leaf_id=?", (leaf.id,))

    def scan(self, *, wait_seconds: float = 0) -> "Registry":
        self.leaves = {}
        self.diagnostics = []
        # An absent/unavailable root is never affirmative uninstall evidence.
        try:
            domains = sorted(self.root.iterdir())
            folders = []
            unavailable_domains = set()
            for domain in domains:
                if not domain.is_dir() or domain.is_symlink():
                    unavailable_domains.add(domain.name)
                    self._error(
                        domain.name, _invalid("domain must be a local directory")
                    )
                else:
                    try:
                        folders.extend(sorted(domain.iterdir()))
                    except OSError as error:
                        unavailable_domains.add(domain.name)
                        self._error(domain.name, error)

        except OSError as error:
            if self.root.exists():
                self._error("plugins", error)
            return self
        directory = self.config_file.parent
        directory.mkdir(parents=True, exist_ok=True)
        lock = os.open(directory / "leaf-registry.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            deadline = time.monotonic() + wait_seconds
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._error(
                            "plugins",
                            CliError(LOCKED, "Plugin registration is busy", True),
                        )
                        return self
                    time.sleep(min(0.05, remaining))
            with sqlite3.connect(
                directory / "leaf-registry.sqlite3", timeout=10
            ) as state:
                state.execute(
                    "CREATE TABLE IF NOT EXISTS bindings (leaf_id TEXT PRIMARY KEY, "
                    "database_path TEXT NOT NULL, relation_name TEXT NOT NULL, "
                    "active INTEGER NOT NULL, UNIQUE(database_path, relation_name))"
                )
                present = {f"{folder.parent.name}.{folder.name}" for folder in folders}
                for folder in folders:
                    identity = f"{folder.parent.name}.{folder.name}"
                    try:
                        leaf = self._load(folder)
                        self._storage(leaf, state)
                        self.leaves[leaf.id] = leaf
                    except Exception as error:
                        self._error(identity, error)
                for (identity,) in state.execute(
                    "SELECT leaf_id FROM bindings WHERE active=1"
                ):
                    if (
                        identity not in present
                        and identity.split(".", 1)[0] not in unavailable_domains
                    ):
                        cache = Cache(self.cache_path)
                        with cache.refresh_lock():
                            cache.remove(f"leaf:{identity}")
                        state.execute(
                            "UPDATE bindings SET active=0 WHERE leaf_id=?", (identity,)
                        )
        except (sqlite3.Error, OSError, CliError) as error:
            self._error("plugins", error)
        finally:
            os.close(lock)
        return self
