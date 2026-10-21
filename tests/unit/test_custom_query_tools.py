"""Custom orchestration shares restricted queries, retries and total budgets."""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

from dogopencli import collect
from dogopencli.contracts import EndpointContract
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.query import (
    CustomListResult,
    QueryBudget,
    QueryFailed,
    QueryRefused,
    QueryTools,
    query_capabilities,
)
from dogopencli.result_policy import AcquisitionEvidence
from dogopencli.transport import OriginMetadata, TransportResponse

ORIGIN = OriginMetadata("fixture", True, None, None, None, None, None)


class Source:
    name = "payment.synthetic.source"
    page_url = "https://fixture.invalid/"
    contract = EndpointContract(
        method="GET",
        host="fixture.invalid",
        path="/list",
        page_size=2,
        one_based=False,
        allowed_body_keys=frozenset({"rowStart", "pageSize"}),
        allowed_page_sizes=(2,),
    )

    def page_body(self, scope, position, size):
        return {"rowStart": position, "pageSize": size}

    def parse_rows(self, body):
        value = parse(body)
        return value["rows"], value["total"]


class Detail:
    name = "payment.synthetic.detail"
    page_url = "https://fixture.invalid/"
    contract = EndpointContract(
        method="GET",
        host="fixture.invalid",
        path="/detail",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"id"}),
    )

    def request_body(self, parameters, identity):
        return {"id": identity}

    def parse_detail(self, body, parameters, identity):
        value = parse(body)
        if value.get("refused"):
            raise QueryRefused(native_code="999")
        if value.get("failed"):
            raise QueryFailed(native_code="999")
        if value.get("invalid"):
            raise CliError("INVALID_RESPONSE", "invalid native detail")
        if value.get("id") != identity:
            raise CliError("INVALID_RESPONSE", "wrong identity echo")
        return value


class Script:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.closed = 0

    def execute(self, request, *, timeout):
        assert timeout > 0
        self.requests.append(request)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        status, body = value if isinstance(value, tuple) else (200, value)
        return TransportResponse(status, canonical(body).encode(), ORIGIN)

    def close(self):
        self.closed += 1


def setup(script, *, maximum=20, deadline=None, detail=None):
    declarations = {
        "execution": "custom",
        "queries": {
            "source": {
                "kind": "list",
                "collection": {
                    "provider": "general",
                    "paging": {"mode": "offset", "page_sizes": [2]},
                    "primary_id": {"type": "field", "fields": ["id"]},
                },
            },
            "detail": {
                "kind": "detail",
                "result_identity": {"fields": ["id"], "description": "Native ID"},
            },
        },
        "max_requests": maximum,
        "budget_seconds": 60,
    }
    leaf = SimpleNamespace(
        domain="payment",
        id="payment.synthetic.custom",
        manifest={"operations": {"list": declarations}},
    )
    capabilities = {"source": Source(), "detail": detail or Detail()}
    tools = QueryTools(
        leaf, "list", {}, capabilities, lambda cap: script, deadline=deadline
    )
    return tools, leaf, capabilities


def result(rows=(), *, complete=True):
    return CustomListResult(
        list(rows),
        AcquisitionEvidence.for_collection(
            complete=complete,
            reported_total=None,
            collected_total=len(rows),
            arrivals=len(rows),
        ),
    )


def test_dependency_queries_preserve_native_types_and_source_evidence():
    rows = [{"id": "one", "amount": Decimal("0.1234567890123456789")}]
    native = {"id": "one", "unknown": [False, None, {"nested": ""}]}
    script = Script({"rows": rows, "total": 1}, native)
    tools, _, _ = setup(script)
    source = tools.collect("source")
    detail = tools.detail("detail", source.records[0]["id"])
    candidate = tools.finish_list(result([{"id": "one", "detail": detail}]))
    trace = candidate.evidence.attempts[-1]
    assert source.records == rows
    assert candidate.records == [{"id": "one", "detail": native}]
    assert trace["request_count"] == 2
    assert trace["queries"]["source"]["collections"][0]["acquisition"] == (
        source.evidence.record()
    )
    assert trace["queries"]["detail"]["succeeded"] == 1
    assert "one" not in canonical(trace)
    assert script.closed == 2


