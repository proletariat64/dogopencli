"""Shared pytest fixtures: synthetic Channel datasets built through the real
preparation tool, config writers, and a public-CLI runner. All data is
synthetic; no production rows, credentials, or CDP access."""

import importlib.util
import json
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_prepare_module():
    spec = importlib.util.spec_from_file_location(
        "prepare_channel_snapshot",
        REPO_ROOT / "scripts" / "prepare_channel_snapshot.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def prepare_module():
    return _load_prepare_module()


@pytest.fixture
def sample_channel_rows() -> list[dict]:
    return sample_rows()


@pytest.fixture
def bulk_channel_rows():
    return bulk_rows


def sample_rows() -> list[dict]:
    def row(
        ability_id: int,
        status: str,
        inst: str,
        account: str,
        account_no: str,
        clearing: str,
        debit_ccy: str,
        credit_ccy: str,
        country: str,
        version: str,
        amount,
    ) -> dict:
        return {
            "abilityId": ability_id,
            "payoutType": "EXTERNAL",
            "status": status,
            "financialInstCode": inst,
            "debitAccountName": account,
            "debitAccountNo": account_no,
            "clearingSystemName": clearing,
            "debitCurrency": debit_ccy,
            "creditCurrency": credit_ccy,
            "debitInstCountryCode": country,
            "configVersion": version,
            "chargeAmount": {
                "amount": amount,
                "cent": 0,
                "centFactor": 100,
                "currency": debit_ccy,
                "currencyCode": debit_ccy,
            },
        }

    return [
        row(
            101,
            "ENABLE",
            "CITILD",
            "ACCT-A",
            "9001",
            "BOOK RTP",
            "USD",
            "CNY",
            "GB",
            "v1",
            Decimal("0.10"),
        ),
        row(
            102,
            "DISABLE",
            "CITILD",
            "ACCT-A",
            "9001",
            "BOOK RTP",
            "USD",
            "USD",
            "GB",
            "v2",
            Decimal("1.00"),
        ),
        row(
            103,
            "ENABLE",
            "SCBLSG",
            "ACCT-B",
            "9002",
            "FX PAYOUT",
            "EUR",
            "USD",
            "SG",
            "v1",
            Decimal("2.50"),
        ),
        row(
            104,
            "GRAY",
            "HSBCHK",
            "ACCT-C",
            "9003",
            "BOOK",
            "USD",
            "IDR",
            "HK",
            "v1",
            Decimal("0.00"),
        ),
        row(
            105,
            "ENABLE",
            "CITILD",
            "ACCT-D",
            "9004",
            "BOOK RTP",
            "USD",
            "CNY",
            "GB",
            "v3",
            Decimal("0.1234567890123456789"),
        ),
        row(
            106,
            "INIT",
            "SCBLSG",
            "ACCT-B",
            "9002",
            "FX PAYOUT",
            "EUR",
            "USD",
            "SG",
            "v2",
            Decimal("3.25"),
        ),
        row(
            107,
            "TEST",
            "HSBCHK",
            "ACCT-E",
            "9005",
            "BOOK",
            "HKD",
            "USD",
            "HK",
            "v1",
            Decimal("4.00"),
        ),
        row(
            108,
            "ENABLE",
            "CITILD",
            "ACCT-F",
            "9006",
            "BOOK RTP",
            "GBP",
            "CNY",
            "GB",
            "v1",
            Decimal("5.75"),
        ),
    ]


def bulk_rows(count: int) -> list[dict]:
    return [
        {
            "abilityId": 900000 + index,
            "payoutType": "EXTERNAL",
            "status": "ENABLE",
            "financialInstCode": "CITILD",
            "debitAccountName": f"ACCT-BULK-{index}",
            "debitAccountNo": str(80000 + index),
            "clearingSystemName": "BOOK RTP",
            "debitCurrency": "USD",
            "creditCurrency": "CNY",
            "debitInstCountryCode": "GB",
            "configVersion": f"bulk-{index}",
            "chargeAmount": {
                "amount": Decimal("0.01"),
                "cent": 1,
                "centFactor": 100,
                "currency": "USD",
                "currencyCode": "USD",
            },
        }
        for index in range(1, count + 1)
    ]


@pytest.fixture
def dataset_factory(tmp_path: Path, prepare_module):
    """Build a synthetic prepared dataset via scripts/prepare_channel_snapshot.py."""

    def build(
        rows: list[dict],
        name: str = "dataset",
        observed_at: str | None = None,
    ) -> Path:
        if observed_at is None:
            observed_at = datetime.now(timezone.utc).isoformat()
        export = tmp_path / f"{name}-export"
        export.mkdir()
        data = [{"seqid": i, **row} for i, row in enumerate(rows, 1)]
        (export / "records.jsonl").write_text(
            "\n".join(prepare_module.canonical(r) for r in data) + "\n"
        )
        (export / "manifest.json").write_text(
            json.dumps(
                {
                    "summary": {
                        "scope": "EXTERNAL",
                        "observed_at": observed_at,
                        "exported_rows": len(rows),
                        "page_size": 100,
                        "failed_pages": [7],
                        "reported_totals": [len(rows) + 100],
                    },
                    "pages": [
                        {
                            "page": 1,
                            "outcome": "success",
                            "rows_observed": len(rows),
                            "seqid_start": 1,
                            "seqid_end": len(rows),
                        }
                    ],
                }
            )
        )
        destination = tmp_path / name
        prepare_module.prepare([export], destination)
        return destination

    return build


@pytest.fixture
def config_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Write a config.toml and point DOGOPENCLI_CONFIG at it."""

    def write(
        dataset: Path,
        ttl_hours: float | int = 72,
        dataset_id: str | None = None,
        kind: str = "snapshot",
    ) -> Path:
        lines = [
            "[cache]",
            f'path = "{tmp_path / "cache.sqlite3"}"',
            f"ttl_hours = {ttl_hours}",
            "",
            "[sources.payment_channel]",
            f'kind = "{kind}"',
            f'path = "{dataset}"',
        ]
        if dataset_id is not None:
            lines.append(f'dataset_id = "{dataset_id}"')
        config_path = tmp_path / "config.toml"
        config_path.write_text("\n".join(lines) + "\n")
        monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config_path))
        return config_path

    return write


@pytest.fixture
def run_cli(
    capsys: pytest.CaptureFixture,
) -> Callable[[list[str]], tuple[int, str, str]]:
    from dogopencli.cli import main

    def run(argv: list[str]) -> tuple[int, str, str]:
        code = main(argv)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


@pytest.fixture(autouse=True)
def _fast_entry_stability_window(monkeypatch: pytest.MonkeyPatch):
    """Shrink the probe's entry-stability window in tests; it is a bounded
    wait, not part of any verdict. Tests exercising the window set it
    explicitly."""
    from dogopencli.browser import cdp

    monkeypatch.setattr(cdp, "ENTRY_STABILITY_SECONDS", 0.01)


@pytest.fixture
def envelope():
    def parse_envelope(stdout: str) -> dict:
        return json.loads(stdout, parse_float=Decimal)

    return parse_envelope
