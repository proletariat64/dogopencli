"""Public-CLI SIT for the Cost CDP query path (issue #5).

Drives ``dogopencli payment cost list`` and ``dogopencli refresh payment
cost`` through dogopencli.cli.main with the browser/CDP external boundary
replaced by the scripted stand-ins in ``fake_cdp.py``. Every request passes
command registration, the shared allowlist, the cost plugin parser, the
bounded collector and SQLite. All rows are synthetic and sanitized; no real
Chrome, network, credentials or production data is involved.
"""

import threading
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_cdp import PAYMENT_URL, FakeBrowser

import dogopencli.collect as collect_mod
from dogopencli.browser import cdp
from dogopencli.cache import Cache, SnapshotMeta
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse
from dogopencli.plugins import get_capability
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import CdpQueryTransport

CDP_URL = "http://127.0.0.1:9222"
COST_TYPE = "FUND_OUT_CHANNEL_TRANS_FEE"
PRECISE_AMOUNT = "0.1234567890123456789"


def cost_row(item_id, **overrides):
    row = {
        "itemId": str(item_id),
        "itemType": COST_TYPE,
        "mappingCode": f"MC-{item_id}",
        "legalEntity": "ALIPAY SG",
        "financialInst": "CITILD",
        "bankAccountAliasName": f"ACCT-{item_id}",
        "transCurrencyCode": "USD",
        "costCurrencyCode": "USD",
        "chargeBearer": "SHAR",
        "clearingNetworkName": "BOOK RTP",
        "isFvt": "N",
        "status": "ACTIVATED",
        "gmtCreate": 1694000000000,
        "gmtModified": 1694100000000,
        "costRateConfigList": [
            {
                "feeItemRateConfigId": f"FRC-{item_id}",
                "feeCalcBasisType": "CA1",
                "feeCalcScale": "TWO_DECIMAL_AFTER_POINTS",
                "feeRoundingMode": "HALF_UP",
                "progressType": "FULL_PROGRESS",
                "validStartTime": 1693500000000,
                "validEndTime": 1893500000000,
                "costRateVO": {
                    "feeItemRateConfigId": f"FRC-{item_id}",
                    "feeCalcBasisTypeCode": "CA1",
                    "status": "ACTIVATED",
                    "bottomAmount": {
                        "amount": Decimal("0.10"),
                        "cent": 10,
                        "centFactor": 100,
                        "currency": "USD",
                        "currencyCode": "USD",
                    },
                    "feeRateRatioValue": {
                        "amount": Decimal(PRECISE_AMOUNT),
                        "hundredthValue": Decimal("12.34567890123456789"),
                        "ratioUnit": "PERCENT",
                        "ratioUnitCode": "PERCENT",
                    },
                },
            }
        ],
        "futureUnknownField": {"keep": ["as-is", 1]},
    }
    row.update(overrides)
    return row


def cost_page(records, page_no=0, page_size=5000, total_count=None, success=True):
    body = {
        "success": success,
        "errorContext": {"errorStack": [{"errorName": "SUCCESS"}]},
        "pageNo": page_no,
        "pageSize": page_size,
        "totalCount": len(records) if total_count is None else total_count,
        "resultDataList": records,
        "permissions": [{"permissionCode": "SYNTHETIC_VIEW"}],
        "showButton": False,
        "sofaTracerId": "synthetic-trace",
    }
    if not success:
        body["errorContext"] = {
            "errorStack": [{"errorName": "PARAM_ILLEGAL", "errorSpecific": "0400"}]
        }
    return {"status": 200, "body": body}


def paging_handler(rows_by_page: dict[int, list], page_size: int, total: int):
    def handle(payload: dict, call_index: int):
        page_no = payload["pageNo"]
        assert payload["pageSize"] == page_size
        return cost_page(
            rows_by_page.get(page_no, []),
            page_no=page_no,
            page_size=page_size,
            total_count=total,
        )

    return handle


@pytest.fixture
def cost_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
            "[sources.payment_cost]\n"
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
def no_sleep(monkeypatch: pytest.MonkeyPatch):
    waits: list[float] = []
    monkeypatch.setattr(collect_mod, "_sleep", waits.append)
    return waits


