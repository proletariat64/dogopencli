"""Scripted CDP fake for auth and business-query SIT: transport seam plus a
launcher substitute.

Ported from the DI test doubles (``tests/test_browser_cdp.py`` FakeTransport
and the scripted launcher/transport pattern in ``tests/test_login.py``). The
``FakeBrowser`` state machine is the controllable stand-in for both the Chrome
process and the human SSO action: the fake launcher flips the recorded mode,
and scripted hrefs decide what each bounded probe observes.

Issue #5 adds the business-request injection: in-page ``fetch`` evaluations
are answered from a scripted queue or a handler, and every request payload
is recorded so tests can assert the exact registered requests.
"""

import json
from collections import deque
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from dogopencli.browser import cdp
from dogopencli.browser.launcher import LauncherError
from dogopencli.jsonutil import canonical

PAYMENT_URL = (
    "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
)
PAYMENT_ORIGIN = "https://ifundcontrol.alipay.com"
SSO_URL = "https://tonelogin.antglobal-inc.com/ssoLogin.htm?token=x"
SSO_ORIGIN = "https://tonelogin.antglobal-inc.com"
# UAT 2026-09-12: the unauthenticated payment entry lands on this login page.
IPAYBUSERVICE_LOGIN_URL = (
    "https://ipaybuservice.alipay.com/login.htm?appName=ifundcontrolprodops&goto=x"
)
HEADED_UA = "Chrome/128.0.0.0"
HEADLESS_UA = "HeadlessChrome/128.0.0.0"


def _extract_payload(expression: str) -> dict:
    # The fetch IIFE ends with `})(<payload>)`; synthetic fixture values
    # never contain the `})(` marker inside strings.
    start = expression.rindex("})(") + 3
    return json.loads(expression[start:-1], parse_float=Decimal)


class FakeSession(cdp.CdpSession):
    """One scripted persistent session; evaluations route through the transport."""

    def __init__(self, transport: "FakeTransport", ws_url: str) -> None:
        self._transport = transport
        self.ws_url = ws_url
        self.closed = False

    def evaluate(self, expression: str, timeout: float):
        if self.closed:
            raise cdp.CdpError("session is closed")
        return self._transport.evaluate_probe(expression)

    def navigate(self, url: str, timeout: float) -> None:
        self._transport.navigations.append(url)

    def close(self) -> None:
        self.closed = True


class FakeTransport(cdp.CdpTransport):
    """Scripted CDP transport bound to one FakeBrowser observation."""

    def __init__(
        self,
        state: "FakeBrowser",
        *,
        ready_state: str = "complete",
    ) -> None:
        self._state = state
        self.ready_state = ready_state
        self.created: list[str] = []
        self.closed: list[str] = []
        self.navigations: list[str] = []
        self.expressions: list[str] = []
        self._next_target = 0
        self._href: str | None = None
        self._evaluations = 0

    def version(self) -> dict:
        if not self._state.running:
            raise cdp.CdpError("connection refused")
        return {
            "Browser": "Chrome/128.0.0.0",
            "User-Agent": (
                HEADLESS_UA if self._state.mode == "headless" else HEADED_UA
            ),
            "webSocketDebuggerUrl": "ws://cdp/devtools",
        }

    def new_target(self, url: str, *, timeout: float | None = None) -> dict:
        if not self._state.running:
            raise cdp.CdpError("connection refused")
        # Sequential targets have independent navigation observations. A
        # re-probe after a fetch failure must not inherit the query page's URL.
        self._href = None
        self._evaluations = 0
        self._next_target += 1
        target_id = f"created-{self._next_target}"
        self.created.append(url)
        return {
            "id": target_id,
            "url": url,
            "webSocketDebuggerUrl": f"ws://cdp/{target_id}",
        }

    def close_target(self, target_id: str) -> None:
        self.closed.append(target_id)

    def open_session(
        self, ws_url: str, *, timeout: float | None = None
    ) -> cdp.CdpSession:
        if not self._state.running:
            raise cdp.CdpError("connection refused")
        return FakeSession(self, ws_url)

    def evaluate_probe(self, expression: str):
        if not self._state.running:
            raise cdp.CdpError("connection refused")
        self.expressions.append(expression)
        if "fetch(" in expression:
            return self._business_fetch(expression)
        if self._state.probe_error:
            raise cdp.CdpError("target crashed")
        self._evaluations += 1
        flip = self._state.href_flip
        if flip is not None and self._evaluations > flip[0]:
            # Scripted late JS redirect: the settled entry URL flips to the
            # login page after ``flip[0]`` probe evaluations on this target.
            self._href = flip[1]
        elif self._href is None:
            self._href = self._state.next_href()
        return {"ready_state": self.ready_state, "href": self._href}

    def _business_fetch(self, expression: str):
        payload = _extract_payload(expression)
        state = self._state
        state.business_requests.append(payload)
        if state.business_handler is not None:
            outcome = state.business_handler(payload, len(state.business_requests) - 1)
        elif state.business_script:
            outcome = state.business_script.popleft()
        else:
            raise AssertionError(f"unscripted business request: {payload}")
        if isinstance(outcome, Exception):
            raise outcome
        if outcome.get("error") is not None:
            return {
                "status": 0,
                "body": "",
                "retryAfter": None,
                "error": outcome["error"],
            }
        body = outcome["body"]
        text = body if isinstance(body, str) else canonical(body)
        return {
            "status": outcome["status"],
            "body": text,
            "retryAfter": outcome.get("retry_after"),
            "finalUrl": outcome.get("final_url"),
            "redirected": outcome.get("redirected", False),
        }


