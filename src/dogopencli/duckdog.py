"""Read-only external selector adapter; never imports or initializes datasets."""

import re
from pathlib import Path

from .config import load_duckdog
from .errors import CONFIG_ERROR, EXIT_USAGE, CliError

# Only capability-declared bindings may be queried. Never accept arbitrary SQL.
SELECTOR_COLUMNS = {"liquidity/reference/entities": frozenset({"instId"})}
NATIVE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*\Z")


def _error(message: str) -> CliError:
    return CliError(CONFIG_ERROR, message, exit_code=EXIT_USAGE)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def resolve_selector(
    logical_selector: str, column: str, *, config_file: Path | None = None
) -> list[str]:
    """Freeze validated native IDs from one configured relation in stable order."""
    if column not in SELECTOR_COLUMNS.get(logical_selector, ()):
        raise _error("duckdog selector/column is not registered for enumeration")
    configuration = load_duckdog(config_file)
    relation = configuration.selectors.get(logical_selector)
    if relation is None:
        raise _error(f"configure duckdog selector {logical_selector}")
    if not configuration.path.is_file():
        raise _error("duckdog database is missing; configure an existing database")
    try:
        import duckdb
    except ImportError as error:
        raise _error("install dogopencli[duckdog] to use online ANY") from error
    try:
        with duckdb.connect(str(configuration.path), read_only=True) as connection:
            records = connection.execute(
                f"SELECT {_quote(column)} FROM {_quote(relation)} "
                f"ORDER BY {_quote(column)}"
            ).fetchall()
    except duckdb.Error as error:
        raise _error(
            "duckdog selector cannot be read; "
            "check database, relation and native column"
        ) from error
    values: list[str] = []
    seen: set[str] = set()
    for (value,) in records:
        if not isinstance(value, str) or NATIVE_ID.fullmatch(value) is None:
            raise _error("duckdog selector contains malformed native identifiers")
        if value not in seen:
            values.append(value)
            seen.add(value)
    if not values:
        raise _error("duckdog selector is empty; prepare native identifiers before ANY")
    # Source collations can consider differently cased IDs equal. Order native
    # strings explicitly so ties never depend on relation scan order.
    return sorted(values)


class AccountSourceUnavailable(Exception):
    """An optional account source is absent, rather than broken."""


def read_account_records(*, config_file: Path | None = None) -> list[dict]:
    """Read only the registered cash-account ownership columns, in source order.

    No database, relation or SQL is accepted from callers. Missing optional
    configuration/dependency is distinct from failure of configured storage.
    """
    from .config import config_path, tomllib

    location = config_file if config_file is not None else config_path()
    try:
        document = tomllib.loads(location.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise AccountSourceUnavailable("duckdog is not configured") from error
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise _error("duckdog requires a readable valid configuration") from error
    if "duckdog" not in document:
        raise AccountSourceUnavailable("duckdog is not configured")
    configuration = load_duckdog(location)
    relation = configuration.selectors.get("liquidity/cash/accounts")
    if relation is None:
        raise AccountSourceUnavailable(
            "duckdog cash accounts selector is not configured"
        )
    if not configuration.path.is_file():
        raise _error("duckdog database is missing; configure an existing database")
    try:
        import duckdb
    except ImportError as error:
        raise AccountSourceUnavailable(
            "optional dogopencli[duckdog] is not installed"
        ) from error
    try:
        with duckdb.connect(str(configuration.path), read_only=True) as connection:
            cursor = connection.execute(f"SELECT * FROM {_quote(relation)} LIMIT 0")
            available = {column[0] for column in cursor.description}
            columns = [
                name for name in ("aliasName", "bankId", "instId") if name in available
            ]
            if not columns:
                raise _error("duckdog cash accounts has no native ownership columns")
            projection = ", ".join(_quote(name) for name in columns)
            rows = connection.execute(
                f"SELECT {projection} FROM {_quote(relation)} LIMIT 100001"
            ).fetchall()
    except duckdb.Error as error:
        raise _error(
            "duckdog cash accounts cannot be read; check database and relation"
        ) from error
    if len(rows) > 100000:
        raise _error("duckdog cash accounts exceeds the 100000-record read budget")
    records = []
    for values in rows:
        if any(value is not None and not isinstance(value, str) for value in values):
            raise _error(
                "duckdog cash accounts contains malformed native ownership fields"
            )
        records.append(dict(zip(columns, values, strict=True)))
    return records
