"""Installed-leaf observations through the public CLI and fake CDP."""

import json
import shutil
from pathlib import Path

import pytest
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp


@pytest.fixture
def installed(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "src/dogopencli/leaf_packages"
    shutil.copytree(source, tmp_path / "plugins")
    config = tmp_path / "config.toml"
    config.write_text(
        f'[auth]\nprofile="{tmp_path / "chrome"}"\ncdp_url="http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    browser = FakeBrowser()
    cdp.set_transport_factory(browser.transport)
    yield browser
    cdp.set_transport_factory(None)


def test_disabled_domain_rejects_before_query_and_does_not_record_execution(
    run_cli, installed
):
    assert run_cli(["domain", "disable", "payment"])[0] == 0
    code, output, _ = run_cli(["payment", "list", "sla.baselines", "--live"])
    assert code == 1
    assert json.loads(output)["error"]["code"] == "DOMAIN_DISABLED"
    assert installed.business_requests == []
    _, output, _ = run_cli(["domain", "leaves", "payment"])
    assert all(
        leaf["last_execution"]["outcome"] == "unknown"
        for leaf in json.loads(output)["result"]
    )


def test_failed_query_records_operation_error_and_preserves_auth_unknown(
    run_cli, installed
):
    code, output, _ = run_cli(["payment", "list", "sla.baselines"])
    assert code == 1
    assert json.loads(output)["error"]["code"] == "CACHE_MISS"
    _, output, _ = run_cli(["domain", "show", "payment"])
    domain = json.loads(output)["result"]
    leaf = domain["leaves"][0]
    assert leaf["id"] == "payment.sla.baselines"
    assert leaf["last_execution"]["outcome"] == "failed"
    assert leaf["last_execution"]["operation"] == "list"
    assert leaf["last_execution"]["error_code"] == "CACHE_MISS"
    assert domain["auth"]["outcome"] == "unknown"


def test_describe_and_prune_do_not_replace_execution_observation(run_cli, installed):
    run_cli(["payment", "list", "sla.baselines"])
    _, output, _ = run_cli(["domain", "leaves", "payment"])
    previous = json.loads(output)["result"][0]["last_execution"]
    assert run_cli(["payment", "describe", "sla.baselines"])[0] == 0
    assert run_cli(["payment", "prune", "sla.baselines"])[0] == 0
    _, output, _ = run_cli(["domain", "leaves", "payment"])
    assert json.loads(output)["result"][0]["last_execution"] == previous


@pytest.mark.parametrize("format", ["json", "text"])
def test_usable_incomplete_result_records_warning_independent_of_rendering(
    run_cli, installed, format
):
    from dogopencli.browser.environment import FX_STARTUP_URL

    installed.href = FX_STARTUP_URL
    installed.business_script.append(
        {
            "status": 200,
            "body": {
                "success": True,
                "result": {
                    "success": True,
                    "value": {
                        "items": [{"uniqueId": "native-1"}],
                        "totalCount": 1,
                        "currentPage": 0,
                        "pageSize": 50,
                    },
                },
            },
        }
    )
    code, output, _ = run_cli(
        ["fx", "list", "trade", "--live", "--trade-id", "native-1", "--format", format]
    )
    assert code == 0, output
    _, output, _ = run_cli(["domain", "show", "fx"])
    leaf = json.loads(output)["result"]["leaves"][0]
    assert leaf["last_execution"]["outcome"] == "warning"
    assert leaf["last_execution"]["operation"] == "list"