def test_retries_and_dependent_queries_share_physical_request_allowance(monkeypatch):
    monkeypatch.setattr(collect, "_sleep", lambda seconds: None)
    script = Script((503, {}), {"rows": [{"id": "one"}], "total": 1})
    tools, _, _ = setup(script, maximum=2)
    assert tools.collect("source").complete
    with pytest.raises(CliError, match="request budget exhausted"):
        tools.detail("detail", "one")
    assert len(script.requests) == 2
    assert tools.evidence()["request_count"] == 2
    # An adapter cannot catch an exhausted budget and publish an empty success.
    with pytest.raises(CliError, match="request budget exhausted"):
        tools.finish_list(result())


def test_every_page_of_repeated_collections_shares_request_budget():
    script = Script({"rows": [{"id": "a"}, {"id": "b"}], "total": 2})
    tools, _, _ = setup(script, maximum=1)
    tools.collect("source", "first")
    with pytest.raises(CliError, match="request budget exhausted"):
        tools.collect("source", "second")
    assert len(script.requests) == 1


def test_dependent_details_reuse_one_named_target_until_operation_finishes():
    script = Script({"id": "one"}, {"id": "two"})
    tools, _, _ = setup(script)
    opened = []

    def factory(capability):
        opened.append(capability.name)
        return script

    tools._transport_factory = factory
    with tools:
        rows = [tools.detail("detail", identity) for identity in ("one", "two")]
        assert opened == ["payment.synthetic.detail"]
        assert script.closed == 0
        candidate = tools.finish_list(result(rows))
        assert candidate.pages == 2
    assert script.closed == 1


def test_operation_scope_closes_target_when_leaf_raises_or_is_interrupted():
    script = Script({"id": "one"})
    tools, _, _ = setup(script)
    with pytest.raises(KeyboardInterrupt), tools:
        tools.detail("detail", "one")
        raise KeyboardInterrupt
    assert script.closed == 1


def test_hard_failure_keeps_query_context_without_lookup_or_response_values():
    tools, _, _ = setup(Script({"invalid": True, "secret": "native-secret"}))
    with pytest.raises(CliError) as caught, tools:
        tools.detail("detail", "private-lookup")
    evidence = caught.value.meta["query_evidence"]
    assert evidence["request_count"] == 1
    assert evidence["queries"]["detail"]["error"]["code"] == "INVALID_RESPONSE"
    assert "private-lookup" not in canonical(evidence)
    assert "native-secret" not in canonical(evidence)


@pytest.mark.parametrize("name,kind", [("unknown", "detail"), ("source", "detail")])
def test_unknown_or_wrong_kind_cannot_open_transport(name, kind):
    script = Script()
    tools, _, _ = setup(script)
    with pytest.raises(CliError) as caught:
        tools.detail(name, "one")
    assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert script.closed == 0 and not script.requests


def test_native_request_allowlist_remains_authoritative():
    native = Detail()
    native.contract = replace(native.contract, allowed_body_keys=frozenset())
    tools, _, _ = setup(Script(), detail=native)
    with pytest.raises(CliError) as caught:
        tools.detail("detail", "one")
    assert caught.value.code == "REQUEST_NOT_ALLOWED"


@pytest.mark.parametrize(
    "response,code",
    [((401, {}), "AUTH_REQUIRED"), ({"invalid": True}, "INVALID_RESPONSE")],
)
def test_caught_hard_failure_cannot_be_converted_to_partial_success(response, code):
    tools, _, _ = setup(Script(response))
    with pytest.raises(CliError) as first:
        tools.detail("detail", "one")
    assert first.value.code == code
    with pytest.raises(CliError) as last:
        tools.finish_list(result(complete=False))
    assert last.value is first.value


