"""Public-CLI SIT for the Channel snapshot source (issue #2).

Drives refresh + list through dogopencli.cli.main with synthetic datasets;
asserts stdout/stderr, exit codes and cache file state. Fully offline.
"""

import json
from decimal import Decimal

import pytest

PRECISE_AMOUNT = "0.1234567890123456789"


@pytest.fixture
def small_setup(dataset_factory, config_factory, sample_channel_rows):
    dataset = dataset_factory(sample_channel_rows)
    config_factory(dataset)
    return dataset


def refresh(run_cli, *extra: str) -> tuple[int, str, str]:
    return run_cli(["refresh", "payment", "channel", *extra])


def listing(run_cli, *extra: str) -> tuple[int, str, str]:
    return run_cli(["payment", "channel", "list", *extra])


def json_decimal(stdout: str) -> dict:

    return json.loads(stdout, parse_float=Decimal)
