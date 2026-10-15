"""Ordered, read-only account ownership resolution for single-account queries."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...duckdog import AccountSourceUnavailable, read_account_records
from ...errors import (
    AUTH_REQUIRED,
    BROWSER_UNAVAILABLE,
    CACHE_MISS,
    EXIT_USAGE,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    SOURCE_DATA_MISSING,
    TIMEOUT,
    CliError,
)


@dataclass(frozen=True)
class AccountDirectory:
    """Rows and acquisition quality from an existing account directory."""

    rows: list[dict]
    quality: dict


@dataclass(frozen=True)
class AccountContext:
    alias: str
    entity: str
    bank: str
    metadata: dict


def resolve_account_context(
    alias: str,
    entity: str | None = None,
    bank: str | None = None,
    *,
    cached_accounts: Callable[[], list[dict] | AccountDirectory],
    live_accounts: Callable[[], list[dict] | AccountDirectory],
    config_file: Path | None = None,
    duckdog_accounts: Callable[[], list[dict] | AccountDirectory] | None = None,
) -> AccountContext:
    """Resolve ownership without overwriting explicit account constraints."""
    for name, value in (("alias", alias), ("entity", entity), ("bank", bank)):
        if value is None and name != "alias":
            continue
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
            or "," in value
            or value.upper() == "ANY"
        ):
            raise CliError(
                INVALID_ARGUMENT,
                f"--{name} requires one nonempty explicit value",
                exit_code=EXIT_USAGE,
            )
    if entity and bank:
        return AccountContext(
            alias, entity, bank, {"source": "explicit", "sources": [], "warnings": []}
        )
    sources: list[dict] = []
    warnings: list[dict] = []
    reader = duckdog_accounts or (lambda: read_account_records(config_file=config_file))
    for source, read in (
        ("duckdog", reader),
        ("cache", cached_accounts),
        ("live", live_accounts),
    ):
        try:
            records = read()
        except AccountSourceUnavailable as error:
            sources.append(
                {"source": source, "status": "unavailable", "reason": str(error)}
            )
            continue
        except CliError as error:
            if source == "cache" and error.code == CACHE_MISS:
                sources.append(
                    {
                        "source": source,
                        "status": "unavailable",
                        "reason": "account cache slot absent",
                    }
                )
                continue
            if source == "live" and error.code in {
                AUTH_REQUIRED,
                BROWSER_UNAVAILABLE,
                TIMEOUT,
            }:
                raise CliError(
                    error.code,
                    error.message
                    + "; restore connection, run dogopencli login --domain liquidity, "
                    "then rerun the original query",
                    retryable=error.retryable,
                    exit_code=error.exit_code,
                    meta=error.meta,
                ) from error
            raise
        quality = records.quality if isinstance(records, AccountDirectory) else {}
        if isinstance(records, AccountDirectory):
            records = records.rows
        if not isinstance(quality, dict):
            raise CliError(INVALID_RESPONSE, f"{source} directory quality is malformed")
        for warning in quality.get("warnings", []):
            if not isinstance(warning, dict):
                raise CliError(
                    INVALID_RESPONSE, f"{source} directory warning is malformed"
                )
            warnings.append({**warning, "source": source})
        if not isinstance(records, list) or any(
            not isinstance(row, dict) for row in records
        ):
            raise CliError(
                INVALID_RESPONSE, f"{source} account directory must return records"
            )
        matches = [
            row
            for row in records
            if row.get("aliasName") == alias
            and (entity is None or row.get("instId") == entity)
            and (bank is None or row.get("bankId") == bank)
        ]
        note = {"source": source, "status": "no_match", "match_count": len(matches)}
        if quality:
            note["quality"] = quality
        sources.append(note)
        if not matches:
            continue
        selected = matches[0]
        if len(matches) > 1:
            warnings.append(
                {
                    "code": "ACCOUNT_CONTEXT_MULTIPLE_MATCHES",
                    "source": source,
                    "match_count": len(matches),
                    "selected": {
                        key: selected.get(key)
                        for key in ("aliasName", "instId", "bankId")
                    },
                    "message": (
                        f"{source} account directory has {len(matches)} matching rows; "
                        "first source row selected"
                    ),
                }
            )
        resolved_entity = entity if entity is not None else selected.get("instId")
        resolved_bank = bank if bank is not None else selected.get("bankId")
        if any(
            value is not None and not isinstance(value, str)
            for value in (resolved_entity, resolved_bank)
        ):
            raise CliError(
                INVALID_RESPONSE,
                f"{source} account directory has malformed ownership fields",
            )
        if any(
            value is None or not value.strip()
            for value in (resolved_entity, resolved_bank)
        ):
            note["status"] = "missing_fields"
            continue
        note["status"] = "selected"
        return AccountContext(
            alias,
            resolved_entity,
            resolved_bank,
            {
                "source": source,
                "directory_quality": quality,
                "sources": sources,
                "warnings": warnings,
                "ownership_reference": (
                    "current account directory; historical ownership is not established"
                ),
            },
        )
    raise CliError(
        SOURCE_DATA_MISSING,
        "no account directory record resolves the requested alias "
        "and explicit ownership constraints",
        meta={"account_context": {"sources": sources, "warnings": warnings}},
    )
