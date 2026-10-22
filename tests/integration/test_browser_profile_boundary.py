"""Public attach-only routes prove ownership before any real CDP transport IO."""

import json

import pytest
from fake_cdp import PAYMENT_URL, SSO_URL, FakeBrowser

from dogopencli.browser import cdp, launcher
from dogopencli.browser.coordination import acquire_browser_control


@pytest.fixture
def owned_endpoint(tmp_path, monkeypatch, run_cli):
    profile = tmp_path / "chrome"
    config = tmp_path / "config.toml"
    config.write_text(f'[auth]\nprofile="{profile}"\n')
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    browser = FakeBrowser()
    # Keep the production ownership path; replace only actual network IO.
    cdp.set_transport_factory(None)
    monkeypatch.setattr(cdp, "HttpCdpTransport", browser.transport)
    monkeypatch.setattr(
        launcher,
        "_endpoint_process_args",
        lambda port: [["chrome", f"--user-data-dir={profile}"]],
    )
    code, out, _ = run_cli(["plugins", "install", "bundled:payment.sla.baselines"])
    assert code == 0, out
    yield profile, browser
    cdp.set_transport_factory(None)


COMMANDS = (
    ["auth", "check", "--domain", "payment"],
    ["payment", "list", "sla.baselines", "--live"],
    ["payment", "get", "sla.baselines", "native-one"],
    ["payment", "refresh", "sla.baselines"],
)


@pytest.mark.parametrize("argv", COMMANDS)
@pytest.mark.parametrize("ownership", ["missing", "foreign", "multiple"])
def test_public_attachment_rejects_unproven_profile_without_cdp_io(
    owned_endpoint, monkeypatch, run_cli, argv, ownership
):
    profile, browser = owned_endpoint
    owners = {
        "missing": [],
        "foreign": [["chrome", "--user-data-dir=/foreign-profile"]],
        "multiple": [
            ["chrome", f"--user-data-dir={profile}"],
            ["chrome", "--user-data-dir=/other-profile"],
        ],
    }[ownership]
    monkeypatch.setattr(launcher, "_endpoint_process_args", lambda port: owners)
    code, out, _ = run_cli(argv)
    body = json.loads(out)
    assert code == 1, body
    assert body["error"]["code"] == (
        "browser_unavailable" if argv[0] == "auth" else "BROWSER_UNAVAILABLE"
    )
    assert browser.transports == []
    assert browser.business_requests == []
    assert browser.launches == []
    acquire_browser_control(profile, shared=False).release()
    if argv[0] == "auth":
        _, out, _ = run_cli(["domain", "show", "payment"])
        assert json.loads(out)["result"]["auth"]["outcome"] == "failed"


@pytest.mark.parametrize("argv", COMMANDS)
def test_public_attachment_uses_verified_profile_and_releases_its_targets(
    owned_endpoint, run_cli, argv
):
    profile, browser = owned_endpoint
    browser.business_script.append(
        {
            "status": 200,
            "body": (
                {"success": True, "resultData": {"id": "native-one"}}
                if argv[1] == "get"
                else {
                    "success": True,
                    "pageNo": 0,
                    "pageSize": 10000,
                    "totalCount": 1,
                    "resultDataList": [{"id": "native-one"}],
                }
            ),
        }
    )
    code, out, _ = run_cli(argv)
    body = json.loads(out)
    assert code == 0, body
    if argv[0] == "auth":
        assert body["result"]["profile"] == str(profile)
        assert body["result"]["authenticated"] is True
        assert browser.business_requests == []
    else:
        assert len(browser.business_requests) == 1
    assert browser.transports
    assert all(len(t.created) == len(t.closed) for t in browser.transports)
    assert browser.launches == []
    acquire_browser_control(profile, shared=False).release()


def test_blocked_fetch_keeps_bounded_auth_diagnosis_and_does_not_retry_expiry(
    owned_endpoint, run_cli
):
    profile, browser = owned_endpoint
    # Redirect policy reports a fetch error. The independent owned probe still
    # classifies verified expiry, without another business request or login.
    browser.hrefs = [PAYMENT_URL, PAYMENT_URL, SSO_URL]
    browser.business_script.append({"error": "TypeError: fetch failed"})
    code, out, _ = run_cli(["payment", "get", "sla.baselines", "native-one"])
    body = json.loads(out)
    assert code == 1
    assert body["error"]["code"] == "AUTH_REQUIRED"
    assert len(browser.business_requests) == 1
    assert browser.launches == []
    assert all(len(t.created) == len(t.closed) for t in browser.transports)
    acquire_browser_control(profile, shared=False).release()
