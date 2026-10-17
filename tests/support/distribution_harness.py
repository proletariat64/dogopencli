"""Standalone installed-process driver; only the external CDP boundary is fake.

Copied outside the checkout by the artifact acceptance test. This file must not
import repository tests or adapters, nor add a checkout to the import path.
"""

import importlib.abc
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

RETIRED = (
    "plugins",
    "catalog",
    "describe",
    "snapshot",
    "cached_query",
    "handler_contract",
    "annotations",
    "execution",
    "snapshot_cache",
    "table",
    "transport.snapshot",
)


class RejectRetired(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(
            fullname == f"dogopencli.{name}"
            or fullname.startswith(f"dogopencli.{name}.")
            for name in RETIRED
        ):
            raise AssertionError(f"retired import attempted: {fullname}")


sys.meta_path.insert(0, RejectRetired())

from dogopencli.browser import cdp  # noqa: E402

requests = []


class Session:
    def __init__(self, url):
        self.url = url

    def navigate(self, url, timeout):
        self.url = url

    def evaluate(self, expression, timeout):
        if "fetch(" not in expression:
            href = self.url
            if os.environ.get("DISTRIBUTION_AUTH_REQUIRED"):
                href = "https://tonelogin.antglobal-inc.com/ssoLogin.htm"
            return {"ready_state": "complete", "href": href}
        payload = json.loads(expression[expression.rindex("})(") + 3 : -1])
        requests.append(payload)
        response = json.loads(os.environ["DISTRIBUTION_RESPONSE"])
        return {
            "status": response.get("status", 200),
            "body": json.dumps(response["body"]),
            "retryAfter": None,
            "finalUrl": None,
            "redirected": False,
        }

    def close(self):
        pass


class Browser:
    def __init__(self, url):
        self.targets = {}

    def version(self, *, timeout=None):
        return {"Browser": "Chrome/128", "User-Agent": "HeadlessChrome/128"}

    def new_target(self, url, *, timeout=None):
        target = str(len(self.targets))
        self.targets[target] = url
        return {"id": target, "webSocketDebuggerUrl": target}

    def open_session(self, ws_url, *, timeout=None):
        return Session(self.targets[ws_url])

    def close_target(self, target_id):
        pass


def forbidden(*args, **kwargs):
    raise AssertionError("real network or browser process forbidden in artifact proof")


# No real browser or remote socket may escape the scripted CDP seam.
subprocess.Popen = forbidden
socket.socket.connect = forbidden
cdp.set_transport_factory(Browser)


def editor_probe():
    from dogopencli import config
    from dogopencli.domains import DomainService
    from dogopencli.gui import create_server
    from dogopencli.leaves.documentation import DocumentationEditor

    service = DomainService(config.config_path())
    server = create_server(service)
    try:
        editor = DocumentationEditor(config.config_path())
        domain, leaf = sys.argv[2:4]
        loaded = editor.load(domain, leaf)
        preview = editor.preview(domain, leaf, loaded)
        assert leaf in preview["preview"]
        print(
            json.dumps({"manifest": loaded["manifest"], "gui_port": server.server_port})
        )
    finally:
        server.server_close()
    return 0


try:
    if sys.argv[1:] and sys.argv[1] == "__editor__":
        code = editor_probe()
    else:
        from dogopencli.cli import main

        code = main(sys.argv[1:])
finally:
    import dogopencli

    package = Path(dogopencli.__file__).resolve().parent
    assert package.is_relative_to(Path(sys.prefix).resolve()), package
    modules = {}
    for name, module in tuple(sys.modules.items()):
        if name == "dogopencli" or name.startswith("dogopencli."):
            source = getattr(module, "__file__", None)
            if source:
                path = Path(source).resolve()
                assert path.is_relative_to(package), (name, str(path))
                modules[name] = str(path)
    assert "site-packages" in package.parts, package
    Path(os.environ["DISTRIBUTION_REPORT"]).write_text(
        json.dumps({"modules": modules, "requests": requests, "sys_path": sys.path})
    )
sys.exit(code)
