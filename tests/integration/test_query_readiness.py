"""Queries must wait for their own target, not rely on a separate auth probe."""

import pytest
from fake_cdp import PAYMENT_URL, SSO_URL, FakeBrowser, FakeSession

from dogopencli.browser import cdp
from dogopencli.errors import CliError
from dogopencli.plugins.collection.cost import COLLECTION_COST_CAPABILITY as CAPABILITY
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport


def request():
    contract = CAPABILITY.contract
    return QueryRequest(
        CAPABILITY.name,
        contract.method,
        contract.host,
        contract.path,
        CAPABILITY.page_body(CAPABILITY.default_scope, 0, 1000),
    )


def test_blank_and_loading_target_settles_before_fetch(monkeypatch):
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
        state.transport("unused"), CAPABILITY, page_url=PAYMENT_URL
    )
    try:
        assert transport.execute(request()).status == 200
    finally:
        transport.close()
    assert state.transports[0].navigations == [PAYMENT_URL]
    assert len(state.transports[0].closed) == 1


@pytest.mark.parametrize(
    "url, code",
    [(SSO_URL, "AUTH_REQUIRED"), ("https://other.example/", "INVALID_RESPONSE")],
)
def test_redirect_never_sends_business_request(monkeypatch, url, code):
    state = FakeBrowser(href=url)
    monkeypatch.setattr(cdp.time, "sleep", lambda seconds: None)
    transport = CdpQueryTransport(
        state.transport("unused"), CAPABILITY, page_url=PAYMENT_URL
    )
    try:
        with pytest.raises(CliError) as caught:
            transport.execute(request())
        assert caught.value.code == code
        assert not state.business_requests
    finally:
        transport.close()
    assert len(state.transports[0].closed) == 1
