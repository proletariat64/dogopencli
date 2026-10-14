"""Import complete live settings into Parquet and publish a DuckDB view."""

import argparse
import datetime as dt
import decimal
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

B03_STORAGE_VERSION = 1
B03_DETAIL_REFRESH = True

REGISTRY = {
    "liquidity/reference/banks": {
        "identity": "bankId",
        "columns": ("bankId", "bankName", "countryCode", "bankSwiftCode"),
    },
    "liquidity/reference/entities": {
        "identity": "id",
        "columns": ("id", "instId", "instCode", "instName", "state"),
    },
}

# Declared list identities from the public CLI describe contracts. Reference
# directories use the same current-only replacement policy as settings.
for _leaf, _identity in {
    "cash/accounts": ("aliasName", "currency"),
    "cash/groups": ("id",),
    "cash/pools": ("id",),
    "cash/credit-lines": ("id",),
    "investment/products": ("incrementProductId",),
    "investment/strategies": ("strategyRuleCode",),
    "investment/benchmarks": ("id",),
    "risk/thresholds": ("benchmarkId",),
    "risk/sla": ("slaConfigId",),
    "rules/funding": ("id",),
    "rules/operation": ("ruleId",),
    "rules/realtime": ("id",),
    "rules/action-mapping": ("id",),
    "rules/fx-settlement": ("id",),
    "rules/notification": ("id",),
    "rules/forecast": ("ruleId",),
    "rules/waterlevel": ("bufferId",),
    "rules/transfer": ("ruleId",),
    "network/realtime": ("id",),
    "network/bank-baselines": ("aliasName",),
    "network/account-capabilities": ("id",),
    "ledger/customers": ("customerNo", "version"),
}.items():
    REGISTRY["liquidity/" + _leaf] = {
        "identity": _identity,
        "columns": _identity,
    }
REGISTRY["liquidity/cash/groups"]["scope"] = {"equiCurrency": "USD"}
REGISTRY["liquidity/cash/groups"]["query"] = {"equiCurrency": "USD"}


class ImportRejected(ValueError):
    """Candidate rejected before publication; previous dataset is preserved."""


RETIRED_SELECTORS = frozenset(
    "liquidity/pricing/" + resource
    for resource in (
        "factors",
        "factor-values",
        "cost-prices",
        "strategies",
        "client-prices",
        "fee-orders",
    )
)


def reject_retired(selector):
    if selector in RETIRED_SELECTORS:
        raise ImportRejected(
            f"{selector} is retired: cost/revenue business discontinued (B01/#164)"
        )


