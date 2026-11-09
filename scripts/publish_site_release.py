#!/usr/bin/env python3
"""Publish verified stable Release metadata to the dog-series homepage."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.request import urlopen

PROJECT = "pd.pt/dogopencli"
RELEASE_URL = f"https://code.alipay.com/{PROJECT}/releases"
SITE = "/home/admin/webserver/site/releases"
SITE_URL = "http://poolab-iys595a7znqgza1e.inc.alipay.net/releases/dogopencli.json"
STAGING = "/home/admin/workspace/.dogopencli-release-site"
TAG_PATTERN = r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"

# This program runs on the host. Only dogopencli.json is replaced; existing HTML,
# catalogs and server configuration remain untouched. The lock also serializes
# competing publishers so an older release cannot win a concurrent update.
REMOTE_UPDATE = r"""
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.request import urlopen

source, destination, public_url = sys.argv[1:]
source = Path(source)
destination = Path(destination)
temporary = None
try:
    payload = source.read_bytes()
    expected = json.loads(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(destination.parent, 0o755)
    with (destination.parent / ".dogopencli.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = destination.read_bytes() if destination.exists() else None
        previous_mode = (
            destination.stat().st_mode & 0o7777 if previous is not None else 0o644
        )
        current = None
        if previous is not None:
            try:
                current = json.loads(previous)
            except (ValueError, UnicodeError):
                pass  # Preserve raw bytes for rollback, but allow metadata repair.
        if isinstance(current, dict):
            version = current.get("version", "")
            if (
                current.get("schema_version") == 1
                and current.get("channel") == "stable"
                and isinstance(version, str)
                and re.fullmatch(
                    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version
                )
                and current.get("tag") == "v" + version
                and tuple(map(int, version.split(".")))
                > tuple(map(int, expected["version"].split(".")))
            ):
                raise ValueError("refusing stable homepage downgrade")
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".release-", delete=False
        ) as stream:
            temporary = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, destination)
        temporary = None
        try:
            if destination.read_bytes() != payload:
                raise ValueError("homepage metadata readback failed")
            with urlopen(
                public_url + "?release=" + expected["tag"], timeout=20
            ) as response:
                if (
                    response.status != 200
                    or json.loads(response.read(65537)) != expected
                ):
                    raise ValueError("homepage HTTP verification failed")
        except (OSError, ValueError):
            # Verification and rollback stay inside the publisher lock. Only
            # roll back after our replacement succeeded, never before it.
            if previous is None:
                destination.unlink()
            else:
                with tempfile.NamedTemporaryFile(
                    dir=destination.parent, prefix=".release-", delete=False
                ) as stream:
                    temporary = stream.name
                    stream.write(previous)
                    stream.flush()
                    os.fsync(stream.fileno())
                    os.fchmod(stream.fileno(), previous_mode)
                os.replace(temporary, destination)
                temporary = None
            raise
finally:
    if temporary is not None:
        os.unlink(temporary)
    source.unlink(missing_ok=True)
    source.parent.rmdir()
