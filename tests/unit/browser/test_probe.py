"""Unit tests for the bounded probe primitives and verdict classification."""

import pytest

from dogopencli.browser import cdp
from dogopencli.browser.environment import BrowserEnvironment
from dogopencli.browser.probe import (
    SSO_LOGIN_ORIGIN,
    browser_mode,
    check_authentication,
)

PAYMENT_URL = (
    "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
)
IPAYBUSERVICE_LOGIN_URL = (
    "https://ipaybuservice.alipay.com/login.htm?appName=ifundcontrolprodops"
)


class _Session(cdp.CdpSession):
    def __init__(self, transport):
        self._transport = transport

    def evaluate(self, expression, timeout):
        self._transport.evaluations += 1
        flip = self._transport.href_flip
        if flip is not None and self._transport.evaluations > flip[0]:
            # Scripted late JS redirect after ``flip[0]`` probe evaluations.
            self._transport.href = flip[1]
        return {
            "ready_state": self._transport.ready_state,
            "href": self._transport.href,
        }

    def navigate(self, url, timeout):
        pass

    def close(self):
        pass


class _Transport(cdp.CdpTransport):
    def __init__(
        self,
        *,
        reachable=True,
        href=PAYMENT_URL,
        ready_state="complete",
        href_flip=None,
    ):
        self.reachable = reachable
        self.href = href
        self.ready_state = ready_state
        self.href_flip = href_flip
        self.evaluations = 0

    def version(self):
        if not self.reachable:
            raise cdp.CdpError("connection refused")
        return {"Browser": "Chrome/128.0.0.0", "User-Agent": "HeadlessChrome/128"}

    def new_target(self, url, *, timeout=None):
        if not self.reachable:
            raise cdp.CdpError("connection refused")
        return {"id": "t1", "webSocketDebuggerUrl": "ws://fake/t1"}

    def close_target(self, target_id):
        pass

    def open_session(self, ws_url, *, timeout=None):
        return _Session(self)


@pytest.fixture
def environment(tmp_path):
    return BrowserEnvironment(
        cdp_url="http://127.0.0.1:9222",
        profile=tmp_path / "chrome",
        startup_url=PAYMENT_URL,
        chrome_bin="google-chrome",
        log_path=tmp_path / "chrome.log",
    )


@pytest.fixture
def install_transport():
    def install(transport):
        cdp.set_transport_factory(lambda url: transport)

    yield install
    cdp.set_transport_factory(None)


def test_url_origin():
    assert cdp.url_origin(PAYMENT_URL) == "https://ifundcontrol.alipay.com"
    assert cdp.url_origin("http://127.0.0.1:9222/json/list") == "http://127.0.0.1:9222"


def test_browser_mode():
    assert browser_mode({"User-Agent": "HeadlessChrome/128"}) == "headless"
    assert browser_mode({"User-Agent": "Chrome/128"}) == "headed"
    assert browser_mode({}) is None
    assert browser_mode({"User-Agent": ""}) is None


def test_authenticated(environment, install_transport):
    install_transport(_Transport())
    result = check_authentication(environment)
    assert result["authenticated"] is True
    assert result["mode"] == "headless"
    assert result["probe"]["final_origin"] == "https://ifundcontrol.alipay.com"


def test_sso_redirect_is_auth_required(environment, install_transport):
    install_transport(_Transport(href=SSO_LOGIN_ORIGIN + "/ssoLogin.htm?token=x"))
    with pytest.raises(Exception) as caught:
        check_authentication(environment)
    assert caught.value.code == "auth_required"
    assert caught.value.retryable is True


def test_ipaybuservice_login_htm_is_auth_required(environment, install_transport):
    # UAT 2026-09-12: the unauthenticated entry lands on ipaybuservice
    # /login.htm (appName=ifundcontrolprodops / iglobalfundcontrol).
    install_transport(_Transport(href=IPAYBUSERVICE_LOGIN_URL))
    with pytest.raises(Exception) as caught:
        check_authentication(environment)
    assert caught.value.code == "auth_required"
    assert caught.value.details["final_origin"] == "https://ipaybuservice.alipay.com"


