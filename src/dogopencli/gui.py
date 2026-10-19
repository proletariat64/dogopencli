"""Foreground, loopback-only domain controls backed by the shared domain service."""

from __future__ import annotations

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit

from .config import config_path
from .errors import CliError

_PAGE = """<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dogopencli domains</title>
<style nonce="NONCE">:root{color-scheme:light;font:18px system-ui;
background:#f3f5f8;color:#17202a}*{box-sizing:border-box}
body{margin:0;padding:12px;min-height:100vh;background:#f3f5f8;color:#17202a}
button,input,textarea{font:inherit}button{cursor:pointer}
#page-header{display:flex;align-items:center;justify-content:space-between;
margin:0 0 10px}#page-header h1{margin:0;font-size:24px}
#page-header small{color:#64707c;font-size:14px}
#error:empty{display:none}.error{color:#a21616;margin:0 0 10px}
#domains{display:grid;grid-template-rows:repeat(2,auto);grid-auto-flow:column;
grid-auto-columns:minmax(300px,1fr);gap:12px;overflow-x:auto;padding-bottom:4px}
.domain-card,#editor{background:#fff;border:1px solid #d9e0e6;border-radius:12px;
padding:14px;box-shadow:0 1px 3px rgba(20,30,40,.05)}
.domain-card{min-width:300px}.domain-header{display:flex;align-items:center;
justify-content:space-between;gap:10px}.domain-card h2{margin:0;font-size:20px}
.domain-state{flex:none;border-radius:999px;padding:3px 8px;background:#e6f4ec;
color:#146c43;font-size:13px;font-weight:600}.domain-state.disabled{background:#edf0f2;color:#596673}
.auth{margin:8px 0;color:#596673;font-size:16px}.leaves{border-top:1px solid #e8ecef;
padding-top:6px}.leaves h3{margin:0 0 2px;color:#75808b;font-size:12px;
letter-spacing:.04em;text-transform:uppercase}.leaf-list{list-style:none;margin:0;padding:0}
.leaf{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;
gap:8px;padding:5px 0;font-size:16px}.leaf-outcome{color:#64707c;\
font-size:14px;white-space:nowrap}
.leaf-docs,.domain-toggle{border:1px solid #cbd4dc;border-radius:7px;\
background:#fff;color:#263645}
.leaf-docs{padding:3px 8px;font-size:13px}.domain-toggle{width:100%;margin-top:8px;
padding:7px 10px;font-size:15px}.diagnostic{margin:8px 0 0;\
padding:8px;border-radius:8px;
background:#fff4e5;color:#8a4b08;font-size:14px}small{color:#465565}
#editor{margin:12px 0}#editor h2{margin-top:0}#editor label{display:block;\
margin:.6rem 0}
#editor input,#editor textarea{display:block;width:95%;padding:.4rem}
#editor fieldset{margin:.6rem 0;border:1px solid #dce1e6}#editor pre{\
white-space:pre-wrap}</style>
<header id="page-header"><h1>Domains</h1><small id="domain-count"></small></header>
<p id="error" class="error" role="alert"></p><main id="domains" aria-live="polite">\
</main>
<article id="editor" hidden><h2 id="editor-title">Leaf documentation</h2>
<p>Technical declarations are read-only. Save applies on the next CLI invocation.</p>
<form id="documentation-form"></form><button id="preview" type="button">Preview</button>
<button id="save" type="button">Save</button>
<button id="reload" type="button">Reload</button>
<p id="editor-status" role="status"></p><pre id="documentation-preview"></pre></article>
<script nonce="NONCE">
const token='TOKEN';
const root=document.getElementById('domains');
const error=document.getElementById('error');
const count=document.getElementById('domain-count');
function text(parent,tag,value){const item=document.createElement(tag);
item.textContent=value;parent.append(item);return item;}
function readable(value){const label=String(value||'unknown').replaceAll('_',' ');
return label.charAt(0).toUpperCase()+label.slice(1);}
function leafName(domain,leaf){if(leaf.name)return leaf.name;
const prefix=domain.id+'.';return leaf.id.startsWith(prefix)?
leaf.id.slice(prefix.length):leaf.id;}
async function request(path,options){const response=await fetch(path,options);
const data=await response.json();if(!response.ok){
throw new Error(data.error?.message||'Request failed');}return data;}
async function load(){try{const data=await request('/api/domains');
count.textContent=data.domains.length+' registered';root.replaceChildren();
for(const domain of data.domains){
const card=document.createElement('article');card.className='domain-card';\
root.append(card);
const header=document.createElement('div');header.className='domain-header';\
card.append(header);
text(header,'h2',domain.id);
const state=text(header,'span',domain.enabled?'Enabled':'Disabled');
state.className='domain-state '+(domain.enabled?'enabled':'disabled');
const auth=domain.auth||{};const authText=text(card,'p',readable(auth.outcome));
authText.className='auth';
const leaves=document.createElement('section');leaves.className='leaves';\
card.append(leaves);
text(leaves,'h3','Leaves');const list=document.createElement('ul');
list.className='leaf-list';leaves.append(list);for(const leaf of domain.leaves){
const last=leaf.last_execution||{};const entry=document.createElement('li');
entry.className='leaf';list.append(entry);text(entry,'span',leafName(domain,leaf));
const outcome=text(entry,'span',readable(last.outcome));\
outcome.className='leaf-outcome';
if(!leaf.diagnostic){const name=leafName(domain,leaf);
const edit=text(entry,'button','Docs');edit.className='leaf-docs';edit.type='button';
edit.setAttribute('aria-label','Edit documentation for '+name);
edit.onclick=()=>openEditor(domain.id,name);}}
if(!domain.leaves.length)text(leaves,'small','No registered leaves');
for(const diagnostic of domain.diagnostics||[]){
const message=text(card,'p',diagnostic.id+': '+diagnostic.code+' — '+\
diagnostic.message);
message.className='diagnostic';}
const button=text(card,'button',domain.enabled?'Disable':'Enable');
button.className='domain-toggle';button.type='button';button.setAttribute('aria-label',
(domain.enabled?'Disable ':'Enable ')+domain.id);
button.onclick=async()=>{button.disabled=true;error.textContent='';try{
await request('/api/domains/'+encodeURIComponent(domain.id),{method:'POST',
headers:{'Content-Type':'application/json','X-Dogopencli-Token':token},
body:JSON.stringify({enabled:!domain.enabled})});await load();
}catch(problem){error.textContent='Save failed: '+problem.message;
button.disabled=false;}}}}
catch(problem){error.textContent='Unable to load domains: '+problem.message;}}
let editing=null;
let editorGeneration=0;
let editorBusy=false;
const editor=document.getElementById('editor');
const form=document.getElementById('documentation-form');
const status=document.getElementById('editor-status');
function emptyValue(schema){if(schema.type==='object'){
const value={};for(const key of schema.required||[]){
value[key]=emptyValue(schema.properties?.[key]||{});}return value;}
if(schema.type==='array')return [];if(schema.type==='boolean')return false;
return '';}
function renderInput(parent,value,schema,path,change,inherited=true){
const locked=schema.readOnly??inherited;
if(value!==null&&typeof value==='object'){
const group=document.createElement('fieldset');parent.append(group);
text(group,'legend',path);
if(Array.isArray(value)){
value.forEach((item,index)=>{const row=document.createElement('div');group.append(row);
renderInput(row,item,schema.items||{},path+' '+(index+1),
next=>{value[index]=next;},locked);
if(!locked){const remove=text(row,'button','Remove '+path+' '+(index+1));
remove.type='button';remove.onclick=()=>{value.splice(index,1);drawForm();};}});
if(!locked){const add=text(group,'button','Add '+path);add.type='button';
add.onclick=()=>{value.push(emptyValue(schema.items||{}));drawForm();};}
}else{for(const [key,definition] of Object.entries(schema.properties||{})){
if(!(key in value)&&definition.readOnly===false&&definition.type==='string'){
value[key]='';}}
for(const [key,item] of Object.entries(value)){
renderInput(group,item,schema.properties?.[key]||{},path+'.'+key,
next=>{value[key]=next;},locked);}}
return;}
const label=text(parent,'label',path+(locked?' (read-only)':''));
const input=document.createElement(typeof value==='string'&&!locked?'textarea':'input');
label.append(input);input.setAttribute('aria-label',path);
if(typeof value==='boolean'){input.type='checkbox';input.checked=value;
input.disabled=locked;
input.onchange=()=>change(input.checked);}else{input.value=editing.number_labels?.[path]??value??'';input.readOnly=locked;
input.oninput=()=>change(input.value);}}
function drawForm(){form.replaceChildren();const manifest=editing.manifest;
for(const [key,value] of Object.entries(manifest)){
renderInput(form,value,editing.schema.properties?.[key]||{},key,
next=>{manifest[key]=next;});}}
async function openEditor(domain,name){if(editorBusy)return;
const generation=++editorGeneration;error.textContent='';try{
const path='/api/leaves/'+encodeURIComponent(domain)+'/'+encodeURIComponent(name);
const loaded=await request(path);if(generation!==editorGeneration)return;
editing={...loaded,path,domain,name};editor.hidden=false;
document.getElementById('editor-title').textContent=domain+'.'+name+' documentation';
status.textContent='';drawForm();
document.getElementById('documentation-preview').textContent=editing.preview;
}catch(problem){error.textContent='Cannot load documentation: '+problem.message;}}
function documentationPatch(manifest){const result={};
for(const key of ['summary','purpose','identity_description','limitations','examples']){
if(key in manifest)result[key]=manifest[key];}
result.operations={};for(const [name,operation] of Object.entries(manifest.operations)){
result.operations[name]={description:operation.description,
parameters:(operation.parameters||[]).map(parameter=>({description:parameter.description}))};}
result.fields=manifest.fields.map(field=>({meaning:field.meaning,
...(field.unit!==undefined?{unit:field.unit}:{})}));return result;}
async function editorAction(action){if(!editing||editorBusy)return;
const active=editing;++editorGeneration;editorBusy=true;status.textContent='';
for(const item of editor.querySelectorAll('input,textarea,button'))item.disabled=true;
try{
const result=await request(active.path+'/'+action,{method:'POST',
headers:{'Content-Type':'application/json','X-Dogopencli-Token':token},
body:JSON.stringify({documentation:documentationPatch(active.manifest),
revision:active.revision})});
if(editing!==active)return;
document.getElementById('documentation-preview').textContent=result.preview;
if(action==='save'){editing={...editing,...result};drawForm();
status.textContent='Saved. Changes apply on the next CLI invocation.';}
else status.textContent='Preview only; not saved.';
}catch(problem){status.textContent='Unable to '+action+': '+problem.message;}
finally{editorBusy=false;drawForm();
for(const button of editor.querySelectorAll('button'))button.disabled=false;}}
document.getElementById('preview').onclick=()=>editorAction('preview');
document.getElementById('save').onclick=()=>editorAction('save');
document.getElementById('reload').onclick=()=>editing&&openEditor(editing.domain,editing.name);
form.onsubmit=event=>event.preventDefault();
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
                    self.json_data(200, {"domains": service.inventory()})
                except CliError as error:
                    self.error(500, error.code, error.message)
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
