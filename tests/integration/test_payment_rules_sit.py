"""Payment rule inquiries through public CLI, fake CDP and real SQLite."""

import pytest
from test_sla_cli_sit import sla_setup  # noqa: F401


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        for slug in ("same_bank_transfer", "cost_reduction", "retry", "bank_switch"):
            file.write(f'\n[sources.payment_rules_{slug}]\nkind = "cdp"\n')
    return sla_setup


def page(rows, slug="same-bank-transfer", **changes):
    bank = slug == "same-bank-transfer"
    data = {
        "pageNum" if bank else "pageNo": 1 if bank else 0,
        "pageSize": 1000,
        "totalCount": len(rows),
        "totalPages" if bank else "totalPageNo": (1 if rows else 0) if bank else 0,
        "payoutBookDecisionRuleVOList" if bank else "businessDataList": rows,
        **({"success": True} if bank else {}),
        **changes,
    }
    return {
        "status": 200,
        "body": {"success": True, "resultObj" if bank else "data": data},
    }


def refresh(run_cli, slug="same-bank-transfer", *flags):
    return run_cli(["refresh", "payment", "rules", slug, *flags])


def listing(run_cli, slug="same-bank-transfer", *flags):
    return run_cli(["payment", "rules", slug, "list", *flags])


def bank_row(identity="SOURCE", *, requirements=None):
    return {
        "switchNodeCode": identity,
        "fundNavigationNodeSwitchRequirementVOList": requirements
        or [
            {
                "requirementId": "REQ",
                "switchBankAccount": identity,
                "switchClearingNetwork": "NET",
                "switchRuleVOList": [
                    {
                        "ruleId": "OLD",
                        "version": "1",
                        "status": "OFF",
                        "ratioList": [
                            {
                                "targetNodeInfoList": [
                                    {
                                        "targetNodeCode": "TARGET",
                                        "clearingNetworkList": ["ACH"],
                                    }
                                ]
                            }
                        ],
                    },
                    {
                        "ruleId": "NEW",
                        "version": "2",
                        "status": "ON",
                        "ratioList": [
                            {
                                "targetNodeInfoList": [
                                    {
                                        "targetNodeCode": "TARGET",
                                        "clearingNetworkList": ["WIRE"],
                                    },
                                    {
                                        "targetNodeCode": "OTHER",
                                        "clearingNetworkList": ["ACH"],
                                    },
                                ]
                            }
                        ],
                    },
                ],
            },
        ],
    }


SLUGS = ("same-bank-transfer", "cost-reduction", "retry", "bank-switch")
IDENTITIES = {
    "same-bank-transfer": "ruleId",
    "cost-reduction": "groupId",
    "retry": "ruleId",
    "bank-switch": "switchNodeCode",
}
FILTER_CASES = [
    ("same-bank-transfer", "bank", "debitInstId", False),
    ("same-bank-transfer", "status", "ruleStatus", False),
    ("cost-reduction", "name", "ruleName", False),
    ("cost-reduction", "business-line", "businessCategory", False),
    ("cost-reduction", "entity", "legalEntity", True),
    ("cost-reduction", "currency", "creditCurrency", False),
    ("cost-reduction", "market", "creditorMarket", False),
    ("cost-reduction", "obo", "needObo", True),
    ("cost-reduction", "fvt", "needFvt", True),
    ("cost-reduction", "status", "status", False),
    ("retry", "name", "ruleName", False),
    ("retry", "entity", "bizLegalEntityList", True),
    ("retry", "business-line", "businessCategoryList", True),
    ("retry", "bank", "debtorInstList", True),
    ("retry", "currency", "creditorCurrencyList", True),
    ("retry", "region", "creditorCountryList", True),
    ("retry", "bank-account", "debtorAccountNoList", True),
    ("retry", "clearing-network", "clearingNetworkList", True),
    ("retry", "status", "status", False),
    ("retry", "communication-mode", "communicationMode", False),
    ("retry", "integration-mode", "integrationMode", False),
]


def simple_row(slug, identity=1):
    return {
        IDENTITIES[slug]: identity if slug == "same-bank-transfer" else str(identity),
        "future": {"nested": [None, 0, ""]},
    }


def seed(run_cli, setup, slug, rows=None):
    setup.state.business_script.append(page(rows or [simple_row(slug)], slug))
    code, out, _ = refresh(run_cli, slug)
    assert code == 0, out
    return listing(run_cli, slug)[1]


@pytest.mark.parametrize("slug", SLUGS)
def test_exact_request_contract_rejects_mutation_filters_and_pagination(slug):
    from dogopencli.errors import CliError
    from dogopencli.plugins import get_capability
    from dogopencli.transport import QueryRequest, validate_request

    cap = get_capability("payment.rules." + slug.replace("-", "_") + ".list")
    body = (
        {"pageNum": 1, "pageSize": 1000}
        if slug == "same-bank-transfer"
        else {"pageNo": 0, "pageSize": 1000}
    )
    base = dict(
        capability=cap.name,
        method=cap.contract.method,
        host=cap.contract.host,
        path=cap.contract.path,
        body=body,
    )
    for changes in [
        dict(method="DELETE"),
        dict(host="other.example"),
        dict(path=cap.contract.path + "/execute"),
        dict(body=body | {"status": "ON"}),
        dict(body=body | {"ctoken": "SECRET"}),
        dict(body=body | {"pageSize": 20}),
        dict(body=body | {"pageNum" if slug == "same-bank-transfer" else "pageNo": 2}),
        dict(body={}),
    ]:
        with pytest.raises(CliError) as exc:
            validate_request(QueryRequest(**(base | changes)), cap.contract)
        assert exc.value.code == "REQUEST_NOT_ALLOWED"
