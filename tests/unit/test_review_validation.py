"""Negative contract and configuration regressions from the second review."""

import json
from pathlib import Path

import pytest

from dogopencli import config
from dogopencli.auth.cli import resolve_config_dir
from dogopencli.browser.environment import resolve_environment
from dogopencli.errors import CliError
from dogopencli.plugins.payment.cost import COST_CAPABILITY
from dogopencli.plugins.payment.sla import SLA_CAPABILITY, parse_detail


@pytest.mark.parametrize("capability", [COST_CAPABILITY, SLA_CAPABILITY])
@pytest.mark.parametrize(
    "field,value",
    [("pageNo", "0"), ("pageSize", 0), ("pageSize", -1), ("totalCount", True)],
)
def test_invalid_pagination_is_rejected(capability, field, value):
    data = {
        "success": True,
        "pageNo": 0,
        "pageSize": 5000,
        "totalCount": 0,
        "resultDataList": [],
    }
    data[field] = value
    with pytest.raises(CliError) as caught:
        capability.parse_page(json.dumps(data).encode())
    assert caught.value.code == "INVALID_RESPONSE"


@pytest.mark.parametrize("capability", [COST_CAPABILITY, SLA_CAPABILITY])
def test_page_cannot_exceed_page_size(capability):
    data = {
        "success": True,
        "pageNo": 0,
        "pageSize": 1,
        "totalCount": 2,
        "resultDataList": [{}, {}],
    }
    with pytest.raises(CliError) as caught:
        capability.parse_page(json.dumps(data).encode())
    assert caught.value.code == "INVALID_RESPONSE"


def test_detail_id_mismatch_is_rejected():
    with pytest.raises(CliError) as caught:
        parse_detail(b'{"success":true,"resultData":{"id":"other"}}', "wanted")
    assert caught.value.code == "INVALID_RESPONSE"


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

        def evaluate(self, expression, timeout):
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
    transport = CdpQueryTransport(browser, COST_CAPABILITY, page_url="about:blank")
    contract = COST_CAPABILITY.contract
    request = QueryRequest(
        COST_CAPABILITY.name,
        contract.method,
        contract.host,
        contract.path,
        COST_CAPABILITY.page_body(COST_CAPABILITY.default_scope, 0, 5000),
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
