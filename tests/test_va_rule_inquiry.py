"""VA refusal policy through the inquiry module, fake transport and real SQLite."""

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from dogopencli.config import Config, SourceConfig
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical
from dogopencli.plugins.collection import va_rule_inquiry as inquiry
from dogopencli.transport import OriginMetadata, TransportResponse

ROW = {
    "vaRuleId": "01",
    "assembleStrategy": None,
    "bankRuleId": "SYNTHETIC-BANK-RULE",
    "entity": "SYNTHETIC-ENTITY",
    "memo": None,
    "regionType": None,
    "ruleStatus": "ENABLED",
    "sceneCodes": [],
}
DETAIL = {**ROW, "assignInfo": None, "clientEntity": None, "creditAreas": []}


class FakeSession:
    def __init__(self):
        self.detail = {"success": True, "resultObj": DETAIL}
        self.status = 200
        self.total = 1

    @contextmanager
    def open(self):
        yield self

    def transport(self, capability):
        return self

    def execute(self, request, *, timeout):
        assert timeout > 0
        if request.capability.endswith("list"):
            status = 200
            body = {
                "success": True,
                "pageNo": 1,
                "pageSize": 1000,
                "totalCount": self.total,
                "resultDataList": [ROW],
            }
        else:
            assert request.body == {"vaRuleId": "01"}
            status, body = self.status, self.detail
        return TransportResponse(
            status,
            canonical(body).encode(),
            OriginMetadata("cdp", True, None, None, None, None, None),
        )


@pytest.mark.parametrize("status", [200, 403])
def test_newest_refusal_replaces_detail_but_http_failure_preserves_it(tmp_path, status):
    source = SourceConfig("cdp", None, None)
    config = Config(tmp_path / "cache.sqlite3", 72, {"collection_va": source})
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    session = FakeSession()

    def refresh(**options):
        return inquiry.refresh(
            config,
            source,
            session_factory=session.open,
            now=lambda: now,
            progress=lambda done, total: None,
            detail_progress=lambda message: None,
            **options,
        )

    def read(**options):
        return inquiry.read_snapshot(
            config,
            source,
            require_fresh=False,
            require_complete=options.get("require_complete", False),
            now=now,
        )

    original = refresh()
    assert read().detail("01") == DETAIL
    session.status = status
    session.detail = {"success": False}
    if status == 403:
        with pytest.raises(CliError) as caught:
            refresh()
    else:
        published = refresh()
        assert published.backend_complete is True
        assert published.dataset_complete is False
        assert published.acquisition["reasons"] == ["DETAIL_REFUSED"]
        assert published.acquisition["attempts"][-1]["details_requested"] == 1
        assert published.acquisition["attempts"][-1]["details_collected"] == 0
        assert published.acquisition["attempts"][-1]["details_refused"] == 1
    snapshot = read()
    assert snapshot.rows == [ROW]
    meta = snapshot.meta(1, 1)
    assert meta["source"] == "cache"
    assert meta["returned_count"] == 1
    assert meta["has_more"] is False
    assert snapshot.meta(2, 1)["has_more"] is True
    assert snapshot.meta(2, 1, offset=1)["has_more"] is False
    if status == 403:
        assert caught.value.code == "BUSINESS_QUERY_FAILED"
        assert meta["snapshot_id"] == original.snapshot_id
        assert snapshot.detail("01") == DETAIL
    else:
        assert meta["snapshot_id"] != original.snapshot_id
        assert meta["complete"] is True
        assert meta["dataset_complete"] is False
        with pytest.raises(CliError, match="refused"):
            snapshot.detail("01")
        with pytest.raises(CliError) as missing:
            snapshot.detail("absent")
        assert missing.value.code == "NOT_FOUND"
        with pytest.raises(CliError) as incomplete:
            read(require_complete=True)
        assert incomplete.value.code == "INCOMPLETE_RESULT"
        with pytest.raises(CliError) as live:
            inquiry.fetch_detail(session, "01")
        assert live.value.code == "BUSINESS_QUERY_FAILED"


@pytest.mark.parametrize("refusal", [False, True])
def test_strict_partial_refresh_preserves_prior_snapshot(tmp_path, refusal):
    source = SourceConfig("cdp", None, None)
    config = Config(tmp_path / "cache.sqlite3", 72, {"collection_va": source})
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    session = FakeSession()

    def refresh(**options):
        return inquiry.refresh(
            config,
            source,
            session_factory=session.open,
            now=lambda: now,
            progress=lambda done, total: None,
            detail_progress=lambda message: None,
            **options,
        )

    original = refresh()
    before = config.cache_path.read_bytes()
    if refusal:
        session.detail = {"success": False}
    else:
        session.total = 2
    with pytest.raises(CliError) as caught:
        refresh(require_complete=True)
    assert caught.value.code == "INCOMPLETE_RESULT"
    assert caught.value.meta["published"] is False
    assert config.cache_path.read_bytes() == before
    snapshot = inquiry.read_snapshot(
        config,
        source,
        require_fresh=False,
        require_complete=True,
        now=now,
    )
    assert snapshot.meta(1, 1)["snapshot_id"] == original.snapshot_id
    assert snapshot.detail("01") == DETAIL


def test_safe_partial_list_publishes_details_and_cannot_prove_absence(tmp_path):
    source = SourceConfig("cdp", None, None)
    config = Config(tmp_path / "cache.sqlite3", 72, {"collection_va": source})
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    session = FakeSession()
    session.total = 1001
    published = inquiry.refresh(
        config,
        source,
        session_factory=session.open,
        now=lambda: now,
        progress=lambda done, total: None,
        detail_progress=lambda message: None,
    )
    assert published.backend_complete is False
    assert published.dataset_complete is False
    assert published.row_count == 1
    assert published.acquisition["reported_total"] == 1001
    cached = inquiry.read_snapshot(
        config,
        source,
        require_fresh=False,
        require_complete=False,
        now=now,
    )
    assert cached.rows == [ROW]
    assert cached.detail("01") == DETAIL
    with pytest.raises(CliError) as missing:
        cached.detail("absent")
    assert missing.value.code == "INCOMPLETE_RESULT"
