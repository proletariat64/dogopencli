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
"""

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
from .environment import BrowserEnvironment
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
    guidance = ["dogopencli login"]
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
