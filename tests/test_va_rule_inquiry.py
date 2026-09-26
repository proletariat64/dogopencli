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
                "totalCount": 1,
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

    def refresh():
        return inquiry.refresh(
            config,
            source,
            session_factory=session.open,
            now=lambda: now,
            progress=lambda done, total: None,
            detail_progress=lambda message: None,
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
    with pytest.raises(CliError) as caught:
        refresh()
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
        assert caught.value.code == "INCOMPLETE_RESULT"
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
