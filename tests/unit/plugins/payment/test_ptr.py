"""Synthetic contracts at PTR parsing and request boundaries."""

import json

import pytest

from dogopencli import collect
from dogopencli.errors import CliError
from dogopencli.plugins.payment.ptr import CASES, collect_stable
from dogopencli.transport import QueryRequest, TransportResponse, validate_request
from dogopencli.transport.cdp import ORIGIN_CDP


def envelope(rows, **changes):
    return json.dumps(
        {
            "success": True,
            "pageNo": 0,
            "pageSize": 5000,
            "totalCount": len(rows),
            "resultDataList": rows,
            **changes,
        }
    ).encode()


def test_case_projection_omits_personal_and_unknown_fields():
    page = CASES.parse_page(
        envelope(
            [
                {
                    "id": "case-synthetic",
                    "caseName": "negative",
                    "oboName": "private",
                    "unknown": "private",
                    "creditorAmount": {
                        "amount": 1.25,
                        "cent": 125,
                        "secret": "private",
                    },
                    "fundOutAbilityBaselineVO": {
                        "financialInstCode": "BANK",
                        "debtorAccountNo": "private",
                    },
                }
            ]
        )
    )
    assert page.records == [
        {
            "id": "case-synthetic",
            "caseName": "negative",
            "creditorAmount": {"amount": 1.25, "cent": 125},
            "fundOutAbilityBaselineVO": {"financialInstCode": "BANK"},
        }
    ]


def row(identity="synthetic-a", **extra):
    return {"id": identity, "fundOutAbilityBaselineVO": {}, **extra}


@pytest.mark.parametrize(
    "changes",
    [
        {"pageNo": 1},
        {"pageNo": False},
        {"pageSize": 10000},
        {"pageSize": "5000"},
        {"totalCount": True},
        {"totalCount": -1},
        {"totalCount": 5001},
        {"totalCount": 2},
        {"resultDataList": None},
        {"success": False},
    ],
)
def test_rejects_unproven_full_page(changes):
    with pytest.raises(CliError):
        CASES.parse_page(envelope([row()], **changes))


@pytest.mark.parametrize(
    "bad",
    [
        row(id=""),
        row(id=1),
        {"id": "case"},
        row(fundOutAbilityBaselineVO=None),
        row(fundOutAbilityBaselineVO=[]),
        row(fundOutAbilityBaselineVO={"supportObo": True}),
        row(verifyResult="true"),
        row(gmtCreate=True),
        row(creditorAmount=[]),
        row(creditorAmount={"cent": 1.2}),
        row(creditorAmount={"amount": True}),
        row(caseName={"unexpected": "object"}),
    ],
)
def test_rejects_invalid_retained_types_and_missing_outflow_provenance(bad):
    with pytest.raises(CliError):
        CASES.parse_page(envelope([bad]))


def test_duplicate_id_never_becomes_a_complete_scope():
    with pytest.raises(CliError, match="duplicate"):
        CASES.parse_page(envelope([row(), row()]))


def test_optional_nulls_survive_without_becoming_defaults():
    original = row(
        caseName=None,
        creditorAmount=None,
        fundOutAbilityBaselineVO={"supportObo": None},
    )
    assert CASES.parse_page(envelope([original])).records == [original]
    CASES.validate_row(original)


@pytest.mark.parametrize(
    "extra",
    [
        {"userIban": "sensitive"},
        {"fundOutAbilityBaselineVO": {"debtorAccountNo": "sensitive"}},
        {"creditorAmount": {"unknown": "sensitive"}},
    ],
)
def test_cache_validation_rejects_unapproved_fields(extra):
    with pytest.raises(CliError):
        CASES.validate_row(row(**extra))


