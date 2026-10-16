"""Public-CLI SIT for the SLA baseline CDP query path (issue #6).

Drives ``dogopencli payment sla baselines list``, ``... get --id`` and
``dogopencli refresh payment sla`` through dogopencli.cli.main with the
browser/CDP external boundary replaced by the scripted stand-ins in
``fake_cdp.py``. Every request passes command registration, the shared
allowlist, the SLA plugin parsers, the bounded collector and SQLite. All
rows are synthetic and sanitized; no real Chrome, network, credentials or
production data is involved.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_cdp import PAYMENT_URL, FakeBrowser

from dogopencli.browser import cdp
from dogopencli.errors import CliError
from dogopencli.plugins import get_capability
from dogopencli.plugins.payment.sla import SLA_DETAIL
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport

CDP_URL = "http://127.0.0.1:9222"
LIST_PATH = "/api/fundOutSlaBaseline/queryFundOutSlaBaseline"
DETAIL_PATH = "/api/fundOutSlaBaseline/getFundOutSlaBaselineDetail"
PRECISE_TEXT = "0.1234567890123456789"


def sla_row(baseline_id, **overrides):
    row = {
        "id": str(baseline_id),
        "bizCategory": "ACQUIRING",
        "creditorCurrency": "USD",
        "regionCode": "US",
        "status": "ACTIVATED",
        "timezone": "Asia/Shanghai",
        "creditorMinAmount": "0.10",
        "creditorMaxAmount": "999999999.99",
        "debitorSuccessSla": "86400",
        "creditorSuccessSla": "172800",
        "holidayLimit": "Y",
        "serviceLevelLimit": [],
        "creator": "synthetic-creator",
        "lastOperator": "synthetic-operator",
        "gmtCreate": 1694000000000,
        "gmtModified": 1694100000000,
        "futureUnknownField": {"keep": ["as-is", 1]},
    }
    row.update(overrides)
    return row


def sla_detail(baseline_id, **overrides):
    detail = sla_row(
        baseline_id,
        riskRuleCode=f"RISK-{baseline_id}",
        detailOnlyDecimal=PRECISE_TEXT,
    )
    detail.update(overrides)
    return detail


def list_page(
    records,
    page_no=0,
    page_size=5000,
    total_count=None,
    success=True,
    omit_list=False,
):
    body = {
        "success": success,
        "errorContext": {"errorStack": [{"errorName": "SUCCESS"}]},
        "pageNo": page_no,
        "pageSize": page_size,
        "totalCount": len(records) if total_count is None else total_count,
        "showButton": False,
        "sofaTracerId": "synthetic-trace",
    }
    if not omit_list:
        body["resultDataList"] = records
    if not success:
        body["errorContext"] = {
            "errorStack": [{"errorName": "PARAM_ILLEGAL", "errorSpecific": "0400"}]
        }
    return {"status": 200, "body": body}


def detail_outcome(baseline_id, found=True, success=True):
    if not success:
        return {
            "status": 200,
            "body": {"success": False, "resultData": None},
        }
    result = sla_detail(baseline_id) if found else None
    return {"status": 200, "body": {"success": True, "resultData": result}}


def refresh_handler(rows, fail_details=(), null_details=()):
    details = {row["id"]: sla_detail(row["id"]) for row in rows}

    def handle(payload: dict, call_index: int):
        if "slaBaselineId" in payload:
            baseline_id = payload["slaBaselineId"]
            if baseline_id in fail_details:
                return detail_outcome(baseline_id, success=False)
            if baseline_id in null_details:
                return detail_outcome(baseline_id, found=False)
            return {
                "status": 200,
                "body": {"success": True, "resultData": details[baseline_id]},
            }
        return list_page(rows, page_no=payload["pageNo"], page_size=payload["pageSize"])

    return handle


@pytest.fixture
def sla_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    profile = tmp_path / "chrome-profile"
    cache_path = tmp_path / "cache.sqlite3"
    config_path = tmp_path / "config.toml"

    def write_config(ttl_hours: float | int = 72) -> None:
        config_path.write_text(
            "[cache]\n"
            f'path = "{cache_path}"\n'
            f"ttl_hours = {ttl_hours}\n"
            "\n"
            "[auth]\n"
            f'profile = "{profile}"\n'
            f'cdp_url = "{CDP_URL}"\n'
            "\n"
            "[sources.payment_sla]\n"
            'kind = "cdp"\n'
        )
        monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config_path))

    write_config()
    state = FakeBrowser()
    cdp.set_transport_factory(state.transport)
    yield SimpleNamespace(
        state=state,
        profile=profile,
        tmp_path=tmp_path,
        cache_path=cache_path,
        write_config=write_config,
    )
    cdp.set_transport_factory(None)


@pytest.fixture
def sample_sla_rows() -> list[dict]:
    return [
        sla_row(101),
        sla_row(102, status="OFFLINE"),
        sla_row(
            103,
            bizCategory="REMITTANCE",
            creditorCurrency="EUR",
            regionCode="SG",
            status="DRAFT",
        ),
        sla_row(104, bizCategory="REMITTANCE", regionCode="HK"),
    ]


def refresh(run_cli, *extra: str):
    return run_cli(["refresh", "payment", "sla", *extra])


def listing(run_cli, *extra: str):
    return run_cli(["payment", "sla", "baselines", "list", *extra])


def getting(run_cli, *extra: str):
    return run_cli(["payment", "sla", "baselines", "get", *extra])


def refreshed(run_cli, sla_setup, rows) -> None:
    sla_setup.state.business_handler = refresh_handler(rows)
    code, _, _ = refresh(run_cli)
    assert code == 0
    sla_setup.state.business_handler = None


def business_expressions(state: FakeBrowser) -> list[str]:
    return [
        expression
        for transport in state.transports
        for expression in transport.expressions
        if "fetch(" in expression
    ]


def test_allowlist_rejects_unregistered_requests(sla_setup):
    list_capability = get_capability("payment.sla.baselines.list")
    list_transport = CdpQueryTransport(
        sla_setup.state.transport(CDP_URL), list_capability, page_url=PAYMENT_URL
    )
    detail_transport = CdpQueryTransport(
        sla_setup.state.transport(CDP_URL), SLA_DETAIL, page_url=PAYMENT_URL
    )

    def forged(**changes):
        base = {
            "capability": "payment.sla.baselines.list",
            "method": "POST",
            "host": "iglobalfundcontrol.alipay.com",
            "path": LIST_PATH,
            "body": {"pageNo": 0, "pageSize": 5000},
        }
        base.update(changes)
        return QueryRequest(**base)

    def forged_detail(**changes):
        base = {
            "capability": SLA_DETAIL.name,
            "method": "GET",
            "host": "iglobalfundcontrol.alipay.com",
            "path": DETAIL_PATH,
            "body": {"slaBaselineId": "1"},
        }
        base.update(changes)
        return QueryRequest(**base)

    cases = [
        (list_transport, forged(host="evil.example.com")),
        (list_transport, forged(host="ifundcontrol.alipay.com")),
        (list_transport, forged(path="/api/fundOutSlaBaseline/saveFundOutSlaBaseline")),
        (list_transport, forged(method="GET")),
        (list_transport, forged(body={"pageNo": 0, "pageSize": 5000, "export": True})),
        (list_transport, forged(capability="payment.cost.list")),
        # The detail endpoint is not reachable through the list contract.
        (
            list_transport,
            forged(method="GET", path=DETAIL_PATH, body={"slaBaselineId": "1"}),
        ),
        # The list endpoint is not reachable through the detail contract.
        (detail_transport, forged(capability=SLA_DETAIL.name)),
        (
            detail_transport,
            forged_detail(body={"slaBaselineId": "1", "slaBaselineName": "x"}),
        ),
        (detail_transport, forged_detail(method="POST")),
        (detail_transport, forged_detail(host="ifundcontrol.alipay.com")),
    ]
    for transport, bad in cases:
        with pytest.raises(CliError) as caught:
            transport.execute(bad)
        assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert sla_setup.state.business_requests == []
