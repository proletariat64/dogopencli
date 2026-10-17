"""Static, bounded portable leaf preparation. Never imports package adapters."""

import http.client
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlsplit

from ..errors import CliError
from .registry import validate_manifest

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_ENTRIES = 1000
DOWNLOAD_TIMEOUT = 60
MAX_REDIRECTS = 5
_CHUNK = 64 * 1024
# ZIP imports compression backends optionally; unavailable codecs must not
# prevent directory or stored-ZIP validation on a minimal Python installation.
_ZIP_CODEC_ERRORS = tuple(
    getattr(codec, error)
    for codec, error in ((zipfile.zlib, "error"), (zipfile.lzma, "LZMAError"))
    if codec is not None
)
_RUNTIME_NAMES = {
    ".env",
    ".git",
    ".aws",
    ".ssh",
    "__pycache__",
    ".venv",
    "venv",
    "config.toml",
    "settings.toml",
    "cookies",
    "cookies.json",
    "credentials",
    "credentials.json",
    "tokens.json",
    "cache",
    "caches",
    "chrome",
    "profile",
    "leaf-cache.sqlite3",
    "duckdog",
    "datasets",
}
_RUNTIME_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".duckdb", ".parquet", ".pyc"}


@dataclass(frozen=True)
class PreparedPackage:
    path: Path
    manifest: dict


def _invalid(message: str) -> CliError:
    return CliError("INVALID_PACKAGE", message)


def _safe_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or "\x00" in name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))
        or re.match(r"^[A-Za-z]:", name)
    ):
        raise _invalid("Package contains an unsafe path")
    if any(
        part.lower() in _RUNTIME_NAMES or part.lower().startswith(".env.")
        for part in path.parts
    ):
        raise _invalid("Package contains runtime configuration or private state")
    if path.suffix.lower() in _RUNTIME_SUFFIXES:
        raise _invalid("Package contains runtime cache or business data")
    if path.name == "leaf.json" and len(path.parts) != 1:
        raise _invalid("Package must contain exactly one leaf at its root")
    return path


def _stream_file(source, destination: Path, remaining: int) -> int:
    copied = 0
    with destination.open("xb") as target:
        while chunk := source.read(min(_CHUNK, remaining - copied + 1)):
            copied += len(chunk)
            if copied > remaining:
                raise _invalid("Package exceeds 100 MiB expanded-content limit")
            target.write(chunk)
    return copied


