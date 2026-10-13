"""The bounded verified-authentication probe for the dedicated browser.

Ported from DI ``src/diauth/browser.py`` at baseline commit
8eb163c6d140554ca167bd50349a85ca224ac342 and adapted to the payment
application: the probe navigates the payment product management entry in one
temporary CDP target and classifies the settled origin:

- final origin == the payment application origin -> authenticated
- final URL is a verified login landing -> ``auth_required``
- CDP unreachable / navigation failure / target never ready -> ``browser_unavailable``
- any other settled origin -> ``service_failure`` (inconclusive, never expired auth)

Verified login landings: the company SSO origin (DI Phase B evidence for the
same company-wide OAuth) and, per production UAT 2026-09-12, the
``ipaybuservice.alipay.com`` ``/login.htm`` page the unauthenticated payment
entry redirects to (``appName=ifundcontrolprodops`` / ``iglobalfundcontrol``).
Any other origin stays inconclusive, never a DI business error code. CDP
metadata alone never counts as authenticated. The probe never launches
Chrome, never switches modes, never initiates human authentication.

The human-login wait uses a separate quiet completion signal below: fetch
the verified BUC user-initialization GET in an existing page, without
executing the frontend logout helper or following login redirects. It is
not an authentication verdict; navigation and headless checks still decide.
"""

import json
import math
from time import monotonic, sleep
from typing import Any
from urllib.parse import urlparse

from .cdp import (
    BrowserLoss,
    CdpError,
    PageNotReady,
    make_transport,
    probe_final_url,
    url_origin,
)
from .environment import (
    FX_STARTUP_URL,
    LIQUIDITY_STARTUP_URL,
    PAYMENT_STARTUP_URL,
    STARTUP_URLS,
    BrowserEnvironment,
)
from .errors import (
    AUTH_REQUIRED,
    BROWSER_UNAVAILABLE,
    SERVICE_FAILURE,
    AuthError,
)

#: Company SSO login origin, shared with the DI evidence for the same
#: company-wide OAuth/SSO; a redirect to this exact origin proves
#: missing/expired authentication. Any other unexpected origin stays
#: inconclusive unless it is a verified login landing below.
SSO_LOGIN_ORIGIN = "https://tonelogin.antglobal-inc.com"

#: UAT 2026-09-12: the unauthenticated payment entry actually lands on the
#: ipaybuservice login page, not the company SSO origin. Only this exact
#: host + path is classified as a login landing; other ipaybuservice paths
#: lack evidence and stay inconclusive.
IPAYBUSERVICE_LOGIN_HOST = "ipaybuservice.alipay.com"
IPAYBUSERVICE_LOGIN_PATH = "/login.htm"


def is_login_landing(final_href: str) -> bool:
    """Whether a settled probe URL is a verified login landing."""
    if url_origin(final_href) == SSO_LOGIN_ORIGIN:
        return True
    parsed = urlparse(final_href)
    return (
        parsed.netloc == IPAYBUSERVICE_LOGIN_HOST
        and parsed.path == IPAYBUSERVICE_LOGIN_PATH
    )


def browser_mode(version: dict[str, Any]) -> str | None:
    """Read verified mode evidence; missing or malformed User-Agent is unknown."""
    user_agent = version.get("User-Agent")
    if not isinstance(user_agent, str) or not user_agent:
        return None
    return "headless" if "HeadlessChrome/" in user_agent else "headed"


