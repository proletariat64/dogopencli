"""Domain acquisition policies remain independent of CLI plugin classes."""

import json

import pytest

from dogopencli import plugins
from dogopencli.plugins.payment.ptr import PtrListCapability, collect_stable
from dogopencli.transport import TransportResponse, validate_request
from dogopencli.transport.cdp import ORIGIN_CDP


@pytest.fixture
def isolated_registry(monkeypatch):
    for name in (
        "_REGISTRY",
        "_COLLECTORS",
        "_REFRESH_HINTS",
        "_COMMANDS",
        "_REFRESH_COMMANDS",
        "_GROUPS",
        "_DESCRIPTIONS",
    ):
        monkeypatch.setattr(plugins, name, getattr(plugins, name).copy())


class ExampleCapability(PtrListCapability):
    name = "example.inquiries.list"
    command_path = "example inquiries"


class Transport:
    def __init__(self, capability):
        self.capability = capability
        self.calls = 0

    def execute(self, request, *, timeout):
        assert request.capability == self.capability.name
        validate_request(request, self.capability.contract)
        self.calls += 1
        return TransportResponse(
            200,
            json.dumps(
                {
                    "success": True,
                    "pageNo": 0,
                    "pageSize": 5000,
                    "totalCount": 1,
                    "resultDataList": [
                        {"id": "synthetic", "fundOutAbilityBaselineVO": {}}
                    ],
                }
            ).encode(),
            ORIGIN_CDP,
        )


def test_registered_policy_uses_runtime_instance_and_resets_to_default(
    isolated_registry,
):
    registered = ExampleCapability()
    bound = ExampleCapability()
    bound.default_scope = "explicit-scope"
    observed = []

    def collector(capability, transport, scope, *, progress=None):
        assert capability is bound
        return collect_stable(capability, transport, scope, progress=progress)

    plugins.register(
        registered,
        collector=collector,
        refresh_hint=lambda capability: (
            f"refresh example --scope {capability.default_scope}"
        ),
    )
    transport = Transport(bound)
    result = plugins.collect_complete_scope(
        bound,
        transport,
        bound.default_scope,
        progress=lambda pages, total: observed.append((pages, total)),
    )
    assert result.complete and result.total_count == 1
    assert transport.calls == 2
    assert observed == [(1, 1), (1, 1)]
    assert plugins.refresh_command(bound) == "refresh example --scope explicit-scope"

    # Replacing a registration without overrides must discard the old policy.
    plugins.register(registered)
    transport = Transport(bound)
    result = plugins.collect_complete_scope(bound, transport, bound.default_scope)
    assert result.complete and transport.calls == 1
    assert plugins.refresh_command(bound) == "refresh example inquiries"