def test_only_qualified_refusal_can_be_retained_and_never_as_complete():
    script = Script({"refused": True})
    tools, _, _ = setup(script)
    with pytest.raises(QueryRefused):
        tools.detail("detail", "one")
    with pytest.raises(CliError, match="coverage contradicts"):
        tools.finish_list(result())
    candidate = tools.finish_list(result(complete=False))
    assert not candidate.complete
    assert candidate.evidence.attempts[-1]["queries"]["detail"]["refused"] == 1


def test_retained_detail_failure_allows_later_queries_but_never_complete_output():
    script = Script({"failed": True, "secret": "native-secret"}, {"id": "two"})
    tools, _, _ = setup(script)
    with pytest.raises(QueryFailed) as caught:
        tools.detail("detail", "private-lookup")
    assert caught.value.meta == {"native_code": "999"}
    assert tools.detail("detail", "two") == {"id": "two"}
    with pytest.raises(CliError, match="coverage contradicts"):
        tools.finish_list(result())
    candidate = tools.finish_list(result(complete=False))
    trace = candidate.evidence.attempts[-1]
    assert trace["request_count"] == 2
    assert trace["queries"]["detail"]["failed"] == 1
    assert trace["queries"]["detail"]["succeeded"] == 1
    assert "refused" not in trace["queries"]["detail"]
    assert "private-lookup" not in canonical(trace)
    assert "native-secret" not in canonical(trace)


@pytest.mark.parametrize("error_type", [QueryRefused, QueryFailed])
def test_retained_business_error_cannot_finish_custom_get(error_type):
    script = Script({"refused" if error_type is QueryRefused else "failed": True})
    tools, _, _ = setup(script)
    with pytest.raises(error_type):
        tools.detail("detail", "one")
    with pytest.raises(CliError, match="incomplete required queries"):
        tools.finish_get({"id": "one"})


@pytest.mark.parametrize("error_type", [QueryRefused, QueryFailed])
@pytest.mark.parametrize("stage", ["request", "transport"])
def test_retained_business_error_outside_detail_parser_is_fatal(error_type, stage):
    class Invalid(Detail):
        def request_body(self, parameters, identity):
            if stage == "request":
                raise error_type(native_code="unqueried")
            return super().request_body(parameters, identity)

    script = Script(error_type(native_code="transport"))
    tools, _, _ = setup(script, detail=Invalid())
    with pytest.raises(error_type) as caught:
        tools.detail("detail", "one")
    with pytest.raises(error_type) as final:
        tools.finish_list(result(complete=False))
    assert final.value is caught.value
    assert len(script.requests) == (stage == "transport")


@pytest.mark.parametrize("kind", ["list", "detail"])
@pytest.mark.parametrize("stage", ["request", "parser", "transport"])
def test_unexpected_inquiry_exceptions_cannot_be_caught_into_success(kind, stage):
    def malformed(*args, **kwargs):
        raise ValueError("private response value must never enter diagnostics")

    script = Script({"id": "one", "rows": [], "total": 0})
    tools, _, capabilities = setup(script)
    native = capabilities["source" if kind == "list" else "detail"]
    if stage == "request":
        setattr(native, "page_body" if kind == "list" else "request_body", malformed)
    elif stage == "parser":
        setattr(native, "parse_rows" if kind == "list" else "parse_detail", malformed)
    else:
        script.execute = malformed
    with pytest.raises(CliError) as first:
        if kind == "list":
            tools.collect("source")
        else:
            tools.detail("detail", "one")
    assert first.value.code == "INVALID_RESPONSE"
    assert "private response value" not in first.value.message
    with pytest.raises(CliError) as last:
        tools.finish_list(result(complete=False))
    assert last.value is first.value


def test_incomplete_source_cannot_be_upgraded_by_assembly():
    tools, _, _ = setup(Script({"rows": [{"id": "one"}], "total": 2}))
    assert not tools.collect("source").complete
    with pytest.raises(CliError, match="coverage contradicts"):
        tools.finish_list(result([{"id": "one"}]))
    assert not tools.finish_list(result([{"id": "one"}], complete=False)).complete


