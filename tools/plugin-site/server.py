"""Small self-hosted leaf registry; uploaded adapters are never imported."""

import argparse
import fcntl
import hashlib
import hmac
import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "runtime"))

from dogopencli.errors import CliError  # noqa: E402
from dogopencli.leaves.package import MAX_ARCHIVE_BYTES, validate_package  # noqa: E402

VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
PREFIX = "/plugins/"


def publish(source: Path, data: Path, version: str) -> dict:
    """Validate using the host contract and atomically expose an immutable release."""
    if not VERSION.fullmatch(version):
        raise ValueError("版本仅支持 1–64 位字母、数字、点、下划线和连字符")
    data.mkdir(parents=True, exist_ok=True)
    with validate_package(source) as package:
        manifest = package.manifest
        identity = f"{manifest['domain']}.{manifest['name']}"
        destination = data / identity / version
        destination.parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".release-", dir=data) as temporary:
            stage = Path(temporary) / "release"
            stage.mkdir()
            shutil.copyfile(source, stage / "package.zip")
            payload = (stage / "package.zip").read_bytes()
            record = {
                "id": identity,
                "version": version,
                "domain": manifest["domain"],
                "name": manifest["name"],
                "summary": manifest["summary"],
                "operations": list(manifest["operations"]),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "published_at": datetime.now(timezone.utc).isoformat(),
                "validation": "static-only",
                "download": f"{PREFIX}downloads/{identity}/{version}/package.zip",
                "manifest": manifest,
            }
            (stage / "release.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False),
                encoding="utf-8",
            )
            with (data / ".publish.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if destination.exists():
                    raise FileExistsError("此插件版本已存在，请使用新版本")
                stage.rename(destination)
    return record


def catalog(data: Path) -> list[dict]:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        # Dot-prefixed staging trees are not committed releases. Published
        # identities always begin with an ASCII lowercase domain name.
        for path in data.glob("[a-z]*/*/release.json")
    ]
    return sorted(records, key=lambda record: record["published_at"], reverse=True)


def make_server(host: str, port: int, data: Path, token: str = ""):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, *_args):
            # URLs and authentication headers never enter application logs.
            pass

        def respond(self, status: int, payload: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def json(self, status: int, value: object):
            self.respond(
                status,
                json.dumps(value, ensure_ascii=False).encode(),
                "application/json; charset=utf-8",
            )

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == "/plugins":
                self.send_response(308)
                self.send_header("Location", PREFIX)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not path.startswith(PREFIX):
                self.json(404, {"error": "不存在的路径"})
                return
            local = path[len(PREFIX) :]
            if local == "api/catalog":
                self.json(200, {"releases": catalog(data), "publishing": bool(token)})
                return
            if local == "api/health":
                self.json(200, {"status": "ok"})
                return
            if local.startswith("downloads/"):
                parts = local.split("/")
                if (
                    len(parts) == 4
                    and re.fullmatch(r"[a-z][a-z0-9_.]*", parts[1])
                    and VERSION.fullmatch(parts[2])
                    and parts[3] == "package.zip"
                ):
                    target = data / parts[1] / parts[2] / "package.zip"
                else:
                    self.json(404, {"error": "下载不存在"})
                    return
            else:
                relative = {"": "index.html", "docs": "docs.html"}.get(local, local)
                target = (ROOT / "web" / relative).resolve()
                if not target.is_relative_to((ROOT / "web").resolve()):
                    self.json(404, {"error": "不存在的路径"})
                    return
            if not target.is_file():
                self.json(404, {"error": "文件不存在"})
                return
            content_type = (
                mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            )
            if target.suffix in {".html", ".js", ".css", ".md", ".txt"}:
                content_type += "; charset=utf-8"
            self.respond(200, target.read_bytes(), content_type)

        def do_POST(self):
            self.json(405, {"error": "发布请使用 PUT /plugins/api/releases/<version>"})

        def do_PUT(self):
            if not token:
                self.json(503, {"error": "发布未启用，请联系站点管理员"})
                return
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
                self.json(401, {"error": "发布密钥无效"})
                return
            route = urlsplit(self.path).path
            start = PREFIX + "api/releases/"
            version = route.removeprefix(start)
            if not route.startswith(start) or not VERSION.fullmatch(version):
                self.json(400, {"error": "发布路径或版本无效"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if (
                self.headers.get("Transfer-Encoding")
                or not 0 < length <= MAX_ARCHIVE_BYTES
            ):
                self.json(
                    413, {"error": "请提交非空 ZIP，最大 50 MiB，需 Content-Length"}
                )
                return
            try:
                with tempfile.TemporaryDirectory(prefix="plugin-upload-") as temporary:
                    source = Path(temporary) / "upload.zip"
                    with source.open("wb") as output:
                        remaining = length
                        while remaining:
                            chunk = self.rfile.read(min(65536, remaining))
                            if not chunk:
                                raise ValueError("上传中断")
                            output.write(chunk)
                            remaining -= len(chunk)
                    result = publish(source, data, version)
                self.json(201, result)
            except FileExistsError as error:
                self.json(409, {"error": str(error)})
            except (CliError, ValueError) as error:
                message = error.message if isinstance(error, CliError) else str(error)
                self.json(400, {"error": message})
            except (OSError, TimeoutError):
                self.json(500, {"error": "上传或存储失败，请检查服务状态"})

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5910)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=True)
    server = make_server(
        args.host,
        args.port,
        args.data.resolve(),
        os.environ.get("PLUGIN_PUBLISH_TOKEN", ""),
    )
    print(f"Plugin site: http://{args.host}:{server.server_port}{PREFIX}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