@pytest.mark.parametrize(
    "changes",
    [
        {"method": "POST"},
        {"host": "other.invalid"},
        {"path": "/api/ptr/case/detail.json"},
        {"body": {"pageNo": 1, "pageSize": 5000}},
        {"body": {"pageNo": 0, "pageSize": 10000}},
        {"body": {"pageNo": False, "pageSize": 5000}},
        {"body": {"pageNo": 0, "pageSize": 5000, "caseName": "x"}},
    ],
)
def test_transport_rejects_every_unregistered_request(changes):
    values = dict(
        capability=CASES.name,
        method="GET",
        host=CASES.contract.host,
        path=CASES.contract.path,
        body={"pageNo": 0, "pageSize": 5000},
    )
    values.update(changes)
    with pytest.raises(CliError):
        validate_request(QueryRequest(**values), CASES.contract)


def test_nested_local_matching_is_exact_or_within_and_across_fields():
    records = [
        row("a", obo="Y", fundOutAbilityBaselineVO={"financialInstCode": "BANK"}),
        row("b", obo="N", fundOutAbilityBaselineVO={"financialInstCode": "BANK"}),
        row("c", obo="Y", fundOutAbilityBaselineVO={"financialInstCode": "bank"}),
        row("d", obo=None),
    ]
    assert CASES.filter_records(
        records,
        {
            "obo": ["Y", "unknown"],
            "fundOutAbilityBaselineVO.financialInstCode": ["BANK"],
        },
    ) == [records[0]]
    assert CASES.filter_records(records, {"obo": [" Y"]}) == []
    with pytest.raises(CliError):
        CASES.filter_records(records, {"obo": [" "]})


class Transport:
    def __init__(self, responses, clock=None):
        self.responses = iter(responses)
        self.timeouts = []
        self.clock = clock

    def execute(self, request, *, timeout):
        validate_request(request, CASES.contract)
        self.timeouts.append(timeout)
        if self.clock is not None:
            self.clock[0] += 4
        return TransportResponse(200, next(self.responses), ORIGIN_CDP)


def test_stable_reads_compare_retained_data_by_identity_with_one_budget(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(collect, "_monotonic", lambda: clock[0])
    monkeypatch.setattr(collect, "REFRESH_BUDGET_SECONDS", 10)
    transport = Transport(
        [
            envelope([row("b"), row("a", oboName="omitted")]),
            envelope([row("a", oboName="changed omitted"), row("b")]),
        ],
        clock,
    )
    result = collect_stable(CASES, transport, CASES.default_scope)
    assert [r["id"] for r in result.records] == ["a", "b"]
    assert result.deadline == 10
    assert transport.timeouts == [10, 6]


def test_stability_rejects_content_drift():
    transport = Transport(
        [envelope([row(caseName="first")]), envelope([row(caseName="changed")])]
    )
    with pytest.raises(CliError, match="changed"):
        collect_stable(CASES, transport, CASES.default_scope)


def test_second_read_cannot_reset_first_read_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(collect, "_monotonic", lambda: clock[0])
    monkeypatch.setattr(collect, "REFRESH_BUDGET_SECONDS", 6)
    transport = Transport([envelope([row()]), envelope([row()])], clock)
    with pytest.raises(CliError) as error:
        collect_stable(CASES, transport, CASES.default_scope)
    assert error.value.code == "TIMEOUT"
    assert transport.timeouts == [6, 2]


def test_schema_describes_only_retained_nullable_fields():
    item = CASES.data_schema["items"]
    assert item["required"] == ["id", "fundOutAbilityBaselineVO"]
    assert item["additionalProperties"] is False
    properties = item["properties"]
    assert properties["verifyResult"] == {"type": ["boolean", "null"]}
    assert "userIban" not in properties
    assert properties["fundOutAbilityBaselineVO"]["additionalProperties"] is False
    assert properties["creditorAmount"]["properties"]["amount"] == {
        "type": ["number", "null"]
    }


def test_request_filter_boundary_rejects_boolean_page_number():
    with pytest.raises(CliError):
        CASES.request_filters({"pageNo": False, "pageSize": 5000})


def test_integer_amount_does_not_round_trip_through_float():
    original = row(creditorAmount={"amount": 10**400})
    assert CASES.parse_page(envelope([original])).records == [original]
