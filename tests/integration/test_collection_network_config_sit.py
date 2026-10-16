"""Public network-configuration CLI, fake CDP and real temporary SQLite."""

import pytest
from test_sla_cli_sit import sla_setup  # noqa: F401


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.collection_clearing_system]\nkind = "cdp"\n')
        file.write('\n[sources.collection_card_template]\nkind = "cdp"\n')
    return sla_setup


def row(identity="001", **changes):
    return {
        "id": identity,
        "supportedCountry": "GB",
        "supportedCurrency": "GBP",
        "clearingNetworkType": "ACH",
        "clearingNetworkId": "SYNTHETIC-NETWORK",
        "status": "VALID",
        "costLevel": "01",
        "efficiencyLevel": "02",
        "future": {"nested": [None, 0, ""]},
        **changes,
    }


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


@pytest.fixture(params=["clearing-system", "card-template"])
def slug(request):
    return request.param


def listing(run_cli, slug, *flags):
    return run_cli(["collection", slug, "list", *flags])


def refresh(run_cli, slug, *flags):
    return run_cli(["refresh", "collection", slug, *flags])


def seed(run_cli, slug, setup):
    setup.state.business_script.append(page())
    assert refresh(run_cli, slug)[0] == 0
    return listing(run_cli, slug)[1]


def test_transport_restrictions(setup, slug):
    from dogopencli.errors import CliError
    from dogopencli.plugins import get_capability
    from dogopencli.transport import QueryRequest, validate_request

    cap = get_capability(f"collection.{slug.replace('-', '_')}.list")
    base = dict(
        capability=cap.name,
        method="POST",
        host="ifundboss-api.alipay.com",
        path=cap.contract.path,
        body={"pageNo": 1, "pageSize": 1000},
    )
    for changes in [
        dict(method="GET"),
        dict(host="other.example"),
        dict(path=cap.contract.path.replace("pageList", "delete")),
        dict(body={"pageNo": 2, "pageSize": 1000}),
        dict(body={"pageNo": 1, "pageSize": 20}),
        dict(body={"pageNo": 1, "pageSize": 1000, "status": "VALID"}),
        dict(body={"pageNo": 1, "pageSize": 1000, "ctoken": "SECRET"}),
    ]:
        with pytest.raises(CliError) as exc:
            validate_request(QueryRequest(**(base | changes)), cap.contract)
        assert exc.value.code == "REQUEST_NOT_ALLOWED"
    assert setup.state.business_requests == []
