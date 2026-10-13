"""Prepare a worktree-local environment with shared dependency files."""

import importlib.metadata
import os
import shutil
import subprocess
import sys
from pathlib import Path


def seed_from_main(destination: Path, lockfile: Path) -> None:
    """Reuse installed distributions without downloading their wheels again."""
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    locked = {
        (package["name"].lower().replace("_", "-"), package["version"])
        for package in tomllib.loads(lockfile.read_text())["package"]
        if "registry" in package["source"]
    }
    source_prefix = Path(sys.prefix).resolve()
    target_python = destination / "bin/python"
    target_version = subprocess.check_output(
        [str(target_python), "-I", "-c", "import sys; print(sys.version)"], text=True
    ).strip()
    if target_version != sys.version:
        print("Main environment uses a different Python; using uv cache instead.")
        return
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"].lower().replace("_", "-")
        if (name, distribution.version) not in locked:
            continue
        for record in distribution.files or ():
            source = Path(distribution.locate_file(record)).resolve()
            if not source.is_file() or "__pycache__" in source.parts:
                continue
            if not source.is_relative_to(source_prefix):
                continue
            target = destination / source.relative_to(source_prefix)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.parent == destination / "bin":
                with source.open("rb") as stream:
                    shebang = stream.readline()
                    if shebang.startswith(b"#!") and b"python" in shebang:
                        target.write_bytes(
                            f"#!{target_python}\n".encode() + stream.read()
                        )
                        target.chmod(source.stat().st_mode & 0o777)
                        continue
            os.link(source, target)
        print(f"Reused {name}=={distribution.version} from main environment")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    environment = root / ".venv"
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("bootstrap requires uv: https://docs.astral.sh/uv/")
    if environment.is_symlink():
        raise SystemExit(".venv must be local to this worktree, not a symlink")
    cache = Path(subprocess.check_output([uv, "cache", "dir"], text=True).strip())
    existing_cache = cache
    while not existing_cache.exists():
        existing_cache = existing_cache.parent
    if existing_cache.stat().st_dev != root.stat().st_dev:
        raise SystemExit("Set UV_CACHE_DIR to a shared path on the worktree filesystem")
    if environment.exists() and environment.stat().st_dev != root.stat().st_dev:
        raise SystemExit(".venv must be on the same filesystem as the shared cache")
    env = os.environ.copy()
    env["UV_PROJECT_ENVIRONMENT"] = str(environment)
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_NO_CACHE", None)
    common = ["--no-python-downloads", "--cache-dir", str(cache)]
    lock_check = subprocess.run(
        [uv, "lock", "--check", *common],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if lock_check.returncode != 0:
        raise SystemExit(
            "uv.lock is out of date with pyproject.toml; "
            "run `uv lock` and commit uv.lock before bootstrapping"
        )
    if not environment.exists():
        subprocess.run(
            [uv, "venv", str(environment), "--python", sys.executable, *common],
            cwd=root,
            env=env,
            check=True,
        )
        git_common = Path(
            subprocess.check_output(
                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                cwd=root,
                text=True,
            ).strip()
        )
        main_python = git_common.parent / ".venv/bin/python"
        if main_python.exists() and main_python.parent.parent != environment:
            subprocess.run(
                [
                    str(main_python),
                    "-I",
                    str(Path(__file__).resolve()),
                    "--seed",
                    str(environment),
                    str(root / "uv.lock"),
                ],
                check=True,
            )
    subprocess.run(
        [
            uv,
            "sync",
            "--locked",
            "--extra",
            "dev",
            "--extra",
            "duckdog",
            "--inexact",
            "--link-mode",
            "hardlink",
            *common,
        ],
        cwd=root,
        env=env,
        check=True,
    )
    verification = """
import pathlib, sys
import dogopencli, duckdb, pytest, ruff
root = pathlib.Path(sys.argv[1]).resolve()
assert pathlib.Path(sys.prefix).resolve() == root / '.venv', sys.prefix
expected = root / 'src/dogopencli/__init__.py'
assert pathlib.Path(dogopencli.__file__).resolve() == expected, dogopencli.__file__
print('bootstrap: PASS; environment and source belong to', root)
"""
    subprocess.run(
        [str(environment / "bin/python"), "-I", "-c", verification, str(root)],
        cwd=root,
        check=True,
    )


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--seed":
        seed_from_main(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        main()