"""


class SitePublishError(Exception):
    """A publication error that is safe to show without provider output."""


def command(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            arguments, capture_output=True, text=True, timeout=120, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SitePublishError(f"{arguments[0]} unavailable or timed out") from None
    if result.returncode:
        raise SitePublishError(
            f"{arguments[0]} command failed (exit {result.returncode})"
        )
    return result.stdout


def fetch(url: str) -> bytes:
    try:
        with urlopen(url, timeout=20) as response:
            body = response.read(1024 * 1024 + 1)
            if response.status != 200 or len(body) > 1024 * 1024:
                raise SitePublishError("Installer HTTP response is invalid")
            return body
    except SitePublishError:
        raise
    except (OSError, ValueError):
        raise SitePublishError("Anonymous installer download failed") from None


def metadata(tag: str, release: object, installer: bytes) -> dict:
    if re.fullmatch(TAG_PATTERN, tag) is None:
        raise SitePublishError("Tag must be canonical vMAJOR.MINOR.PATCH")
    if not isinstance(release, dict) or release.get("tag_name") != tag:
        raise SitePublishError("Release identity mismatch")
    for key, expected in (
        ("is_draft", False),
        ("is_anonymous", True),
        ("is_prerelease", False),
        ("is_blocked", False),
    ):
        if release.get(key) is not expected:
            raise SitePublishError(
                "Release must be published, anonymous, stable and unblocked"
            )
    version = tag[1:]
    wheel = f"dogopencli-{version}-py3-none-any.whl"
    assets = release.get("assets")
    if not isinstance(assets, list) or any(not isinstance(row, dict) for row in assets):
        raise SitePublishError("Invalid Release assets")
    if not {"install.sh", wheel} <= {
        row.get("filename") for row in assets if isinstance(row.get("filename"), str)
    }:
        raise SitePublishError("Release installer or wheel missing")
    published = release.get("published_at")
    if not isinstance(published, str) or not published.strip():
        raise SitePublishError("Release publication time missing")
    base = f"{RELEASE_URL}/download/{tag}"
    try:
        text = installer.decode("utf-8")
    except UnicodeError:
        raise SitePublishError("Installer is not UTF-8 shell text") from None
    if (
        not text.startswith(("#!/bin/bash\n", "#!/usr/bin/env bash\n"))
        or "<html" in text.lower()
    ):
        raise SitePublishError("Installer is not a shell script")
    for key, value in (
        ("VERSION", version),
        ("WHEEL", wheel),
        ("RELEASE_BASE_URL", base),
    ):
        assignments = re.findall(rf"(?m)^{key}=(.*)$", text)
        if assignments != [f"'{value}'"]:
            raise SitePublishError("Installer does not match the selected Release")
    return {
        "schema_version": 1,
        "product": "dogopencli",
        "version": version,
        "tag": tag,
        "channel": "stable",
        "provider": "antcode",
        "installer_url": f"{base}/install.sh",
        "release_url": RELEASE_URL,
        "auth": "none",
        "published_at": published,
    }


def remote_python(program: str, *arguments: str) -> str:
    return command(
        [
            "poolab",
            "terminal",
            "execute",
            "--alias",
            "default",
            "--timeout",
            "30s",
            shlex.join(["python3", "-c", program, *arguments]),
        ]
    )


def publish(tag: str) -> None:
    if re.fullmatch(TAG_PATTERN, tag) is None:
        raise SitePublishError("Tag must be canonical vMAJOR.MINOR.PATCH")
    output = command(
        ["antcode", "release", "show", tag, "--project", PROJECT, "--json"]
    )
    try:
        release = json.loads(output)
    except (ValueError, TypeError):
        raise SitePublishError("Invalid AntCode Release JSON") from None
    # Validate all Release fields before performing any remote write.
    installer = fetch(f"{RELEASE_URL}/download/{tag}/install.sh")
    data = metadata(tag, release, installer)
    stage = f"{STAGING}/{uuid.uuid4().hex}"
    staged_file = f"{stage}/release.json"
    remote_python(
        "from pathlib import Path; import sys; Path(sys.argv[1]).mkdir(parents=True)",
        stage,
    )
    try:
        with tempfile.TemporaryDirectory(prefix="dogopencli-site-") as directory:
            local = Path(directory) / "release.json"
            local.write_text(
                json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            command(
                [
                    "poolab",
                    "sync",
                    "--instance",
                    "default",
                    str(local),
                    f":{staged_file}",
                ]
            )
            remote_python(
                REMOTE_UPDATE, staged_file, f"{SITE}/dogopencli.json", SITE_URL
            )
    finally:
        # Only the unique staging directory owned by this invocation is removed.
        try:
            remote_python(
                "import shutil, sys; shutil.rmtree(sys.argv[1], ignore_errors=True)",
                stage,
            )
        except SitePublishError:
            pass
    print(f"Homepage updated to {tag}: {SITE_URL}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    try:
        publish(args.tag)
    except SitePublishError as error:
        print(f"publish-site-release: FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
