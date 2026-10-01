"""Authenticated, inquiry-only CDP lifetime; never launches or logs in Chrome."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from .browser import errors as auth_errors
from .browser.cdp import CdpTransport, make_transport, url_origin
from .browser.coordination import acquire_browser_control
from .browser.environment import resolve_environment
from .browser.errors import AuthError
from .browser.probe import check_authentication, probe_entry
from .errors import AUTH_REQUIRED, BROWSER_UNAVAILABLE, LOCKED, CliError
from .plugins import TransportCapability
from .transport.cdp import CdpQueryTransport


def _map_auth_error(error: AuthError) -> CliError:
    if error.code == auth_errors.AUTH_REQUIRED:
        return CliError(AUTH_REQUIRED, error.message)
    if error.code == auth_errors.BROWSER_BUSY:
        return CliError(LOCKED, error.message, retryable=True)
    return CliError(BROWSER_UNAVAILABLE, error.message, retryable=True)


class InquirySession:
    """Own all capability transports under one authenticated browser lease."""

    def __init__(self, cdp: CdpTransport, page_url: str, resources: ExitStack):
        self._cdp = cdp
        self._page_url = page_url
        self._resources = resources
        # The entry probe at session setup verified this origin; peer plugin
        # origins are verified lazily, once per session and per origin.
        self._verified_origins = {url_origin(page_url)}

    def transport(self, capability: TransportCapability) -> CdpQueryTransport:
        # Peer plugins declare their verified application entry; sharing the
        # core never assumes another domain's base URL applies (ADR 0015).
        page_url = getattr(capability, "page_url", None) or self._page_url
        origin = url_origin(page_url)
        if origin not in self._verified_origins:
            try:
                probe_entry(self._cdp, page_url)
            except AuthError as error:
                raise _map_auth_error(error) from error
            self._verified_origins.add(origin)
        transport = CdpQueryTransport(self._cdp, capability, page_url=page_url)
        self._resources.callback(transport.close)
        return transport


@contextmanager
def inquiry_session(
    *, config_file: Path, startup_url: str | None = None
) -> Iterator[InquirySession]:
    """Check an existing session and release targets before its shared lock.

    ExitStack also releases earlier resources if auth or later transport setup
    fails. Browser errors cross into the business error protocol at this seam.
    """
    with ExitStack() as resources:
        try:
            environment = resolve_environment(config_file=config_file)
            control = acquire_browser_control(environment.profile, shared=True)
            resources.callback(control.release)
            check_authentication(environment, startup_url=startup_url)
            cdp = make_transport(environment.cdp_url)
        except AuthError as error:
            raise _map_auth_error(error) from error
        yield InquirySession(cdp, startup_url or environment.startup_url, resources)
