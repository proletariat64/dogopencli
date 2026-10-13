"""``dogopencli login``: restore the dedicated login and verify authentication.

Ported from DI ``src/diauth/login.py`` at baseline commit
8eb163c6d140554ca167bd50349a85ca224ac342, adapted to the single dogopencli
browser environment and the in-process launcher. One login operation: take
the profile login lock (``login_in_progress`` on conflict), take browser
control exclusive (``browser_busy`` while data work is active), reuse a
healthy headless Chrome or launch/switch one through the launcher, then
verify persisted authentication with the same bounded probe as
``dogopencli auth check``.

Only a verified ``auth_required`` (the probe saw the company SSO redirect)
enters the human flow: switch the dedicated Chrome to headed, wait for
programmatic proof of the human company SSO by polling the bounded probe
(never an Enter key), let Chrome settle the freshly set session cookies,
switch back to headless, and re-probe. Only headless-verified authentication
is success; a failed handoff returns to headed and resumes waiting, bounded
by MAX_HANDOFF_ATTEMPTS. Network/service failures (``browser_unavailable``,
``service_failure``) never enter the human flow and are never misread as
expired authentication. PINs, role selection, QR scans, and approvals remain
human actions.

Login never refreshes business caches, never becomes a daemon, and leaves
Chrome running after exit. Ctrl+C during the human wait preserves Chrome
exactly as it is, releases coordination, and exits 130; re-invoking login
recovers the browser state it finds.
"""

import sys
from time import monotonic, sleep
from typing import Any

from . import launcher
from .coordination import acquire_browser_control, acquire_login_lock
from .environment import (
    FX_STARTUP_URL,
    LIQUIDITY_STARTUP_URL,
    STARTUP_URLS,
    BrowserEnvironment,
)
from .errors import AUTH_REQUIRED, BROWSER_UNAVAILABLE, SERVICE_FAILURE, AuthError
from .probe import check_authentication, probe_login_completion

#: The launcher waits at most ~10s for CDP readiness; spawn failures surface
#: as LauncherError inside that bound.
DEFAULT_WAIT_TIMEOUT_SECONDS = 600.0

#: Interval between bounded authentication probes during the human wait.
POLL_INTERVAL_SECONDS = 5.0

#: Settle window between headed verification and the headless switch. Chrome
#: commits freshly set SSO cookies to the profile asynchronously, and stopping
#: Chrome inside that window drops the just-established session (DI live UAT).
HANDOFF_SETTLE_SECONDS = 20.0
MAX_HANDOFF_ATTEMPTS = 3

# A ready document can outlive a transient service outage. Recheck it only
# twice, with backoff, while confirmed auth redirects stay document-gated.
MAX_CANDIDATE_SERVICE_ATTEMPTS = 3
CANDIDATE_SERVICE_RETRY_SECONDS = 5.0

#: Why a GUI is mandatory: the company OAuth flow cannot be completed from a
#: copied authorization URL, so the headed login on this host IS the recovery
#: path.
HEADED_SSO_REQUIREMENT = (
    "visible Chrome on this host is required for the human company SSO: the "
    "OAuth flow cannot be completed from a copied authorization URL; restore "
    "a GUI/display and re-run dogopencli login"
)