def probe_entry(transport: Any, startup_url: str, *, timeout: float = 15.0) -> str:
    """Classify one application entry navigation; return its settled origin.

    Shared by the full authentication probe and the per-origin checks peer
    plugins need (ADR 0015): a healthy session for one origin never proves
    another origin's authorization. Raises ``AuthError`` with the stable
    classifications; success returns the verified final origin.
    """
    details: dict[str, Any] = {"startup_url": startup_url}
    expected_origin = url_origin(startup_url)
    try:
        final_href = probe_final_url(transport, startup_url, timeout=timeout)
    except BrowserLoss as exc:
        raise AuthError(
            BROWSER_UNAVAILABLE,
            str(exc),
            details={**details, "reason": exc.reason},
        ) from exc
    except PageNotReady as exc:
        raise AuthError(
            BROWSER_UNAVAILABLE,
            f"Runtime probe failed: {exc}",
            details={**details, "ready_state": exc.ready_state},
        ) from exc
    except CdpError as exc:
        raise AuthError(
            BROWSER_UNAVAILABLE,
            f"Runtime probe failed: {exc}",
            details=details,
        ) from exc
    final_origin = url_origin(final_href)
    if is_login_landing(final_href):
        raise AuthError(
            AUTH_REQUIRED,
            f"the application entry {startup_url} redirected to a login page; "
            "the dedicated authentication is expired or missing",
            details={
                **details,
                "reason": "auth_redirect",
                "final_origin": final_origin,
            },
        )
    if final_origin != expected_origin:
        raise AuthError(
            SERVICE_FAILURE,
            "the application probe settled on unexpected origin "
            f"{final_origin}; the authentication verdict is inconclusive",
            details={
                **details,
                "reason": "probe_inconclusive",
                "expected_origin": expected_origin,
                "final_origin": final_origin,
            },
        )
    return final_origin


def check_authentication(
    environment: BrowserEnvironment,
    *,
    startup_url: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Probe the dedicated browser and return a verified auth verdict.

    Success requires the entry navigation to settle on the application
    origin. The default entry is the shared environment startup URL
    (payment); callers checking a peer plugin's authorization pass that
    plugin's entry so the verdict names the domain actually checked.
    Failures raise ``AuthError`` with the stable classifications above;
    launcher guidance rides in the details so callers can point at
    ``dogopencli login`` for recovery.
    """
    entry_url = environment.startup_url if startup_url is None else startup_url
    domain = next(
        (name for name, url in STARTUP_URLS.items() if url == entry_url), None
    )
    guidance = [
        "dogopencli login"
        + (f" --domain {domain}" if domain and domain != "payment" else "")
    ]
    details = {"cdp_url": environment.cdp_url, "launch_command": guidance}
    transport = make_transport(environment.cdp_url)
    try:
        version = transport.version()
    except CdpError as exc:
        raise AuthError(
            BROWSER_UNAVAILABLE,
            f"CDP endpoint unreachable at {environment.cdp_url}: {exc}; "
            "run dogopencli login to start or restore the dedicated Chrome",
            details=details,
        ) from exc
    mode = browser_mode(version)
    if mode is None:
        raise AuthError(
            BROWSER_UNAVAILABLE,
            "CDP /json/version did not provide a User-Agent; browser mode is unknown",
            details=details,
        )
    final_origin = probe_entry(transport, entry_url, timeout=timeout)
    return {
        "domain": domain,
        "authenticated": True,
        "healthy": True,
        "cdp_url": environment.cdp_url,
        "profile": str(environment.profile),
        "browser": version.get("Browser"),
        "mode": mode,
        "probe": {
            "startup_url": entry_url,
            "final_origin": final_origin,
            "authenticated": True,
        },
    }


# Verified read-only GET, documented in:
# docs/research/general/2026-09-26-collection-menu-deep-survey.md.
# Current frontend getUserInfo consumes data.outUserNo; isolated Chrome
# returns success:false / USER_NOT_LOGIN anonymously. Identity never leaves JS.
_USER_INFO_URL = f"https://{IPAYBUSERVICE_LOGIN_HOST}/pub/getUserInfomation.json"

# Same-origin on the login page; the production frontend uses CORS from payment.
_CARRIER_ORIGINS = (
    url_origin(PAYMENT_STARTUP_URL),
    f"https://{IPAYBUSERVICE_LOGIN_HOST}",
)

_FETCH_SIGNAL = r"""
(async (probe) => {
  if (!probe.origins.includes(location.origin)) return {state: "inconclusive"};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), probe.timeoutMs);
  try {
    const response = await fetch(probe.url, {
      method: "GET", credentials: "include", cache: "no-store",
      redirect: "manual", signal: controller.signal
    });
    if (response.status !== 200 || response.url !== probe.url)
      return {state: "inconclusive"};
    const body = await response.json();
    if (!body || typeof body !== "object" || Array.isArray(body))
      return {state: "inconclusive"};
    if (body.success === false && body.buserviceErrorCode === "USER_NOT_LOGIN")
      return {state: "pending"};
    // Unknown service/permission/referer failures are not expired-auth proof.
    if (body.success === false || body.stat === "fail")
      return {state: "inconclusive"};
    const user = body.data;
    if (!user || typeof user !== "object" || Array.isArray(user))
      return {state: "inconclusive"};
    const id = user.outUserNo;
    const complete = (typeof id === "string" && id.trim().length > 0) ||
                     (typeof id === "number" && Number.isFinite(id) && id > 0);
    // Global SSO user information alone must not interrupt a form still
    // waiting for role/MFA input. Wait for the human tab's completed goto.
    const returned = location.origin === probe.applicationOrigin &&
                     ["interactive", "complete"].includes(document.readyState);
    return {state: complete && returned ? "complete" : "inconclusive"};
  } catch (_) {
    // CORS/network/parse failures are inconclusive, not expired auth.
    return {state: "inconclusive"};
  } finally {
    clearTimeout(timer);
  }
})(__PAYLOAD__)
"""


# Observe only the existing document, without requests or SSO URL parameters.
_LIQUIDITY_SIGNAL = """
(() => ({origin: location.origin, path: location.pathname,
         ready_state: document.readyState, document_id: performance.timeOrigin}))()