def encode(value):
    """Preserve JSON numbers, nested values and unknown fields without floats."""
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            raise ImportRejected("non-finite JSON number")
        return str(value)
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(
                json.dumps(key, ensure_ascii=False) + ":" + encode(value[key])
                for key in sorted(value)
            )
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(encode(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def reject_constant(value):
    raise ImportRejected("non-finite JSON number")


def validate(text, selector):
    reject_retired(selector)
    envelope = json.loads(
        text, parse_float=decimal.Decimal, parse_constant=reject_constant
    )
    if not isinstance(envelope, dict) or envelope.get("error") is not None:
        raise ImportRejected("source envelope contains an error")
    rows, meta = envelope.get("data"), envelope.get("meta")
    if not isinstance(rows, list) or not isinstance(meta, dict):
        raise ImportRejected("expected data array and acquisition metadata")
    expected = selector.replace("/", ".") + ".list"
    if meta.get("capability") != expected or meta.get("source") != "live":
        raise ImportRejected("wrong capability or non-live source")
    if meta.get("simulated") is not False or meta.get("complete") is not True:
        raise ImportRejected("candidate must be real and complete")
    if meta.get("has_more") is not False:
        raise ImportRejected("candidate display is truncated")
    if meta.get("scope") != REGISTRY[selector].get("scope", {}) or meta.get(
        "query"
    ) != REGISTRY[selector].get("query", {}):
        raise ImportRejected("settings replacement requires unfiltered scope")
    for key in ("returned_count", "matched_total", "collected_total", "reported_total"):
        count = meta.get(key)
        if type(count) is not int or count != len(rows):
            raise ImportRejected(f"count mismatch: {key}")
    acquired = dt.datetime.fromisoformat(meta.get("fetched_at", ""))
    if acquired.tzinfo is None:
        raise ImportRejected("capture time requires an explicit time zone")
    identity = REGISTRY[selector]["identity"]
    identity = (identity,) if isinstance(identity, str) else identity
    seen, native_ids = set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise ImportRejected("business records must be objects")
        key = []
        for field in identity:
            value = row.get(field)
            if not isinstance(value, (str, int)) or isinstance(value, bool):
                raise ImportRejected("missing or invalid native identity")
            if not str(value).strip():
                raise ImportRejected("blank native identity")
            # Preserve tuple boundaries for compound native identities.
            key.append(str(value))
        key = tuple(key)
        if key in seen:
            raise ImportRejected("blank or duplicate native identity")
        seen.add(key)
        if selector.endswith("/entities"):
            native = row.get("instId")
            if (
                not isinstance(native, str)
                or not native.strip()
                or native in native_ids
            ):
                raise ImportRejected("missing or duplicate instId")
            native_ids.add(native)
    return rows, meta


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


def newer_realtime_details(
    connection: Any, previous_parquet: str, rows: list[dict[str, Any]]
) -> bool:
    """Order detail refreshes within an unchanged saved list acquisition."""
    previous_rows = [
        json.loads(raw, parse_float=decimal.Decimal, parse_constant=reject_constant)
        for (raw,) in connection.execute(
            "SELECT record FROM read_parquet(?) ORDER BY _row_order",
            [previous_parquet],
        ).fetchall()
    ]
    reserved = {"_detail", "_detail_meta", "_detail_storage"}

    def roots(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in row.items() if key not in reserved}
            for row in values
        ]

    if encode(roots(rows)) != encode(roots(previous_rows)):
        return False
    advanced = False
    for current, previous in zip(rows, previous_rows, strict=True):
        current_meta = current.get("_detail_meta")
        previous_meta = previous.get("_detail_meta")
        if current_meta is None:
            if previous_meta is not None:
                return False
            continue
        current_time = dt.datetime.fromisoformat(current_meta["fetched_at"])
        if current_time.tzinfo is None:
            raise ImportRejected("detail capture time requires timezone")
        if previous_meta is None:
            advanced = True
            continue
        previous_time = dt.datetime.fromisoformat(previous_meta["fetched_at"])
        if previous_time.tzinfo is None:
            raise ImportRejected("previous detail capture time requires timezone")
        if current_time < previous_time:
            return False
        if current_time == previous_time:
            if encode({k: v for k, v in current.items() if k in reserved}) != encode(
                {k: v for k, v in previous.items() if k in reserved}
            ):
                return False
        else:
            advanced = True
    return advanced


def publish(root, selector, text):
    rows, meta = validate(text, selector)
    import duckdb

    relation = selector.replace("/", "_")
    digest = hashlib.sha256(encode(rows).encode()).hexdigest()
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / ".import.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db_dir = root / "duckdb"
        db_dir.mkdir(exist_ok=True)
        db_path = db_dir / "duckdog.duckdb"
        with duckdb.connect(str(db_path)) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS _duckdog_datasets (
                    selector VARCHAR PRIMARY KEY, kind VARCHAR NOT NULL,
                    relation_name VARCHAR NOT NULL, parquet_path VARCHAR NOT NULL,
                    content_sha256 VARCHAR NOT NULL, row_count BIGINT NOT NULL,
                    fetched_at TIMESTAMPTZ NOT NULL, imported_at TIMESTAMPTZ NOT NULL,
                    acquisition_metadata JSON NOT NULL
                )
            """)
            previous = connection.execute(
                "SELECT parquet_path, content_sha256, epoch(fetched_at) "
                "FROM _duckdog_datasets WHERE selector = ?",
                [selector],
            ).fetchone()
            acquired = dt.datetime.fromisoformat(meta["fetched_at"])
            if previous and acquired.timestamp() < previous[2]:
                raise ImportRejected("older acquisition cannot replace a newer dataset")
            if (
                previous
                and acquired.timestamp() == previous[2]
                and digest != previous[1]
            ):
                if (
                    selector != "liquidity/network/realtime"
                    or not newer_realtime_details(connection, previous[0], rows)
                ):
                    raise ImportRejected("same capture time has conflicting content")
            leaf_dir = root / "parquet" / selector
            leaf_dir.mkdir(parents=True, exist_ok=True)
            parquet = leaf_dir / (uuid.uuid4().hex + ".parquet")
            # Reuse a verified identical generation; update capture metadata only.
            reuse = bool(
                previous and digest == previous[1] and Path(previous[0]).is_file()
            )
            if reuse:
                parquet = Path(previous[0])
            else:
                try:
                    with tempfile.TemporaryDirectory(
                        prefix=".stage-", dir=leaf_dir
                    ) as temp:
                        os.chmod(temp, 0o700)
                        source = Path(temp) / "records.jsonl"
                        with source.open("w", encoding="utf-8") as stream:
                            for position, row in enumerate(rows):
                                stream.write(
                                    encode(
                                        {"_row_order": position, "record": encode(row)}
                                    )
                                    + "\n"
                                )
                        connection.execute(
                            "CREATE TEMP TABLE candidate "
                            "(_row_order BIGINT, record JSON)"
                        )
                        if rows:
                            connection.execute(
                                "INSERT INTO candidate SELECT _row_order, record::JSON "
                                "FROM read_json(?, format='newline_delimited', "
                                "columns={_row_order:'BIGINT', record:'VARCHAR'})",
                                [str(source)],
                            )
                        staged = Path(temp) / "candidate.parquet"
                        connection.execute(
                            "COPY candidate TO "
                            + literal(staged)
                            + " (FORMAT PARQUET, COMPRESSION ZSTD)"
                        )
                        count = connection.execute(
                            "SELECT count(*) FROM read_parquet(?)", [str(staged)]
                        ).fetchone()[0]
                        if count != len(rows):
                            raise ImportRejected("Parquet verification count mismatch")
                        staged.rename(parquet)
                except BaseException:
                    parquet.unlink(missing_ok=True)
                    raise
            columns = ["_row_order", "record AS _record"]
            for column in REGISTRY[selector]["columns"]:
                columns.append(
                    "json_extract_string(record, "
                    + literal("$." + column)
                    + ") AS "
                    + identifier(column)
                )
            try:
                connection.execute("BEGIN TRANSACTION")
                connection.execute(
                    "CREATE OR REPLACE VIEW "
                    + identifier(relation)
                    + " AS SELECT "
                    + ", ".join(columns)
                    + " FROM read_parquet("
                    + literal(parquet)
                    + ")"
                )
                if connection.execute(
                    "SELECT count(*) FROM " + identifier(relation)
                ).fetchone()[0] != len(rows):
                    raise ImportRejected(
                        "published relation verification count mismatch"
                    )
                connection.execute(
                    "INSERT OR REPLACE INTO _duckdog_datasets "
                    "VALUES (?, 'settings', ?, ?, ?, ?, ?, now(), ?)",
                    [
                        selector,
                        relation,
                        str(parquet),
                        digest,
                        len(rows),
                        meta["fetched_at"],
                        encode(
                            {
                                "application": "dogopencli",
                                "domain": selector.split("/")[0],
                                "leaf": selector,
                                "command": [
                                    "dogopencli",
                                    *selector.split("/"),
                                    "list",
                                    "--live",
                                    "--limit",
                                    "0",
                                    "--offset",
                                    "0",
                                    "--require-complete",
                                    "--format",
                                    "json",
                                ],
                                "acquisition": meta,
                            }
                        ),
                    ],
                )
                if selector == "liquidity/network/realtime":
                    expected = [encode(row) for row in rows]
                    for sql in (
                        "SELECT _record FROM "
                        + identifier(relation)
                        + " ORDER BY _row_order",
                        "SELECT record FROM read_parquet("
                        + literal(parquet)
                        + ") ORDER BY _row_order",
                    ):
                        if [
                            r[0] for r in connection.execute(sql).fetchall()
                        ] != expected:
                            raise ImportRejected("realtime full readback mismatch")
                    registry = connection.execute(
                        "SELECT parquet_path, content_sha256, row_count, "
                        "acquisition_metadata "
                        "FROM _duckdog_datasets WHERE selector = ?",
                        [selector],
                    ).fetchone()
                    if registry[:3] != (str(parquet), digest, len(rows)):
                        raise ImportRejected("realtime registry verification mismatch")
                    if (
                        json.loads(registry[3], parse_float=decimal.Decimal)[
                            "acquisition"
                        ]
                        != meta
                    ):
                        raise ImportRejected("realtime metadata verification mismatch")
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                if not reuse:
                    parquet.unlink(missing_ok=True)
                raise
        # Under the writer lock, remove unreferenced generations for this leaf only.
        cleanup_pending = False
        for old in (
            ()
            if selector == "liquidity/network/realtime"
            else leaf_dir.glob("*.parquet")
        ):
            if old != parquet:
                try:
                    old.unlink()
                except OSError:
                    cleanup_pending = True
        return {
            "selector": selector,
            "kind": "settings",
            "rows": len(rows),
            "complete": True,
            "fetched_at": meta["fetched_at"],
            "database": str(db_path),
            "relation": relation,
            "parquet": str(parquet),
            "reused_content": reuse,
            "cleanup_pending": cleanup_pending,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selector", required=True, choices=sorted(set(REGISTRY) | RETIRED_SELECTORS)
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--input",
        type=Path,
        help="Existing complete live JSON envelope; otherwise query dogopencli",
    )
    args = parser.parse_args()
    try:
        reject_retired(args.selector)
        if args.input:
            text = args.input.read_text(encoding="utf-8")
        else:
            command = [
                "dogopencli",
                *args.selector.split("/"),
                "list",
                "--live",
                "--limit",
                "0",
                "--offset",
                "0",
                "--require-complete",
                "--format",
                "json",
            ]
            process = subprocess.run(
                command, capture_output=True, text=True, timeout=300
            )
            if process.returncode:
                raise ImportRejected("live query failed; no dataset was published")
            text = process.stdout
        print(json.dumps(publish(args.root, args.selector, text), ensure_ascii=False))
    except Exception as error:
        # Never echo source response bodies, row identifiers or auth diagnostics.
        result = {"error": type(error).__name__, "published": False}
        if args.selector in RETIRED_SELECTORS:
            result.update(code="UNSUPPORTED_CAPABILITY", message=str(error))
        print(
            json.dumps(result),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
