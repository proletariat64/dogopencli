"""Offline public CLI fixtures; no production rows, credentials or CDP access."""

import json
import os
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest


@pytest.fixture
def run_cli(
    capsys: pytest.CaptureFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[list[str]], tuple[int, str, str]]:
    from dogopencli.cli import main

    # Public commands now persist operational observations. Keep tests that
    # don't supply configuration away from the real user's domain settings.
    if not any(
        key in os.environ for key in ("DOGOPENCLI_CONFIG", "DOGOPENCLI_CONFIG_DIR")
    ):
        monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "config.toml"))

    def run(argv: list[str]) -> tuple[int, str, str]:
        code = main(argv)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


@pytest.fixture(autouse=True)
def _fast_entry_stability_window(monkeypatch: pytest.MonkeyPatch):
    """Shrink the probe's entry-stability window and poll interval in tests;
    both are bounded waits, not part of any verdict. Tests exercising the
    window set it explicitly."""
    from dogopencli.browser import cdp

    monkeypatch.setattr(cdp, "ENTRY_STABILITY_SECONDS", 0.01)
    monkeypatch.setattr(cdp, "POLL_INTERVAL_SECONDS", 0.01)


@pytest.fixture
def envelope():
    def parse_envelope(stdout: str) -> dict:
        return json.loads(stdout, parse_float=Decimal)

    return parse_envelope