"""
LIQUIDITY_CANDIDATE_STABILITY_SECONDS = 0.25


def _entry_completion(
    environment: BrowserEnvironment,
    *,
    timeout: float,
    rejected_candidates: set[tuple[str, float]] | None = None,
) -> tuple[str, float]:
    """Observe a stable returned entry document; it is never an auth verdict.

    A still-open verified SSO/login tab blocks candidates, so an old entry tab
    cannot interrupt human role/MFA input. Ambiguous tabs remain untouched.
    """
    deadline = monotonic() + timeout
    transport = make_transport(environment.cdp_url)
    session = None
    try:
        transport.version(timeout=max(0.001, deadline - monotonic()))
    except CdpError as exc:
        code = BROWSER_UNAVAILABLE if deadline - monotonic() >= 1.0 else SERVICE_FAILURE
        raise AuthError(
            code,
            "the headed Chrome is unreachable or the reachability budget is exhausted",
        ) from exc
    try:
        targets = transport.list_targets(timeout=max(0.001, deadline - monotonic()))
        pages = [
            t
            for t in targets
            if t.get("type") == "page" and isinstance(t.get("url"), str)
        ]
        if any(is_login_landing(t["url"]) for t in pages):
            raise AuthError(
                SERVICE_FAILURE,
                "waiting for existing SSO/login tabs to return to the application",
            )
        eligible = [
            t
            for t in pages
            if url_origin(t["url"]) == url_origin(environment.startup_url)
            and isinstance(t.get("webSocketDebuggerUrl"), str)
        ]
        for target in eligible:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            session = transport.open_session(
                target["webSocketDebuggerUrl"], timeout=remaining
            )
            observations = []
            try:
                for sample in range(2):
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        break
                    observation = session.evaluate(_LIQUIDITY_SIGNAL, remaining)
                    if not (
                        isinstance(observation, dict)
                        and observation.get("origin")
                        == url_origin(environment.startup_url)
                        and observation.get("path")
                        == urlparse(environment.startup_url).path
                        and observation.get("ready_state")
                        in {"interactive", "complete"}
                        and type(observation.get("document_id")) in {int, float}
                        and math.isfinite(observation["document_id"])
                        and observation["document_id"] > 0
                    ):
                        break
                    observations.append(observation["document_id"])
                    if sample == 0:
                        if (
                            deadline - monotonic()
                            <= LIQUIDITY_CANDIDATE_STABILITY_SECONDS
                        ):
                            break
                        sleep(LIQUIDITY_CANDIDATE_STABILITY_SECONDS)
                if len(observations) == 2 and observations[0] == observations[1]:
                    candidate = (target["webSocketDebuggerUrl"], observations[1])
                    if not rejected_candidates or candidate not in rejected_candidates:
                        return candidate
            except CdpError:
                # A lost/transitioning document does not hide another ready tab.
                pass
            finally:
                session.close()
                session = None
        raise AuthError(
            SERVICE_FAILURE, "waiting for a stable existing application entry document"
        )
    except CdpError as exc:
        remaining = deadline - monotonic()
        if remaining >= 1.0:
            try:
                transport.version(timeout=remaining)
            except CdpError:
                raise AuthError(
                    BROWSER_UNAVAILABLE, "the headed Chrome became unreachable"
                ) from exc
        raise AuthError(
            SERVICE_FAILURE, "quiet application observation is temporarily unavailable"
        ) from exc
    finally:
        if session is not None:
            session.close()


def probe_login_completion(
    environment: BrowserEnvironment,
    *,
    timeout: float = 15.0,
    rejected_candidates: set[tuple[str, float]] | None = None,
) -> tuple[str, float] | None:
    """Return on a completion candidate; otherwise raise a wait classification.

    Attach only to existing payment/login page targets. A transitioning or
    closed target is retryable while Chrome remains reachable. Never fall
    back to navigations during human input, even on CORS/network failure.
    """
    if environment.startup_url in {LIQUIDITY_STARTUP_URL, FX_STARTUP_URL}:
        return _entry_completion(
            environment, timeout=timeout, rejected_candidates=rejected_candidates
        )
    if environment.startup_url != PAYMENT_STARTUP_URL:
        raise AuthError(
            SERVICE_FAILURE, "quiet login probe has no verified entry contract"
        )
    deadline = monotonic() + timeout
    transport = make_transport(environment.cdp_url)
    reachability_budget = deadline - monotonic()
    try:
        transport.version(timeout=max(0.001, reachability_budget))
    except CdpError as exc:
        if reachability_budget < 1.0:
            raise AuthError(
                SERVICE_FAILURE,
                "quiet login probe has insufficient reachability budget",
            ) from exc
        raise AuthError(
            BROWSER_UNAVAILABLE, "the headed Chrome is unreachable"
        ) from exc

    session = None
    try:
        targets = transport.list_targets(timeout=max(0.001, deadline - monotonic()))
        target = next(
            (
                t
                for t in sorted(
                    targets,
                    key=lambda t: (
                        url_origin(str(t.get("url", "")))
                        != url_origin(environment.startup_url)
                    ),
                )
                if t.get("type") == "page"
                and isinstance(t.get("url"), str)
                and url_origin(t["url"]) in _CARRIER_ORIGINS
                and isinstance(t.get("webSocketDebuggerUrl"), str)
            ),
            None,
        )
        if target is None:
            raise AuthError(
                SERVICE_FAILURE, "waiting for an existing payment or login page"
            )
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CdpError("quiet login probe deadline exhausted")
        session = transport.open_session(
            target["webSocketDebuggerUrl"], timeout=remaining
        )
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CdpError("quiet login probe deadline exhausted")
        payload = json.dumps(
            {
                "url": _USER_INFO_URL,
                "origins": _CARRIER_ORIGINS,
                "applicationOrigin": url_origin(environment.startup_url),
                "timeoutMs": max(1, math.floor(remaining * 1000)),
            }
        )
        result = session.evaluate(
            _FETCH_SIGNAL.replace("__PAYLOAD__", payload), remaining
        )
    except CdpError as exc:
        remaining = deadline - monotonic()
        # A near-expired budget cannot establish browser loss: a healthy
        # Chrome need not answer /json/version within a millisecond.
        if remaining >= 1.0:
            try:
                transport.version(timeout=remaining)
            except CdpError:
                raise AuthError(
                    BROWSER_UNAVAILABLE, "the headed Chrome became unreachable"
                ) from exc
        raise AuthError(
            SERVICE_FAILURE, "quiet login probe is temporarily unavailable"
        ) from exc
    finally:
        if session is not None:
            session.close()

    if isinstance(result, dict) and result.get("state") == "complete":
        return
    if isinstance(result, dict) and result.get("state") == "pending":
        raise AuthError(AUTH_REQUIRED, "the user-initialization gate requires login")
    raise AuthError(SERVICE_FAILURE, "quiet login probe is inconclusive")
