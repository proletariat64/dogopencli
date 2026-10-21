"""Read-only account ownership sources exposed to opted-in custom inquiries."""

from pathlib import Path

from dogopencli.cache import Cache
from dogopencli.duckdog import AccountSourceUnavailable, read_account_records
from dogopencli.errors import INVALID_RESPONSE, CliError
from dogopencli.jsonutil import parse


def read_account_directory(source: str, config_file: Path) -> dict | None:
    """Keep absent optional sources distinct from malformed configured storage."""
    if source == "duckdog":
        try:
            records = read_account_records(config_file=config_file)
        except AccountSourceUnavailable:
            return None
        return {"records": records, "quality": {}}
    if source != "cache":
        raise CliError("REQUEST_NOT_ALLOWED", "unsupported account directory source")
    snapshot, stored = Cache(config_file.parent / "leaf-cache.sqlite3").read(
        "leaf:liquidity.cash.accounts"
    )
    if snapshot is None:
        return None
    if len(stored) != snapshot.row_count or len(stored) > 100000:
        raise CliError(INVALID_RESPONSE, "cached account directory row count conflicts")
    try:
        records = [parse(body) for _, body in stored]
    except ValueError as error:
        raise CliError(
            INVALID_RESPONSE, "cached account directory is malformed"
        ) from error
    if any(not isinstance(row, dict) for row in records):
        raise CliError(
            INVALID_RESPONSE, "cached account directory contains invalid records"
        )
    return {
        "records": records,
        "quality": {
            "complete": snapshot.backend_complete,
            "dataset_complete": snapshot.dataset_complete,
            "simulated": snapshot.simulated,
            "fetched_at": snapshot.fetched_at,
            "acquisition": snapshot.acquisition,
        },
    }
