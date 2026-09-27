"""Synthetic boundary proof for bounded outflow PTR order inquiries."""

import json

import pytest

from dogopencli.errors import CliError
from dogopencli.plugins.payment import ptr_orders

START = "2025-01-01T00:00:00+08:00"
END = "2025-01-02T00:00:00+08:00"
START_MS = 1735660800000
END_MS = 1735747200000


def row(identity="ORDER-A", modified=START_MS, **fields):
    return {
        "ptrOrderId": identity,
        "gmtModified": modified,
        "productionTrialRunFundOutAbilityVO": {"financialInstCode": "BANK"},
        **fields,
    }


def envelope(rows, **fields):
    return json.dumps(
        {
            "success": True,
            "pageNo": 0,
            "pageSize": 500,
            "totalCount": len(rows),
            "resultDataList": rows,
            **fields,
        }
    ).encode()


def test_window_binds_exact_scope_and_padded_request():
    cap = ptr_orders.bind_window(
        "2025-01-01T00:00:00+08:00", "2025-01-02T00:00:00+08:00"
    )
    assert cap.default_scope == (
        "updated:2025-01-01T00:00:00+08:00:2025-01-02T00:00:00+08:00"
    )
    assert cap.page_body(cap.default_scope, 0, 500) == {
        "pageNo": 0,
        "pageSize": 500,
        "modifiedTimeBegin": "2024-12-31 23:59:59",
        "modifiedTimeEnd": "2025-01-02 00:00:01",
    }


def test_parser_keeps_padding_for_completeness_and_projects_sensitive_fields():
    cap = ptr_orders.bind_window(START, END)
    raw = row(
        modified=START_MS - 500,
        creditorAccountNo="PRIVATE",
        oboName="PRIVATE",
        failureReason="Operational failure text",
        debtorAmount={"amount": 1.25, "currencyCode": "USD", "secret": "PRIVATE"},
    )
    parsed = cap.parse_page(envelope([raw]))
    assert parsed.records == [
        row(
            modified=START_MS - 500,
            failureReason="Operational failure text",
            debtorAmount={"amount": 1.25, "currencyCode": "USD"},
        )
    ]
    assert parsed.total_count == 1
    with pytest.raises(CliError):
        cap.validate_row(parsed.records[0])


def test_filters_schema_and_fixed_request_boundary():
    cap = ptr_orders.bind_window(START, END)
    assert cap.request_filters(cap.page_body(cap.default_scope, 0, 500)) == {}
    with pytest.raises(CliError):
        cap.request_filters({**cap.page_body(cap.default_scope, 0, 500), "caseId": "x"})
    rows = [row("b", caseId="CASE"), row("a", caseId=None)]
    assert cap.filter_records(rows, {"caseId": ["CASE", "other"]}) == [rows[0]]
    assert cap.sort_records(rows) == list(reversed(rows))
    assert cap.identity_key(rows[0]) == "b"
    assert ptr_orders.ORDERS.data_schema["items"]["required"] == [
        "ptrOrderId",
        "gmtModified",
        "productionTrialRunFundOutAbilityVO",
    ]


class Transport:
    def __init__(self, cap, responses):
        self.cap = cap
        self.responses = iter(responses)

    def execute(self, request, *, timeout):
        from dogopencli.transport import TransportResponse, validate_request
        from dogopencli.transport.cdp import ORIGIN_CDP

        validate_request(request, self.cap.contract)
        return TransportResponse(200, next(self.responses), ORIGIN_CDP)


def test_stability_precedes_half_open_trimming():
    cap = ptr_orders.bind_window(START, END)
    rows = [row("before", START_MS - 500), row("start", START_MS), row("end", END_MS)]
    result = ptr_orders.collect_stable(
        cap, Transport(cap, [envelope(rows), envelope(rows[::-1])]), cap.default_scope
    )
    assert result.records == [rows[1]]
    assert result.complete and result.total_count == 1
    changed = [
        dict(r, failureReason="changed") if r["ptrOrderId"] == "before" else r
        for r in rows
    ]
    with pytest.raises(CliError, match="changed"):
        ptr_orders.collect_stable(
            cap, Transport(cap, [envelope(rows), envelope(changed)]), cap.default_scope
        )


@pytest.mark.parametrize(
    "start,end",
    [
        ("2025-01-01", END),
        (START.replace("+08:00", "Z"), END),
        (START.replace("00:00:00", "00:00:00.001"), END),
        (END, START),
        (START, START),
        (START, "2025-02-02T00:00:00+08:00"),
        ("9999-01-01T00:00:00+08:00", "9999-01-02T00:00:00+08:00"),
        ("2025-02-30T00:00:00+08:00", END),
        ("0001-01-01T00:00:00+08:00", "0001-01-02T00:00:00+08:00"),
    ],
)
def test_invalid_window_rejected_before_transport(start, end):
    with pytest.raises(CliError) as error:
        ptr_orders.bind_window(start, end)
    assert error.value.code == "INVALID_ARGUMENT"
    assert error.value.exit_code == 2


