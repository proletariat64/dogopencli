"""Page-level CDP cookie clearing for the dedicated local logout.

Ported from DI ``src/diexporter/browser_cdp.py`` (``_domain_matches`` and
``delete_domain_cookies``) at baseline commit
8eb163c6d140554ca167bd50349a85ca224ac342: browser-endpoint cookie calls are
silent no-ops in the deployed Chrome build, so clearing attaches one temporary
target and uses page-level ``Network.getAllCookies`` /
``Network.deleteCookies``. The deletion calls are never trusted as proof —
``browser.logout`` verifies the effect with the bounded startup-origin probe.
"""

from collections.abc import Mapping
from typing import Any

from .cdp import CdpError, CdpSession, CdpTransport, _target_field


def _domain_matches(domain: Any, suffix: str) -> bool:
    """Match the bare suffix or any subdomain; never lookalike hosts.

    A plain ``endswith`` would also match lookalike hosts such as
    ``notantglobal-inc.com``; cookie domains for a family are either the bare
    suffix or carry a leading dot / subdomain.
    """
    if not isinstance(domain, str) or not domain:
        return False
    text = domain.lstrip(".")
    return text == suffix or text.endswith("." + suffix)


def delete_domain_cookies(
    transport: CdpTransport, domain_suffix: str, *, timeout: float = 15.0
) -> int:
    """Delete every cookie in the ``domain_suffix`` family; return the count.

    Page-level clearing (DI Phase B evidence): attaches one temporary target
    and uses page-level ``Network.getAllCookies`` / ``Network.deleteCookies``.
    Other domains' cookies in the same profile are never touched. The deletion
    calls are never trusted as proof — the caller verifies the effect with the
    bounded startup-origin probe.
    """
    target: dict[str, Any] | None = None
    session: CdpSession | None = None
    try:
        target = transport.new_target("about:blank")
        session = transport.open_session(_target_field(target, "webSocketDebuggerUrl"))
        result = session.command("Network.getAllCookies", {}, timeout)
        cookies = result.get("cookies") if isinstance(result, Mapping) else None
        if not isinstance(cookies, list):
            raise CdpError("Network.getAllCookies returned an unusable value")
        family = [
            cookie
            for cookie in cookies
            if isinstance(cookie, Mapping)
            and _domain_matches(cookie.get("domain"), domain_suffix)
        ]
        if any(not isinstance(cookie.get("name"), str) for cookie in family):
            raise CdpError("Network.getAllCookies returned a malformed cookie")
        for cookie in family:
            params: dict[str, Any] = {
                "name": cookie["name"],
                "domain": cookie["domain"],
            }
            path = cookie.get("path")
            if isinstance(path, str) and path:
                params["path"] = path
            session.command("Network.deleteCookies", params, timeout)
        return len(family)
    finally:
        if session is not None:
            session.close()
        if target is not None:
            target_id = target.get("id")
            if isinstance(target_id, str) and target_id:
                transport.close_target(target_id)
