"""Existing outflow PTR orders within an explicit updated-time interval."""

import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from ...errors import (
    EXIT_USAGE,
    INCOMPLETE_RESULT,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from ...temporal import parse_numeric_offset_instant
from .. import EndpointContract, ParsedPage
from ..envelope import success_document
from . import ptr
from .ptr_common import filter_exact, is_nullable_number, money_schema, project_money

if TYPE_CHECKING:
    from ...collect import CollectedScope

# Verified source zone for the native updated-time interval.
SHANGHAI = timezone(timedelta(hours=8))
WINDOW_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+-][0-9]{2}:[0-9]{2}"
)


ORDER_STRING_FIELDS = frozenset(
    {
        "ptrOrderId",
        "caseId",
        "caseName",
        "caseType",
        "allocateOrderId",
        "finNetId",
        "bizRequestId",
        "creditorAccountAliasName",
        "creditorCurrency",
        "obo",
        "fvt",
        "referenceObo",
        "purposeCode",
        "orderStatus",
        "verifyStatus",
        "ptrFinalResult",
        "failureReason",
        "verifyFvtResult",
        "verifyOboResult",
        "verifyReferenceOboResult",
        "spentTime",
        "spentTimeInfoSource",
        "transactionRateRef",
    }
)
ORDER_TIMESTAMP_FIELDS = frozenset(
    {
        "gmtModified",
        "gmtCreate",
        "bizRequestTime",
        "lastVerificationDt",
        "allocatePayoutTime",
    }
)
ORDER_BASELINE_STRING_FIELDS = frozenset(
    {
        "clearingSystemName",
        "debtorAccountAliasName",
        "financialInstCode",
        "regulatoryRequiredObo",
        "supportFvt",
        "supportObo",
        "supportReferenceObo",
        "integrationMode",
        "communicationMode",
    }
)
BASELINE_KEY = "productionTrialRunFundOutAbilityVO"


def _project(row: Any) -> dict[str, Any]:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("ptrOrderId"), str)
        or not row["ptrOrderId"].strip()
        or type(row.get("gmtModified")) is not int
    ):
        raise CliError(
            INVALID_RESPONSE,
            "PTR order requires an identity and modification timestamp",
        )
    if not isinstance(row.get(BASELINE_KEY), dict):
        raise CliError(
            INVALID_RESPONSE, "PTR order requires an outflow baseline object"
        )
    result: dict[str, Any] = {}
    for key in ORDER_STRING_FIELDS | ORDER_TIMESTAMP_FIELDS | {"transactionRate"}:
        if key not in row:
            continue
        value = row[key]
        valid = (
            is_nullable_number(value)
            if key == "transactionRate"
            else value is None
            or type(value) is (str if key in ORDER_STRING_FIELDS else int)
        )
        if not valid:
            raise CliError(INVALID_RESPONSE, "invalid PTR order field type")
        result[key] = value
    baseline = {
        k: v for k, v in row[BASELINE_KEY].items() if k in ORDER_BASELINE_STRING_FIELDS
    }
    if any(v is not None and type(v) is not str for v in baseline.values()):
        raise CliError(INVALID_RESPONSE, "invalid PTR order baseline field type")
    result[BASELINE_KEY] = baseline
    for key in ("debtorAmount", "returnAmount"):
        if key in row:
            result[key] = project_money(
                row[key], error_prefix="invalid PTR order money"
            )
    return result