class FakeBrowser:
    """Controllable Chrome/human stand-in driven through the launcher seam."""

    def __init__(
        self,
        *,
        running: bool = True,
        mode: str = "headless",
        href: str = PAYMENT_URL,
    ) -> None:
        self.running = running
        self.mode = mode
        self.href = href
        self.hrefs: list = []  # scripted per-probe hrefs; callables see self
        self.launches: list[str] = []
        self.fail_modes: set[str] = set()
        self.probe_error = False
        self.href_flip: tuple[int, str] | None = None  # late JS redirect script
        self.transports: list[FakeTransport] = []
        self.cookie = "ctoken=FAKE-CTOKEN-SECRET; unrelated=1"
        self.business_requests: list[dict] = []
        self.business_script: deque = deque()
        self.business_handler: Callable[[dict, int], Any] | None = None

    def launch(self, environment, mode: str, *, control_held: bool = False) -> str:
        self.launches.append(mode)
        if mode in self.fail_modes:
            raise LauncherError("no display available")
        self.running = True
        self.mode = mode
        return f"Chrome mode {mode} | CDP {environment.cdp_url}"

    def next_href(self) -> str:
        href = self.hrefs.pop(0) if self.hrefs else self.href
        if callable(href):
            return href(self)
        return href

    def transport(self, cdp_url: str) -> FakeTransport:
        made = FakeTransport(self)
        self.transports.append(made)
        return made


# --- issue #8: page-level cookie commands for the logout SIT ------------------
# Appended extension: FakeBrowser instances used by logout tests seed
# ``cookies`` (list of name/domain/path dicts) and ``deleted_cookies`` (the
# recorded Network.deleteCookies params); the lazy defaults below keep every
# pre-existing FakeBrowser behavior unchanged.

LOGOUT_FAMILY_COOKIES = [
    {"name": "SSO_TICKET", "domain": ".antglobal-inc.com", "path": "/"},
    {"name": "tone_session", "domain": "tonelogin.antglobal-inc.com", "path": "/"},
    {"name": "PAY_SESSION", "domain": ".ifundcontrol.alipay.com", "path": "/"},
    {"name": "API_SESSION", "domain": ".iglobalfundcontrol.alipay.com", "path": "/"},
    # UAT 2026-09-12: the .alipay.com parent family carries the entry session.
    {"name": "SSO_GLOBAL_AUTHTOKEN", "domain": ".alipay.com", "path": "/"},
]
LOOKALIKE_COOKIE = {
    "name": "LOOKALIKE",
    "domain": ".notantglobal-inc.com",
    "path": "/",
}
UNRELATED_COOKIE = {"name": "UNRELATED", "domain": ".example.com", "path": "/"}


def seed_cookies(state: "FakeBrowser") -> None:
    """Give a FakeBrowser an SSO/app cookie family plus foreign survivors."""
    state.cookies = [
        dict(cookie)
        for cookie in (*LOGOUT_FAMILY_COOKIES, LOOKALIKE_COOKIE, UNRELATED_COOKIE)
    ]
    state.deleted_cookies = []


def _fake_command(self, method, params, timeout):
    """Scripted page-level CDP commands; only the cookie surface is supported."""
    state = self._transport._state
    if not state.running:
        raise cdp.CdpError("connection refused")
    if state.probe_error:
        raise cdp.CdpError("target crashed")
    if not hasattr(state, "cookies"):
        seed_cookies(state)
    if method == "Network.getAllCookies":
        return {"cookies": [dict(cookie) for cookie in state.cookies]}
    if method == "Network.deleteCookies":
        state.deleted_cookies.append(dict(params))
        state.cookies = [
            cookie
            for cookie in state.cookies
            if not (
                cookie["name"] == params["name"]
                and cookie["domain"] == params["domain"]
            )
        ]
        return {}
    raise cdp.CdpError(f"unsupported CDP method {method}")


FakeSession.command = _fake_command
