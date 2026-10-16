"""Session ownership at the existing fake-CDP boundary, with real file locks."""

import pytest
from fake_cdp import SSO_URL, FakeBrowser

from dogopencli import inquiry
from dogopencli.browser import cdp
from dogopencli.browser.coordination import acquire_browser_control
from dogopencli.browser.errors import AuthError
from dogopencli.errors import CliError
from dogopencli.plugins import get_capability
from dogopencli.plugins.payment.sla import SLA_DETAIL, detail_body
from dogopencli.transport import QueryRequest


@pytest.fixture
def session_setup(tmp_path):
    profile = tmp_path / "profile"
    config = tmp_path / "config.toml"
    config.write_text(f'[auth]\nprofile = "{profile}"\n')
    state = FakeBrowser()
    cdp.set_transport_factory(state.transport)
    yield config, profile, state
    cdp.set_transport_factory(None)


def execute(transport, capability, body):
    contract = capability.contract
    return transport.execute(
        QueryRequest(
            capability.name, contract.method, contract.host, contract.path, body
        )
    )


@pytest.mark.parametrize("failure", [None, "query", "second_transport"])
def test_multiple_transports_release_targets_and_lease(
    session_setup, monkeypatch, failure
):
    config, profile, state = session_setup
    capability = get_capability("payment.sla.baselines.list")
    state.business_handler = lambda payload, index: {"status": 200, "body": {}}
    error = RuntimeError("synthetic failure")

    def run():
        with inquiry.inquiry_session(config_file=config) as session:
            first = session.transport(capability)
            execute(
                first,
                capability,
                capability.page_body(capability.default_scope, 0, 5000),
            )
            if failure == "second_transport":

                def fail(*args, **kwargs):
                    raise error

                monkeypatch.setattr(inquiry, "CdpQueryTransport", fail)
            second = session.transport(SLA_DETAIL)
            execute(second, SLA_DETAIL, detail_body("1"))
            if failure == "query":
                raise error

    if failure:
        with pytest.raises(RuntimeError) as caught:
            run()
        assert caught.value is error
    else:
        run()
    business = state.transports[-1]
    assert len(business.created) == (1 if failure == "second_transport" else 2)
    assert len(business.closed) == len(business.created)
    # An exclusive lease proves the shared lease was released on every exit.
    acquire_browser_control(profile, shared=False).release()
    assert not state.launches


def test_auth_failure_maps_error_and_releases_lease(session_setup):
    config, profile, state = session_setup
    state.href = SSO_URL
    with pytest.raises(CliError) as caught:
        with inquiry.inquiry_session(config_file=config):
            pytest.fail("unauthenticated session was exposed")
    assert caught.value.code == "AUTH_REQUIRED"
    assert not caught.value.retryable
    acquire_browser_control(profile, shared=False).release()
    assert not state.business_requests
    assert not state.launches


@pytest.mark.parametrize(
    "argv",
    [
        ["payment", "refresh", "sla.baselines"],
        ["payment", "list", "sla.baselines", "--live"],
        ["payment", "get", "sla.baselines", "1"],
    ],
)
def test_public_queries_hold_lease_until_fetch_finishes(
    session_setup, monkeypatch, run_cli, argv
):
    config, profile, state = session_setup
    import shutil
    from pathlib import Path

    source = (
        Path(__file__).parents[2] / "src/dogopencli/leaf_packages/payment/sla.baselines"
    )
    shutil.copytree(source, config.parent / "plugins/payment/sla.baselines")
    with config.open("a") as stream:
        for source in ("channel", "cost", "sla"):
            stream.write(f'\n[sources.payment_{source}]\nkind = "cdp"\n')
    # Keep both configuration and failed-refresh SQLite files in the fixture.
    text = config.read_text()
    config.write_text(f'[cache]\npath = "{config.parent / "cache.sqlite3"}"\n' + text)
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    observed = []

    def fetch(payload, index):
        try:
            lease = acquire_browser_control(profile, shared=False)
        except AuthError as error:
            assert error.code == "browser_busy"
            observed.append("held")
        else:
            lease.release()
            pytest.fail("query ran after its session lease was released")
        return {"status": 401, "body": {}}

    state.business_handler = fetch
    code, out, err = run_cli(argv)
    assert code == 1
    assert "AUTH_REQUIRED" in out
    assert observed == ["held"]
    business = state.transports[-1]
    assert len(business.created) == len(business.closed) == 1
    acquire_browser_control(profile, shared=False).release()
