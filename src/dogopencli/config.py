"""Shared configuration location and explicit Duckdog selector configuration."""

import math
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import CONFIG_ERROR, EXIT_USAGE, CliError

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

CONFIG_ENV = "DOGOPENCLI_CONFIG"
CONFIG_DIR_ENV = "DOGOPENCLI_CONFIG_DIR"
DEFAULT_CONFIG = Path.home() / ".config" / "dogopencli" / "config.toml"
DEFAULT_TTL_HOURS = 72.0


def cache_ttl_hours(config_file: Path) -> float:
    """Resolve the shared cache retention policy without creating configuration."""
    try:
        document = (
            tomllib.loads(config_file.read_text()) if config_file.exists() else {}
        )
        value = document.get("cache", {}).get("ttl_hours", DEFAULT_TTL_HOURS)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError
        return float(value)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError) as error:
        raise _config_error(
            "cache.ttl_hours must be a finite nonnegative number"
        ) from error


def _config_error(message: str) -> CliError:
    return CliError(CONFIG_ERROR, message, exit_code=EXIT_USAGE)


def config_path(explicit_dir: str | Path | None = None) -> Path:
    """One precedence for auth and queries: explicit dir > env dir > env file."""
    directory = (
        explicit_dir if explicit_dir is not None else os.environ.get(CONFIG_DIR_ENV)
    )
    if directory is not None:
        if not str(directory).strip():
            raise _config_error("configuration directory cannot be empty")
        return Path(directory).expanduser().resolve() / DEFAULT_CONFIG.name
    override = os.environ.get(CONFIG_ENV)
    if override is not None:
        if not override.strip():
            raise _config_error(f"{CONFIG_ENV} is empty")
        return Path(override).expanduser().resolve()
    return DEFAULT_CONFIG


@dataclass(frozen=True)
class DuckdogConfig:
    path: Path
    selectors: dict[str, str]


def load_duckdog(config_file: Path | None = None) -> DuckdogConfig:
    """Load optional selector configuration only when enumeration is requested."""
    location = config_file if config_file is not None else config_path()
    try:
        document = tomllib.loads(location.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as error:
        raise _config_error(
            "duckdog requires a readable valid configuration"
        ) from error
    section = document.get("duckdog")
    if not isinstance(section, dict) or set(section) - {"path", "selectors"}:
        raise _config_error("configure [duckdog] path and [duckdog.selectors]")
    raw_path = section.get("path")
    selectors = section.get("selectors")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise _config_error("duckdog.path must be a nonempty database path")
    if not isinstance(selectors, dict) or any(
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(relation, str)
        or not relation.strip()
        or "\x00" in relation
        for name, relation in selectors.items()
    ):
        raise _config_error("duckdog.selectors must map logical names to relations")
    database = Path(raw_path).expanduser()
    if not database.is_absolute():
        database = location.resolve().parent / database
    return DuckdogConfig(database, selectors)
