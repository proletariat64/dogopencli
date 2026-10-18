"""Leaf development: verify, pack, check HTTP delivery and capture evidence."""

import argparse
import contextlib
import hashlib
import importlib.metadata
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import zipfile
from pathlib import Path

import dogopencli
from dogopencli.errors import CliError
from dogopencli.jsonutil import parse
from dogopencli.leaves.package import _download, validate_package

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class HelperError(ValueError):
    """A failed helper check, without business response values."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def files(path: Path) -> dict[str, bytes]:
    return {
        p.relative_to(path).as_posix(): p.read_bytes()
        for p in sorted(path.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, indent=2)
        output.write("\n")


def host_check(repo: Path) -> dict:
    """Compare the actual installed payload; editable/source imports do not qualify."""
    repo = repo.resolve()
    package = Path(dogopencli.__file__).resolve().parent
    if "site-packages" not in package.parts or package.is_relative_to(repo):
        raise HelperError("Use a source-independent installed host interpreter.")
    names = (
        subprocess.check_output(
            [
                "git",
                "-C",
                str(repo),
                "ls-files",
                "-co",
                "--exclude-standard",
                "-z",
                "--",
                "src/dogopencli",
            ]
        )
        .decode()
        .split("\0")
    )
    expected = {
        name.removeprefix("src/dogopencli/"): (repo / name).read_bytes()
        for name in names
        if name
    }
    if not expected or files(package) != expected:
        raise HelperError(
            "HOST_REBUILD_REQUIRED: installed payload differs from source."
        )
    project = tomllib.loads((repo / "pyproject.toml").read_text())["project"]
    distribution = importlib.metadata.distribution("dogopencli")
    normalize = lambda s: re.sub(r"\s+", "", s.replace("'", '"'))  # noqa: E731
    requirements = {
        normalize(s) for s in distribution.requires or [] if "extra ==" not in s
    }
    scripts = {
        p.name: p.value
        for p in distribution.entry_points
        if p.group == "console_scripts"
    }
    if (
        distribution.version != project["version"]
        or requirements != {normalize(s) for s in project["dependencies"]}
        or scripts != project["scripts"]
    ):
        raise HelperError(
            "HOST_REBUILD_REQUIRED: installed metadata differs from source."
        )
    return {
        "state": "verified",
        "python": sys.executable,
        "package": str(package),
        "version": distribution.version,
        "files_checked": len(expected),
    }


def verify(source: Path) -> dict:
    with validate_package(source) as package:
        return {
            "state": "verified",
            "identity": f"{package.manifest['domain']}.{package.manifest['name']}",
        }


def pack(sources: list[Path], output: Path) -> dict:
    """Create one new delivery directory; never import adapters or inspect the host."""
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise HelperError("Output already exists; choose a new directory.")
    for source in sources:
        if not source.is_dir():
            raise HelperError("Pack requires local source directories.")
        if output.resolve().is_relative_to(source.resolve()):
            raise HelperError("Output must be outside source directories.")
    with tempfile.TemporaryDirectory(
        prefix=".leaf-pack-", dir=output.parent
    ) as temporary:
        staging = Path(temporary) / "delivery"
        staging.mkdir()
        packages = []
        for source in sources:
            with validate_package(source) as package:
                identity = f"{package.manifest['domain']}.{package.manifest['name']}"
                filename = identity + ".zip"
                archive_path = staging / filename
                if archive_path.exists():
                    raise HelperError(f"Duplicate leaf identity: {identity}")
                with archive_path.open("xb") as output_file:
                    with zipfile.ZipFile(
                        output_file, "w", zipfile.ZIP_DEFLATED
                    ) as archive:
                        for path in sorted(package.path.rglob("*")):
                            name = path.relative_to(package.path).as_posix()
                            entry = zipfile.ZipInfo(
                                name + "/" if path.is_dir() else name
                            )
                            entry.create_system = 3
                            entry.external_attr = (
                                0o40755 if path.is_dir() else 0o100644
                            ) << 16
                            entry.compress_type = zipfile.ZIP_DEFLATED
                            archive.writestr(
                                entry, b"" if path.is_dir() else path.read_bytes()
                            )
            with validate_package(archive_path):
                pass
            packages.append(
                {
                    "identity": identity,
                    "filename": filename,
                    "sha256": sha(archive_path.read_bytes()),
                }
            )
        write_json(staging / "delivery.json", {"packages": packages})
        (staging / "SHA256SUMS").write_text(
            "".join(f"{p['sha256']}  {p['filename']}\n" for p in packages)
        )
        staging.rename(output)
    return {"state": "packed", "packages": len(packages), "delivery": str(output)}


def cli(arguments: list[str], config: Path) -> None:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("DOGOPENCLI_") and k != "PYTHONPATH"
    }
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "dogopencli",
            *arguments,
            "--config-dir",
            str(config),
            "--format",
            "json",
        ],
        env=env,
        cwd=config.parent,
        capture_output=True,
        text=True,
    )
    value = parse(result.stdout)
    if result.returncode or value.get("error"):
        code = (value.get("error") or {}).get("code", "CLI_FAILED")
        raise HelperError(f"Lifecycle command failed: {code}")


def http_smoke(delivery: Path, base_url: str, work: Path) -> dict:
    """Check delivery bytes and local lifecycle only; never issue business queries."""
    manifest = json.loads((delivery / "delivery.json").read_text())
    parsed = urllib.parse.urlsplit(base_url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HelperError(
            "Use an HTTP(S) directory URL without credentials/query/fragment."
        )
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    summaries = []
    with tempfile.TemporaryDirectory(prefix="lifecycle-", dir=work) as temporary:
        config = Path(temporary) / "config"
        enabled = set()
        for item in manifest["packages"]:
            identity, filename = item["identity"], item["filename"]
            if (
                not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", identity)
                or filename != identity + ".zip"
            ):
                raise HelperError("Invalid delivery identity or filename.")
            archive = delivery / filename
            if sha(archive.read_bytes()) != item["sha256"]:
                raise HelperError("Local delivery ZIP changed.")
            url = base_url.rstrip("/") + "/" + filename
            download = Path(temporary) / filename
            _download(url, download)
            if sha(download.read_bytes()) != item["sha256"]:
                raise HelperError(
                    "Remote HTTP ZIP checksum differs from tested delivery."
                )
            domain, name = identity.split(".", 1)
            if domain not in enabled:
                cli(["domain", "enable", domain], config)
                enabled.add(domain)
            cli(["plugins", "install", str(download)], config)
            installed = config / "plugins" / domain / name
            if not installed.is_dir():
                raise HelperError("Install did not create the leaf directory.")
            cli(["plugins", "uninstall", identity], config)
            if installed.exists() or installed.is_symlink():
                raise HelperError("Uninstall left an installed package.")
            summaries.append(
                {
                    "identity": identity,
                    "sha256": item["sha256"],
                    "http_sha256": True,
                    "install": True,
                    "uninstall": True,
                }
            )
    result = {
        "state": "passed",
        "scope": "HTTP bytes and lifecycle only",
        "business_queries": 0,
        "packages": summaries,
    }
    write_json(work / "http-smoke.json", result)
    return result


def capture(directory: Path, config: Path, arguments: list[str]) -> dict:
    """Save private original native bodies and one public inquiry envelope."""
    from dogopencli.cli import main as run
    from dogopencli.transport.cdp import CdpQueryTransport

    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if (
        len(arguments) < 3
        or arguments[0] not in ("payment", "collection", "liquidity", "fx")
        or arguments[1] not in ("list", "get", "refresh")
        or any(a.split("=", 1)[0] in ("--config-dir", "--format") for a in arguments)
    ):
        raise HelperError(
            "Use domain list/get/refresh leaf; config/format are helper-owned."
        )
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    previous = os.umask(0o077)
    original = CdpQueryTransport.execute
    calls = []

    def recorded(self, request, **kwargs):
        response = original(self, request, **kwargs)
        (directory / f"native-{len(calls)}.json").write_bytes(response.body)
        calls.append(
            {
                "method": request.method,
                "path": request.path,
                "body": request.body,
                "status": response.status,
                "encoding": self._capability.contract.encoding,
            }
        )
        return response

    CdpQueryTransport.execute = recorded
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            code = run([*arguments, "--config-dir", str(config), "--format", "json"])
        (directory / "envelope.json").write_text(output.getvalue())
        # Host serialization preserves exact decimals in native request values.
        from dogopencli.jsonutil import canonical

        (directory / "requests.json").write_text(canonical(calls))
        value = parse(output.getvalue())
        if code:
            raise HelperError(
                f"Inquiry failed: {(value.get('error') or {}).get('code')}"
            )
        data, meta = value["data"], value.get("meta") or {}
        return {
            "state": "captured",
            "native_responses": len(calls),
            "rows": len(data) if isinstance(data, list) else None,
            "complete": meta.get("complete"),
            "private_directory": str(directory),
        }
    finally:
        CdpQueryTransport.execute = original
        os.umask(previous)


def select(value: object, pointer: str) -> object:
    if pointer and not pointer.startswith("/"):
        raise HelperError("JSON pointers start with / (empty selects the whole value).")
    for part in pointer.split("/")[1:]:
        if re.search(r"~(?![01])", part):
            raise HelperError("Invalid JSON pointer escape.")
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", part):
                raise HelperError(
                    "Use a canonical nonnegative JSON pointer array index."
                )
            if len(part) > len(str(len(value))) or int(part) >= len(value):
                raise HelperError("JSON pointer array index is out of range.")
            value = value[int(part)]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise HelperError("JSON pointer does not select a value.")
    return value


def typed(value: object) -> object:
    if isinstance(value, dict):
        return ("object", {key: typed(item) for key, item in value.items()})
    if isinstance(value, list):
        return ("array", [typed(item) for item in value])
    return (type(value).__name__, value)


def compare(
    expected: Path, actual: Path, expected_pointer: str, actual_pointer: str
) -> dict:
    left = select(parse(expected.read_text()), expected_pointer)
    right = select(parse(actual.read_text()), actual_pointer)
    if typed(left) != typed(right):
        raise HelperError(
            "JSON values/types/order/multiplicity differ; inspect private inputs."
        )
    return {
        "state": "equal",
        "exact_json_types_values_order": True,
        "rows": len(left) if isinstance(left, list) else None,
    }


def batches(path: Path) -> dict:
    """Check the single current scope map before handing out independent tickets."""
    plan = json.loads(path.read_text())
    identities, labels = set(), set()
    summary = []
    done_packages = done_actions = 0
    for batch in plan["batches"]:
        label, status = batch["id"], batch["status"]
        if (
            not re.fullmatch(r"B[0-9]{2,}", label)
            or label in labels
            or status
            not in (
                "delivered",
                "planned",
                "assigned",
                "blocked",
            )
        ):
            raise HelperError("Duplicate batch ID or invalid batch status.")
        labels.add(label)
        actions = 0
        for member in batch["members"]:
            identity, operations = member["identity"], member["operations"]
            if (
                not re.fullmatch(
                    r"(?:payment|collection|liquidity|fx)\.[a-z][a-z0-9_]*"
                    r"(?:\.[a-z][a-z0-9_]*)*",
                    identity,
                )
                or identity in identities
                or not operations
                or len(operations) != len(set(operations))
                or not set(operations) <= {"list", "get"}
            ):
                raise HelperError("Duplicate leaf or invalid list/get action mapping.")
            identities.add(identity)
            actions += len(operations)
        count = len(batch["members"])
        if status == "delivered":
            done_packages += count
            done_actions += actions
        summary.append(
            {
                "id": label,
                "issue": batch["issue"],
                "status": status,
                "packages": count,
                "actions": actions,
            }
        )
    total_actions = sum(b["actions"] for b in summary)
    if (
        len(identities) != plan["expected_packages"]
        or total_actions != plan["expected_actions"]
    ):
        raise HelperError("Batch mapping does not cover the declared complete scope.")
    return {
        "packages": len(identities),
        "actions": total_actions,
        "delivered_packages": done_packages,
        "delivered_actions": done_actions,
        "remaining_packages": len(identities) - done_packages,
        "remaining_actions": total_actions - done_actions,
        "batches": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    host = commands.add_parser(
        "host-check", help="Reuse a matching installed host; no build."
    )
    host.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    verification = commands.add_parser(
        "verify", help="Statically validate a directory or ZIP."
    )
    verification.add_argument("source", type=Path)
    packaging = commands.add_parser(
        "pack", help="Pack one or more leaves into a new delivery directory."
    )
    packaging.add_argument("sources", type=Path, nargs="+")
    packaging.add_argument("--output", type=Path, required=True)
    http = commands.add_parser(
        "http-smoke", help="Check HTTP bytes and install/uninstall only."
    )
    http.add_argument("--delivery", type=Path, required=True)
    http.add_argument("--base-url", required=True)
    http.add_argument("--work-dir", type=Path, required=True)
    recording = commands.add_parser(
        "capture", help="Capture inquiry evidence privately."
    )
    recording.add_argument("--directory", type=Path, required=True)
    recording.add_argument("--config-dir", type=Path, required=True)
    recording.add_argument("arguments", nargs=argparse.REMAINDER)
    comparison = commands.add_parser(
        "compare", help="Compare exact JSON values and types."
    )
    comparison.add_argument("expected", type=Path)
    comparison.add_argument("actual", type=Path)
    comparison.add_argument("--expected-pointer", default="")
    comparison.add_argument("--actual-pointer", default="")
    listing = commands.add_parser(
        "batches", help="Validate batch scope and list tickets."
    )
    listing.add_argument(
        "--plan", type=Path, default=Path(__file__).with_name("batches.json")
    )
    args = parser.parse_args()
    try:
        if args.action == "host-check":
            result = host_check(args.repo)
        elif args.action == "verify":
            result = verify(args.source)
        elif args.action == "pack":
            result = pack(args.sources, args.output)
        elif args.action == "http-smoke":
            result = http_smoke(args.delivery, args.base_url, args.work_dir)
        elif args.action == "capture":
            result = capture(args.directory, args.config_dir, args.arguments)
        elif args.action == "batches":
            result = batches(args.plan)
        else:
            result = compare(
                args.expected, args.actual, args.expected_pointer, args.actual_pointer
            )
    except (
        HelperError,
        CliError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as error:
        # Transport/OS exceptions can contain URLs or private values; only helper
        # diagnostics are safe for the public summary.
        message = (
            str(error)
            if isinstance(error, HelperError)
            or (args.action in ("verify", "pack") and isinstance(error, CliError))
            else type(error).__name__
        )
        print(
            json.dumps(
                {
                    "state": "failed",
                    "error": getattr(error, "code", "HELPER_FAILED"),
                    "message": message,
                }
            )
        )
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
