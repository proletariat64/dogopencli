"""Exercise a built wheel in isolated uv tool directories without business access."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def smoke(dist: Path) -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    wheels = list(dist.glob("dogopencli-*-py3-none-any.whl"))
    if len(wheels) != 1:
        raise ValueError("Smoke requires exactly one wheel; use a clean DIST_DIR")
    with tempfile.TemporaryDirectory(prefix="dogopencli-smoke-") as directory:
        root = Path(directory)
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("UV_", "DOGOPENCLI_", "PYTHON"))
        }
        env.update(
            HOME=str(root),
            UV_TOOL_DIR=str(root / "tools"),
            UV_TOOL_BIN_DIR=str(root / "bin"),
            UV_PYTHON=sys.executable,
        )
        config = root / ".config/dogopencli"
        config.mkdir(parents=True)
        sentinel = config / "preserve.txt"
        sentinel.write_text("keep")
        for args in (
            ["bash", str(ROOT / "install.sh"), "install", str(wheels[0].resolve())],
            [str(root / "bin/dogopencli"), "--version"],
            [str(root / "bin/dogopencli"), "update", "--help"],
            [
                str(root / "bin/dogopencli"),
                "update",
                "--source",
                str(wheels[0].resolve()),
            ],
            [str(root / "bin/dogopencli"), "uninstall"],
        ):
            try:
                result = subprocess.run(
                    args,
                    env=env,
                    check=False,
                    timeout=180,
                    capture_output=True,
                    text=True,
                )
            except subprocess.TimeoutExpired as error:
                output = (error.stdout or b"") + b"\n" + (error.stderr or b"")
                raise RuntimeError(
                    f"Smoke command timed out: {' '.join(args[:2])}\n"
                    f"{output.decode('utf-8', errors='replace')}"
                ) from None
            if result.returncode:
                raise RuntimeError(
                    f"Smoke command failed: {' '.join(args[:2])}\n"
                    f"{result.stdout}\n{result.stderr}"
                )
            if args[1:] == ["--version"]:
                reported = json.loads(result.stdout)["data"]["version"]
                if reported != version:
                    raise ValueError(
                        f"Installed CLI version {reported!r} "
                        f"does not match planned release {version!r}"
                    )
        if (root / "bin/dogopencli").exists() or sentinel.read_text() != "keep":
            raise ValueError("Uninstall smoke failed")
    print("Wheel install/update/uninstall smoke passed; external data retained.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    smoke(parser.parse_args().dist)
