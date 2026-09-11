"""Configuration loading and validation.

Default locations (ADR 0003), both overridable for tests:

- config: ``~/.config/dogopencli/config.toml`` (env ``DOGOPENCLI_CONFIG``)
- cache:  ``~/.local/share/dogopencli/cache.sqlite3`` (config key ``cache.path``)
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import CONFIG_ERROR, EXIT_USAGE, CliError

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

CONFIG_ENV = "DOGOPENCLI_CONFIG"
DEFAULT_CONFIG = Path.home() / ".config" / "dogopencli" / "config.toml"
DEFAULT_CACHE = Path.home() / ".local" / "share" / "dogopencli" / "cache.sqlite3"
DEFAULT_TTL_HOURS = 72.0

SOURCE_SNAPSHOT = "snapshot"
SOURCE_CDP = "cdp"


@dataclass(frozen=True)
class SourceConfig:
    kind: str
    path: Path | None
    dataset_id: str | None


@dataclass(frozen=True)
class Config:
    cache_path: Path
    ttl_hours: float
    sources: dict[str, SourceConfig]


def _config_error(message: str) -> CliError:
    return CliError(CONFIG_ERROR, message, exit_code=EXIT_USAGE)


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV)
    if override is not None:
        if not override.strip():
            raise _config_error(f"{CONFIG_ENV} is empty")
        return Path(override)
    return DEFAULT_CONFIG


def _source(section: Any, key: str) -> SourceConfig:
    if not isinstance(section, dict):
        raise _config_error(f"[sources.{key}] must be a table")
    allowed = {"kind", "path", "dataset_id"}
    unknown = set(section) - allowed
    if unknown:
        raise _config_error(f"[sources.{key}] unknown keys: {sorted(unknown)}")
    kind = section.get("kind")
    if kind not in (SOURCE_SNAPSHOT, SOURCE_CDP):
        raise _config_error(f"[sources.{key}] kind must be snapshot or cdp")
    raw_path = section.get("path")
    dataset_id = section.get("dataset_id")
    if dataset_id is not None and not isinstance(dataset_id, str):
        raise _config_error(f"[sources.{key}] dataset_id must be a string")
    path = None
    if kind == SOURCE_SNAPSHOT:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise _config_error(f"[sources.{key}] snapshot source requires path")
        path = Path(raw_path)
    return SourceConfig(kind=kind, path=path, dataset_id=dataset_id)


def load(source_keys: list[str]) -> Config:
    path = config_path()
    if not path.is_file():
        raise _config_error(f"config file not found: {path}")
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as error:
        raise _config_error(f"invalid config file: {error}") from error
    if not isinstance(document, dict):
        raise _config_error("config root must be a table")
    cache_section = document.get("cache", {})
    if not isinstance(cache_section, dict):
        raise _config_error("[cache] must be a table")
    unknown_cache = set(cache_section) - {"path", "ttl_hours"}
    if unknown_cache:
        raise _config_error(f"[cache] unknown keys: {sorted(unknown_cache)}")
    raw_cache = cache_section.get("path")
    if raw_cache is not None and not isinstance(raw_cache, str):
        raise _config_error("cache.path must be a string")
    ttl = cache_section.get("ttl_hours", DEFAULT_TTL_HOURS)
    if isinstance(ttl, bool) or not isinstance(ttl, int | float) or ttl < 0:
        raise _config_error("cache.ttl_hours must be a non-negative number")
    sources_section = document.get("sources", {})
    if not isinstance(sources_section, dict):
        raise _config_error("[sources] must be a table")
    sources: dict[str, SourceConfig] = {}
    for key in source_keys:
        section = sources_section.get(key)
        if section is None:
            raise _config_error(f"missing [sources.{key}] configuration")
        sources[key] = _source(section, key)
    cache_path = Path(raw_cache) if raw_cache else DEFAULT_CACHE
    return Config(cache_path=cache_path, ttl_hours=float(ttl), sources=sources)
