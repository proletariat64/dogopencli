"""Statically verify or package one local dogopencli leaf."""

import argparse
import json
import os
import tempfile
import uuid
import zipfile
from pathlib import Path

from dogopencli.errors import CliError
from dogopencli.leaves.package import validate_package


def pack(source: Path, output: Path) -> dict:
    source = source.absolute()
    output = output.absolute()
    if not source.is_dir():
        raise ValueError("Pack requires a local source directory.")
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists; choose a new ZIP path.")
    if output.resolve().is_relative_to(source.resolve()):
        raise ValueError("Output must be outside the source directory.")
    with validate_package(source) as package:
        with tempfile.TemporaryDirectory(prefix="dogopencli-pack-") as temporary:
            archive_path = Path(temporary) / "package.zip"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(package.path.rglob("*")):
                    name = path.relative_to(package.path).as_posix()
                    entry = zipfile.ZipInfo(name + "/" if path.is_dir() else name)
                    entry.create_system = 3
                    entry.external_attr = (0o40755 if path.is_dir() else 0o100644) << 16
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(entry, b"" if path.is_dir() else path.read_bytes())
            with validate_package(archive_path) as verified:
                identity = f"{verified.manifest['domain']}.{verified.manifest['name']}"
            # Stage on the destination filesystem. Hard-link publication is atomic
            # and refuses a destination created concurrently, unlike replace().
            staging_path = output.parent / f".dogopencli-pack-{uuid.uuid4().hex}"
            descriptor = os.open(
                staging_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666
            )
            try:
                with os.fdopen(descriptor, "wb") as destination:
                    destination.write(archive_path.read_bytes())
                    destination.flush()
                    os.fsync(destination.fileno())
                os.link(staging_path, output)
            finally:
                staging_path.unlink(missing_ok=True)
    return {"identity": identity, "output": str(output), "state": "packed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    verify = commands.add_parser("verify", help="Validate a local directory or ZIP.")
    verify.add_argument("source", type=Path)
    packaging = commands.add_parser("pack", help="Create a validated ordinary ZIP.")
    packaging.add_argument("source", type=Path)
    packaging.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        if arguments.action == "pack":
            result = pack(arguments.source, arguments.output)
        else:
            with validate_package(arguments.source) as package:
                manifest = package.manifest
                result = {
                    "identity": f"{manifest['domain']}.{manifest['name']}",
                    "state": "verified",
                }
    except (CliError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "error": getattr(error, "code", "PACKAGE_HELPER_FAILED"),
                    "message": str(error),
                }
            )
        )
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
