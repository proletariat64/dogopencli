"""Queries must wait for their own target, not rely on a separate auth probe."""

import pytest
from fake_cdp import PAYMENT_URL, SSO_URL, FakeBrowser, FakeSession

from dogopencli.browser import cdp
from dogopencli.errors import CliError
from dogopencli.plugins.collection.cost import COLLECTION_COST_CAPABILITY
from dogopencli.plugins.payment.cost import COST_CAPABILITY
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport


@pytest.fixture(params=[COLLECTION_COST_CAPABILITY, COST_CAPABILITY])
def capability(request):
    return request.param


def request(capability):
    contract = capability.contract
    return QueryRequest(
        capability.name,
        contract.method,
        contract.host,
        contract.path,
        capability.page_body(capability.default_scope, 0, contract.page_size),
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
