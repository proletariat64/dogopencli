"""``dogopencli logout``: clear and verify the dedicated local authentication.

Ported from DI ``src/diauth/logout.py`` at baseline commit
8eb163c6d140554ca167bd50349a85ca224ac342, adapted from the DI multi-context
shared browser to the single dogopencli browser environment and to the payment
platform. One logout operation: take the profile login lock
(``login_in_progress`` on conflict), take browser control exclusive
(``browser_busy`` while data work is active), connect to the EXISTING CDP
endpoint (never launches, repairs, or switches Chrome), clear the applicable
authentication cookie families through page-level CDP calls, then verify with
the bounded payment-entry probe. Only a probe that now lands on a verified
login page (``auth_required``) proves the clearing; a
still-authenticated probe is ``logout_unverified`` and any other settled
origin stays an inconclusive ``service_failure``. CDP failure leaves browser
liveness unknown, so logout returns retryable ``browser_unavailable`` without
touching the profile cookie store — there is no offline file-clearing
fallback, and success is never claimed unverified.

Clearing domains are adapted to the payment platform, not copied from DI
(``AUTH_COOKIE_DOMAIN_SUFFIXES`` below, verified by production UAT
2026-09-12, issues #3/#8).
Clearing is LOCAL only: no company-wide remote SSO logout is invoked, the
remote SSO session is not revoked, other domains' cookies in the profile
survive, the business cache (``cache.sqlite3``) is untouched, no other
browser profile is accessed, and repeated logout is idempotent success when
CDP is available and verification passes.
"""

from collections.abc import Callable
from typing import Any

from . import launcher
from .cdp import CdpError, make_transport
from .cookies import delete_domain_cookies
from .coordination import acquire_browser_control, acquire_login_lock
from .environment import BrowserEnvironment
from .errors import (
    AUTH_REQUIRED,
    BROWSER_UNAVAILABLE,
    LOGOUT_UNVERIFIED,
    AuthError,
)
from .probe import browser_mode, check_authentication

#: Cookie families carrying the dedicated local authentication, adapted to
#: the payment platform (extend only with evidence, never by guessing):
#:
#: - ``antglobal-inc.com``: the company SSO cookie family. The DI Phase B
#:   evidence for the same company-wide OAuth shows the session lives in the
#:   parent-domain family cookies; deleting them forces the human SSO step on
#:   the next login without revoking the remote company session.
#: - ``ifundcontrol.alipay.com`` / ``iglobalfundcontrol.alipay.com``: the
#:   payment application entry host and its API host, so application-local
#:   session cookies cannot keep the entry authenticated after the SSO family
#:   is gone.
#: - ``alipay.com``: production UAT 2026-09-12 — deleting only the three
#:   families above left the payment entry authenticated (21 ``.alipay.com``
#:   cookies survived: ``sso.global.authtoken``, ``IAM_TOKEN``,
#:   ``IAM_TOKEN_HTTP``, ``BUSERVICE_SSO_V2``, ``zt-auth``, ``ctoken`` …);
#:   clearing this parent family made the entry redirect to the login page.
#:   The entry session is carried by the ``.alipay.com`` family. Clearing it
#:   inside the dedicated profile is a local-only operation: it does not
#:   revoke the company-wide server-side SSO state.
AUTH_COOKIE_DOMAIN_SUFFIXES = (
    "antglobal-inc.com",
    "ifundcontrol.alipay.com",
    "iglobalfundcontrol.alipay.com",
    "alipay.com",
)

SCOPE_NOTE = (
    "local clearing only: the remote company SSO session is not revoked; "
    "business caches and other domains' cookies are untouched; the next "
    "dogopencli login requires the human SSO step again"
)


def logout(
    environment: BrowserEnvironment,
    *,
    timeout: float = 15.0,
    before_clear: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Clear the dedicated local authentication and return a verified verdict."""
    login_lock = acquire_login_lock(environment.profile)
    try:
        control = acquire_browser_control(environment.profile, shared=False)
        try:
            return _clear(environment, timeout=timeout, before_clear=before_clear)
        finally:
            control.release()
    finally:
        login_lock.release()


def _clear(
    environment: BrowserEnvironment,
    *,
    timeout: float,
    before_clear: Callable[[], None] | None = None,
) -> dict[str, Any]:
    transport = make_transport(environment.cdp_url)
    try:
        version = transport.version()
    except CdpError as exc:
        # Endpoint failure says nothing about profile ownership. Never clear
        # the on-disk store while the browser's in-memory state is unknown.
        raise AuthError(
            BROWSER_UNAVAILABLE,
            f"the CDP endpoint {environment.cdp_url} is unavailable: {exc}; "
            "logout could not be verified and the cookie file was not changed — "
            "start or restore the dedicated Chrome with CDP enabled, then "
            "retry dogopencli logout",
            retryable=True,
            details={"cdp_url": environment.cdp_url},
        ) from exc
    mode = browser_mode(version)
    if mode is None:
        raise AuthError(
            BROWSER_UNAVAILABLE,
            "CDP /json/version did not provide a User-Agent; browser mode is unknown",
            details={"cdp_url": environment.cdp_url},
        )
    try:
        launcher.require_profile(environment)
    except launcher.LauncherError as exc:
        raise AuthError(BROWSER_UNAVAILABLE, str(exc)) from exc
    if before_clear is not None:
        before_clear()
    try:
        deleted = sum(
            delete_domain_cookies(transport, suffix, timeout=timeout)
            for suffix in AUTH_COOKIE_DOMAIN_SUFFIXES
        )
    except CdpError as exc:
        raise AuthError(
            BROWSER_UNAVAILABLE,
            f"page-level cookie clearing failed: {exc}; the authentication "
            "cookie families may be partially cleared — retry dogopencli logout",
            retryable=True,
            details={"cdp_url": environment.cdp_url},
        ) from exc
    _verify_cleared(environment, timeout=timeout)
    return {
        "authenticated": False,
        "verified": True,
        "cleared": "cdp",
        "cookies_deleted": deleted,
        "domains": list(AUTH_COOKIE_DOMAIN_SUFFIXES),
        "cdp_url": environment.cdp_url,
        "profile": str(environment.profile),
        "mode": mode,
        "note": SCOPE_NOTE,
    }


def _verify_cleared(environment: BrowserEnvironment, *, timeout: float) -> None:
    """Only the post-clearing SSO redirect proves the logout."""
    try:
        check_authentication(environment, timeout=timeout)
    except AuthError as exc:
        if exc.code == AUTH_REQUIRED:
            return  # verified: the payment entry now redirects to the SSO
        if exc.code == BROWSER_UNAVAILABLE:
            raise AuthError(
                BROWSER_UNAVAILABLE,
                f"the post-logout verification probe failed: {exc.message}; "
                "the clearing is unverified — retry dogopencli logout",
                retryable=True,
                details={**exc.details, "cdp_url": environment.cdp_url},
            ) from exc
        raise  # service_failure: the verdict is inconclusive, never success
    raise AuthError(
        LOGOUT_UNVERIFIED,
        "the authentication cookie families were deleted but the payment "
        "entry still probes authenticated; logout is NOT in effect",
        details={"cdp_url": environment.cdp_url},
    )
