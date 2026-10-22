"""Remaining budget applies to each request and successful responses."""

import pytest
from synthetic_capability import SAMPLE, SCOPE

from dogopencli import collect
from dogopencli.errors import CliError
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
        collect.execute_bounded(
            SAMPLE, Transport(), SAMPLE.page_body(SCOPE, 0, 5000), deadline=1
        )
    assert error.value.code == "TIMEOUT"
    assert observed == [1.0]


def test_cdp_setup_and_fetch_receive_remaining_budget(monkeypatch):
    from dogopencli.browser import cdp as browser_cdp
    from dogopencli.transport import QueryRequest
    from dogopencli.transport import cdp as transport_mod

    # The budget arithmetic below is asserted against the production poll
    # interval; pin it against the shared test shrink.
    monkeypatch.setattr(browser_cdp, "POLL_INTERVAL_SECONDS", 0.25)
    clock = [0.0]
    monkeypatch.setattr(transport_mod.time, "monotonic", lambda: clock[0])
    observed = []
    monkeypatch.setattr(
        transport_mod.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    class Session:
        def navigate(self, url, timeout):
            observed.append(("navigate", timeout))
            clock[0] += 0.125

        def evaluate(self, expression, timeout):
            if "fetch(" not in expression:
                observed.append(("ready", timeout))
                return {"ready_state": "complete", "href": "https://example.invalid"}
            observed.append(("fetch", timeout))
            assert "controller.abort(), 375" in expression
            return {"status": 200, "body": "{}"}

    class Browser:
        def new_target(self, url, *, timeout):
            observed.append(("target", timeout))
            clock[0] += 0.125
            return {"id": "fake", "webSocketDebuggerUrl": "ws://fake"}

        def open_session(self, url, *, timeout):
            observed.append(("session", timeout))
            clock[0] += 0.125
            return Session()

    transport = transport_mod.CdpQueryTransport(
        Browser(), SAMPLE, page_url="https://example.invalid"
    )
    contract = SAMPLE.contract
    request = QueryRequest(
        SAMPLE.name,
        contract.method,
        contract.host,
        contract.path,
        SAMPLE.page_body(SCOPE, 0, 5000),
    )
    transport.execute(request, timeout=1.0)
    assert observed == [
        ("target", 1.0),
        ("session", 0.875),
        ("navigate", 0.75),
        ("ready", 0.625),
        ("ready", 0.375),
        ("fetch", 0.375),
    ]