@pytest.fixture
def sample_cost_rows() -> list[dict]:
    return [
        cost_row(101),
        cost_row(102, chargeBearer="CRED", status="OFFLINE"),
        cost_row(
            103,
            legalEntity="ALIPAY HK",
            financialInst="SCBLSG",
            bankAccountAliasName="ACCT-B",
            transCurrencyCode="EUR",
            clearingNetworkName="FX PAYOUT",
        ),
        cost_row(
            104,
            legalEntity="ALIPAY HK",
            financialInst="HSBCHK",
            bankAccountAliasName="ACCT-C",
            chargeBearer="DEBT",
            clearingNetworkName="BOOK",
        ),
        cost_row(105, bankAccountAliasName="ACCT-A"),
        cost_row(
            106,
            legalEntity="ALIPAY HK",
            financialInst="SCBLSG",
            bankAccountAliasName="ACCT-B",
            transCurrencyCode="EUR",
            chargeBearer="FVT",
            clearingNetworkName="FX PAYOUT",
        ),
        cost_row(
            107,
            legalEntity="ALIPAY UK",
            financialInst="HSBCHK",
            bankAccountAliasName="ACCT-E",
            transCurrencyCode="HKD",
            clearingNetworkName="BOOK",
        ),
        cost_row(108, bankAccountAliasName="ACCT-F", transCurrencyCode="GBP"),
    ]


def script_full(state: FakeBrowser, rows: list[dict]) -> None:
    state.business_script.append(cost_page(rows))


def refresh(run_cli, *extra: str):
    return run_cli(["refresh", "payment", "cost", *extra])


def listing(run_cli, *extra: str):
    return run_cli(["payment", "cost", "list", *extra])


def refreshed(run_cli, cost_setup, rows) -> None:
    script_full(cost_setup.state, rows)
    code, _, _ = refresh(run_cli)
    assert code == 0
    cost_setup.state.business_script.clear()


def test_allowlist_rejects_unregistered_requests(cost_setup):
    capability = get_capability("payment.cost.list")
    transport = CdpQueryTransport(
        cost_setup.state.transport(CDP_URL), capability, page_url=PAYMENT_URL
    )

    def forged(**changes):
        base = {
            "capability": capability.name,
            "method": "POST",
            "host": "iglobalfundcontrol.alipay.com",
            "path": "/api/fundCost/query.json",
            "body": {"costTypeCode": COST_TYPE, "pageNo": 0, "pageSize": 5000},
        }
        base.update(changes)
        return QueryRequest(**base)

    for bad in (
        forged(host="evil.example.com"),
        forged(host="ifundcontrol.alipay.com"),
        forged(path="/api/fundCost/save.json"),
        forged(path="/api/fundCost/detail.json"),
        forged(method="GET"),
        forged(
            body={
                "costTypeCode": "FX_FEE",
                "pageNo": 0,
                "pageSize": 5000,
                "approve": True,
            }
        ),
        forged(capability="payment.channel.list"),
    ):
        with pytest.raises(CliError) as caught:
            transport.execute(bad)
        assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert cost_setup.state.business_requests == []


def test_concurrent_reads_see_complete_snapshots(cost_setup):
    store = Cache(cost_setup.cache_path)

    def snapshot(ns: str, rows: int, marker: str) -> SnapshotMeta:
        return SnapshotMeta(
            namespace=ns,
            capability="payment.cost.list",
            scope=COST_TYPE,
            source_kind="cdp",
            snapshot_id=marker,
            dataset_id=None,
            simulated=False,
            backend_complete=True,
            dataset_complete=True,
            fetched_at="2026-09-11T00:00:00+00:00",
            loaded_at="2026-09-11T00:00:00+00:00",
            source_observed_from=None,
            source_observed_to=None,
            row_count=rows,
        )

    ns = "payment.cost.list:FUND_OUT_CHANNEL_TRANS_FEE:cdp"
    failures: list[str] = []
    writer_errors: list[BaseException] = []
    stop = threading.Event()

    def writer() -> None:
        try:
            for round_no in range(40):
                rows = 3 if round_no % 2 == 0 else 5
                keyed = [
                    (index, canonical({"seq": index, "round": round_no}))
                    for index in range(1, rows + 1)
                ]
                store.publish(snapshot(ns, rows, f"snap-{round_no}"), keyed)
        except BaseException as error:
            writer_errors.append(error)
        finally:
            stop.set()

    def reader() -> None:
        while not stop.is_set():
            meta, bodies = store.read(ns)
            if meta is None:
                continue
            if len(bodies) != meta.row_count:
                failures.append(f"row_count {meta.row_count} but {len(bodies)} records")
                return
            if [seq for seq, _ in bodies] != list(range(1, meta.row_count + 1)):
                failures.append("seqids are not continuous for one snapshot")
                return
            rounds = {parse(body)["round"] for _, body in bodies}
            if len(rounds) != 1:
                failures.append("records mix two published snapshots")
                return

    thread = threading.Thread(target=writer)
    thread.start()
    reader()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert writer_errors == []
    assert failures == []
