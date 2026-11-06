"""Exercise the shell installer against real uv in disposable tool directories."""

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"
pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required")


@pytest.fixture
def installation(tmp_path):
    # Spaces exercise quoting throughout the script, uv and generated entry point.
    root = tmp_path / "isolated installation"
    root.mkdir()
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith(("UV_", "DOGOPENCLI_", "PYTHON")):
            env.pop(key)
    env.update(
        HOME=str(root),
        XDG_CONFIG_HOME=str(root / "config"),
        XDG_DATA_HOME=str(root / "data"),
        XDG_CACHE_HOME=str(root / "cache"),
        UV_TOOL_DIR=str(root / "tools"),
        UV_TOOL_BIN_DIR=str(root / "bin"),
        UV_PYTHON_DOWNLOADS="never",
        UV_OFFLINE="1",
    )
    return root, env


def wheel(
    directory: Path, version: str, message: str, *, old_module=False, dependency=False
) -> Path:
    directory.mkdir(parents=True)
    path = directory / f"dogopencli-{version}-py3-none-any.whl"
    info = f"dogopencli-{version}.dist-info"
    files = {
        "dogopencli/__init__.py": "",
        "dogopencli/cli.py": f"def main():\n    print({message!r})\n",
        f"{info}/METADATA": (
            "Metadata-Version: 2.1\nName: dogopencli\n"
            f"Version: {version}\nRequires-Python: >=3.12,<3.13\n"
            + ("Requires-Dist: cached-dependency>=1\n" if dependency else "")
        ),
        f"{info}/WHEEL": "Wheel-Version: 1.0\nTag: py3-none-any\n",
        f"{info}/entry_points.txt": (
            "[console_scripts]\ndogopencli = dogopencli.cli:main\n"
        ),
    }
    if old_module:
        files["dogopencli/removed.py"] = "OLD = True\n"
    files[f"{info}/RECORD"] = "".join(f"{name},,\n" for name in files)
    with zipfile.ZipFile(path, "w") as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
    return path


def run(env: dict[str, str], *args: str | Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(INSTALLER), *map(str, args)],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )


def succeeded(result: subprocess.CompletedProcess) -> str:
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_install_overwrites_same_version_update_and_uninstall(installation):
    root, env = installation
    preserved = [
        root / "config/dogopencli/config.toml",
        root / "config/dogopencli/plugins/payment/example/leaf.json",
        root / "config/dogopencli/duckdog.duckdb",
        root / "data/dogopencli/chrome/Default/Cookies",
    ]
    for path in preserved:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("keep me")
    first = wheel(root / "first", "1.0.0", "first", old_module=True)
    second = wheel(root / "second", "1.0.0", "replacement")
    third = wheel(root / "third", "2.0.0", "updated")

    assert "first" in succeeded(run(env, "install", first))
    program = root / "tools/dogopencli"
    assert list(program.rglob("removed.py"))
    assert "replacement" in succeeded(run(env, "install", second))
    assert not list(program.rglob("removed.py"))
    assert "updated" in succeeded(run(env, "update", third))
    assert [path.name for path in (root / "tools").iterdir() if path.is_dir()] == [
        "dogopencli"
    ]
    assert (root / "bin/dogopencli").exists()
    succeeded(run(env, "uninstall"))
    succeeded(run(env, "uninstall"))
    assert not program.exists()
    assert not (root / "bin/dogopencli").is_symlink()
    assert not (root / "bin/dogopencli").exists()
    assert all(path.read_text() == "keep me" for path in preserved)
    assert (root / "cache/uv").exists()


def test_update_invalid_wheel_preserves_installation(installation):
    root, env = installation
    first = wheel(root / "first", "1.0.0", "first")
    succeeded(run(env, "install", first))
    bad = root / "dogopencli-2.0.0-py3-none-any.whl"
    bad.write_bytes(b"invalid wheel")
    assert run(env, "update", bad).returncode != 0
    assert (root / "tools/dogopencli").exists()
    assert (root / "bin/dogopencli").exists()


def test_update_without_existing_installation(installation):
    root, env = installation
    source = wheel(root / "wheel", "1.0.0", "fresh update")
    assert "fresh update" in succeeded(run(env, "update", source))


@pytest.mark.parametrize("args", [("invalid",), ("uninstall", "extra")])
def test_invalid_arguments_do_not_remove_installation(installation, args):
    root, env = installation
    first = wheel(root / "first", "1.0.0", "first")
    succeeded(run(env, "install", first))
    assert run(env, *args).returncode == 2
    assert (root / "bin/dogopencli").exists()


def test_missing_source_is_rejected_before_uninstall(installation):
    root, env = installation
    first = wheel(root / "first", "1.0.0", "first")
    succeeded(run(env, "install", first))
    assert run(env, "update", root / "missing.whl").returncode != 0
    assert (root / "bin/dogopencli").exists()


def test_release_installer_pins_origin_and_checks_before_replacement(installation):
    import hashlib

    root, env = installation
    first = wheel(root / "wheel", "1.0.0", "release")
    fake_bin = root / "fake-bin"
    fake_bin.mkdir()
    curl = fake_bin / "curl"
    curl.write_text(
        '#!/bin/bash\nwhile [[ "$1" != -o ]]; do shift; done\n'
        'cp "$FAKE_DOWNLOAD" "$2"\n'
    )
    curl.chmod(0o755)
    env.update(PATH=str(fake_bin) + os.pathsep + env["PATH"], FAKE_DOWNLOAD=str(first))
    template = (INSTALLER.parent / "scripts/install-release.sh").read_text()
    rendered = (
        template.replace("@VERSION@", "1.0.0")
        .replace(
            "@RELEASE_BASE_URL@",
            "https://github.com/proletariat64/dogopencli/releases/download/v1.0.0",
        )
        .replace("@WHEEL@", first.name)
        .replace("@WHEEL_SHA256@", hashlib.sha256(first.read_bytes()).hexdigest())
    )
    script = root / "release.sh"
    script.write_text(rendered)
    result = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    marker = root / "tools/dogopencli/.dogopencli-release"
    assert marker.read_text().strip().endswith("/v1.0.0")
    first.write_bytes(b"corrupt")
    result = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr
    assert marker.exists() and (root / "bin/dogopencli").exists()


def test_update_reuses_dependency_cache_offline(installation):
    root, env = installation
    links = root / "links"
    links.mkdir()
    dependency = links / "cached_dependency-1.0-py3-none-any.whl"
    info = "cached_dependency-1.0.dist-info"
    with zipfile.ZipFile(dependency, "w") as archive:
        files = {
            "cached_dependency.py": "VALUE = 1\n",
            f"{info}/METADATA": (
                "Metadata-Version: 2.1\nName: cached-dependency\nVersion: 1.0\n"
            ),
            f"{info}/WHEEL": "Wheel-Version: 1.0\nTag: py3-none-any\n",
        }
        files[f"{info}/RECORD"] = "".join(f"{name},,\n" for name in files)
        for name, body in files.items():
            archive.writestr(name, body)
    env.update(UV_FIND_LINKS=str(links), UV_NO_INDEX="1")
    first = wheel(root / "first", "1.0.0", "first", dependency=True)
    second = wheel(root / "second", "2.0.0", "updated", dependency=True)
    succeeded(run(env, "install", first))
    result = run(env, "update", second)
    assert "updated" in succeeded(result)
    assert list((root / "tools/dogopencli").rglob("cached_dependency.py"))
    assert "Prepared 1 package" in result.stderr
