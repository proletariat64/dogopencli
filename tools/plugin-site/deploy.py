"""Activate a verified site bundle on its Linux host using a systemd user service."""

import argparse
import fcntl
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

SERVICE = "plugin-site.service"


def verify(bundle: Path) -> dict:
    metadata = json.loads((bundle / "bundle.json").read_text())
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", metadata["version"]):
        raise ValueError("Invalid site version")
    actual = {}
    for path in sorted(bundle.rglob("*")):
        if path.is_symlink():
            raise ValueError("Bundle must not contain symlinks")
        if path.is_file() and path != bundle / "bundle.json":
            actual[path.relative_to(bundle).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    if not actual or actual != metadata["files"]:
        raise ValueError("Site bundle checksum mismatch")
    for required in (
        "server.py",
        "deploy.py",
        "web/index.html",
        "runtime/dogopencli/__init__.py",
    ):
        if required not in actual:
            raise ValueError("Incomplete site bundle")
    return metadata


def systemctl(*args: str) -> None:
    result = subprocess.run(
        ["systemctl", "--user", *args], capture_output=True, timeout=60
    )
    if result.returncode:
        raise ValueError("systemd user service command failed")


def healthy(port: int, version: str) -> None:
    for _ in range(20):
        try:
            with urlopen(
                f"http://127.0.0.1:{port}/plugins/api/health", timeout=2
            ) as response:
                status = json.load(response)
            if status.get("status") == "ok" and status.get("version") == version:
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.25)
    raise ValueError("New site release failed its health check")


def activate(root: Path, release: Path) -> None:
    link = root / ".current-next"
    link.unlink(missing_ok=True)
    link.symlink_to(release)
    link.replace(root / "current")


def deploy(bundle: Path, root: Path, port: int = 5910) -> Path:
    if sys.version_info < (3, 11):
        raise ValueError("Site requires Python 3.11+")
    bundle = bundle.resolve()
    metadata = verify(bundle)
    root = root.absolute()
    if root.resolve() != root or root == Path("/") or bundle.is_relative_to(root):
        raise ValueError("Use a real deployment root separate from the input bundle")
    # systemd has its own escaping rules; restrict generated unit paths explicitly.
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(root)) or not re.fullmatch(
        r"/[A-Za-z0-9_./-]+", sys.executable
    ):
        raise ValueError(
            "Deployment/Python paths must not contain whitespace or unit specifiers"
        )
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be 1024..65535")
    systemctl("show-environment")
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = root / "current"
        if current.exists() and not current.is_symlink():
            raise ValueError("current must be an owned release symlink")
        previous = current.resolve() if current.is_symlink() else None
        releases = root / "releases"
        if releases.is_symlink() or (root / "data").is_symlink():
            raise ValueError("Release and data directories must not be symlinks")
        releases.mkdir(exist_ok=True)
        if previous and (previous.parent != releases or not previous.is_dir()):
            raise ValueError("current points outside the release directory")
        release = releases / metadata["version"]
        if release.is_symlink():
            raise ValueError("Release directory must not be a symlink")
        if release.exists():
            if verify(release) != metadata:
                raise ValueError("Site version already exists with different bytes")
        else:
            with tempfile.TemporaryDirectory(
                prefix=".stage-", dir=releases
            ) as temporary:
                stage = Path(temporary) / "bundle"
                shutil.copytree(bundle, stage)
                verify(stage)
                stage.rename(release)
        # First installation seeds once. Updates never sync over live publications.
        data = root / "data"
        if not data.exists():
            with tempfile.TemporaryDirectory(prefix=".seed-", dir=root) as temporary:
                stage = Path(temporary) / "data"
                shutil.copytree(release / "seed", stage)
                stage.rename(data)
        unit_dir = Path.home() / ".config/systemd/user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        unit = unit_dir / SERVICE
        if unit.is_symlink():
            raise ValueError("Service unit must not be a symlink")
        old_unit = unit.read_bytes() if unit.exists() else None
        if old_unit and f"WorkingDirectory={root}/current\n".encode() not in old_unit:
            raise ValueError("Existing service belongs to another deployment root")
        text = (
            "[Unit]\nDescription=Dogopencli plugin registry\nAfter=network.target\n\n"
            f"[Service]\nWorkingDirectory={root}/current\n"
            f"ExecStart={sys.executable} -B {root}/current/server.py "
            f"--host 127.0.0.1 --port {port} --data {data}\n"
            f"EnvironmentFile=-{root}/publish.env\n"
            "Restart=on-failure\nRestartSec=3\nUMask=0077\nNoNewPrivileges=true\n\n"
            "[Install]\nWantedBy=default.target\n"
        )
        try:
            unit.write_text(text)
            activate(root, release)
            systemctl("daemon-reload")
            systemctl("restart", SERVICE)
            healthy(port, metadata["version"])
            systemctl("enable", SERVICE)
        except Exception:
            if old_unit is None:
                unit.unlink(missing_ok=True)
            else:
                unit.write_bytes(old_unit)
            if previous:
                activate(root, previous)
                systemctl("daemon-reload")
                systemctl("restart", SERVICE)
            else:
                systemctl("stop", SERVICE)
                current.unlink(missing_ok=True)
                systemctl("daemon-reload")
            raise
        return release


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=5910)
    args = parser.parse_args()
    try:
        release = deploy(args.bundle, args.root, args.port)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print(
            "Site deployment failed; inspect bundle, systemd and host configuration.",
            file=sys.stderr,
        )
        return 1
    print(f"Activated {release}. Data and publish.env preserved.")
    print(
        "Reverse proxy: include nginx.conf in the existing server; "
        "nginx -t before reload."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
