"""Native VA detail refusal and identity policy through fake transport."""

from contextlib import contextmanager

import pytest

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
def test_native_detail_refusal_is_strict_and_never_cached(tmp_path, status):
    session = FakeSession()
    assert inquiry.fetch_detail(session, "01") == DETAIL
    session.status = status
    session.detail = {"success": False}
    with pytest.raises(CliError) as caught:
        inquiry.fetch_detail(session, "01")
    assert caught.value.code == "BUSINESS_QUERY_FAILED"
    assert not (tmp_path / "cache.sqlite3").exists()


def test_native_get_requires_matching_identity():
    session = FakeSession()
    session.detail = {"success": True, "resultObj": {**DETAIL, "vaRuleId": "02"}}
    with pytest.raises(CliError) as caught:
        inquiry.fetch_detail(session, "01")
    assert caught.value.code == "INVALID_RESPONSE"
