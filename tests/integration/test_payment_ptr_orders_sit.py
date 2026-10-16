"""Bounded PTR order inquiries through public CLI and synthetic CDP."""

from datetime import datetime

import pytest
from test_sla_cli_sit import list_page, sla_setup  # noqa: F401

START = "2025-01-01T00:00:00+08:00"
END = "2025-01-02T00:00:00+08:00"
START_MS = int(datetime.fromisoformat(START).timestamp()) * 1000
END_MS = int(datetime.fromisoformat(END).timestamp()) * 1000
WINDOW = ["--updated-from", START, "--updated-to", END]


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        file.write('\n[sources.payment_ptr_orders]\nkind = "cdp"\n')
    return sla_setup


def order(identity, modified, **changes):
    return {
        "ptrOrderId": identity,
        "gmtModified": modified,
        "orderStatus": "FAILED",
        "verifyStatus": "VERIFIED",
        "ptrFinalResult": "PASS",
        "productionTrialRunFundOutAbilityVO": {"financialInstCode": "SYNTHETIC"},
        **changes,
    }


def page(rows, **changes):
    return list_page(rows, page_size=500, **changes)


def refresh(run_cli, window=WINDOW):
    return run_cli(["refresh", "payment", "ptr", "orders", *window])


def listing(run_cli, *flags, window=WINDOW):
    return run_cli(["payment", "ptr", "orders", "list", *window, *flags])
