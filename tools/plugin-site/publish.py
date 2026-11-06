"""Publish an existing leaf ZIP and verify the served immutable bytes."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from dogopencli.errors import CliError  # noqa: E402
from dogopencli.leaves.package import MAX_ARCHIVE_BYTES, validate_package  # noqa: E402


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Registry redirects are not accepted")


def publish(source: Path, url: str, version: str, *, allow_http: bool = False) -> dict:
    parts = urlsplit(url)
    if (
        parts.scheme not in ({"https", "http"} if allow_http else {"https"})
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path.rstrip("/") != "/plugins"
    ):
        raise ValueError(
            "Use an HTTPS registry /plugins URL (HTTP requires --allow-http)"
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version):
        raise ValueError("Invalid registry version")
    token = os.environ.get("PLUGIN_PUBLISH_TOKEN", "").strip()
    if not token:
        raise ValueError("PLUGIN_PUBLISH_TOKEN is required")
    # Validate the exact bytes submitted, not a source file that may change later.
    with source.open("rb") as stream:
        body = stream.read(MAX_ARCHIVE_BYTES + 1)
    if not 0 < len(body) <= MAX_ARCHIVE_BYTES:
        raise ValueError("ZIP must be nonempty and at most 50 MiB")
    with tempfile.TemporaryDirectory(prefix="plugin-publish-") as temporary:
        snapshot = Path(temporary) / "package.zip"
        snapshot.write_bytes(body)
        with validate_package(snapshot) as package:
            identity = f"{package.manifest['domain']}.{package.manifest['name']}"
    digest = hashlib.sha256(body).hexdigest()
    base = url.rstrip("/")
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(
        base + "/api/releases/" + version,
        data=body,
        method="PUT",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/zip"},
    )
    try:
        with opener.open(request, timeout=60) as response:
            if response.status != 201:
                raise ValueError("Registry did not confirm publication")
            response.read(65536)
    except urllib.error.HTTPError as error:
        if error.code != 409:
            raise ValueError(
                f"Registry publication failed (HTTP {error.code})"
            ) from None
        # Lost response/retry is a no-op only when remote bytes actually match.
    expected = f"{base}/downloads/{identity}/{version}/package.zip"
    with opener.open(expected, timeout=60) as response:
        downloaded = response.read(MAX_ARCHIVE_BYTES + 1)
    if hashlib.sha256(downloaded).hexdigest() != digest:
        raise ValueError(
            "Remote plugin differs; existing versions are never overwritten"
        )
    return {"id": identity, "version": version, "sha256": digest, "download": expected}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--allow-http", action="store_true")
    args = parser.parse_args()
    try:
        record = publish(args.zip, args.url, args.version, allow_http=args.allow_http)
    except (OSError, ValueError, CliError):
        print(
            "Plugin publication failed; check package, registry "
            "and publish credentials.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
