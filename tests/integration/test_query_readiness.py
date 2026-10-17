"""Queries must wait for their own target, not rely on a separate auth probe."""

from types import SimpleNamespace

import pytest
from fake_cdp import PAYMENT_URL, SSO_URL, FakeBrowser, FakeSession

from dogopencli.browser import cdp
from dogopencli.contracts import EndpointContract
from dogopencli.errors import CliError
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport


@pytest.fixture
def capability():
    return SimpleNamespace(
        name="sample.rows",
        contract=EndpointContract(
            "POST",
            "example.test",
            "/inquiry",
            50,
            False,
            frozenset({"pageNo", "pageSize"}),
        ),
    )


def request(capability):
    contract = capability.contract
    return QueryRequest(
        capability.name,
        contract.method,
        contract.host,
        contract.path,
        {"pageNo": 0, "pageSize": contract.page_size},
    )


def test_blank_and_loading_target_settles_before_fetch(monkeypatch, capability):
    state = FakeBrowser()
    state.business_script.append({"status": 200, "body": {}})
    states = iter(
        [
            {"ready_state": "complete", "href": "about:blank"},
            {"ready_state": "loading", "href": PAYMENT_URL},
            {"ready_state": "interactive", "href": PAYMENT_URL},
            {"ready_state": "complete", "href": PAYMENT_URL},
        ]
    )
    reads = []
    original = FakeSession.evaluate

    def evaluate(self, expression, timeout):
        if "fetch(" in expression:
            assert len(reads) == 4, "fetch ran before this target was ready"
            return original(self, expression, timeout)
        result = next(states)
        reads.append(result)
        return result

    monkeypatch.setattr(FakeSession, "evaluate", evaluate)
    monkeypatch.setattr(cdp.time, "sleep", lambda seconds: None)
    transport = CdpQueryTransport(
        state.transport("unused"), capability, page_url=PAYMENT_URL
    )
    try:
        assert transport.execute(request(capability)).status == 200
    finally:
        transport.close()
    assert state.transports[0].navigations == [PAYMENT_URL]
    assert len(state.transports[0].closed) == 1


@pytest.mark.parametrize(
    "url, code",
    [(SSO_URL, "AUTH_REQUIRED"), ("https://other.example/", "INVALID_RESPONSE")],
)
def test_redirect_never_sends_business_request(monkeypatch, url, code, capability):
    state = FakeBrowser(href=url)
    monkeypatch.setattr(cdp.time, "sleep", lambda seconds: None)
    transport = CdpQueryTransport(
        state.transport("unused"), capability, page_url=PAYMENT_URL
    )
    try:
        with pytest.raises(CliError) as caught:
            transport.execute(request(capability))
        assert caught.value.code == code
        assert not state.business_requests
    finally:
        transport.close()
    assert len(state.transports[0].closed) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"host": "evil.example"},
        {"path": "/save"},
        {"method": "GET"},
        {"capability": "sample.other"},
        {"body": {"pageNo": 0, "pageSize": 50, "approve": True}},
    ],
)
def test_allowlist_rejects_before_creating_browser_target(capability, changes):
    from dataclasses import replace

    state = FakeBrowser()
    transport = CdpQueryTransport(
        state.transport("unused"), capability, page_url=PAYMENT_URL
    )
    try:
        with pytest.raises(CliError) as caught:
            transport.execute(replace(request(capability), **changes))
        assert caught.value.code == "REQUEST_NOT_ALLOWED"
        assert not state.business_requests
        assert not state.transports[0].created
    finally:
        transport.close()