@dataclass
class OrdersCapability:
    updated_from: str | None = None
    updated_to: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    native_begin: str | None = None
    native_end: str | None = None

    slug = "orders"
    name = "payment.ptr.orders.list"
    source_config_key = "payment_ptr_orders"
    command_path = "payment ptr orders"
    id_field = "ptrOrderId"
    table_columns: tuple[str, ...] = (
        "ptrOrderId",
        "caseId",
        "orderStatus",
        "verifyStatus",
        "ptrFinalResult",
        "gmtModified",
    )
    filters = (
        ("id", "ptrOrderId"),
        ("case-id", "caseId"),
        ("channel", f"{BASELINE_KEY}.financialInstCode"),
        ("debtor-account", f"{BASELINE_KEY}.debtorAccountAliasName"),
        ("debtor-currency", "debtorAmount.currencyCode"),
        ("creditor-currency", "creditorCurrency"),
        ("clearing-system", f"{BASELINE_KEY}.clearingSystemName"),
        ("order-status", "orderStatus"),
        ("verify-status", "verifyStatus"),
        ("final-result", "ptrFinalResult"),
    )

    def parse_page(self, body: bytes) -> ParsedPage:
        self._require_window()
        data = success_document(body)
        if (
            any(
                type(data.get(k)) is not int or data[k] < 0
                for k in ("pageNo", "pageSize", "totalCount")
            )
            or data["pageNo"] != 0
            or data["pageSize"] != 500
        ):
            raise CliError(INVALID_RESPONSE, "invalid PTR order pagination echo")
        rows = data.get("resultDataList")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "missing PTR order list")
        total = data["totalCount"]
        if total > 500 or total != len(rows):
            raise CliError(
                INCOMPLETE_RESULT,
                "PTR order window exceeds verified full-page coverage",
            )
        projected = [_project(row) for row in rows]
        assert self.start_ms is not None and self.end_ms is not None
        if any(
            not self.start_ms - 1000 <= row["gmtModified"] <= self.end_ms + 1000
            for row in projected
        ):
            raise CliError(
                INVALID_RESPONSE, "PTR order falls outside the acquisition window"
            )
        if len({row["ptrOrderId"] for row in projected}) != len(projected):
            raise CliError(INCOMPLETE_RESULT, "duplicate PTR order identities")
        return ParsedPage(projected, 0, 500, total, 1 if total else 0)

    def validate_row(self, row: Any) -> None:
        self._require_window()
        if _project(row) != row:
            raise CliError(
                INVALID_RESPONSE, "PTR cached order contains unapproved fields"
            )
        assert self.start_ms is not None and self.end_ms is not None
        if not self.start_ms <= row["gmtModified"] < self.end_ms:
            raise CliError(
                INVALID_RESPONSE, "PTR cached order falls outside the requested window"
            )

    @property
    def data_schema(self) -> dict[str, Any]:
        properties: dict[str, Any] = {
            key: {"type": ["string", "null"]} for key in sorted(ORDER_STRING_FIELDS)
        }
        properties.update(
            {
                key: {"type": ["integer", "null"]}
                for key in sorted(ORDER_TIMESTAMP_FIELDS)
            }
        )
        properties["ptrOrderId"] = {"type": "string", "minLength": 1, "pattern": r"\S"}
        properties["gmtModified"] = {"type": "integer"}
        properties["transactionRate"] = {"type": ["number", "null"]}
        properties[BASELINE_KEY] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                key: {"type": ["string", "null"]}
                for key in sorted(ORDER_BASELINE_STRING_FIELDS)
            },
        }
        for key in ("debtorAmount", "returnAmount"):
            properties[key] = money_schema()
        return {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["ptrOrderId", "gmtModified", BASELINE_KEY],
                "properties": properties,
            },
        }

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        if any(
            type(body.get(key)) is not int for key in ("pageNo", "pageSize")
        ) or body != self.page_body(self.default_scope, 0, 500):
            raise CliError(
                REQUEST_NOT_ALLOWED, "only the bound PTR order request is allowed"
            )
        return {}

    def identity_key(self, record: dict[str, Any]) -> str:
        return record["ptrOrderId"]

    def sort_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(records, key=self.identity_key)

    def filter_records(
        self, records: list[dict[str, Any]], filters: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        return filter_exact(
            records,
            filters,
            allowed_fields={field for _, field in self.filters},
            error_message="invalid PTR order exact-match filter",
        )

    @property
    def refresh_command(self) -> str:
        self._require_window()
        return (
            "refresh payment ptr orders "
            f"--updated-from {shlex.quote(self.updated_from or '')}"
            f" --updated-to {shlex.quote(self.updated_to or '')}"
        )

    @property
    def default_scope(self) -> str:
        self._require_window()
        return f"updated:{self.updated_from}:{self.updated_to}"

    def _require_window(self) -> None:
        if self.start_ms is None or self.end_ms is None:
            raise CliError(REQUEST_NOT_ALLOWED, "PTR order window must be bound")

    @property
    def contract(self) -> EndpointContract:
        self._require_window()
        assert self.native_begin is not None and self.native_end is not None
        return EndpointContract(
            method="GET",
            host="iglobalfundcontrol.alipay.com",
            path="/api/ptr/manage/query.json",
            page_size=500,
            one_based=False,
            allowed_body_keys=frozenset(
                {"pageNo", "pageSize", "modifiedTimeBegin", "modifiedTimeEnd"}
            ),
            fixed_body_values=(
                ("pageNo", 0),
                ("pageSize", 500),
                ("modifiedTimeBegin", self.native_begin),
                ("modifiedTimeEnd", self.native_end),
            ),
        )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope != self.default_scope
            or type(page_num) is not int
            or page_num != 0
            or type(page_size) is not int
            or page_size != 500
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "only the bound PTR order page is allowed"
            )
        return dict(self.contract.fixed_body_values)


def bind_window(from_value: str, to_value: str) -> OrdersCapability:
    values = (from_value, to_value)
    if any(
        not isinstance(v, str)
        or not WINDOW_PATTERN.fullmatch(v)
        or v.endswith("-00:00")
        for v in values
    ):
        raise CliError(
            INVALID_ARGUMENT,
            "updated bounds require YYYY-MM-DDTHH:MM:SS with an explicit numeric"
            " offset (preferred +08:00); -00:00 carries no instant",
            exit_code=EXIT_USAGE,
        )
    try:
        # Equivalent instants normalize to the +08 representation before
        # scope binding, so scope keys equal the baseline spelling.
        start, end = (
            parse_numeric_offset_instant(v).astimezone(SHANGHAI) for v in values
        )
        if not start < end or end - start > timedelta(days=31):
            raise ValueError("invalid span")
        if end > datetime.now(timezone.utc):
            raise ValueError("future cutoff")
        begin = (start - timedelta(seconds=1)).isoformat(sep=" ", timespec="seconds")[
            :-6
        ]
        finish = (end + timedelta(seconds=1)).isoformat(sep=" ", timespec="seconds")[
            :-6
        ]
        normalized = [
            bound.isoformat(sep="T", timespec="seconds") for bound in (start, end)
        ]
    except (ValueError, OverflowError) as error:
        raise CliError(
            INVALID_ARGUMENT,
            "updated bounds must be valid, ordered, at most 31 days and not future",
            exit_code=EXIT_USAGE,
        ) from error
    return OrdersCapability(
        normalized[0],
        normalized[1],
        int(start.timestamp()) * 1000,
        int(end.timestamp()) * 1000,
        begin,
        finish,
    )


ORDERS = OrdersCapability()


def collect_stable(
    capability: OrdersCapability,
    transport: Any,
    scope: str,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> "CollectedScope":
    """Prove the entire padded scope stable before trimming to the public window."""
    result = ptr.collect_stable(capability, transport, scope, progress=progress)
    assert capability.start_ms is not None and capability.end_ms is not None
    rows = [
        row
        for row in result.records
        if capability.start_ms <= row["gmtModified"] < capability.end_ms
    ]
    return replace(result, records=rows, total_count=len(rows))
