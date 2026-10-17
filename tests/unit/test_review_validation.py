"""Negative contract and configuration regressions from the second review."""

from pathlib import Path

import pytest
from synthetic_capability import SAMPLE

from dogopencli import config
from dogopencli.auth.cli import resolve_config_dir
from dogopencli.browser.environment import resolve_environment


def test_configuration_resolution_is_shared(tmp_path, monkeypatch):
    directory = tmp_path / "directory"
    directory.mkdir()
    custom = tmp_path / "custom-name.toml"
    custom.write_text('[auth]\nprofile="/private/custom-profile"\n')
    monkeypatch.delenv("DOGOPENCLI_CONFIG_DIR", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(custom))
    assert config.config_path() == custom
    assert resolve_config_dir(None) == custom.parent
    assert resolve_environment(config_file=config.config_path()).profile == Path(
        "/private/custom-profile"
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(directory))
    assert config.config_path() == directory / "config.toml"
    assert resolve_config_dir(None) == directory
    assert config.config_path(tmp_path) == tmp_path / "config.toml"


def test_dead_cdp_session_is_recreated_on_retry():
    from dogopencli.browser.cdp import CdpError
    from dogopencli.transport import QueryRequest
    from dogopencli.transport.cdp import CdpQueryTransport, FetchFailed

    class Session:
        def __init__(self, dead):
            self.dead = dead
            self.closed = False

        def navigate(self, url, timeout):
            self.url = url

        def evaluate(self, expression, timeout):
            if "fetch(" not in expression:
                return {"ready_state": "complete", "href": self.url}
            if self.dead:
                raise CdpError("socket closed")
            return {"status": 200, "body": "{}"}

        def close(self):
            self.closed = True

    class Browser:
        def __init__(self):
            self.sessions = []
            self.closed_targets = []

        def new_target(self, url, **kwargs):
            return {"id": str(len(self.sessions)), "webSocketDebuggerUrl": "ws://fake"}

        def open_session(self, url, **kwargs):
            session = Session(not self.sessions)
            self.sessions.append(session)
            return session

        def close_target(self, target_id):
            self.closed_targets.append(target_id)

    browser = Browser()
    transport = CdpQueryTransport(browser, SAMPLE, page_url="https://example.invalid")
    contract = SAMPLE.contract
    request = QueryRequest(
        SAMPLE.name,
        contract.method,
        contract.host,
        contract.path,
        SAMPLE.page_body(SAMPLE.default_scope, 0, 5000),
    )
    with pytest.raises(FetchFailed):
        transport.execute(request)
    assert browser.sessions[0].closed
    assert browser.closed_targets == ["0"]
    assert transport.execute(request).status == 200
    assert len(browser.sessions) == 2
    transport.close()


def test_websocket_uses_no_origin_instead_of_wildcard(monkeypatch):
    import websocket

    from dogopencli.browser.cdp import HttpCdpSession

    calls = []
    monkeypatch.setattr(
        websocket, "create_connection", lambda *args, **kwargs: calls.append(kwargs)
    )
    HttpCdpSession("ws://127.0.0.1:9222/fake", timeout=2)
    assert calls == [{"timeout": 2, "suppress_origin": True}]