def login(
    environment: BrowserEnvironment,
    *,
    timeout_seconds: float = DEFAULT_WAIT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Restore the dedicated headless browser and return a verified verdict."""
    login_lock = acquire_login_lock(environment.profile)
    try:
        control = acquire_browser_control(environment.profile, shared=False)
        try:
            if not _ensure_headless(environment):
                return _human_login(
                    environment, timeout_seconds=timeout_seconds, resume=True
                )
            try:
                return _check_headless(environment)
            except AuthError as exc:
                if exc.code != AUTH_REQUIRED:
                    raise
            return _human_login(environment, timeout_seconds=timeout_seconds)
        finally:
            control.release()
    finally:
        login_lock.release()


def _check_headless(
    environment: BrowserEnvironment, *, timeout: float = 15.0
) -> dict[str, Any]:
    verdict = check_authentication(environment, timeout=timeout)
    if verdict.get("mode") != "headless":
        raise AuthError(
            BROWSER_UNAVAILABLE,
            "authentication checked outside headless mode; retry login",
        )
    return verdict


def _human_login(
    environment: BrowserEnvironment, *, timeout_seconds: float, resume: bool = False
) -> dict[str, Any]:
    """Headed human SSO verified by probes, then a verified headless handoff."""
    deadline = monotonic() + timeout_seconds
    domain = next(
        (name for name, url in STARTUP_URLS.items() if url == environment.startup_url),
        "payment",
    )
    recovery_command = "dogopencli login" + (
        f" --domain {domain}" if domain != "payment" else ""
    )
    print(
        "login: resuming the existing headed Chrome for human company SSO"
        if resume
        else "login: switching the dedicated Chrome to headed mode "
        "for the human company SSO",
        file=sys.stderr,
    )
    if not resume:
        _launch(environment, mode="headed")
    attempts = 0
    rejected_candidates: set[tuple[str, float]] = set()
    candidate_failure = AUTH_REQUIRED
    candidate_service_attempts: dict[tuple[str, float], int] = {}
    candidate_retry_after: dict[tuple[str, float], float] = {}
    while True:
        try:
            candidate = _wait_for_human_auth(
                environment,
                deadline=deadline,
                rejected_candidates=rejected_candidates,
                last_failure=candidate_failure,
                candidate_retry_after=candidate_retry_after,
            )
            if environment.startup_url in {LIQUIDITY_STARTUP_URL, FX_STARTUP_URL}:
                sleep(min(HANDOFF_SETTLE_SECONDS, max(0.0, deadline - monotonic())))
                if monotonic() >= deadline:
                    raise AuthError(
                        AUTH_REQUIRED,
                        "login deadline reached during session settle; "
                        "headed Chrome was preserved",
                    )
            else:
                sleep(HANDOFF_SETTLE_SECONDS)
        except KeyboardInterrupt:
            # Preserve Chrome exactly as it is; coordination releases through
            # the caller's finally blocks. Report, then let the CLI shell map
            # the interruption to exit 130.
            print(
                "dogopencli login interrupted while waiting for human "
                "authentication; Chrome was left running as-is and coordination "
                f"was released; re-run {recovery_command} to recover",
                file=sys.stderr,
            )
            raise
        try:
            if environment.startup_url in {LIQUIDITY_STARTUP_URL, FX_STARTUP_URL}:
                check_authentication(
                    environment, timeout=min(15.0, max(0.001, deadline - monotonic()))
                )
            else:
                check_authentication(environment)
        except AuthError as exc:
            if exc.code in {AUTH_REQUIRED, SERVICE_FAILURE} and monotonic() < deadline:
                if candidate is not None:
                    candidate_failure = exc.code
                    if exc.code == AUTH_REQUIRED:
                        rejected_candidates.add(candidate)
                    else:
                        count = candidate_service_attempts.get(candidate, 0) + 1
                        candidate_service_attempts[candidate] = count
                        if count >= MAX_CANDIDATE_SERVICE_ATTEMPTS:
                            rejected_candidates.add(candidate)
                        else:
                            candidate_retry_after[candidate] = monotonic() + (
                                CANDIDATE_SERVICE_RETRY_SECONDS * 2 ** (count - 1)
                            )
                continue  # quiet wait until a new document or a bounded retry
            raise
        print(
            "login: headed authentication verified; switching back to headless",
            file=sys.stderr,
        )
        _launch(environment, mode="headless")
        try:
            if environment.startup_url in {LIQUIDITY_STARTUP_URL, FX_STARTUP_URL}:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise AuthError(
                        AUTH_REQUIRED,
                        "login deadline reached during headless handoff; "
                        "headed Chrome was restored",
                    )
                return _check_headless(environment, timeout=min(15.0, remaining))
            return _check_headless(environment)
        except AuthError as exc:
            if exc.code != AUTH_REQUIRED:
                raise
            attempts += 1
            if attempts >= MAX_HANDOFF_ATTEMPTS or monotonic() >= deadline:
                if environment.startup_url in {LIQUIDITY_STARTUP_URL, FX_STARTUP_URL}:
                    _launch(environment, mode="headed")
                raise AuthError(
                    AUTH_REQUIRED,
                    "headed authentication was verified, but the headless re-probe "
                    "still redirects to the company SSO after "
                    f"{attempts} handoff attempt(s); the session did not persist "
                    "to the dedicated profile: re-run dogopencli login",
                    details={**exc.details, "handoff_attempts": attempts},
                ) from exc
            # The just-set session was not durable yet; return to headed and
            # keep waiting for the human within the same deadline.
            _launch(environment, mode="headed")


def _wait_for_human_auth(
    environment: BrowserEnvironment,
    *,
    deadline: float,
    rejected_candidates: set[tuple[str, float]] | None = None,
    last_failure: str = AUTH_REQUIRED,
    candidate_retry_after: dict[tuple[str, float], float] | None = None,
) -> tuple[str, float] | None:
    """Poll quietly for a completion signal, then let the caller verify auth.

    The fetch attaches to an existing page, never opens/closes tabs, never
    navigates the human form, and never follows a redirect into SSO.
    ``auth_required`` (verified USER_NOT_LOGIN response) and ``service_failure``
    (an inconclusive fetch or a transitioning target) both keep waiting; a lost
    headed Chrome aborts as ``browser_unavailable`` and never reports success.
    At the deadline the LAST observed classification decides the error:
    persistent ``service_failure`` is a service problem, never reported as
    expired authentication.
    """
    print(
        "login: waiting for the human company SSO in the headed Chrome",
        file=sys.stderr,
    )
    while True:
        remaining = deadline - monotonic()
        if remaining > 0:
            try:
                blocked_candidates = set(rejected_candidates or ())
                blocked_candidates.update(
                    candidate
                    for candidate, retry_at in (candidate_retry_after or {}).items()
                    if monotonic() < retry_at
                )
                candidate = probe_login_completion(
                    environment,
                    timeout=min(15.0, remaining),
                    rejected_candidates=blocked_candidates,
                )
            except AuthError as exc:
                if exc.code == BROWSER_UNAVAILABLE:
                    raise AuthError(
                        BROWSER_UNAVAILABLE,
                        "the headed Chrome became unreachable while waiting for human "
                        f"authentication: {exc.message}; re-run dogopencli login to "
                        "recover",
                        details=exc.details,
                    ) from exc
                if exc.code not in {AUTH_REQUIRED, SERVICE_FAILURE}:
                    raise
                last_failure = exc.code
            else:
                if (
                    candidate is None
                    or not rejected_candidates
                    or candidate not in rejected_candidates
                ):
                    return candidate
        if monotonic() >= deadline:
            if last_failure == SERVICE_FAILURE:
                raise AuthError(
                    SERVICE_FAILURE,
                    "the quiet authentication probe stayed inconclusive until the "
                    "login deadline; check the service state, then re-run "
                    "dogopencli login",
                    details={"profile": str(environment.profile)},
                )
            raise AuthError(
                AUTH_REQUIRED,
                "no verified authentication within the login deadline while "
                "waiting for the human company SSO; the headed Chrome is still "
                "available: complete the login there, then re-run dogopencli login",
                details={"profile": str(environment.profile)},
            )
        sleep(min(POLL_INTERVAL_SECONDS, max(0.0, deadline - monotonic())))


def _ensure_headless(environment: BrowserEnvironment) -> bool:
    """Reuse a healthy headless Chrome; launch or switch modes otherwise."""
    from .cdp import CdpError, make_transport

    transport = make_transport(environment.cdp_url)
    try:
        version = transport.version()
    except CdpError:
        version = None
    user_agent = (version or {}).get("User-Agent") or ""
    headless = "HeadlessChrome/" in user_agent
    resume_headed = (
        environment.startup_url in {LIQUIDITY_STARTUP_URL, FX_STARTUP_URL}
        and bool(user_agent)
        and not headless
    )
    if version is not None and (headless or resume_headed):
        try:
            launcher.require_profile(environment)
        except launcher.LauncherError as exc:
            raise AuthError(BROWSER_UNAVAILABLE, str(exc)) from exc
        return headless  # preserve an in-progress Liquidity SSO on re-entry
    _launch(environment, mode="headless")
    return True


def _launch(environment: BrowserEnvironment, *, mode: str) -> None:
    try:
        note = launcher.launch(environment, mode, control_held=True)
    except launcher.LauncherError as exc:
        message = str(exc)
        if mode == "headed":
            message = (
                f"visible Chrome for human login could not start: {message}; "
                f"{HEADED_SSO_REQUIREMENT}"
            )
        raise AuthError(
            BROWSER_UNAVAILABLE,
            message,
            details={
                "cdp_url": environment.cdp_url,
                "profile": str(environment.profile),
            },
        ) from exc
    print(f"login: {note}", file=sys.stderr)
