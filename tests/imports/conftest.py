"""Prepared external settings helpers; each test owns its publication root."""

import importlib.util
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = Path(".agents/skills/duckdog-import/scripts/import_settings.py")


def _apply_patch(root: Path, name: str) -> None:
    result = subprocess.run(
        ["patch", "--batch", "-p1", "-i", str(ROOT / "scripts/patches" / name)],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _load_importer(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def reference_importer_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("reference-settings-helper")
    source = root / HELPER
    source.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "tests/fixtures/duckdog/import_settings.py", source)
    _apply_patch(root, "migration-b01-duckdog-import.patch")
    return source


@pytest.fixture(scope="session")
def reference_importer(reference_importer_path: Path) -> ModuleType:
    return _load_importer(reference_importer_path, "reference_settings_importer")


@pytest.fixture(scope="session")
def settings_importer(
    reference_importer_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> ModuleType:
    root = tmp_path_factory.mktemp("installed-settings-helper")
    source = root / HELPER
    source.parent.mkdir(parents=True)
    shutil.copyfile(reference_importer_path, source)
    _apply_patch(root, "migration-b02-duckdog-import.patch")
    return _load_importer(source, "installed_settings_importer")
