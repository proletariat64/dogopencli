"""PTR public CLI with synthetic CDP responses and real private SQLite."""

import pytest
from test_sla_cli_sit import list_page, sla_setup  # noqa: F401


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.payment_ptr_cases]\nkind = "cdp"\n')
    return sla_setup


def case(identity="CASE-01", **changes):
    return {
        "id": identity,
        "caseName": "Expected rejection",
        "caseType": "NEGATIVE",
        "verifyResult": True,
        "fundOutAbilityBaselineVO": {
            "financialInstCode": "SYNTHETIC-BANK",
            "debtorCurrency": "USD",
        },
        **changes,
    }


def refresh(run_cli):
    return run_cli(["refresh", "payment", "ptr", "cases"])


def listing(run_cli, *flags):
    return run_cli(["payment", "ptr", "cases", "list", *flags])
