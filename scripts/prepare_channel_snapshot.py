"""Prepare a private, explicitly incomplete Channel dataset from saved exports.

Offline only. Never connects to Chrome or publishes a production cache.
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


def canonical(value: Any) -> str:
    """Canonical JSON without float conversion; only object-key order is ignored."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite number")
        return str(value)
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(json.dumps(k) + ":" + canonical(value[k]) for k in sorted(value))
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(canonical(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def observed(value: str) -> datetime:
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Observation time must have a timezone")
    return date.astimezone(timezone.utc)


def prepare(inputs: list[Path], destination: Path) -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[1]
    destination = destination.resolve()
    if destination.is_relative_to(repo) and not destination.is_relative_to(
        repo / "tmp"
    ):
        raise ValueError(
            "Repository datasets must stay inside the ignored tmp directory"
        )
    if destination.exists():
        raise ValueError("Destination already exists; never overwrite a dataset")
    records: dict[str, dict[str, Any]] = {}
    sources: dict[str, dict[str, Any]] = {}
    references: dict[str, list[dict[str, Any]]] = {}
    for directory in inputs:
        raw = (directory / "records.jsonl").read_bytes()
        manifest_bytes = (directory / "manifest.json").read_bytes()
        source_id = digest(manifest_bytes + b"\n" + raw)
        if source_id in sources:
            continue
        manifest = json.loads(manifest_bytes)
        summary = manifest["summary"]
        if summary["scope"] != "EXTERNAL":
            raise ValueError("Only EXTERNAL exports are supported")
        timestamp = observed(summary["observed_at"])
        rows = [
            json.loads(line, parse_float=Decimal)
            for line in raw.splitlines()
            if line.strip()
        ]
        if len(rows) != summary["exported_rows"] or not rows:
            raise ValueError("Missing rows or manifest count mismatch")
        page_for_seqid: dict[int, int] = {}
        for page in manifest["pages"]:
            if page["outcome"] != "success" or not page["rows_observed"]:
                continue
            start, end = page["seqid_start"], page["seqid_end"]
            if end - start + 1 != page["rows_observed"]:
                raise ValueError("Invalid source page range")
            for seqid in range(start, end + 1):
                if seqid in page_for_seqid:
                    raise ValueError("Overlapping source page ranges")
                page_for_seqid[seqid] = page["page"]
        if set(page_for_seqid) != set(range(1, len(rows) + 1)):
            raise ValueError("Incomplete source-row provenance")
        for index, row in enumerate(rows, 1):
            if type(row.get("seqid")) is not int or row["seqid"] != index:
                raise ValueError("Invalid source seqid")
            if row.get("payoutType") != "EXTERNAL":
                raise ValueError("Source row scope mismatch")
            payload = {k: v for k, v in row.items() if k != "seqid"}
            identity = canonical(payload)
            records.setdefault(identity, payload)
            references.setdefault(identity, []).append(
                {
                    "source_id": source_id,
                    "source_seqid": index,
                    "page": page_for_seqid[index],
                }
            )
        sources[source_id] = {
            "source_id": source_id,
            "records_sha256": digest(raw),
            "manifest_sha256": digest(manifest_bytes),
            "observed_at": timestamp.isoformat(),
            "rows": len(rows),
            "page_size": summary["page_size"],
            "failed_pages": summary["failed_pages"],
            "reported_totals": summary["reported_totals"],
        }
    if not records:
        raise ValueError("No source records")
    ordered = sorted(records, key=lambda text: (digest(text.encode()), text))
    data_lines, provenance_lines = [], []
    for seqid, identity in enumerate(ordered, 1):
        data_lines.append(canonical({"seqid": seqid, **records[identity]}))
        provenance_lines.append(
            canonical(
                {
                    "seqid": seqid,
                    "record_sha256": digest(identity.encode()),
                    "observations": sorted(
                        references[identity],
                        key=lambda x: (x["source_id"], x["source_seqid"]),
                    ),
                }
            )
        )
    data = ("\n".join(data_lines) + "\n").encode()
    provenance = ("\n".join(provenance_lines) + "\n").encode()
    source_list = [sources[k] for k in sorted(sources)]
    dates = [observed(s["observed_at"]) for s in source_list]
    manifest = {
        "schema_version": 1,
        "dataset_id": digest(data + provenance),
        "capability": "payment.channel.list",
        "scope": "EXTERNAL",
        "origin": "production_exports",
        "simulated": True,
        "dataset_complete": True,
        "backend_complete": False,
        "source_observed_from": min(dates).isoformat(),
        "source_observed_to": max(dates).isoformat(),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(records),
        "input_rows": sum(s["rows"] for s in source_list),
        "removed_exact_duplicates": sum(s["rows"] for s in source_list) - len(records),
        "records_sha256": digest(data),
        "provenance_sha256": digest(provenance),
        "sources": source_list,
    }
    destination.mkdir(mode=0o700)
    for name, contents in (
        ("records.jsonl", data),
        ("provenance.jsonl", provenance),
        ("manifest.json", (canonical(manifest) + "\n").encode()),
    ):
        fd = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(contents)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exports", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.exports, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        # Do not echo exception details that may contain original business content.
        print(
            json.dumps(
                {"error": "SOURCE_PREPARATION_FAILED", "kind": type(error).__name__}
            )
        )
        return 1
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "dataset_id",
                    "row_count",
                    "input_rows",
                    "removed_exact_duplicates",
                    "dataset_complete",
                    "backend_complete",
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
