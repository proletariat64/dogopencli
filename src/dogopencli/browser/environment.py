"""Dedicated browser environment: dogopencli profile, CDP endpoint, entry URL.

Replaces the DI ``settings.json`` browser-context resolution (baseline commit
8eb163c6d140554ca167bd50349a85ca224ac342) with dogopencli conventions:
``~/.config/dogopencli/config.toml`` ``[auth]`` overrides, environment
variables, profile under ``~/.local/share/dogopencli/chrome/`` and CDP default
port 9222. Ports 9330-9340 are forbidden everywhere, including configuration
and tests.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .. import config as config_mod
from .errors import CONFIG_INVALID, AuthError

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

PAYMENT_STARTUP_URL = (
    "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
)

DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_CHROME_BIN = "google-chrome"
FORBIDDEN_PORTS = frozenset(range(9330, 9341))

PROFILE_ENV = "DOGOPENCLI_CHROME_PROFILE"
CDP_URL_ENV = "DOGOPENCLI_CHROME_CDP_URL"
CHROME_BIN_ENV = "DOGOPENCLI_CHROME_BIN"
CHROME_LOG_ENV = "DOGOPENCLI_CHROME_LOG"


@dataclass(frozen=True)
class BrowserEnvironment:
    """The single machine-local dedicated browser environment."""

    cdp_url: str
    profile: Path
    startup_url: str
    chrome_bin: str
    log_path: Path


def default_profile() -> Path:
    return Path.home() / ".local" / "share" / "dogopencli" / "chrome"


def _config_error(message: str) -> AuthError:
    return AuthError(CONFIG_INVALID, message, retryable=False)


def cdp_port(cdp_url: str) -> int:
    """Extract and validate the explicit CDP port; 9330-9340 are forbidden."""
    try:
        port = urlparse(cdp_url).port
    except ValueError as exc:
        raise _config_error(f"invalid CDP URL {cdp_url!r}: {exc}") from exc
    if port is None:
        raise _config_error(f"CDP URL must include an explicit port: {cdp_url}")
    if port in FORBIDDEN_PORTS:
        raise _config_error(f"CDP port {port} is forbidden (9330-9340 are reserved)")
    return port


def _auth_section(config_dir: Path) -> dict[str, str]:
    path = config_dir / config_mod.DEFAULT_CONFIG.name
    if not path.is_file():
        return {}
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise _config_error(f"invalid config file: {exc}") from exc
    section = document.get("auth", {})
    if not isinstance(section, dict):
        raise _config_error("[auth] must be a table")
    unknown = set(section) - {"profile", "cdp_url", "chrome_bin"}
    if unknown:
        raise _config_error(f"[auth] unknown keys: {sorted(unknown)}")
    values: dict[str, str] = {}
    for key, value in section.items():
        if not isinstance(value, str) or not value.strip():
            raise _config_error(f"[auth] {key} must be a non-empty string")
        values[key] = value
    return values


def resolve_environment(config_dir: Path) -> BrowserEnvironment:
    """Resolve the dedicated browser environment: defaults < [auth] < env."""
    section = _auth_section(config_dir)
    raw_profile = os.environ.get(PROFILE_ENV) or section.get("profile")
    profile = Path(raw_profile).expanduser() if raw_profile else default_profile()
    cdp_url = os.environ.get(CDP_URL_ENV) or section.get("cdp_url") or DEFAULT_CDP_URL
    chrome_bin = (
        os.environ.get(CHROME_BIN_ENV)
        or section.get("chrome_bin")
        or DEFAULT_CHROME_BIN
    )
    cdp_port(cdp_url)  # validate before any browser work
    raw_log = os.environ.get(CHROME_LOG_ENV)
    log_path = (
        Path(raw_log).expanduser()
        if raw_log
        else profile.parent / "dogopencli-chrome.log"
    )
    return BrowserEnvironment(
        cdp_url=cdp_url,
        profile=profile.resolve(),
        startup_url=PAYMENT_STARTUP_URL,
        chrome_bin=chrome_bin,
        log_path=log_path,
    )