def test_expired_deadline_fails_before_query_or_publication(monkeypatch):
    tools, _, _ = setup(Script(), deadline=10)
    monkeypatch.setattr(collect, "_monotonic", lambda: 11)
    with pytest.raises(CliError) as caught:
        tools.detail("detail", "one")
    assert caught.value.code == "TIMEOUT"
    with pytest.raises(CliError):
        tools.finish_list(result())


def test_capability_resolution_checks_interfaces_without_calling_request_hooks():
    tools, leaf, capabilities = setup(Script())
    leaf.adapter = SimpleNamespace(
        query_capability=lambda operation, name, parameters: capabilities[name]
    )
    assert query_capabilities(leaf, "list", {}) == capabilities
    assert tools.evidence()["request_count"] == 0
    capabilities["detail"].parse_detail = lambda body: {}
    with pytest.raises(CliError) as caught:
        query_capabilities(leaf, "list", {})
    assert caught.value.code == "INVALID_LEAF"


def test_shared_get_budget_cannot_reset_for_each_selected_row():
    script = Script({"id": "one"})
    tools, leaf, capabilities = setup(script)
    specification = leaf.manifest["operations"]["list"]
    specification["result_identity"] = {"fields": ["id"]}
    budget = QueryBudget(collect._monotonic() + 60, 1)
    first = QueryTools(
        leaf, "list", {}, capabilities, lambda cap: script, budget=budget
    )
    assert first.finish_get(first.detail("detail", "one")) == {"id": "one"}
    second = QueryTools(
        leaf, "list", {}, capabilities, lambda cap: script, budget=budget
    )
    with pytest.raises(CliError, match="request budget exhausted"):
        second.detail("detail", "two")


@pytest.mark.parametrize("candidate", [None, [], CustomListResult([], None)])
def test_invalid_custom_result_is_rejected(candidate):
    tools, _, _ = setup(Script())
    with pytest.raises(CliError, match="invalid custom List result"):
        tools.finish_list(candidate)


class Aggregate:
    name = "payment.synthetic.aggregate"
    page_url = "https://fixture.invalid/"
    contract = EndpointContract(
        method="GET",
        host="fixture.invalid",
        path="/aggregate",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"account"}),
    )

    def request_body(self, parameters):
        return {"account": parameters["account"]}

    def parse_inquiry(self, body, parameters):
        value = parse(body)
        if value.get("failure"):
            raise CliError("BUSINESS_QUERY_FAILED", "native inquiry failed")
        return value


def aggregate_tools(script, *, maximum=20):
    tools, leaf, capabilities = setup(script, maximum=maximum)
    leaf.manifest["operations"]["list"]["queries"]["aggregate"] = {
        "kind": "inquiry",
        "result_shape": "object",
    }
    capabilities["aggregate"] = Aggregate()
    return tools, leaf, capabilities


def test_native_aggregate_retains_unkeyed_duplicates_and_shared_budget():
    native = {"rows": [{"quotaId": "", "amount": Decimal("1.234567890123456789")}] * 2}
    script = Script(native)
    tools, _, _ = aggregate_tools(script, maximum=1)
    assert tools.inquire("aggregate", {"account": "private-account"}) == native
    with pytest.raises(CliError, match="request budget exhausted"):
        tools.inquire("aggregate", {"account": "private-account"})
    with pytest.raises(CliError, match="request budget exhausted"):
        tools.finish_list(result())
    trace = tools.evidence()
    assert trace["request_count"] == 1
    assert "private-account" not in canonical(trace)


def test_aggregate_parser_failure_remains_fatal_if_leaf_catches_it():
    tools, _, _ = aggregate_tools(Script({"failure": True}))
    with pytest.raises(CliError, match="native inquiry failed"):
        tools.inquire("aggregate", {"account": "a"})
    with pytest.raises(CliError, match="native inquiry failed"):
        tools.finish_list(result(complete=False))


def test_aggregate_allowlist_rejects_unregistered_fields():
    tools, _, caps = aggregate_tools(Script())
    caps["aggregate"].contract = replace(
        caps["aggregate"].contract, allowed_body_keys=frozenset()
    )
    with pytest.raises(CliError) as caught:
        tools.inquire("aggregate", {"account": "a"})
    assert caught.value.code == "REQUEST_NOT_ALLOWED"


