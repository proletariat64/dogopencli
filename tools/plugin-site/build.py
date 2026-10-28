"""Build a self-contained Python 3.11+ registry bundle for poolab sync."""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(ROOT))

from server import publish  # noqa: E402


def build(output: Path, version: str) -> int:
    if output.exists():
        raise ValueError("Output already exists; choose a new bundle directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".plugin-site-", dir=output.parent) as temp:
        bundle = Path(temp) / "bundle"
        bundle.mkdir()
        for name in ("server.py", "README.md", "nginx.conf", "plugin-site.service"):
            shutil.copy2(ROOT / name, bundle / name)
        shutil.copytree(ROOT / "web", bundle / "web")
        # Ship the authoritative host code unchanged. No adapter is imported.
        shutil.copytree(
            REPO / "src/dogopencli",
            bundle / "runtime/dogopencli",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "leaf_packages"),
        )
        for relative in (
            "tools/leaf-dev",
            "docs/agents/list-collection-sdk.md",
            "docs/agents/get-sdk.md",
            "docs/agents/custom-query-sdk.md",
            "docs/agents/result-policy.md",
            "src/dogopencli/leaves/registry.py",
            "src/dogopencli/leaves/package.py",
            "src/dogopencli/contracts.py",
        ):
            source = REPO / relative
            target = bundle / "web/reference" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(
                    source,
                    target,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
            else:
                shutil.copy2(source, target)
        sources = sorted((REPO / "leaf_packages").glob("*/*/leaf.json"))
        sources += sorted((REPO / "src/dogopencli/leaf_packages").glob("*/*/leaf.json"))
        # The existing helper owns the packing policy and checksum format.
        command = [sys.executable, str(REPO / "tools/leaf-dev/leaf.py"), "pack"]
        command += [str(path.parent) for path in sources]
        command += ["--output", str(Path(temp) / "packed")]
        subprocess.run(command, check=True, capture_output=True)
        archives = sorted((Path(temp) / "packed").glob("*.zip"))
        for archive in archives:
            publish(archive, bundle / "seed", version)
        bundle.rename(output)
    return len(archives)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--version",
        required=True,
        help="Registry release label, not leaf manifest version",
    )
    args = parser.parse_args()
    print(
        f"Built {build(args.output.absolute(), args.version)} plugin releases: "
        f"{args.output}"
    )
