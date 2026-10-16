"""Domain selection and bounded orchestration over the shared browser lifecycle."""

import sys
from dataclasses import replace
from time import monotonic
from typing import Any

from ..browser.coordination import acquire_browser_control, acquire_login_lock
from ..browser.environment import BrowserEnvironment
from ..browser.errors import (
    AUTH_REQUIRED,
    BROWSER_BUSY,
    BROWSER_UNAVAILABLE,
    LOGIN_IN_PROGRESS,
    AuthError,
)
from ..browser.login import restore_authentication
from ..browser.probe import check_authentication
from ..domains import DomainService
from ..errors import CliError


def _persist(service: DomainService, domain_id: str, verdict: dict[str, Any]) -> None:
    try:
        service.record_auth(domain_id, verdict)
    except CliError:
        print(
            "warning: DOMAIN_STATE_ERROR: auth observation was not saved",
            file=sys.stderr,
        )


def authenticate_domains(
    environment: BrowserEnvironment,
    service: DomainService,
    selectors: list[str] | None,
    *,
    recover: bool,
    timeout_seconds: float = 600.0,
) -> dict[str, Any]:
    """Return every selected verdict; never multiply the human login budget."""
    try:
        selected = service.select_domains(selectors)
    except CliError as exc:
        raise AuthError(exc.code.lower(), exc.message) from exc
    deadline = monotonic() + (timeout_seconds if recover else 15.0 * len(selected))
    outcomes: list[dict[str, Any]] = []
    first_error: AuthError | None = None
    interrupted = False
    unavailable = False
    login_lock = None
    control = None
    try:
        if recover:
            login_lock = acquire_login_lock(environment.profile)
            control = acquire_browser_control(environment.profile, shared=False)
        for domain in selected:
            remaining = deadline - monotonic()
            if interrupted or unavailable or remaining <= 0:
                outcomes.append(
                    {
                        "domain": domain.id,
                        "authenticated": None,
                        "checked": False,
                        "error": {
                            "code": "not_checked",
                            "message": "shared login unavailable or interrupted",
                        },
                    }
                )
                continue
            target = replace(
                environment,
                startup_url=domain.entry_point,
                domain_id=domain.id,
                auth_policy=domain.auth,
            )
            try:
                if recover:
                    verdict = restore_authentication(target, timeout_seconds=remaining)
                else:
                    probe = domain.auth.probe or check_authentication
                    verdict = probe(target, timeout=min(15.0, remaining))
                verdict = {**verdict, "domain": domain.id}
                outcomes.append({**verdict, "checked": True})
                _persist(service, domain.id, verdict)
            except AuthError as exc:
                details = {
                    **exc.details,
                    "domain": domain.id,
                    "startup_url": domain.entry_point,
                }
                exc.details = details
                error = {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                }
                outcomes.append(
                    {
                        "domain": domain.id,
                        "authenticated": False,
                        "checked": True,
                        "error": error,
                    }
                )
                _persist(
                    service,
                    domain.id,
                    {
                        "authenticated": False if exc.code == AUTH_REQUIRED else None,
                        "error_code": exc.code,
                        "diagnostic": exc.code,
                    },
                )
                if first_error is None:
                    first_error = exc
                unavailable = exc.code in {
                    BROWSER_UNAVAILABLE,
                    BROWSER_BUSY,
                    LOGIN_IN_PROGRESS,
                }
            except KeyboardInterrupt:
                interrupted = True
                outcomes.append(
                    {
                        "domain": domain.id,
                        "authenticated": None,
                        "checked": False,
                        "error": {
                            "code": "interrupted",
                            "message": "authentication interrupted",
                        },
                    }
                )
        if interrupted:
            raise AuthError(
                "interrupted",
                "Command interrupted",
                details={
                    "domains": outcomes,
                    **(
                        {
                            "domain": selected[0].id,
                            "startup_url": selected[0].entry_point,
                        }
                        if len(selected) == 1
                        else {}
                    ),
                },
            )
        if first_error is not None or any(
            not item.get("authenticated") for item in outcomes
        ):
            if first_error is None:
                first_error = AuthError(
                    AUTH_REQUIRED,
                    "login deadline reached before all domains were verified",
                )
            first_error.details = {**first_error.details, "domains": outcomes}
            raise first_error
        if len(outcomes) == 1:
            return outcomes[0]
        return {
            "authenticated": True,
            "mode": outcomes[-1].get("mode"),
            "domains": outcomes,
        }
    except AuthError as exc:
        if "domains" not in exc.details:
            seen = {item["domain"] for item in outcomes}
            exc.details = {
                **exc.details,
                "domains": [
                    *outcomes,
                    *(
                        {
                            "domain": domain.id,
                            "authenticated": None,
                            "checked": False,
                            "error": {
                                "code": "not_checked",
                                "message": "shared browser lifecycle unavailable",
                            },
                        }
                        for domain in selected
                        if domain.id not in seen
                    ),
                ],
            }
        raise
    finally:
        if control is not None:
            control.release()
        if login_lock is not None:
            login_lock.release()
