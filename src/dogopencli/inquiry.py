"""Authenticated, inquiry-only CDP lifetime; never launches or logs in Chrome."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from .browser import errors as auth_errors
from .browser.cdp import CdpTransport, make_transport
from .browser.coordination import acquire_browser_control
from .browser.environment import resolve_environment
from .browser.errors import AuthError
from .browser.probe import check_authentication
from .errors import AUTH_REQUIRED, BROWSER_UNAVAILABLE, LOCKED, CliError
from .plugins import Capability
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

    def transport(self, capability: Capability) -> CdpQueryTransport:
        transport = CdpQueryTransport(self._cdp, capability, page_url=self._page_url)
        self._resources.callback(transport.close)
        return transport


@contextmanager
def inquiry_session(*, config_file: Path) -> Iterator[InquirySession]:
    """Check an existing session and release targets before its shared lock.

    ExitStack also releases earlier resources if auth or later transport setup
    fails. Browser errors cross into the business error protocol at this seam.
    """
    with ExitStack() as resources:
        try:
            environment = resolve_environment(config_file=config_file)
            control = acquire_browser_control(environment.profile, shared=True)
            resources.callback(control.release)
            check_authentication(environment)
            cdp = make_transport(environment.cdp_url)
        except AuthError as error:
            raise _map_auth_error(error) from error
        yield InquirySession(cdp, environment.startup_url, resources)