def _copy_directory(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise _invalid("Package root cannot be a symlink")
    count = size = 0

    def copy(descriptor: int, relative: Path) -> None:
        nonlocal count, size
        with os.scandir(descriptor) as entries:
            for entry in entries:
                count += 1
                if count > MAX_ENTRIES:
                    raise _invalid("Package exceeds 1000-entry limit")
                local = relative / entry.name
                _safe_name(local.as_posix())
                info = entry.stat(follow_symlinks=False)
                target = destination / local
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(
                        entry.name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=descriptor,
                    )
                    try:
                        target.mkdir()
                        copy(child, local)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    child = os.open(
                        entry.name,
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=descriptor,
                    )
                    with os.fdopen(child, "rb") as handle:
                        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                            raise _invalid("Package file changed while copying")
                        size += _stream_file(handle, target, MAX_EXPANDED_BYTES - size)
                else:
                    raise _invalid(
                        "Package entries must be regular files or directories; "
                        "symlinks are forbidden"
                    )

    descriptor = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        copy(descriptor, Path())
    finally:
        os.close(descriptor)


def _extract_archive(source: Path, destination: Path) -> None:
    if source.is_symlink() or source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise _invalid("ZIP must be a local file within 50 MiB archive limit")
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES:
            raise _invalid("Package exceeds 1000-entry limit")
        seen = set()
        size = 0
        for entry in entries:
            path = _safe_name(entry.filename)
            key = path.as_posix()
            if key in seen:
                raise _invalid("ZIP contains duplicate or ambiguous paths")
            seen.add(key)
            mode = entry.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise _invalid(
                    "ZIP entries must be regular files or directories; "
                    "symlinks are forbidden"
                )
            target = destination.joinpath(*path.parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as handle:
                size += _stream_file(handle, target, MAX_EXPANDED_BYTES - size)


def _manifest(root: Path) -> dict:
    path = root / "leaf.json"
    if not path.is_file():
        raise _invalid("Package requires leaf.json directly at its root")
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(value)
    binding = value["adapter"]
    if binding.count(":") != 1:
        raise _invalid("Adapter must bind local-file.py:attribute")
    filename, attribute = binding.split(":")
    if (
        not filename
        or Path(filename).name != filename
        or "\\" in filename
        or Path(filename).suffix != ".py"
        or not attribute.isidentifier()
        or not (root / filename).is_file()
    ):
        raise _invalid(
            "Declared adapter must be a Python file directly at package root"
        )
    return value


def _download_transfer(url: str, destination: Path) -> None:
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT
    try:
        for redirects in range(MAX_REDIRECTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            parsed = urlsplit(url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError
            connection_type = (
                http.client.HTTPSConnection
                if parsed.scheme == "https"
                else http.client.HTTPConnection
            )
            connection = connection_type(
                parsed.hostname, parsed.port, timeout=remaining
            )

            response = None
            try:
                target = parsed.path or "/"
                if parsed.query:
                    target += "?" + parsed.query
                connection.request(
                    "GET", target, headers={"Accept-Encoding": "identity"}
                )
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if redirects == MAX_REDIRECTS or not location:
                        raise ValueError
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise ValueError
                length = response.getheader("Content-Length")
                expected = int(length) if length is not None else None
                if expected is not None and (
                    expected < 0 or expected > MAX_ARCHIVE_BYTES
                ):
                    raise ValueError
                size = 0
                with destination.open("xb") as output:
                    while not response.isclosed():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError
                        # A close-delimited response may detach connection.sock.
                        response.fp.raw._sock.settimeout(remaining)
                        chunk = response.read1(
                            min(_CHUNK, MAX_ARCHIVE_BYTES - size + 1)
                        )
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > MAX_ARCHIVE_BYTES or time.monotonic() > deadline:
                            raise ValueError
                        output.write(chunk)
                if expected is not None and size != expected:
                    raise ValueError
                return
            finally:
                if response is not None:
                    response.close()
                connection.close()
        raise ValueError
    except (OSError, ValueError, http.client.HTTPException, AttributeError):
        raise ValueError("Download failed") from None


def _download(url: str, destination: Path) -> None:
    # A socket timeout cannot bound synchronous DNS. A separate interpreter
    # makes every transfer phase cancellable without forking host threads.
    worker = (
        "import json, sys; "
        "request = json.load(sys.stdin); "
        "sys.path[:] = request['path']; "
        "from dogopencli.leaves import package; "
        "package.MAX_ARCHIVE_BYTES = request['max_bytes']; "
        "package.MAX_REDIRECTS = request['max_redirects']; "
        "package.DOWNLOAD_TIMEOUT = request['timeout']; "
        "package._download_transfer(request['url'], "
        "package.Path(request['destination']))"
    )
    payload = json.dumps(
        {
            "url": url,
            "destination": str(destination),
            "path": sys.path,
            "max_bytes": MAX_ARCHIVE_BYTES,
            "max_redirects": MAX_REDIRECTS,
            "timeout": DOWNLOAD_TIMEOUT,
        }
    )
    try:
        # Secret URLs only cross stdin; child diagnostics never reach logs.
        with subprocess.Popen(
            [sys.executable, "-c", worker],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        ) as process:
            try:
                process.communicate(payload, timeout=DOWNLOAD_TIMEOUT)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
            if process.returncode:
                raise ValueError
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise CliError(
            "DOWNLOAD_FAILED",
            "HTTP ZIP download failed; "
            "check source, transfer limits, redirects or deadline",
        ) from None


@contextmanager
def validate_package(path: Path):
    """Yield an isolated validated snapshot of a local directory or ZIP."""
    with tempfile.TemporaryDirectory(prefix="dogopencli-package-") as temporary:
        root = Path(temporary) / "leaf"
        root.mkdir()
        try:
            path = Path(path)
            if path.is_dir():
                _copy_directory(path, root)
            else:
                _extract_archive(path, root)
            manifest = _manifest(root)
        except CliError:
            raise
        except (
            OSError,
            ValueError,
            TypeError,
            zipfile.BadZipFile,
            RuntimeError,
            RecursionError,
            *_ZIP_CODEC_ERRORS,
        ):
            raise _invalid(
                "Cannot validate package; check root layout, manifest and ZIP integrity"
            ) from None
        yield PreparedPackage(root, manifest)


@contextmanager
def prepare_package(source: str | Path):
    """Prepare local, direct HTTP(S), or explicit bundled leaf sources."""
    value = str(source)
    if value.startswith("bundled:"):
        identity = value.removeprefix("bundled:")
        domain, separator, name = identity.partition(".")
        if (
            not separator
            or not re.fullmatch(r"[a-z][a-z0-9_]*", domain)
            or not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*", name)
        ):
            raise _invalid("Bundled source requires domain.leaf identity")
        resource = resources.files("dogopencli").joinpath("leaf_packages", domain, name)
        with resources.as_file(resource) as path:
            with validate_package(path) as package:
                yield package
    elif value.lower().startswith(("http:", "https:")):
        with tempfile.TemporaryDirectory(prefix="dogopencli-download-") as temporary:
            archive = Path(temporary) / "download.zip"
            _download(value, archive)
            with validate_package(archive) as package:
                yield package
    else:
        with validate_package(Path(source).expanduser()) as package:
            yield package
