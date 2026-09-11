"""Snapshot transport: serves the registered Channel query from a prepared
offline dataset (ADR 0005).

It applies the same validated request shape, grounded exact filtering and
one-based pagination, and produces the same success envelope as the
backend. Local seqid values are stripped from simulated responses; the
output layer restores them from the dataset's deterministic order.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..errors import (
    REQUEST_NOT_ALLOWED,
    SOURCE_DATA_INVALID,
    SOURCE_DATA_MISSING,
    SOURCE_SCOPE_UNAVAILABLE,
    CliError,
)
from ..jsonutil import canonical, parse
from ..plugins import Capability
from . import OriginMetadata, QueryRequest, TransportResponse, validate_request

DATASET_FILES = ("manifest.json", "records.jsonl", "provenance.jsonl")


def _missing(message: str) -> CliError:
    return CliError(SOURCE_DATA_MISSING, message)


def _invalid_dataset(message: str) -> CliError:
    return CliError(SOURCE_DATA_INVALID, message)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _observed(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise _invalid_dataset(f"manifest {field} must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise _invalid_dataset(f"manifest {field} is not a timestamp") from error
    if parsed.tzinfo is None:
        raise _invalid_dataset(f"manifest {field} must carry a timezone")
    return value


@dataclass(frozen=True)
class ChannelDataset:
    dataset_id: str
    scope: str
    records: list[dict[str, Any]]
    identity: dict[str, int]
    row_count: int
    source_observed_from: str
    source_observed_to: str
    simulated: bool
    dataset_complete: bool
    backend_complete: bool


def read_manifest(path: Path, capability: str) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise _missing(f"dataset manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (ValueError, OSError) as error:
        raise _invalid_dataset("dataset manifest is not readable JSON") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise _invalid_dataset("unsupported dataset manifest schema")
    if manifest.get("capability") != capability:
        raise _invalid_dataset("dataset capability mismatch")
    scope = manifest.get("scope")
    if not isinstance(scope, str) or not scope:
        raise _invalid_dataset("dataset scope missing")
    return manifest


def load_dataset(
    path: Path, capability: str, expected_dataset_id: str | None
) -> ChannelDataset:
    if not path.is_dir():
        raise _missing(f"dataset directory not found: {path}")
    raw: dict[str, bytes] = {}
    for name in DATASET_FILES:
        file_path = path / name
        if not file_path.is_file():
            raise _missing(f"dataset file not found: {file_path}")
        raw[name] = file_path.read_bytes()
    manifest = read_manifest(path, capability)
    dataset_id = manifest.get("dataset_id")
    row_count = manifest.get("row_count")
    for key in ("records_sha256", "provenance_sha256"):
        if not isinstance(manifest.get(key), str):
            raise _invalid_dataset(f"manifest {key} missing")
    if not isinstance(dataset_id, str) or len(dataset_id) != 64:
        raise _invalid_dataset("manifest dataset_id invalid")
    if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 1:
        raise _invalid_dataset("manifest row_count invalid")
    if manifest.get("simulated") is not True:
        raise _invalid_dataset("dataset must be marked simulated")
    if manifest.get("dataset_complete") is not True:
        raise _invalid_dataset("dataset is not a complete prepared set")
    if manifest.get("backend_complete") is not False:
        raise _invalid_dataset("substitute dataset cannot claim backend coverage")
    observed_from = _observed(
        manifest.get("source_observed_from"), "source_observed_from"
    )
    observed_to = _observed(manifest.get("source_observed_to"), "source_observed_to")
    if _digest(raw["records.jsonl"]) != manifest["records_sha256"]:
        raise _invalid_dataset("records.jsonl hash mismatch")
    if _digest(raw["provenance.jsonl"]) != manifest["provenance_sha256"]:
        raise _invalid_dataset("provenance.jsonl hash mismatch")
    if _digest(raw["records.jsonl"] + raw["provenance.jsonl"]) != dataset_id:
        raise _invalid_dataset("dataset_id does not match dataset files")
    if expected_dataset_id is not None and dataset_id != expected_dataset_id:
        raise _invalid_dataset("dataset_id does not match configured source identity")
    scope = manifest["scope"]
    try:
        records = [
            parse(line)
            for line in raw["records.jsonl"].decode().splitlines()
            if line.strip()
        ]
        provenance = [
            parse(line)
            for line in raw["provenance.jsonl"].decode().splitlines()
            if line.strip()
        ]
    except (ValueError, UnicodeDecodeError) as error:
        raise _invalid_dataset("dataset rows are not valid JSON") from error
    if len(records) != row_count or len(provenance) != row_count:
        raise _invalid_dataset("dataset row count mismatch")
    identity: dict[str, int] = {}
    provenance_hashes: dict[int, str] = {}
    for entry in provenance:
        if not isinstance(entry, dict):
            raise _invalid_dataset("invalid provenance entry")
        seqid = entry.get("seqid")
        record_hash = entry.get("record_sha256")
        if (
            isinstance(seqid, bool)
            or not isinstance(seqid, int)
            or seqid in provenance_hashes
            or not isinstance(record_hash, str)
        ):
            raise _invalid_dataset("provenance seqid is not continuous")
        provenance_hashes[seqid] = record_hash
    if set(provenance_hashes) != set(range(1, row_count + 1)):
        raise _invalid_dataset("provenance seqid is not continuous")
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict) or record.get("seqid") != index:
            raise _invalid_dataset("record seqid is not continuous")
        if record.get("payoutType") != scope:
            raise _invalid_dataset("record scope mismatch")
        payload = {k: v for k, v in record.items() if k != "seqid"}
        key = canonical(payload)
        if _digest(key.encode()) != provenance_hashes[index]:
            raise _invalid_dataset("record provenance hash mismatch")
        identity[key] = index
    if len(identity) != row_count:
        raise _invalid_dataset("duplicate records in dataset")
    return ChannelDataset(
        dataset_id=dataset_id,
        scope=scope,
        records=records,
        identity=identity,
        row_count=row_count,
        source_observed_from=observed_from,
        source_observed_to=observed_to,
        simulated=True,
        dataset_complete=True,
        backend_complete=False,
    )


class SnapshotTransport:
    """QueryTransport backed by a fixed prepared dataset; no browser, no network."""

    def __init__(self, dataset: ChannelDataset, capability: Capability) -> None:
        self._dataset = dataset
        self._capability = capability

    def execute(self, request: QueryRequest) -> TransportResponse:
        if request.capability != self._capability.name:
            raise CliError(
                REQUEST_NOT_ALLOWED,
                "snapshot source only serves the registered channel query",
            )
        validate_request(request, self._capability.contract)
        body = request.body
        scope = body.get("payoutType", self._capability.default_scope)
        if scope != self._dataset.scope:
            raise CliError(
                SOURCE_SCOPE_UNAVAILABLE,
                f"snapshot dataset does not cover scope {scope}",
            )
        page_size = body.get("pageSize", self._capability.contract.page_size)
        page_num = body.get("pageNum", 1)
        for value in (page_size, page_num):
            if isinstance(value, bool) or not isinstance(value, int):
                raise CliError(REQUEST_NOT_ALLOWED, "pagination must be integers")
        if page_size < 1:
            raise CliError(REQUEST_NOT_ALLOWED, "pageSize must be positive")
        filters = self._capability.request_filters(body)
        rows = self._capability.filter_records(self._dataset.records, filters)
        total = len(rows)
        total_pages = -(-total // page_size)
        if total == 0:
            echoed_num, page_rows = 0, []
        else:
            echoed_num = min(max(page_num, 1), total_pages)
            start = (echoed_num - 1) * page_size
            page_rows = rows[start : start + page_size]
        items = [
            {key: value for key, value in row.items() if key != "seqid"}
            for row in page_rows
        ]
        envelope = {
            "success": True,
            "status": True,
            "data": None,
            "resultObj": {
                "success": True,
                "code": "IPAY_RS_100000200",
                "pageNum": echoed_num,
                "pageSize": page_size,
                "totalCount": total,
                "totalPages": total_pages,
                "payoutAbilityVOList": items,
            },
        }
        origin = OriginMetadata(
            backend="snapshot",
            simulated=True,
            dataset_id=self._dataset.dataset_id,
            dataset_complete=True,
            backend_complete=False,
            source_observed_from=self._dataset.source_observed_from,
            source_observed_to=self._dataset.source_observed_to,
        )
        return TransportResponse(
            status=200, body=canonical(envelope).encode(), origin=origin
        )
