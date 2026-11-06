"""Update or remove only the uv tool environment running this command."""

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from importlib.metadata import version as installed_version
from pathlib import Path

from .helpspec import NO_EFFECTS, BizNode, opt

MARKER = ".dogopencli-release"
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
BASE = re.compile(
    r"https://(?:github\.com|code\.alipay\.com)/"
    r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*/releases/download/v"
    r"(\d+\.\d+\.\d+)\Z"
)
DECLARATIONS = (
    BizNode(
        ("update",),
        "Update this uv-installed CLI; retain configuration, plugins and data.",
        handler="update",
        options=(
            opt("to", "Exact release version, e.g. 0.6.5 (same release provider)."),
            opt("source", "Explicit checkout, wheel path or HTTPS wheel URL."),
        ),
        effects={**NO_EFFECTS, "mutates": True, "network": True},
        constraints=("Exactly one of --to or --source is required.",),
    ),
    BizNode(
        ("uninstall",),
        "Remove this uv-installed CLI; retain configuration, plugins and data.",
        handler="uninstall",
        effects={**NO_EFFECTS, "mutates": True},
    ),
)


def uv_command(*args: str) -> str:
    uv = shutil.which("uv")
    if not uv:
        raise ValueError("uv is required to manage this installation")
    result = subprocess.run(
        [uv, *args], capture_output=True, text=True, timeout=600, check=False
    )
    if result.returncode:
        raise ValueError("uv operation failed; installation was not confirmed")
    return result.stdout.strip()


def locate() -> Path:
    environment = Path(sys.prefix).resolve()
    expected = Path(uv_command("tool", "dir")) / "dogopencli"
    if (
        expected.is_symlink()
        or environment != expected.resolve()
        or not (environment / "uv-receipt.toml").is_file()
        or not Path(__file__).resolve().is_relative_to(environment)
    ):
        raise ValueError(
            "Run the uv-installed dogopencli; source/venv installs are not managed"
        )
    return environment


class HTTPSOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise ValueError("Release downloads must remain HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url: str, maximum: int) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("Release downloads require HTTPS")
    with urllib.request.build_opener(HTTPSOnly).open(url, timeout=60) as response:
        body = response.read(maximum + 1)
    if len(body) > maximum:
        raise ValueError("Release download exceeds size limit")
    return body


def update(environment: Path, *, to: str | None, source: str | None) -> None:
    if bool(to) == bool(source):
        raise ValueError("Specify exactly one of --to or --source")
    marker = environment / MARKER
    if source:
        if source.startswith("https://"):
            selected = source
        else:
            local = Path(source).resolve()
            if not (local.is_dir() and (local / "pyproject.toml").is_file()) and not (
                local.is_file() and local.suffix == ".whl"
            ):
                raise ValueError("Source must be a checkout, wheel or HTTPS wheel URL")
            selected = str(local)
        uv_command(
            "tool",
            "install",
            "--force",
            "--reinstall-package",
            "dogopencli",
            "--python",
            "3.12",
            f"dogopencli @ {selected}",
        )
        marker.unlink(missing_ok=True)
        return
    if not VERSION.fullmatch(to or ""):
        raise ValueError("--to requires MAJOR.MINOR.PATCH")
    current = installed_version("dogopencli")
    if not VERSION.fullmatch(current) or tuple(map(int, to.split("."))) < tuple(
        map(int, current.split("."))
    ):
        raise ValueError("Downgrades are not supported")
    if marker.is_symlink() or not marker.is_file():
        raise ValueError(
            "This install has no release origin; use --source or the release installer"
        )
    origin = marker.read_text().strip()
    if not BASE.fullmatch(origin):
        raise ValueError("Invalid installation release origin")
    base = origin.rsplit("/", 1)[0] + "/v" + to
    wheel = f"dogopencli-{to}-py3-none-any.whl"
    sums = download(base + "/SHA256SUMS", 65536).decode("utf-8")
    matches = re.findall(r"(?m)^([0-9a-f]{64})  " + re.escape(wheel) + r"$", sums)
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous wheel checksum")
    body = download(base + "/" + wheel, 128 * 1024 * 1024)
    if hashlib.sha256(body).hexdigest() != matches[0]:
        raise ValueError("Wheel checksum mismatch; installed program retained")
    with tempfile.TemporaryDirectory(prefix="dogopencli-update-") as directory:
        package = Path(directory) / wheel
        package.write_bytes(body)
        uv_command(
            "tool",
            "install",
            "--force",
            "--reinstall-package",
            "dogopencli",
            "--python",
            "3.12",
            f"dogopencli @ {package}",
        )
    marker.write_text(base + "\n")


def execute(action: str, args) -> int:
    # Import output code before uv can remove the environment containing it.
    from .leaves.cli import emit

    try:
        environment = locate()
        if action == "uninstall":
            uv_command("tool", "uninstall", "dogopencli")
        else:
            update(environment, to=args.to, source=args.source)
        emit(
            {"action": action, "status": "complete", "data_preserved": True},
            output_format=args.format,
        )
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        # No provider bodies, credential-bearing URLs or tokens in error output.
        emit(
            None,
            error={
                "code": "LIFECYCLE_FAILED",
                "message": (
                    "Operation failed. Use a uv tool installation and valid "
                    "source/release; check uv and download access."
                ),
            },
            output_format=args.format,
        )
        return 1
