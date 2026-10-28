"""Verify the exact deployment bundle outside the source import environment."""

import hashlib
import json
import os
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(
            value
            for key, value in attrs
            if key in {"href", "src"} and value and not value.startswith("#")
        )


def test_standalone_bundle_catalog_downloads_and_documentation(tmp_path):
    bundle = tmp_path / "bundle"
    environment = {
        key: value for key, value in os.environ.items() if key != "PYTHONPATH"
    }
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/plugin-site/build.py"),
            "--output",
            str(bundle),
            "--version",
            "acceptance-1",
        ],
        check=True,
        capture_output=True,
        env=environment,
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            str(bundle / "server.py"),
            "--port",
            "0",
            "--data",
            str(bundle / "seed"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
        cwd=tmp_path,
    )
    try:
        line = process.stdout.readline()
        assert line.startswith("Plugin site: "), line
        base = line.removeprefix("Plugin site: ").strip()
        with urlopen(base + "api/catalog", timeout=5) as response:
            records = json.load(response)["releases"]
        expected = list((ROOT / "leaf_packages").glob("*/*/leaf.json"))
        expected += list((ROOT / "src/dogopencli/leaf_packages").glob("*/*/leaf.json"))
        assert len(records) == len(expected)
        assert len({record["id"] for record in records}) == len(expected)
        assert {record["domain"] for record in records} == {
            "payment",
            "collection",
            "liquidity",
            "fx",
        }
        for record in records:
            with urlopen(urljoin(base, record["download"]), timeout=5) as response:
                payload = response.read()
            assert len(payload) == record["bytes"]
            assert hashlib.sha256(payload).hexdigest() == record["sha256"]
        for page in ("", "docs"):
            with urlopen(base + page, timeout=5) as response:
                parser = Links()
                parser.feed(response.read().decode())
            for link in parser.links:
                with urlopen(urljoin(base + page, link), timeout=5) as response:
                    assert response.status == 200, link
        for path in ("llms.txt", "agent-guide.md"):
            with urlopen(base + path, timeout=5) as response:
                assert response.read()
    finally:
        process.terminate()
        process.communicate(timeout=5)
