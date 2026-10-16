"""Shared runtime helpers for liquidity query and refresh flows."""

import argparse
import sys
from datetime import datetime, timezone
from typing import Any

from ... import config as config_mod
from ...errors import CONFIG_ERROR, EXIT_USAGE, CliError
from ...execution import observe_result
from ...jsonutil import canonical
from .leaves import DetailLeaf, ListLeaf


def now() -> datetime:
    return datetime.now(timezone.utc)


def emit(data: Any, meta: Any, error: Any = None) -> None:
    observe_result(meta, error)
    sys.stdout.write(canonical({"data": data, "error": error, "meta": meta}) + "\n")


def load_config() -> config_mod.Config:
    """Liquidity config: the peer plugin requires a cdp source."""
    config = config_mod.load(["liquidity"])
    source = config.sources["liquidity"]
    if source.kind != config_mod.SOURCE_CDP:
        raise CliError(
            CONFIG_ERROR,
            f"source kind {source.kind} is not available for liquidity",
            exit_code=EXIT_USAGE,
        )
    return config


def provided(args: argparse.Namespace, flags: list[str]) -> dict[str, Any]:
    return {flag: getattr(args, flag) for flag in flags}


def scope_flags(leaf: ListLeaf) -> list[str]:
    return [option.flag for option in leaf.options]


def identity_values(args: argparse.Namespace, leaf: DetailLeaf) -> dict[str, str]:
    return {option.flag: getattr(args, option.flag) for option in leaf.spec.identity}
