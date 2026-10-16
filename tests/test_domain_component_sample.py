"""The runnable example uses the same public auth contract as real domains."""

import runpy
from pathlib import Path

from dogopencli import plugins
from dogopencli.auth.domains import authenticate_domains
from dogopencli.browser.environment import BrowserEnvironment
from dogopencli.domains import DomainService


def test_sample_auth_runs_through_shared_orchestration(tmp_path):
    sample = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "examples/domain_component.py")
    )
    original = plugins.domain_plugins()
    domains = tuple(sample["component"](name) for name in ("sample", "sample_peer"))
    environment = BrowserEnvironment(
        cdp_url="http://127.0.0.1:48529",
        profile=tmp_path / "chrome",
        startup_url=domains[0].entry_point,
        chrome_bin="unused-synthetic-browser",
        log_path=tmp_path / "chrome.log",
    )
    try:
        plugins.register_domains(domains)
        service = DomainService(tmp_path / "config.toml")
        result = authenticate_domains(environment, service, None, recover=False)
        assert result["authenticated"] is True
        assert [item["domain"] for item in result["domains"]] == [
            "sample",
            "sample_peer",
        ]
        assert all(item["mode"] == "headless" for item in result["domains"])
        assert all(item["checked"] is True for item in result["domains"])
        inventory = service.inventory()
        assert [item["auth"]["outcome"] for item in inventory] == [
            "authenticated",
            "authenticated",
        ]
        assert all(item["auth"]["updated_at"] for item in inventory)
        assert not environment.profile.exists()
    finally:
        plugins.register_domains(original)
