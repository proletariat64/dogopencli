"""New leaf pilots through the public CLI and fake CDP browser."""

import json
import shutil
from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp


@pytest.fixture
def pilots(tmp_path, monkeypatch):
    source = Path(__file__).parents[2] / "src/dogopencli/leaf_packages"
    shutil.copytree(source, tmp_path / "plugins")
    config = tmp_path / "config.toml"
    config.write_text(
        '[auth]\nprofile = "'
        + str(tmp_path / "chrome")
        + '"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    monkeypatch.delenv("DOGOPENCLI_CHROME_CDP_URL", raising=False)
    monkeypatch.delenv("DOGOPENCLI_CHROME_PROFILE", raising=False)
    browser = FakeBrowser()
    cdp.set_transport_factory(browser.transport)
    yield browser
    cdp.set_transport_factory(None)


def test_payment_native_list_and_detail(run_cli, pilots):
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "pageNo": 0,
                "pageSize": 5000,
                "totalCount": 1,
                "resultDataList": [{"id": "101", "status": "ACTIVE"}],
            },
        }
    )
    code, out, _ = run_cli(["payment", "list", "sla.baselines", "--live"])
    assert code == 0
    assert json.loads(out)["data"] == [{"id": "101", "status": "ACTIVE"}]
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "resultData": {"id": "101", "detailOnly": "native"},
            },
        }
    )
    code, out, _ = run_cli(["payment", "get", "sla.baselines", "101"])
    assert code == 0
    assert json.loads(out)["data"]["detailOnly"] == "native"
    assert pilots.business_requests[-1] == {"slaBaselineId": "101"}


def fx_page(rows, number=0, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "result": {
                "success": True,
                "value": {
                    "items": rows,
                    "totalCount": len(rows) if total is None else total,
                    "currentPage": number,
                    "pageSize": 50,
                },
            },
        },
    }


def test_fx_native_pages_preserve_unknown_identity(run_cli, pilots):
    from dogopencli.browser.environment import FX_STARTUP_URL

    pilots.href = FX_STARTUP_URL
    rows = [{"uniqueId": str(i), "amount": "0.1234567890123456789"} for i in range(52)]
    pilots.business_script.extend(
        [fx_page(rows[:50], total=52), fx_page(rows[50:], number=1, total=52)]
    )
    code, out, err = run_cli(
        ["fx", "list", "trade", "--live", "--trade-id", "TEST", "--limit", "1"]
    )
    value = json.loads(out)
    assert code == 0
    assert value["data"] == rows[:1]
    assert value["meta"]["collected_total"] == 52
    assert value["meta"]["complete"] is False
    assert value["meta"]["unique_count"] is None
    assert "INCOMPLETE_RESULT" in err
    assert [request["pageNo"] for request in pilots.business_requests] == [0, 1]
    assert pilots.business_requests[0]["queryRequest"] == {"uniqueIds": ["TEST"]}
    pilots.business_script.append(fx_page(rows[:1]))
    code, out, _ = run_cli(
        ["fx", "list", "trade", "--live", "--trade-id", "TEST", "--require-complete"]
    )
    assert code == 1 and json.loads(out)["data"] is None


def test_liquidity_entities_accept_native_inst_id_without_synthetic_id(run_cli, pilots):
    from dogopencli.browser.environment import LIQUIDITY_STARTUP_URL

    pilots.href = LIQUIDITY_STARTUP_URL
    rows = [{"instId": "INSTITUTION-A", "instName": "Synthetic institution"}]
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": 1,
                "result": {"entityMaintVOList": rows},
            },
        }
    )
    code, out, _ = run_cli(["liquidity", "list", "reference.entities", "--live"])
    assert code == 0
    assert json.loads(out)["data"] == rows


def test_collection_single_verified_capacity_reports_incomplete(run_cli, pilots):
    rows = [{"itemId": "1", "itemType": "FUND_IN_CHANNEL_TRANS_FEE"}]
    pilots.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": 1001,
                "resultDataList": rows,
            },
        }
    )
    code, out, err = run_cli(["collection", "list", "cost", "--live"])
    assert code == 0
    value = json.loads(out)
    assert value["data"] == rows
    assert value["meta"]["complete"] is False
    assert "INCOMPLETE_RESULT" in err
    assert pilots.business_requests == [
        {"costTypeCode": "FUND_IN_CHANNEL_TRANS_FEE", "pageNo": 0, "pageSize": 1000}
    ]
