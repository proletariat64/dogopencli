"""Exercise a built wheel in isolated uv tool directories without business access."""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def smoke(dist: Path) -> None:
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
            subprocess.run(args, env=env, check=True, timeout=180, capture_output=True)
        if (root / "bin/dogopencli").exists() or sentinel.read_text() != "keep":
            raise ValueError("Uninstall smoke failed")
    print("Wheel install/update/uninstall smoke passed; external data retained.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    smoke(parser.parse_args().dist)
