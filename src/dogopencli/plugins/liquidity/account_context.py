"""Ordered, read-only account ownership resolution for single-account queries."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...duckdog import AccountSourceUnavailable, read_account_records
from ...errors import (
    AUTH_REQUIRED,
    BROWSER_UNAVAILABLE,
    CACHE_MISS,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    SOURCE_DATA_MISSING,
    TIMEOUT,
    CliError,
)


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
    cached_accounts: Callable[[], list[dict]],
    live_accounts: Callable[[], list[dict]],
    config_file: Path | None = None,
    duckdog_accounts: Callable[[], list[dict]] | None = None,
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
                INVALID_ARGUMENT, f"--{name} requires one nonempty explicit value"
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
        if not resolved_entity or not resolved_bank:
            note["status"] = "missing_fields"
            continue
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (resolved_entity, resolved_bank)
        ):
            raise CliError(
                INVALID_RESPONSE,
                f"{source} account directory has malformed ownership fields",
            )
        note["status"] = "selected"
        return AccountContext(
            alias,
            resolved_entity,
            resolved_bank,
            {
                "source": source,
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
