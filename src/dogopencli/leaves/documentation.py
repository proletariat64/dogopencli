"""Shared leaf documentation and explicit, conflict-aware prose editing."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ..errors import CliError

COMMON_GUIDANCE = (
    "List defaults to offline cache replay; --live queries without publishing. "
    "Refresh replaces cache only for accepted nonempty results. "
    "Get performs native detail lookup without cache or dataset. "
    "Display: --limit 100 (0 for all remaining), --offset 0, --fields. "
    "Output: --format json|text. Incomplete results carry warnings; "
    "--require-complete rejects them. --require-fresh rejects stale cache. "
    "Authentication, business and parsing failures are errors."
)
DETAIL_GUIDANCE = (
    "Get is live-only and returns one validated native root object. "
    "Separate histories, logs and child pages are not acquired."
)
ARRAY_DETAIL_GUIDANCE = (
    "Get is live-only and returns the validated native root array in source order, "
    "including a qualified successful empty array. --fields projects each member; "
    "returned_count is the actual member count. No List binding or paging applies. "
    "Separate histories, logs and child pages are not acquired."
)
COMPOSITION_GUIDANCE = (
    "list --live --with-detail selects the output window after local filtering "
    "and offset/limit; limit 0 means all remaining rows, empty windows issue no Gets. "
    "Each entry is {record, detail}; --fields projects record only. Any detail or "
    "binding failure fails the whole command. List coverage is retained; separate "
    "histories, logs and child pages are not acquired. "
    "No cache or dataset is published."
)
DOC_KEYS = {"summary", "purpose", "identity_description", "limitations", "examples"}


def describe(leaf: Any) -> dict[str, Any]:
    """Render the same declarations for CLI help, descriptions and preview."""
    return {
        "id": leaf.id,
        "domain": leaf.domain,
        "name": leaf.name,
        **copy.deepcopy(leaf.manifest),
        "guidance": COMMON_GUIDANCE,
        **(
            {
                "detail_guidance": ARRAY_DETAIL_GUIDANCE
                if leaf.manifest["operations"]["get"].get("result_shape") == "array"
                else DETAIL_GUIDANCE
            }
            if "get" in leaf.manifest["operations"]
            else {}
        ),
        **(
            {"composition_guidance": COMPOSITION_GUIDANCE}
            if leaf.manifest["operations"].get("get", {}).get("list_binding")
            else {}
        ),
    }


def render_text(document: dict[str, Any]) -> str:
    lines = [document.get("id", ""), document.get("summary", "")]
    for key in ("purpose", "identity_description"):
        if document.get(key):
            lines.append(document[key])
    for operation, specification in document.get("operations", {}).items():
        lines.append(
            f"{document.get('domain', '')} {operation} {document.get('name', '')}: "
            + specification.get("description", "")
        )
        if operation == "get":
            lookup = specification["lookup"]
            identity = specification["result_identity"]
            lines.append(f"  Lookup {lookup['name']}: {lookup['description']}")
            lines.append(
                "  Returned shape: " + specification.get("result_shape", "object")
            )
            identity_names = identity.get("request_fields", identity.get("fields"))
            if identity_names is None:
                identity_names = [
                    json.dumps(path, ensure_ascii=False) for path in identity["paths"]
                ]
            lines.append(
                (
                    "  Request context identity "
                    if "request_fields" in identity
                    else "  Returned identity "
                )
                + ", ".join(identity_names)
                + ": "
                + identity["description"]
            )
            if binding := specification.get("list_binding"):
                lines.append("  List lookup source: " + binding["identity_field"])
                for name, field in binding.get("parameters", {}).items():
                    lines.append(f"  List context --{name}: {field}")
        for parameter in specification.get("parameters", []):
            rules = ["required" if parameter.get("required") else "optional"]
            if "default" in parameter:
                rules.append(
                    "default=" + json.dumps(parameter["default"], ensure_ascii=False)
                )
            if "choices" in parameter:
                rules.append("choices=" + "|".join(map(str, parameter["choices"])))
            if parameter.get("multiple"):
                rules.append("repeatable")
            lines.append(
                f"  --{parameter['name']} ({parameter['type']}; {', '.join(rules)}): "
                + parameter.get("description", "")
            )
    for field in document.get("fields", []):
        unit = f" [{field['unit']}]" if field.get("unit") else ""
        lines.append(
            f"{field['name']} ({field['type']}){unit}: {field.get('meaning', '')}"
        )
    lines.extend(
        document[key]
        for key in ("detail_guidance", "composition_guidance")
        if key in document
    )
    lines.extend(document.get("limitations", []))
    for example in document.get("examples", []):
        lines.append(f"{example['title']}: {example['command']}")
    lines.append(document.get("guidance", COMMON_GUIDANCE))
    return "\n".join(lines) + "\n"


def _technical(manifest: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(manifest)
    for key in DOC_KEYS:
        value.pop(key, None)
    for operation in value.get("operations", {}).values():
        operation.pop("description", None)
        for parameter in operation.get("parameters", []):
            parameter.pop("description", None)
    for field in value.get("fields", []):
        field.pop("meaning", None)
        field.pop("unit", None)
    return value


def _merge_documentation(original: Any, patch: Any, path: tuple = ()) -> Any:
    if path in {("limitations",), ("examples",)}:
        return copy.deepcopy(patch)
    if isinstance(original, dict) and isinstance(patch, dict):
        result = copy.deepcopy(original)
        for key, value in patch.items():
            result[key] = _merge_documentation(result.get(key), value, (*path, key))
        return result
    if isinstance(original, list) and isinstance(patch, list):
        if len(original) != len(patch):
            raise CliError("READ_ONLY_FIELD", "Technical list structure is read-only")
        return [
            _merge_documentation(before, after, (*path, index))
            for index, (before, after) in enumerate(zip(original, patch, strict=True))
        ]
    return copy.deepcopy(patch)


def _number_labels(value: Any, path: str = "") -> dict[str, str]:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            result.update(_number_labels(item, f"{path}.{key}" if path else key))
        return result
    if isinstance(value, list):
        result = {}
        for index, item in enumerate(value, 1):
            result.update(_number_labels(item, f"{path} {index}"))
        return result
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {path: str(value)}
    return {}


def editor_schema() -> dict[str, Any]:
    """A single host-owned form schema, shared by every leaf."""
    from .registry import MANIFEST_SCHEMA

    schema = copy.deepcopy(MANIFEST_SCHEMA)

    # Annotate documentation affordances without a second executable contract.
    def annotate(node: Any, path: tuple[str, ...] = ()) -> None:
        if not isinstance(node, dict):
            return
        for key, child in node.get("properties", {}).items():
            if isinstance(child, dict):
                child["readOnly"] = not (
                    key in DOC_KEYS
                    if not path
                    else key in {"description", "meaning", "unit"}
                    or path[0] == "examples"
                )
                if path in {
                    ("operations", "get", "lookup"),
                    ("operations", "get", "result_identity"),
                }:
                    child["readOnly"] = True
                annotate(child, (*path, key))
        if isinstance(node.get("items"), dict):
            annotate(node["items"], path)
        if isinstance(node.get("additionalProperties"), dict):
            annotate(node["additionalProperties"], path)

    annotate(schema)
    return schema


class DocumentationEditor:
    def __init__(self, config_file: Path):
        self.config_file = config_file

    def _leaf(self, domain: str, name: str):
        from .registry import Registry

        return Registry(self.config_file).scan().get(domain, name)

    @staticmethod
    def _revision(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    def load(self, domain: str, name: str) -> dict[str, Any]:
        leaf = self._leaf(domain, name)
        try:
            raw = (leaf.path / "leaf.json").read_bytes()
            manifest = json.loads(raw)
        except (OSError, ValueError) as error:
            raise CliError(
                "LEAF_DOCUMENT_ERROR", "Cannot read leaf documentation"
            ) from error
        document = describe(leaf)
        document.update(manifest)
        return {
            "manifest": manifest,
            "revision": self._revision(raw),
            "schema": editor_schema(),
            "preview": render_text(document),
            "number_labels": _number_labels(manifest),
        }

    def _candidate(self, domain: str, name: str, payload: Any):
        from .registry import validate_manifest

        if not isinstance(payload, dict) or not isinstance(
            payload.get("revision"), str
        ):
            raise CliError(
                "INVALID_ARGUMENT", "Manifest and revision are required", exit_code=2
            )
        leaf = self._leaf(domain, name)
        path = leaf.path / "leaf.json"
        raw = path.read_bytes()
        if self._revision(raw) != payload["revision"]:
            raise CliError(
                "EDIT_CONFLICT", "Leaf changed on disk; reload before saving"
            )
        original = json.loads(raw)
        if "documentation" in payload:
            if not isinstance(payload["documentation"], dict):
                raise CliError(
                    "INVALID_ARGUMENT", "Documentation must be an object", exit_code=2
                )
            candidate = _merge_documentation(original, payload["documentation"])
        else:
            candidate = payload.get("manifest")
        validate_manifest(candidate)
        if _technical(original) != _technical(candidate):
            raise CliError(
                "READ_ONLY_FIELD", "Technical declarations are read-only in the form"
            )
        return leaf, path, raw, copy.deepcopy(candidate)

    def preview(self, domain: str, name: str, payload: Any) -> dict[str, Any]:
        leaf, _, _, candidate = self._candidate(domain, name, payload)
        document = describe(leaf)
        document.update(candidate)
        return {"preview": render_text(document)}

    def save(self, domain: str, name: str, payload: Any) -> dict[str, Any]:
        leaf = self._leaf(domain, name)
        staging = None
        try:
            # Serialize competing GUI saves; recheck revision under the lock.
            with (leaf.path / ".documentation.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                _, path, raw, candidate = self._candidate(domain, name, payload)
                with tempfile.NamedTemporaryFile(
                    dir=leaf.path, prefix=".leaf-", delete=False
                ) as output:
                    staging = Path(output.name)
                    output.write(
                        (
                            json.dumps(candidate, ensure_ascii=False, indent=2) + "\n"
                        ).encode()
                    )
                    output.flush()
                    os.fsync(output.fileno())
                os.chmod(staging, path.stat().st_mode & 0o777)
                if path.read_bytes() != raw:
                    raise CliError(
                        "EDIT_CONFLICT", "Leaf changed on disk; reload before saving"
                    )
                os.replace(staging, path)
                staging = None
        except OSError as error:
            raise CliError(
                "LEAF_DOCUMENT_ERROR", "Cannot save leaf documentation"
            ) from error
        finally:
            if staging is not None:
                staging.unlink(missing_ok=True)
        return self.load(domain, name)
