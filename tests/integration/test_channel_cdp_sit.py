"""Public-CLI SIT for the Channel CDP query path and source switching (issue #7).

Drives ``dogopencli payment channel list`` and ``dogopencli refresh payment
channel`` through dogopencli.cli.main with ``sources.payment_channel.kind``
set to ``cdp`` and the browser/CDP external boundary replaced by the scripted
stand-ins in ``fake_cdp.py``. Every request passes command registration, the
shared allowlist, the channel plugin parser, the bounded collector and
SQLite. All rows are synthetic and sanitized; no real Chrome, network,
credentials or production data is involved.

The production Channel backend defect is an external dependency: real full
UAT waits for the backend fix (issue #10). This file passing does not claim
production has recovered.
"""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_cdp import PAYMENT_URL, FakeBrowser

import dogopencli.collect as collect_mod
from dogopencli.browser import cdp
from dogopencli.errors import CliError
from dogopencli.plugins import get_capability
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport

CDP_URL = "http://127.0.0.1:9222"
PAGE_SIZE = 100
PRECISE_AMOUNT = "0.1234567890123456789"


def channel_row(ability_id, **overrides):
    row = {
        "abilityId": ability_id,
        "payoutType": "EXTERNAL",
        "status": "ENABLE",
        "financialInstCode": "CITILD",
        "debitAccountName": f"ACCT-{ability_id}",
        "debitAccountNo": str(900000 + ability_id),
        "clearingSystemName": "BOOK RTP",
        "debitCurrency": "USD",
        "creditCurrency": "CNY",
        "debitInstCountryCode": "GB",
        "configVersion": "v1",
        "chargeAmount": {
            "amount": Decimal("0.10"),
            "cent": 10,
            "centFactor": 100,
            "currency": "USD",
            "currencyCode": "USD",
        },
        "futureUnknownField": {"keep": ["as-is", 1]},
    }
    row.update(overrides)
    return row


def channel_page(
    records,
    page_num,
    page_size=PAGE_SIZE,
    total_count=None,
    total_pages=None,
    success=True,
    inner_success=True,
):
    if total_count is None:
        total_count = len(records)
    if total_pages is None:
        total_pages = -(-total_count // page_size)
    document = {"success": success, "status": success, "data": None}
    if success:
        document["resultObj"] = {
            "success": inner_success,
            "code": "IPAY_RS_100000200" if inner_success else "IPAY_RS_510090020",
            "pageNum": page_num,
            "pageSize": page_size,
            "totalCount": total_count,
            "totalPages": total_pages,
            "payoutAbilityVOList": records,
        }
    return {"status": 200, "body": document}


def paging_handler(pages: dict[int, list], total: int):
    def handle(payload: dict, call_index: int):
        page_num = payload["pageNum"]
        page_size = payload["pageSize"]
        rows = pages.get(page_num)
        assert rows is not None, f"unexpected request page {page_num}"
        return channel_page(rows, page_num, page_size, total_count=total)

    return handle


@pytest.fixture
def cdp_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    profile = tmp_path / "chrome-profile"
    cache_path = tmp_path / "cache.sqlite3"
    config_path = tmp_path / "config.toml"

    def write_config(
        kind: str = "cdp",
        dataset: Path | None = None,
        dataset_id: str | None = None,
        ttl_hours: float | int = 72,
    ) -> None:
        lines = [
            "[cache]",
            f'path = "{cache_path}"',
            f"ttl_hours = {ttl_hours}",
            "",
            "[auth]",
            f'profile = "{profile}"',
            f'cdp_url = "{CDP_URL}"',
            "",
            "[sources.payment_channel]",
            f'kind = "{kind}"',
        ]
        if dataset is not None:
            lines.append(f'path = "{dataset}"')
        if dataset_id is not None:
            lines.append(f'dataset_id = "{dataset_id}"')
        lines += ["", "[sources.payment_sla]", 'kind = "cdp"']
        config_path.write_text("\n".join(lines) + "\n")
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
def no_sleep(monkeypatch: pytest.MonkeyPatch):
    waits: list[float] = []
    monkeypatch.setattr(collect_mod, "_sleep", waits.append)
    return waits


def refresh(run_cli, *extra: str):
    return run_cli(["refresh", "payment", "channel", *extra])


def listing(run_cli, *extra: str):
    return run_cli(["payment", "channel", "list", *extra])


def refreshed(run_cli, cdp_setup, rows) -> None:
    cdp_setup.state.business_handler = paging_handler({1: rows}, len(rows))
    code, _, _ = refresh(run_cli)
    assert code == 0
    cdp_setup.state.business_handler = None


def test_allowlist_rejects_unregistered_requests(cdp_setup):
    capability = get_capability("payment.channel.list")
    transport = CdpQueryTransport(
        cdp_setup.state.transport(CDP_URL), capability, page_url=PAYMENT_URL
    )

    def forged(**changes):
        base = {
            "capability": capability.name,
            "method": "POST",
            "host": "ifundboss-api.alipay.com",
            "path": "/payout/api/ability/search.json",
            "body": {"payoutType": "EXTERNAL", "pageNum": 1, "pageSize": 100},
        }
        base.update(changes)
        return QueryRequest(**base)

    for bad in (
        forged(host="evil.example.com"),
        forged(host="iglobalfundcontrol.alipay.com"),
        forged(path="/payout/api/ability/save.json"),
        forged(method="GET"),
        forged(
            body={
                "payoutType": "EXTERNAL",
                "pageNum": 1,
                "pageSize": 100,
                "approve": True,
            }
        ),
        forged(capability="payment.cost.list"),
    ):
        with pytest.raises(CliError) as caught:
            transport.execute(bad)
        assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert cdp_setup.state.business_requests == []
