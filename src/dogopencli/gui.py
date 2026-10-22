"""Foreground, loopback-only domain controls backed by the shared domain service."""

from __future__ import annotations

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any
from urllib.parse import unquote, urlsplit

from .config import config_path
from .errors import CliError

_PAGE = files("dogopencli").joinpath("gui_page.html").read_text(encoding="utf-8")


def create_server(service: Any, port: int = 0) -> ThreadingHTTPServer:
    """Create a loopback HTTP server; the caller owns its foreground lifecycle."""
    token = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(24)
    page = _PAGE.replace("NONCE", nonce).replace("TOKEN", token).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            # Operational state and local request details do not belong in logs.
            pass

        def send_data(
            self, status: int, data: bytes, content_type: str = "application/json"
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; "
                f"script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
                "form-action 'none'",
            )
            self.end_headers()
            self.wfile.write(data)

        def json_data(self, status: int, data: dict) -> None:
            self.send_data(status, json.dumps(data).encode())

        def error(self, status: int, code: str, message: str) -> None:
            self.json_data(status, {"error": {"code": code, "message": message}})

        def local_request(self, *, mutation: bool = False) -> bool:
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if port == 80:
                hosts.update({"127.0.0.1", "localhost"})
            host = self.headers.get("Host")
            if host not in hosts:
                self.error(403, "INVALID_HOST", "Use the printed localhost URL")
                return False
            origin = self.headers.get("Origin")
            expected_origin = (
                f"http://{host.removesuffix(':80') if port == 80 else host}"
            )
            if origin is not None and origin != expected_origin:
                self.error(403, "INVALID_ORIGIN", "Cross-origin requests are rejected")
                return False
            if mutation and not secrets.compare_digest(
                self.headers.get("X-Dogopencli-Token", "").encode(), token.encode()
            ):
                self.error(403, "INVALID_TOKEN", "Local page token required")
                return False
            return True

        def leaf_resource(self, *, mutation: bool = False) -> bool:
            if not self.path.startswith("/api/leaves/"):
                return False
            parts = [unquote(part) for part in urlsplit(self.path).path.split("/")[3:]]
            if (
                len(parts) != (3 if mutation else 2)
                or any(not part or "/" in part or part in {".", ".."} for part in parts)
                or not hasattr(service, "config_file")
            ):
                self.error(404, "NOT_FOUND", "Unknown leaf resource")
                return True
            from .leaves.documentation import DocumentationEditor

            editor = DocumentationEditor(service.config_file)
            try:
                if not mutation:
                    result = editor.load(*parts)
                else:
                    if parts[2] not in {"preview", "save"}:
                        self.error(404, "NOT_FOUND", "Unknown editor action")
                        return True
                    if self.headers.get("Content-Type") != "application/json":
                        self.error(415, "INVALID_ARGUMENT", "JSON body required")
                        return True
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 524288:
                        raise ValueError
                    payload = json.loads(self.rfile.read(length))
                    result = getattr(editor, parts[2])(*parts[:2], payload)
                self.json_data(200, result)
            except CliError as error:
                status = {
                    "EDIT_CONFLICT": 409,
                    "LEAF_NOT_FOUND": 404,
                    "INVALID_ARGUMENT": 400,
                    "INVALID_MANIFEST": 400,
                    "READ_ONLY_FIELD": 400,
                }.get(error.code, 400)
                self.error(status, error.code, error.message)
            except (ValueError, UnicodeDecodeError):
                self.error(400, "INVALID_ARGUMENT", "Invalid editor payload")
            except OSError:
                self.error(
                    500, "LEAF_DOCUMENT_ERROR", "Cannot access leaf documentation"
                )
            return True

        def do_GET(self) -> None:
            if not self.local_request():
                return
            if self.leaf_resource():
                return
            if self.path == "/":
                self.send_data(200, page, "text/html; charset=utf-8")
            elif self.path == "/api/domains":
                try:
                    self.json_data(200, {"domains": service.overview()})
                except CliError as error:
                    self.error(500, error.code, error.message)
            elif self.path == "/api/system" and hasattr(service, "config_file"):
                from .system_info import read_system_info

                self.json_data(200, {"system": read_system_info(service.config_file)})
            else:
                self.error(404, "NOT_FOUND", "Unknown GUI resource")

        def do_POST(self) -> None:
            if not self.local_request(mutation=True):
                return
            if self.leaf_resource(mutation=True):
                return
            prefix = "/api/domains/"
            domain_id = unquote(self.path[len(prefix) :])
            if (
                not self.path.startswith(prefix)
                or not domain_id
                or "/" in domain_id
                or "?" in domain_id
            ):
                self.error(404, "NOT_FOUND", "Unknown GUI resource")
                return
            if self.headers.get("Content-Type") != "application/json":
                self.error(415, "INVALID_ARGUMENT", "JSON body required")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    raise ValueError
                payload = json.loads(self.rfile.read(length))
                if (
                    not isinstance(payload, dict)
                    or set(payload) != {"enabled"}
                    or not isinstance(payload["enabled"], bool)
                ):
                    raise ValueError
            except (ValueError, UnicodeDecodeError):
                self.error(400, "INVALID_ARGUMENT", "Body must contain enabled boolean")
                return
            try:
                domain = service.set_enabled(domain_id, payload["enabled"])
            except CliError as error:
                status = {
                    "DOMAIN_NOT_FOUND": 404,
                    "INVALID_ARGUMENT": 400,
                }.get(error.code, 500)
                self.error(status, error.code, error.message)
                return
            self.json_data(200, {"domain": domain})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str]) -> int:
    """Run the local control interface until interrupted."""
    parser = argparse.ArgumentParser(prog="dogopencli gui", add_help=False)
    parser.add_argument("--help", "-h", action="store_true")
    from .helpspec import add_options
    from .management import GUI_DECLARATION

    add_options(parser, GUI_DECLARATION.options)
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    if args.help:
        from .command_model import emit_help, resolve

        return emit_help(resolve(["gui", *argv]))
    if not 0 <= args.port <= 65535:
        print(
            json.dumps(
                {
                    "error": {
                        "code": "INVALID_ARGUMENT",
                        "message": "port must be between 0 and 65535",
                    }
                }
            )
        )
        return 2
    # Delayed import keeps help available without initializing domain state.
    from .domains import DomainService

    try:
        service = DomainService(config_file=config_path(args.config_dir))
        service.inventory()  # Reject unreadable state before advertising a ready GUI.
        server = create_server(service, args.port)
    except CliError as error:
        print(json.dumps({"error": {"code": error.code, "message": error.message}}))
        return error.exit_code
    except OSError:
        print(
            json.dumps(
                {
                    "error": {
                        "code": "GUI_UNAVAILABLE",
                        "message": "Cannot bind localhost GUI port",
                    }
                }
            )
        )
        return 1
    print(f"http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
