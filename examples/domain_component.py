"""Runnable domain registration example using synthetic data and fake transport.

Run from the repository root: PYTHONPATH=src python examples/domain_component.py
This process never opens Chrome, reads production data, or changes user settings.
"""

from __future__ import annotations

import json
from argparse import Namespace
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from dogopencli import plugins
from dogopencli.auth.domains import authenticate_domains
from dogopencli.browser.environment import BrowserEnvironment
from dogopencli.catalog import build_domain_catalog
from dogopencli.domains import DomainService
from dogopencli.helpspec import BizNode
from dogopencli.plugins import DomainAuthPolicy, DomainComponent, leaf_registration

PORTAL = "https://example.test/shared-portal"


class FakeTransport:
    """Replace only the external boundary, preserving domain declarations."""

    def query(self, domain_id: str) -> list[dict]:
        return [{"id": "synthetic-1", "domain": domain_id}]

    def authenticated(self, domain_id: str) -> bool:
        return domain_id in {"sample", "sample_peer"}


def fake_auth(environment: BrowserEnvironment, *, timeout: float = 15.0) -> dict:
    """Use the real domain probe signature with a synthetic external boundary."""
    return {
        "domain": environment.domain_id,
        "authenticated": FakeTransport().authenticated(environment.domain_id),
        "mode": "headless",
        "startup_url": environment.startup_url,
    }


def sample_list(args: Namespace) -> int:
    """A declared execution binding; core resolves it through the registry."""
    print(json.dumps(FakeTransport().query(args.command_path[0])))
    return 0


def sample_description(node) -> dict:
    """Describe synthetic data without inspecting browser, config or records."""
    return {
        "schema_version": 1,
        "data_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "domain": {"type": "string"}},
                "required": ["id", "domain"],
            },
        },
        "read_guide": {"summary": "Synthetic records for the domain component sample."},
    }


@dataclass(frozen=True)
class SampleCapability:
    name: str
    cache_enabled: bool = False


def component(domain_id: str) -> DomainComponent:
    """Contribute a whole domain through the same interface as built-ins."""
    capability = SampleCapability(f"{domain_id}_items")
    return DomainComponent(
        id=domain_id,
        entry_point=PORTAL,
        auth=DomainAuthPolicy(probe=fake_auth),
        handlers={f"{domain_id}_list": sample_list},
        groups=(BizNode((domain_id,), "Synthetic inquiry domain."),),
        leaves=(
            leaf_registration(
                capability,
                description=sample_description,
                commands=(
                    BizNode(
                        (domain_id, "list"),
                        "List synthetic records through fake transport.",
                        handler=f"{domain_id}_list",
                    ),
                ),
            ),
        ),
    )


def run() -> dict:
    original = plugins.domain_plugins()
    sample, peer = component("sample"), component("sample_peer")
    try:
        plugins.register_domains((*original, sample, peer))
        catalog = build_domain_catalog(plugins.domain_plugins())
        assert ("sample", "list") in catalog
        assert ("sample_peer", "list") in catalog
        # A shared portal does not merge identities or auth observations.
        assert sample.entry_point == peer.entry_point
        with TemporaryDirectory(prefix="dogopencli-domain-sample-") as directory:
            root = Path(directory)
            environment = BrowserEnvironment(
                cdp_url="http://127.0.0.1:48529",
                profile=root / "chrome",
                startup_url=PORTAL,
                chrome_bin="unused-synthetic-browser",
                log_path=root / "chrome.log",
            )
            result = authenticate_domains(
                environment,
                DomainService(root / "config.toml"),
                [sample.id, peer.id],
                recover=False,
            )
            auth = result["domains"]
        handler = plugins.handler_for(catalog[("sample", "list")].handler)
        assert handler is sample_list
        output = StringIO()
        with redirect_stdout(output):
            assert handler(Namespace(command_path=("sample", "list"))) == 0
        rows = json.loads(output.getvalue())
        plugins.register_domains((*original, peer))
        remaining = build_domain_catalog(plugins.domain_plugins())
        assert not any("sample" in path[:2] for path in remaining)
        assert ("sample_peer", "list") in remaining
        return {"auth": auth, "records": rows, "removed_domain": sample.id}
    finally:
        plugins.register_domains(original)


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