def test_ipaybuservice_other_path_is_service_failure(environment, install_transport):
    # Only /login.htm has UAT evidence; other ipaybuservice paths stay
    # inconclusive.
    install_transport(_Transport(href="https://ipaybuservice.alipay.com/home.htm"))
    with pytest.raises(Exception) as caught:
        check_authentication(environment)
    assert caught.value.code == "service_failure"


def test_delayed_entry_redirect_is_auth_required(
    environment, install_transport, monkeypatch
):
    # The entry settles on its own URL (two stable samples), then the
    # JS-driven redirect fires inside the bounded stability window.
    monkeypatch.setattr(cdp, "ENTRY_STABILITY_SECONDS", 2.0)
    install_transport(_Transport(href_flip=(2, IPAYBUSERVICE_LOGIN_URL)))
    with pytest.raises(Exception) as caught:
        check_authentication(environment)
    assert caught.value.code == "auth_required"
    assert caught.value.details["final_origin"] == "https://ipaybuservice.alipay.com"


def test_steady_entry_survives_stability_window(
    environment, install_transport, monkeypatch
):
    # A healthy session stays on the entry URL through the window and still
    # verifies as authenticated.
    monkeypatch.setattr(cdp, "ENTRY_STABILITY_SECONDS", 0.3)
    monkeypatch.setattr(cdp, "POLL_INTERVAL_SECONDS", 0.25)
    install_transport(_Transport(href_flip=(100, IPAYBUSERVICE_LOGIN_URL)))
    result = check_authentication(environment)
    assert result["authenticated"] is True


def test_unexpected_origin_is_service_failure(environment, install_transport):
    install_transport(_Transport(href="https://elsewhere.example.com/"))
    with pytest.raises(Exception) as caught:
        check_authentication(environment)
    assert caught.value.code == "service_failure"


def test_unreachable_is_browser_unavailable(environment, install_transport):
    install_transport(_Transport(reachable=False))
    with pytest.raises(Exception) as caught:
        check_authentication(environment)
    assert caught.value.code == "browser_unavailable"


def test_never_ready_is_browser_unavailable(environment, install_transport):
    install_transport(_Transport(ready_state="loading"))
    with pytest.raises(Exception) as caught:
        check_authentication(environment, timeout=0.05)
    assert caught.value.code == "browser_unavailable"
    assert caught.value.details["ready_state"] == "loading"


def test_navigation_error_is_browser_unavailable(environment, install_transport):
    install_transport(_Transport(href="chrome-error://chromewebdata/"))
    with pytest.raises(Exception) as caught:
        check_authentication(environment)
    assert caught.value.code == "browser_unavailable"
    assert caught.value.details["reason"] == "navigation_error"


def test_probe_setup_navigation_and_settle_share_deadline(monkeypatch):
    clock = [0.0]
    waits = []
    monkeypatch.setattr(cdp.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        cdp.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )

    class Session:
        def navigate(self, url, timeout):
            waits.append(timeout)
            clock[0] += 0.4

        def evaluate(self, expression, timeout):
            waits.append(timeout)
            clock[0] += timeout
            return {"ready_state": "loading", "href": PAYMENT_URL}

        def close(self):
            pass

    class Transport:
        def new_target(self, url, *, timeout):
            waits.append(timeout)
            clock[0] += 0.4
            return {"id": "1", "webSocketDebuggerUrl": "ws://fake"}

        def open_session(self, url, *, timeout):
            waits.append(timeout)
            return Session()

        def close_target(self, target_id):
            pass

    with pytest.raises(cdp.CdpError):
        cdp.probe_final_url(Transport(), PAYMENT_URL, timeout=1.0)
    assert clock[0] == pytest.approx(1.0)
    assert waits == pytest.approx([1.0, 0.6, 0.6, 0.2])