def test_aggregate_capability_hooks_are_checked_before_transport():
    tools, leaf, caps = aggregate_tools(Script())
    leaf.adapter = SimpleNamespace(query_capability=lambda op, name, params: caps[name])
    assert query_capabilities(leaf, "list", {}) == caps
    caps["aggregate"].parse_inquiry = lambda body: {}
    with pytest.raises(CliError, match="hooks"):
        query_capabilities(leaf, "list", {})
    assert tools.evidence()["request_count"] == 0


def test_request_identity_validates_context_without_changing_native_root():
    tools, leaf, _ = aggregate_tools(Script())
    spec = leaf.manifest["operations"]["list"]
    spec["lookup"] = {"name": "route"}
    spec["result_identity"] = {"request_fields": ["route", "account", "tenant"]}
    tools._parameters = {"account": "account-a", "tenant": "tenant-a"}
    native = {"dynamicQuotas": [], "staticQuotas": []}
    assert tools.finish_get(native, "route-a") is native
    assert native == {"dynamicQuotas": [], "staticQuotas": []}
    tools._parameters["account"] = ""
    with pytest.raises(CliError, match="scalar components"):
        tools.finish_get(native, "route-a")


def test_local_account_source_requires_opt_in_and_denial_is_fatal(tmp_path):
    tools, _, _ = setup(Script())
    tools._config_file = tmp_path / "config.toml"
    with pytest.raises(CliError) as caught:
        tools.account_directory("cache")
    assert caught.value.code == "REQUEST_NOT_ALLOWED"
    with pytest.raises(CliError):
        tools.finish_list(result())


def test_opted_in_local_absence_never_initializes_cache_or_duckdog(tmp_path):
    tools, leaf, _ = setup(Script())
    leaf.manifest["operations"]["list"]["account_directory"] = True
    tools._config_file = tmp_path / "config.toml"
    assert tools.account_directory("duckdog") is None
    assert tools.account_directory("cache") is None
    assert not list(tmp_path.iterdir())
    assert tools.evidence()["request_count"] == 0


def test_custom_get_retains_unproven_relationship_coverage_in_metadata():
    from dogopencli.leaves.query import CustomGetResult

    tools, leaf, _ = setup(Script())
    leaf.manifest["operations"]["list"]["result_identity"] = {"fields": ["id"]}
    native = {"id": "private-root-identity", "history": [{"id": "old", "version": 1}]}
    evidence = AcquisitionEvidence.for_collection(
        complete=False,
        reported_total=None,
        collected_total=1,
        reasons=("HISTORY_COVERAGE_UNPROVEN",),
        attempts=({"component": "history", "complete": False},),
    )
    assert tools.finish_get(CustomGetResult(native, evidence)) is native
    retained = tools.evidence()["coverage"]
    assert retained["scope_complete"] is False
    assert retained["reasons"] == ["HISTORY_COVERAGE_UNPROVEN"]
    assert "private-root-identity" not in canonical(tools.evidence())


def test_caught_local_reader_exception_cannot_finish_success(tmp_path, monkeypatch):
    from dogopencli.leaves import account_sources

    tools, leaf, _ = setup(Script())
    leaf.manifest["operations"]["list"]["account_directory"] = True
    tools._config_file = tmp_path / "config.toml"

    def broken(*args):
        raise ValueError("private values")

    monkeypatch.setattr(account_sources, "read_account_directory", broken)
    with pytest.raises(CliError, match="account directory source failed"):
        tools.account_directory("cache")
    with pytest.raises(CliError, match="account directory source failed"):
        tools.finish_list(result())


def test_entity_selector_is_opt_in_and_never_accepts_arbitrary_selector(tmp_path):
    tools, _, _ = setup(Script())
    tools._config_file = tmp_path / "config.toml"
    with pytest.raises(CliError) as caught:
        tools.entity_selector()
    assert caught.value.code == "REQUEST_NOT_ALLOWED"
    assert not list(tmp_path.iterdir())
