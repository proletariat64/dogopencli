"""Account-isolation public CLI with fake CDP and a private SQLite cache."""

import pytest
from test_sla_cli_sit import sla_setup  # noqa: F401


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.collection_account_isolation]\nkind = "cdp"\n')
    return sla_setup


def row(identity="001", **changes):
    return {
        "id": identity,
        "businessCategory": "SYNTHETIC",
        "businessRegionScope": "GB",
        "customerTags": "A,B",
        "sceneCode": "SCENE",
        "creditArea": "US",
        "currency": "USD,GBP",
        "regionType": "CROSS_BORDER",
        "future": {"nested": [None, 0, ""]},
        **changes,
    }


def page(rows=None, **changes):
    rows = [row()] if rows is None else rows
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "businessDataList": rows,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": len(rows),
                "totalPageNo": 0,
                **changes,
            },
        },
    }


FILTERS = {
    "--opening-rule-id": "id",
    "--business-line": "businessCategory",
    "--business-region": "businessRegionScope",
    "--customer-group": "customerTags",
    "--scene-code": "sceneCode",
    "--collection-region": "creditArea",
    "--currency": "currency",
    "--transaction-type": "regionType",
}


def listing(run_cli, *flags):
    return run_cli(["collection", "account-isolation", "list", *flags])


def refresh(run_cli, *flags):
    return run_cli(["refresh", "collection", "account-isolation", *flags])


def seed(run_cli, setup):
    setup.state.business_script.append(page())
    assert refresh(run_cli)[0] == 0
    return listing(run_cli)[1]


def test_request_allowlist_rejects_selectors_mutations_and_pagination(setup):
    from dogopencli.errors import CliError
    from dogopencli.plugins import get_capability
    from dogopencli.transport import QueryRequest, validate_request

    cap = get_capability("collection.account_isolation.list")
    base = dict(
        capability=cap.name,
        method="POST",
        host="ifundcontrolprodops.alipay.com",
        path="/api/virtualAccountRuleConfig/search",
        body={"pageNo": 0, "pageSize": 1000},
    )
    for changes in [
        dict(method="GET"),
        dict(host="other.example"),
        dict(path="/api/virtualAccountRuleConfig/createBizRule"),
        dict(body={"pageNo": 1, "pageSize": 1000}),
        dict(body={"pageNo": 0, "pageSize": 10}),
        dict(body={"pageNo": 0, "pageSize": 1000, "id": "001"}),
        dict(body={"pageNo": 0, "pageSize": 1000, "ctoken": "SECRET"}),
    ]:
        with pytest.raises(CliError) as exc:
            validate_request(QueryRequest(**(base | changes)), cap.contract)
        assert exc.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
