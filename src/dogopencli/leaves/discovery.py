"""Read-only plugin inventory from bundled and installed declarations."""

import json
from importlib.resources import files
from pathlib import Path

from ..errors import CliError
from .registry import Registry, validate_manifest


def list_plugins(config_file: Path, *, registry: Registry | None = None) -> dict:
    """Report declarations without adapter execution or lifecycle reconciliation."""
    registry = registry if registry is not None else Registry(config_file).discover()
    rows = {}
    diagnostics = list(registry.diagnostics)
    try:
        root = files("dogopencli").joinpath("leaf_packages")
        for domain in root.iterdir():
            if not domain.is_dir():
                continue
            for folder in domain.iterdir():
                if not folder.is_dir():
                    continue
                manifest = folder.joinpath("leaf.json")
                if not manifest.is_file():
                    continue
                identity = f"{domain.name}.{folder.name}"
                try:
                    declaration = json.loads(manifest.read_text(encoding="utf-8"))
                    validate_manifest(declaration)
                    if identity != f"{declaration['domain']}.{declaration['name']}":
                        raise ValueError("Bundled identity mismatch")
                    rows[identity] = {
                        "identity": identity,
                        "summary": declaration["summary"],
                        "state": "available",
                        "bundled": True,
                        "diagnostics": [],
                        "next_commands": [
                            f"dogopencli plugins install bundled:{identity}"
                        ],
                    }
                except (OSError, ValueError, KeyError, TypeError, CliError):
                    diagnostics.append(
                        {
                            "id": identity,
                            "code": "INVALID_LEAF",
                            "message": "Invalid bundled leaf declaration",
                        }
                    )
    except OSError:
        diagnostics.append(
            {
                "id": "bundled",
                "code": "IO_ERROR",
                "message": "Cannot read bundled leaf declarations",
            }
        )
    for leaf in registry.leaves.values():
        rows[leaf.id] = {
            "identity": leaf.id,
            "summary": leaf.manifest["summary"],
            "state": "installed",
            "bundled": bool(rows.get(leaf.id, {}).get("bundled")),
            "diagnostics": [],
            "next_commands": [
                f"dogopencli {leaf.domain} describe {leaf.name}",
                f"dogopencli plugins uninstall {leaf.id}",
            ],
        }
    for diagnostic in registry.diagnostics:
        identity = diagnostic["id"]
        if identity in {"plugins", "bundled"} or "." not in identity:
            continue
        previous = rows.get(identity, {})
        rows[identity] = {
            "identity": identity,
            "summary": previous.get("summary", "Invalid installed declaration."),
            "state": "invalid",
            "bundled": bool(previous.get("bundled")),
            "diagnostics": [diagnostic],
            "next_commands": [f"dogopencli plugins uninstall {identity}"],
        }
    return {"plugins": [rows[key] for key in sorted(rows)], "diagnostics": diagnostics}
