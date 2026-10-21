"""Configuration-scoped installed leaves and conservative storage ownership.

Scanning is local. Missing or malformed storage never triggers business acquisition,
repair or deletion of DuckDB data. Ownership records survive folder removal.
"""

import fcntl
import hashlib
import importlib.util
import inspect
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from collections.abc import Callable
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
    "version",
    "format",
    "fields",
    "limit",
    "offset",
    "live",
    "with-detail",
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
PAGING_SCHEMA = {
    "type": "object",
    "required": ["mode", "page_sizes"],
    "additionalProperties": False,
    "properties": {
        "mode": {"enum": ["offset", "page_number", "single", "single_response"]},
        "page_sizes": {"type": "array"},
        "termination": {"enum": ["native_total", "short_page"]},
    },
}
PRIMARY_ID_SCHEMA = {
    "type": "object",
    "required": ["type", "fields"],
    "additionalProperties": False,
    "properties": {
        "type": {"enum": ["field", "hash", "unproven"]},
        "fields": {"type": "array", "items": {"type": "string"}},
    },
}
SOURCE_SCHEMA = {
    "type": "object",
    "required": ["paging", "primary_id"],
    "additionalProperties": False,
    "properties": {"paging": PAGING_SCHEMA, "primary_id": PRIMARY_ID_SCHEMA},
}
RESULT_IDENTITY_SCHEMA = {
    "type": "object",
    "required": ["description"],
    "additionalProperties": False,
    "properties": {
        "fields": {"type": "array", "items": {"type": "string"}},
        "request_fields": {"type": "array", "items": {"type": "string"}},
        "paths": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "string"}},
        },
        "description": {"type": "string"},
    },
}
QUERY_SCHEMA = {
    "type": "object",
    "required": ["kind"],
    "additionalProperties": False,
    "properties": {
        "kind": {"enum": ["list", "detail", "inquiry"]},
        "collection": {
            "type": "object",
            "required": ["provider", "paging", "primary_id"],
            "additionalProperties": False,
            "properties": {
                "provider": {"type": "string"},
                "paging": PAGING_SCHEMA,
                "primary_id": PRIMARY_ID_SCHEMA,
                "latest_by": {"type": "string"},
                "max_pages": {"type": "integer", "minimum": 1, "maximum": 1000},
                "budget_seconds": {"type": "integer", "minimum": 1, "maximum": 900},
            },
        },
        "result_identity": RESULT_IDENTITY_SCHEMA,
        "result_shape": {"enum": ["object", "array"]},
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
                        "execution": {"enum": ["standard", "custom"]},
                        "account_directory": {"type": "boolean"},
                        "entity_selector": {"type": "boolean"},
                        "queries": {
                            "type": "object",
                            "minProperties": 1,
                            "additionalProperties": QUERY_SCHEMA,
                        },
                        "max_requests": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10000,
                        },
                        "budget_seconds": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 1800,
                        },
                        **(
                            {
                                "lookup": {
                                    "type": "object",
                                    "required": ["name", "description"],
                                    "additionalProperties": False,
                                    "properties": {
                                        key: {"type": "string"}
                                        for key in ("name", "description")
                                    },
                                },
                                "result_identity": RESULT_IDENTITY_SCHEMA,
                                "result_shape": {"enum": ["object", "array"]},
                                "list_binding": {
                                    "type": "object",
                                    "required": ["identity_field"],
                                    "additionalProperties": False,
                                    "properties": {
                                        "identity_field": {"type": "string"},
                                        "parameters": {"type": "object"},
                                    },
                                },
                            }
                            if op == "get"
                            else {}
                        ),
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
        "collection": {
            "type": "object",
            "required": ["provider", "primary_id"],
            "additionalProperties": False,
            "properties": {
                "provider": {"type": "string"},
                "paging": PAGING_SCHEMA,
                "primary_id": PRIMARY_ID_SCHEMA,
                "sources": {
                    "type": "object",
                    "minProperties": 1,
                    "additionalProperties": SOURCE_SCHEMA,
                },
                "latest_by": {"type": "string"},
                "max_pages": {"type": "integer", "minimum": 1, "maximum": 1000},
                "budget_seconds": {"type": "integer", "minimum": 1, "maximum": 900},
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
        "integer": type(value) is int,
    }
    if kind and not valid.get(kind, False):
        raise _invalid(f"{path} must be {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise _invalid(f"{path} has unsupported value")
    if kind == "integer" and not schema.get("minimum", value) <= value <= schema.get(
        "maximum", value
    ):
        raise _invalid(f"{path} is outside the allowed range")
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
            elif isinstance(schema.get("additionalProperties"), dict):
                _validate(item, schema["additionalProperties"], f"{path}.{key}")
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


def _validate_primary(policy: dict, *, verified: bool = False) -> None:
    fields = policy["primary_id"]["fields"]
    kind = policy["primary_id"]["type"]
    unproven = kind == "unproven"
    if (
        (not fields and not unproven)
        or (unproven and (fields or "latest_by" in policy or verified))
        or len(fields) != len(set(fields))
        or any(not field.strip() for field in fields)
        or kind == "field"
        and len(fields) != 1
        or not policy.get("latest_by", "present").strip()
    ):
        raise _invalid("List primary identity or timestamp declaration is invalid")


def _validate_paging(policy: dict) -> None:
    pages = policy["paging"]["page_sizes"]
    mode = policy["paging"]["mode"]
    short_page = policy["paging"].get("termination") == "short_page"
    if short_page and mode not in {"offset", "page_number"}:
        raise _invalid("Short-page termination requires offset or numbered paging")
    if (
        not pages
        or len(pages) > 8
        or any(
            type(size) is not int
            or not (
                0 <= size <= 100000 if mode == "single_response" else 0 < size <= 100000
            )
            for size in pages
        )
        or pages != sorted(set(pages), reverse=True)
        or mode in {"single", "single_response"}
        and len(pages) != 1
    ):
        raise _invalid("List page sizes must be unique, descending and qualified")
    _validate_primary(policy, verified=mode == "single_response" or short_page)


def _validate_result_identity(identity: dict) -> None:
    if "request_fields" in identity:
        fields = identity["request_fields"]
        if (
            set(identity) != {"request_fields", "description"}
            or not fields
            or len(fields) != len(set(fields))
            or any(not field.strip() for field in fields)
            or not identity["description"].strip()
        ):
            raise _invalid(
                "request identity requires nonempty unique fields and meaning"
            )
        return
    if ("fields" in identity) == ("paths" in identity):
        raise _invalid("Get result identity requires exactly one of fields or paths")
    if "fields" in identity:
        fields = identity["fields"]
        if (
            not fields
            or len(fields) != len(set(fields))
            or any(not field.strip() for field in fields)
        ):
            raise _invalid("Get result identity fields must be nonempty and unique")
    else:
        paths = identity["paths"]
        if (
            not paths
            or any(not path or any(not key.strip() for key in path) for path in paths)
            or len(paths) != len({tuple(path) for path in paths})
        ):
            raise _invalid("Get result identity paths must be nonempty and unique")
    if not identity["description"].strip():
        raise _invalid("Get result identity meaning must be nonempty")


def _validate_custom_queries(domain: str, operation: dict) -> None:
    from ..contracts import resolve_collection_provider

    required = {"queries", "max_requests", "budget_seconds"}
    if required - operation.keys():
        raise _invalid(
            "custom execution requires queries, max_requests and budget_seconds"
        )
    for name, query in operation["queries"].items():
        if re.fullmatch(r"[a-z][a-z0-9_]*", name) is None:
            raise _invalid("custom query name has invalid spelling")
        if query["kind"] == "list":
            if set(query) != {"kind", "collection"}:
                raise _invalid("custom List query requires only kind and collection")
            collection = query["collection"]
            try:
                resolve_collection_provider(domain, collection["provider"])
            except CliError as error:
                raise _invalid(error.message) from error
            _validate_paging(collection)
        elif query["kind"] == "inquiry":
            if set(query) != {"kind", "result_shape"}:
                raise _invalid("custom inquiry requires only kind and result_shape")
        else:
            if "result_identity" not in query or "collection" in query:
                raise _invalid(
                    "custom detail query requires result_identity and no collection"
                )
            _validate_result_identity(query["result_identity"])
            if "request_fields" in query["result_identity"]:
                raise _invalid(
                    "internal detail requires native identity; "
                    "use an inquiry for request-scoped aggregates"
                )


def validate_manifest(value: Any) -> None:
    _validate(value, MANIFEST_SCHEMA, "leaf")
    for action, operation in value["operations"].items():
        if operation.get("execution", "standard") == "custom":
            supported = MANIFEST_SCHEMA["properties"]["operations"]["properties"][
                action
            ]["properties"]
            if set(operation) - supported.keys():
                raise _invalid("custom operation has unsupported entries")
            if action == "list" and "collection" in value:
                raise _invalid("custom List cannot declare a standard collection")
            _validate_custom_queries(value["domain"], operation)
        elif {
            "queries",
            "max_requests",
            "budget_seconds",
            "account_directory",
            "entity_selector",
        } & operation.keys():
            raise _invalid("standard execution cannot declare custom query settings")
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
    detail = value["operations"].get("get")
    if detail is not None:
        if "lookup" not in detail or "result_identity" not in detail:
            raise _invalid("get requires lookup and result_identity declarations")
        if any(not item.strip() for item in detail["lookup"].values()):
            raise _invalid("Get lookup meaning must be nonempty")
        _validate_result_identity(detail["result_identity"])
        if "request_fields" in detail["result_identity"]:
            if (
                detail.get("execution") != "custom"
                or detail.get("result_shape", "object") != "object"
                or "list_binding" in detail
            ):
                raise _invalid(
                    "request-scoped identity requires unbound custom object Get"
                )
            allowed = {detail["lookup"]["name"]} | {
                parameter["name"].replace("-", "_")
                for parameter in detail["parameters"]
            }
            if set(detail["result_identity"]["request_fields"]) - allowed:
                raise _invalid(
                    "request identity must name lookup or declared parameters"
                )
        binding = detail.get("list_binding")
        if binding is not None:
            if detail.get("result_shape", "object") == "array":
                raise _invalid("array Get cannot bind to List records")
            if (
                "list" not in value["operations"]
                or not binding["identity_field"].strip()
            ):
                raise _invalid(
                    "Get List binding requires List and a native identity field"
                )
            mapping = binding.get("parameters", {})
            definitions = {item["name"]: item for item in detail["parameters"]}
            if any(
                name not in definitions
                or not isinstance(field, str)
                or not field.strip()
                for name, field in mapping.items()
            ):
                raise _invalid(
                    "Get List binding has unknown parameters or empty source fields"
                )
            if any(
                item["required"] and "default" not in item and name not in mapping
                for name, item in definitions.items()
            ):
                raise _invalid("Get List binding must supply required context")
    collection = value.get("collection")
    if collection is not None:
        from ..contracts import resolve_collection_provider

        if "list" not in value["operations"]:
            raise _invalid("get-only leaf cannot use a List collection provider")
        try:
            resolve_collection_provider(value["domain"], collection["provider"])
        except CliError as error:
            raise _invalid(error.message) from error
        if ("paging" in collection) == ("sources" in collection):
            raise _invalid("List collection requires exactly one of paging or sources")
        if "sources" in collection:
            _validate_primary(collection, verified=True)
            for name, source in collection["sources"].items():
                if re.fullmatch(r"[a-z][a-z0-9_]*", name) is None:
                    raise _invalid("List source name has invalid spelling")
                _validate_paging(source)
                _validate_primary(source, verified=True)
        else:
            _validate_paging(collection)
            if collection["primary_id"]["type"] == "unproven" and value["identity"]:
                raise _invalid("unproven List cannot declare public identity")
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
    adapter: Any = None
    adapter_sha256: str = ""
    installation_token: tuple[int, int, int] | None = None

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

    def _declaration(self, folder: Path) -> Leaf:
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
        from ..domain_contracts import domain_declarations

        if value["domain"] not in {domain.id for domain in domain_declarations()}:
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
        return Leaf(value["domain"], value["name"], folder, value)

    def discover(self) -> "Registry":
        """Read local declarations only: no adapters, configuration or lifecycle IO."""
        self.leaves = {}
        self.diagnostics = []
        try:
            domains = sorted(self.root.iterdir())
        except FileNotFoundError:
            return self
        except OSError:
            self.diagnostics.append(
                {
                    "id": "plugins",
                    "code": "LEAF_LOAD_ERROR",
                    "message": "Cannot read installation directories",
                }
            )
            return self
        for domain in domains:
            try:
                if domain.is_symlink() or not domain.is_dir():
                    raise _invalid("invalid installation directory")
                folders = sorted(domain.iterdir())
            except (OSError, CliError):
                self.diagnostics.append(
                    {
                        "id": domain.name[:128],
                        "code": "INVALID_LEAF",
                        "message": "Invalid installation directory",
                    }
                )
                continue
            for folder in folders:
                try:
                    leaf = self._declaration(folder)
                    self.leaves[leaf.id] = leaf
                except Exception as error:
                    self.diagnostics.append(
                        {
                            "id": f"{domain.name}.{folder.name}"[:256],
                            "code": "INVALID_LEAF"
                            if isinstance(error, (CliError, ValueError))
                            else "LEAF_LOAD_ERROR",
                            "message": "Invalid local leaf declaration"
                            if isinstance(error, (CliError, ValueError))
                            else "Cannot read local leaf declaration",
                        }
                    )
        return self

    def _load(self, folder: Path) -> Leaf:
        declaration = self._declaration(folder)
        value = declaration.manifest
        filename, attribute = value["adapter"].split(":")
        location = (folder / filename).resolve()
        # Execute fresh source rather than timestamp-based bytecode: a replacement
        # with equal size and timestamp must still take effect next invocation.
        module_name = "_dogopencli_leaf_" + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(module_name, location)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            source = location.read_bytes()
            adapter_sha256 = hashlib.sha256(source).hexdigest()
            exec(compile(source, str(location), "exec"), module.__dict__)
            adapter = getattr(module, attribute)
            required = set()
            for action, operation in value["operations"].items():
                if action == "list":
                    required |= {"scope", "filter"}
                if operation.get("execution", "standard") == "custom":
                    required |= {"query_capability", f"query_{action}"}
                elif action == "get":
                    required.add("detail_capability")
                elif "sources" in value.get("collection", {}):
                    required |= {"source_capability", "source_scope", "assemble"}
                else:
                    required.add("capability")
                    if "collection" not in value:
                        required.add("collector")
            arguments = {
                "capability": ({},),
                "scope": ({},),
                "collector": (None, None, "scope"),
                "filter": ([], {}),
                "detail_capability": ({},),
                "source_capability": ("source", {}),
                "source_scope": ("source", {}),
                "assemble": ({}, {}),
                "query_capability": ("list", "query", {}),
                "query_list": ({}, None),
                "query_get": ({}, "identity", None),
            }
            for name in required:
                method = getattr(adapter, name, None)
                if not callable(method):
                    raise _invalid("adapter does not implement declared operations")
                try:
                    # Validate call compatibility without executing business methods.
                    inspect.signature(method).bind(*arguments[name])
                except (TypeError, ValueError):
                    raise _invalid(
                        "adapter method signature does not implement "
                        "declared operations"
                    ) from None
        finally:
            sys.modules.pop(module_name, None)
        status = folder.stat()
        return Leaf(
            value["domain"],
            value["name"],
            folder,
            value,
            adapter,
            adapter_sha256,
            (status.st_dev, status.st_ino, status.st_ctime_ns),
        )

    def _storage(
        self,
        leaf: Leaf,
        state: sqlite3.Connection,
        *,
        publish: Callable[[], None] | None = None,
    ) -> None:
        if "list" not in leaf.manifest["operations"]:
            if publish is not None:
                publish()
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
            state.execute(
                "INSERT OR IGNORE INTO bindings VALUES (?, ?, ?, 1)",
                (leaf.id, str(database), relation.lower()),
            )
            state.execute("UPDATE bindings SET active=1 WHERE leaf_id=?", (leaf.id,))
            if publish is not None:
                publish()
            db.execute("COMMIT")

    def scan(self, *, wait_seconds: float = 0) -> "Registry":
        self.leaves = {}
        self.diagnostics = []
        # Probe availability without creating a new configuration scope. This
        # does not capture folder names; authoritative enumeration is locked.
        try:
            with os.scandir(self.root):
                pass
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
                            # A folder installed after enumeration is not uninstalled.
                            domain, name = identity.split(".", 1)
                            try:
                                (self.root / domain / name).lstat()
                            except FileNotFoundError:
                                # Missing parents can mean an unavailable root,
                                # not an uninstalled leaf. Revalidate the scope.
                                with os.scandir(self.root):
                                    pass
                                if any(item.name == domain for item in domains):
                                    with os.scandir(self.root / domain):
                                        pass
                            else:
                                continue
                            cache.remove(f"leaf:{identity}")
                        state.execute(
                            "UPDATE bindings SET active=0 WHERE leaf_id=?", (identity,)
                        )
        except (sqlite3.Error, OSError, CliError) as error:
            self._error("plugins", error)
        finally:
            os.close(lock)
        return self
