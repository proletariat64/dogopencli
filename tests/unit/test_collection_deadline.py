"""Remaining budget applies to each request and successful responses."""

import pytest

from dogopencli import collect
from dogopencli.errors import CliError
from dogopencli.plugins.payment.cost import COST_CAPABILITY, COST_TYPE
from dogopencli.transport import TransportResponse
from dogopencli.transport.cdp import ORIGIN_CDP


def test_deadline_is_passed_and_late_success_rejected(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(collect, "_monotonic", lambda: clock[0])
    observed = []

    class Transport:
        def execute(self, request, *, timeout):
            observed.append(timeout)
            clock[0] += 60
            return TransportResponse(200, b"{}", ORIGIN_CDP)

    with pytest.raises(CliError) as error:
        collect.collect_scope(COST_CAPABILITY, Transport(), COST_TYPE, budget_seconds=1)
    assert error.value.code == "TIMEOUT"
    assert observed == [1.0]


def test_cdp_setup_and_fetch_receive_remaining_budget(monkeypatch):
    from dogopencli.transport import QueryRequest
    from dogopencli.transport import cdp as transport_mod

    clock = [0.0]
    monkeypatch.setattr(transport_mod.time, "monotonic", lambda: clock[0])
    observed = []

    class Session:
        def evaluate(self, expression, timeout):
            observed.append(("fetch", timeout))
            assert "controller.abort(), 300" in expression
            return {"status": 200, "body": "{}"}

    class Browser:
        def new_target(self, url, *, timeout):
            observed.append(("target", timeout))
            clock[0] += 0.1
            return {"id": "fake", "webSocketDebuggerUrl": "ws://fake"}

        def open_session(self, url, *, timeout):
            observed.append(("session", timeout))
            clock[0] += 0.1
            return Session()

    transport = transport_mod.CdpQueryTransport(
        Browser(), COST_CAPABILITY, page_url="https://example.invalid"
    )
    contract = COST_CAPABILITY.contract
    request = QueryRequest(
        COST_CAPABILITY.name,
        contract.method,
        contract.host,
        contract.path,
        COST_CAPABILITY.page_body(COST_TYPE, 0, 5000),
    )
    transport.execute(request, timeout=0.5)
    assert observed == [("target", 0.5), ("session", 0.4), ("fetch", 0.3)]