def test_early_year_wire_remains_zero_padded():
    cap = ptr_orders.bind_window(
        "0999-01-02T00:00:00+08:00", "0999-01-03T00:00:00+08:00"
    )
    assert (
        cap.page_body(cap.default_scope, 0, 500)["modifiedTimeBegin"]
        == "0999-01-01 23:59:59"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"pageNo": True},
        {"pageNo": 1},
        {"pageSize": 200},
        {"pageSize": "500"},
        {"totalCount": True},
        {"totalCount": -1},
        {"totalCount": 501},
        {"totalCount": 2},
        {"resultDataList": None},
        {"success": False},
    ],
)
def test_unproven_acquisition_rejected(changes):
    cap = ptr_orders.bind_window(START, END)
    with pytest.raises(CliError):
        cap.parse_page(envelope([row()], **changes))


@pytest.mark.parametrize(
    "bad",
    [
        row(identity=" "),
        row(identity=3),
        row(modified=True),
        row(modified=None),
        row(modified=START_MS - 1001),
        row(modified=END_MS + 1001),
        row(productionTrialRunFundOutAbilityVO=None),
        row(productionTrialRunFundOutAbilityVO={"supportObo": True}),
        row(failureReason={}),
        row(transactionRate=True),
        row(transactionRate=float("inf")),
        row(debtorAmount={"amount": True}),
        row(returnAmount={"cent": 1.2}),
    ],
)
def test_invalid_raw_row_types_and_scope_rejected(bad):
    cap = ptr_orders.bind_window(START, END)
    with pytest.raises(CliError):
        cap.parse_page(envelope([bad]))


@pytest.mark.parametrize(
    "bad",
    [
        row(secret="private"),
        row(debtorAmount={"secret": "private"}),
        row(modified=START_MS - 1),
        row(modified=END_MS),
    ],
)
def test_cache_validates_public_scope_and_projection(bad):
    cap = ptr_orders.bind_window(START, END)
    with pytest.raises(CliError):
        cap.validate_row(bad)


def test_duplicates_in_padding_cannot_be_hidden_by_trim():
    cap = ptr_orders.bind_window(START, END)
    with pytest.raises(CliError) as error:
        cap.parse_page(
            envelope([row(modified=START_MS - 1), row(modified=START_MS - 1)])
        )
    assert error.value.code == "INCOMPLETE_RESULT"


def test_empty_window_and_nullable_fields_preserve_semantics():
    cap = ptr_orders.bind_window(START, END)
    result = ptr_orders.collect_stable(
        cap, Transport(cap, [envelope([]), envelope([])]), cap.default_scope
    )
    assert result.complete and result.records == [] and result.total_count == 0
    original = row(caseId=None, debtorAmount=None, transactionRate=None)
    assert cap.parse_page(envelope([original])).records == [original]
    cap.validate_row(original)


def test_large_integer_and_decimal_amounts_remain_exact():
    from decimal import Decimal

    cap = ptr_orders.bind_window(START, END)
    original = row(debtorAmount={"amount": 10**400})
    assert cap.parse_page(envelope([original])).records == [original]
    body = envelope([row(transactionRate=0)]).replace(
        b'"transactionRate": 0', b'"transactionRate": 0.12345678901234567890123456789'
    )
    assert cap.parse_page(body).records[0]["transactionRate"] == Decimal(
        "0.12345678901234567890123456789"
    )


@pytest.mark.parametrize(
    "filters",
    [{"caseId": [" "]}, {"caseId": []}, {"batchId": ["x"]}, {"caseId": [True]}],
)
def test_bad_filters_rejected(filters):
    with pytest.raises(CliError):
        ptr_orders.ORDERS.filter_records([], filters)


def test_request_validation_has_exact_bound_values():
    from dogopencli.transport import QueryRequest, validate_request

    cap = ptr_orders.bind_window(START, END)
    body = cap.page_body(cap.default_scope, 0, 500)
    for changes in (
        {"modifiedTimeBegin": "2025-01-01 00:00:00"},
        {"pageNo": False},
        {"pageSize": 501},
        {"action": "verify"},
    ):
        with pytest.raises(CliError):
            validate_request(
                QueryRequest(
                    cap.name,
                    "GET",
                    cap.contract.host,
                    cap.contract.path,
                    {**body, **changes},
                ),
                cap.contract,
            )
    with pytest.raises(CliError):
        ptr_orders.ORDERS.page_body("outflow", 0, 500)


def test_cache_refresh_hint_retains_exact_window():
    cap = ptr_orders.bind_window(START, END)
    assert (
        cap.refresh_command
        == f"refresh payment ptr orders --updated-from {START} --updated-to {END}"
    )
