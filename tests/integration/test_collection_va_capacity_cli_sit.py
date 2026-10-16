"""Collection VA capacity public CLI + fake CDP + real SQLite acceptance (#38)."""

import pytest
from test_sla_cli_sit import sla_setup  # noqa: F401


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.collection_va_capacity]\nkind = "cdp"\n')
    return sla_setup


def row(rule_id="1", **changes):
    """Synthetic capacity row: the 22 verified fields, no production values."""
    base = {
        "id": "SYNTHETIC-SURROGATE-1",
        "ruleId": rule_id,
        "bankAccountVaId": "SYNTHETIC-BANKRULE-1",
        "accountNo": "SYNTHETIC-ACCOUNT",
        "bankAccountingEntityCode": "SBE",
        "serviceAccountingEntityCode": "SSE",
        "financialInst": "SYNTHETIC-INST",
        "currency": "USD",
        "sceneCode": "SC1",
        "memo": "synthetic memo",
        "totalCount": 10,
        "usedCount": 4,
        "availableCount": 6,
        "canAllocateCount": 6,
        "lastDayUseCount": 1,
        "averageApplyCount": 2,
        "totalMaxUseCount": 3,
        "warningCount": 0,
        "warningDays": 0,
        "canUseDays": 9,
        "gmtCreate": 1694000000000,
        "gmtModified": 1694100000000,
    }
    base.update(changes)
    return base


def page(rows=None, **changes):
    rows = [row()] if rows is None else rows
    return {
        "status": 200,
        "body": {
            "success": True,
            "pageNo": 1,
            "pageSize": 1000,
            "totalCount": len(rows),
            "resultDataList": rows,
            **changes,
        },
    }


def bulk_rows(count):
    return [row(f"{1000 + index}") for index in range(count)]


def listing(run_cli, *flags):
    return run_cli(["collection", "va", "capacity", "list", *flags])


def refresh(run_cli, *flags):
    return run_cli(["refresh", "collection", "va", "capacity", *flags])


def seed(run_cli, setup):
    setup.state.business_script.append(page())
    assert refresh(run_cli)[0] == 0
    return listing(run_cli)[1]


def filter_rows():
    return [
        row("1", bankAccountVaId="B-ONE", currency="USD"),
        row("2", bankAccountVaId="B-TWO", currency="EUR"),
        row("3", bankAccountVaId="B-one", currency="USD"),
        row("4", bankAccountVaId=None, currency="USD"),
    ]


def filter_seed(run_cli, setup):
    setup.state.business_script.append(page(filter_rows()))
    assert refresh(run_cli)[0] == 0


def test_transport_restrictions_before_browser(setup):
    from dataclasses import replace

    from dogopencli.errors import CliError
    from dogopencli.plugins.collection.va_capacity import COLLECTION_VA_CAPACITY
    from dogopencli.transport import QueryRequest
    from dogopencli.transport.cdp import CdpQueryTransport

    capability = COLLECTION_VA_CAPACITY
    transport = CdpQueryTransport(
        setup.state.transport("http://127.0.0.1:9222"),
        capability,
        page_url="https://ifundcontrol.alipay.com",
    )
    request = QueryRequest(
        capability.name,
        capability.contract.method,
        capability.contract.host,
        capability.contract.path,
        {"pageNo": 1, "pageSize": 1000},
    )
    for change in [
        {"path": "/ivostro/api/warningUseCount/save.json"},
        {"host": "evil.example"},
        {"method": "DELETE"},
        {"body": {"pageNo": 1, "pageSize": 1000, "ruleId": "1"}},
        {"body": {"pageNo": 1, "pageSize": 10}},
        {"body": {"pageNo": 1}},
        {"capability": "collection.va.rules.list"},
    ]:
        with pytest.raises(CliError) as caught:
            transport.execute(replace(request, **change))
        assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert not setup.state.business_requests
    assert not any(t.created for t in setup.state.transports)
