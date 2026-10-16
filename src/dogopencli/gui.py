"""Foreground, loopback-only domain controls backed by the shared domain service."""

from __future__ import annotations

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote

from .config import config_path
from .errors import CliError

_PAGE = """<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dogopencli domains</title>
<style nonce="NONCE">body{font:16px system-ui;max-width:900px;margin:3rem auto;
padding:0 1rem;background:#f7f8fa;color:#17202a}article{background:white;
border:1px solid #dce1e6;border-radius:8px;padding:1rem;margin:1rem 0}
button{padding:.5rem 1rem;cursor:pointer}li{margin:.4rem 0}
.error{color:#a21616}small{color:#465565}h2{margin-top:0}</style>
<h1>Domains</h1><p>Local execution settings and recorded status.</p>
<p id="error" class="error" role="alert"></p><main id="domains"></main>
<script nonce="NONCE">
const token='TOKEN';
const root=document.getElementById('domains');
const error=document.getElementById('error');
function text(parent,tag,value){const item=document.createElement(tag);
item.textContent=value;parent.append(item);return item;}
async function request(path,options){const response=await fetch(path,options);
const data=await response.json();if(!response.ok){
throw new Error(data.error?.message||'Request failed');}return data;}
async function load(){try{const data=await request('/api/domains');
root.replaceChildren();for(const domain of data.domains){
const card=document.createElement('article');root.append(card);
text(card,'h2',domain.id);text(card,'p',domain.entry_point);
text(card,'p',domain.enabled?'Enabled':'Disabled');
const auth=domain.auth||{};
text(card,'p','Auth: '+(auth.outcome||'unknown')+
(auth.updated_at?' — '+auth.updated_at:''));
const button=text(card,'button',domain.enabled?'Disable':'Enable');
button.type='button';button.setAttribute('aria-label',
(domain.enabled?'Disable ':'Enable ')+domain.id);
button.onclick=async()=>{button.disabled=true;error.textContent='';try{
await request('/api/domains/'+encodeURIComponent(domain.id),{method:'POST',
headers:{'Content-Type':'application/json','X-Dogopencli-Token':token},
body:JSON.stringify({enabled:!domain.enabled})});await load();
}catch(problem){error.textContent='Save failed: '+problem.message;
button.disabled=false;}};
text(card,'h3','Registered leaves');const list=document.createElement('ul');
card.append(list);for(const leaf of domain.leaves){
const last=leaf.last_execution||{};text(list,'li',leaf.id+' — '+
(leaf.enabled?'enabled':'disabled')+' — '+(last.outcome||'unknown')+
(last.updated_at?' — '+last.updated_at:''));}
if(!domain.leaves.length)text(card,'small','No registered leaves');
}}catch(problem){error.textContent='Unable to load domains: '+problem.message;}}
load();
</script></html>"""


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

        def do_GET(self) -> None:
            if not self.local_request():
                return
            if self.path == "/":
                self.send_data(200, page, "text/html; charset=utf-8")
            elif self.path == "/api/domains":
                try:
                    self.json_data(200, {"domains": service.inventory()})
                except CliError as error:
                    self.error(500, error.code, error.message)
            else:
                self.error(404, "NOT_FOUND", "Unknown GUI resource")

        def do_POST(self) -> None:
            if not self.local_request(mutation=True):
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
    parser.add_argument("--config-dir")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    if args.help:
        from .management import GUI_DECLARATION

        description = {
            "help_version": 1,
            "command": "dogopencli gui",
            "summary": "Run foreground localhost domain controls; Ctrl+C stops server",
            "effects": dict(GUI_DECLARATION.effects),
            "constraints": list(GUI_DECLARATION.constraints),
            "options": [
                {
                    "name": "--config-dir",
                    "description": "Shared configuration directory",
                },
                {
                    "name": "--port",
                    "description": "Loopback port; 0 chooses available port",
                },
                {
                    "name": "--format",
                    "description": "Help output: json (default) or text",
                },
            ],
            "children": [],
        }
        if args.format == "json":
            print(json.dumps(description))
        else:
            print(description["command"] + " — " + description["summary"])
            print("Effects: " + str(description["effects"]))
            for constraint in description["constraints"]:
                print(constraint)
            for option in description["options"]:
                print(option["name"] + "  " + option["description"])
        return 0
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
