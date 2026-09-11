"""Unit tests for the snapshot transport boundary and dataset validation."""

import pytest

from dogopencli.errors import (
    REQUEST_NOT_ALLOWED,
    SOURCE_DATA_INVALID,
    SOURCE_DATA_MISSING,
    SOURCE_SCOPE_UNAVAILABLE,
    CliError,
)
from dogopencli.jsonutil import parse
from dogopencli.plugins.payment.channel import CHANNEL_CAPABILITY as CAP
from dogopencli.transport import QueryRequest
from dogopencli.transport.snapshot import (
    ChannelDataset,
    SnapshotTransport,
    load_dataset,
)


def make_dataset(rows: list[dict]) -> ChannelDataset:
    records = [{"seqid": i, **row} for i, row in enumerate(rows, 1)]
    from dogopencli.jsonutil import canonical

    identity = {
        canonical({k: v for k, v in record.items() if k != "seqid"}): record["seqid"]
        for record in records
    }
    return ChannelDataset(
        dataset_id="d" * 64,
        scope="EXTERNAL",
        records=records,
        identity=identity,
        row_count=len(records),
        source_observed_from="2026-01-01T00:00:00+00:00",
        source_observed_to="2026-01-01T01:00:00+00:00",
        simulated=True,
        dataset_complete=True,
        backend_complete=False,
    )


def request(**body) -> QueryRequest:
    return QueryRequest(
        capability=CAP.name,
        method="POST",
        host="ifundboss-api.alipay.com",
        path="/payout/api/ability/search.json",
        body=body,
    )


ROWS = [
    {"abilityId": i, "payoutType": "EXTERNAL", "status": "ENABLE"} for i in range(1, 6)
]


def transport() -> SnapshotTransport:
    return SnapshotTransport(make_dataset(ROWS), CAP)


def execute_page(body: bytes) -> dict:
    return parse(body)["resultObj"]


def test_pagination_clamps_like_backend():
    page = execute_page(transport().execute(request(pageNum=1, pageSize=2)).body)
    assert (page["totalCount"], page["totalPages"], page["pageNum"]) == (5, 3, 1)
    assert len(page["payoutAbilityVOList"]) == 2
    page = execute_page(transport().execute(request(pageNum=99, pageSize=2)).body)
    assert page["pageNum"] == 3
    assert len(page["payoutAbilityVOList"]) == 1
    page = execute_page(transport().execute(request(pageNum=0, pageSize=2)).body)
    assert page["pageNum"] == 1


def test_empty_result_mirrors_backend_echo():
    page = execute_page(
        transport()
        .execute(request(payoutType="EXTERNAL", status="GRAY", pageNum=1, pageSize=100))
        .body
    )
    assert (page["pageNum"], page["totalCount"], page["totalPages"]) == (0, 0, 0)
    assert page["payoutAbilityVOList"] == []


def test_simulated_rows_strip_seqid_and_envelope_matches_backend():
    response = transport().execute(
        request(payoutType="EXTERNAL", pageNum=1, pageSize=100)
    )
    document = parse(response.body)
    assert document["success"] is True and document["status"] is True
    rows = document["resultObj"]["payoutAbilityVOList"]
    assert all("seqid" not in row for row in rows)
    assert [row["abilityId"] for row in rows] == [1, 2, 3, 4, 5]
    origin = response.origin
    assert origin.backend == "snapshot"
    assert origin.simulated is True
    assert origin.backend_complete is False
    assert origin.dataset_complete is True
    assert origin.dataset_id == "d" * 64


def test_allowlist_rejects_unregistered_access():
    bad_host = QueryRequest(
        capability=CAP.name,
        method="POST",
        host="example.com",
        path="/payout/api/ability/search.json",
        body={},
    )
    with pytest.raises(CliError) as caught:
        transport().execute(bad_host)
    assert caught.value.code == REQUEST_NOT_ALLOWED

    with pytest.raises(CliError) as caught:
        transport().execute(request(unknownKey=1))
    assert caught.value.code == REQUEST_NOT_ALLOWED

    wrong_capability = QueryRequest(
        capability="payment.cost.list",
        method="POST",
        host="ifundboss-api.alipay.com",
        path="/payout/api/ability/search.json",
        body={},
    )
    with pytest.raises(CliError) as caught:
        transport().execute(wrong_capability)
    assert caught.value.code == REQUEST_NOT_ALLOWED


def test_uncovered_scope_fails_explicitly():
    with pytest.raises(CliError) as caught:
        transport().execute(request(payoutType="LIQUIDITY", pageNum=1, pageSize=100))
    assert caught.value.code == SOURCE_SCOPE_UNAVAILABLE


def test_load_dataset_roundtrip(dataset_factory, sample_channel_rows):
    dataset = load_dataset(dataset_factory(sample_channel_rows), CAP.name, None)
    assert dataset.row_count == 8
    assert dataset.scope == "EXTERNAL"
    assert len(dataset.records) == 8
    assert len(dataset.identity) == 8
    assert dataset.backend_complete is False


def test_load_dataset_rejects_tampered_records(dataset_factory, sample_channel_rows):
    path = dataset_factory(sample_channel_rows)
    (path / "records.jsonl").write_bytes(b"{}\n")
    with pytest.raises(CliError) as caught:
        load_dataset(path, CAP.name, None)
    assert caught.value.code == SOURCE_DATA_INVALID


def test_load_dataset_rejects_missing_and_wrong_identity(
    tmp_path, dataset_factory, sample_channel_rows
):
    with pytest.raises(CliError) as caught:
        load_dataset(tmp_path / "absent", CAP.name, None)
    assert caught.value.code == SOURCE_DATA_MISSING

    path = dataset_factory(sample_channel_rows)
    with pytest.raises(CliError) as caught:
        load_dataset(path, CAP.name, "0" * 64)
    assert caught.value.code == SOURCE_DATA_INVALID

    (path / "provenance.jsonl").unlink()
    with pytest.raises(CliError) as caught:
        load_dataset(path, CAP.name, None)
    assert caught.value.code == SOURCE_DATA_MISSING
