"""Native bank blacklist occurrence coverage and approved latest selection."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.query import CustomListResult
from dogopencli.result_policy import SOURCE_ROW_OCCURRENCES, AcquisitionEvidence

TENANT = "GUAPW3SG"
WIDTHS = (5000, 1000)
CONTEXT = {"tntInstId": TENANT, "timezone": "GMT+08", "currentArea": "2"}
SCOPE = canonical(CONTEXT)
FILTERS = (
    ("bank_id", "bankId"),
    ("status", "status"),
)


def validate_filters(parameters: dict[str, Any]) -> None:
    for parameter, _ in FILTERS:
        values = parameters.get(parameter)
        if values is not None and (
            not isinstance(values, list)
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise CliError(
                INVALID_ARGUMENT, "local filters require nonblank strings", exit_code=2
            )
    if any(
        value not in ("VALID", "INVALID") for value in parameters.get("status") or []
    ):
        raise CliError(INVALID_ARGUMENT, "status must be VALID or INVALID", exit_code=2)


class Inquiry:
    name = "liquidity.reference.blacklist.bank.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/bankFilterConfigQuery.json",
        page_size=5000,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "bankFilterConfigQuery"}),
        fixed_body_values=(("tntInstId", TENANT),),
        allowed_page_sizes=WIDTHS,
        json_body_contracts=(
            (
                "bankFilterConfigQuery",
                frozenset(
                    {"tntInstId", "timezone", "currentArea", "rowStart", "pageSize"}
                ),
                tuple(CONTEXT.items()),
                frozenset(WIDTHS),
            ),
        ),
    )

    def request_body(self, parameters: dict[str, Any]) -> dict[str, Any]:
        row_start = parameters.get("row_start")
        page_size = parameters.get("page_size")
        if (
            set(parameters) != {"row_start", "page_size"}
            or type(row_start) is not int
            or row_start < 0
            or type(page_size) is not int
            or page_size not in WIDTHS
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified bank blacklist request")
        return {
            "tntInstId": TENANT,
            "bankFilterConfigQuery": canonical(
                {**CONTEXT, "rowStart": row_start, "pageSize": page_size}
            ),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "response is not valid JSON") from error
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            raise CliError(INVALID_RESPONSE, "resultFlag must be boolean")
        if not document["resultFlag"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected bank blacklist inquiry"
            )
        result = document.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "inner success must be boolean")
        if not result["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected bank blacklist inquiry"
            )
        total = result.get("count")
        if (
            type(total) is not int
            or total < 0
            or type(document.get("count")) is not int
            or document["count"] != total
        ):
            raise CliError(INVALID_RESPONSE, "native inner and outer counts must agree")
        rows = result.get("data")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "native records are not an array")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("bankId"), str)
                or not row["bankId"].strip()
                or not isinstance(row.get("bankSwiftCode"), str)
                or any(
                    type(row.get(field)) is not int or row[field] < 0
                    for field in ("gmtModified", "gmtCreate")
                )
            ):
                raise CliError(
                    INVALID_RESPONSE,
                    "bank blacklist requires native identity and timestamps",
                )
            if "tntInstId" in row and row["tntInstId"] not in ("", TENANT):
                raise CliError(
                    INVALID_RESPONSE, "native row tenant contradicts request"
                )
        return rows, total

    def parse_inquiry(self, body: bytes, parameters: dict[str, Any]) -> dict:
        self.parse_rows(body)
        return parse(body)


CAPABILITY = Inquiry()


def latest_rows(rows: list[dict]) -> list[dict]:
    selected: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["bankId"], row["bankSwiftCode"])
        previous = selected.get(key)
        rank = (row["gmtModified"], row["gmtCreate"])
        if previous is None or rank > (previous["gmtModified"], previous["gmtCreate"]):
            selected[key] = row
        elif rank == (previous["gmtModified"], previous["gmtCreate"]) and canonical(
            row
        ) != canonical(previous):
            raise CliError(
                INVALID_RESPONSE, "bank configurations share both timestamps"
            )
    return list(selected.values())


class Adapter:
    def query_capability(self, operation: str, name: str, parameters: dict) -> Inquiry:
        validate_filters(parameters)
        if (operation, name) != ("list", "rows"):
            raise CliError(REQUEST_NOT_ALLOWED, "unknown bank blacklist inquiry")
        return CAPABILITY

    def query_list(self, parameters: dict, tools: Any) -> CustomListResult:
        validate_filters(parameters)
        arrived: list[dict] = []
        attempts: list[dict] = []
        boundaries: list[int] = []
        reasons: list[str] = []
        expected: int | None = None
        width = 5000
        offset = 0
        coverage = False

        def fetch(start: int, size: int, purpose: str) -> list[dict]:
            nonlocal expected
            document = tools.inquire("rows", {"row_start": start, "page_size": size})
            total = document["result"]["count"]
            rows = document["result"]["data"]
            if expected is None:
                expected = total
            elif total != expected:
                raise CliError(INVALID_RESPONSE, "bank source total changed")
            if len(rows) > size or start + len(rows) > total:
                raise CliError(INVALID_RESPONSE, "bank source exceeds page bounds")
            attempts.append(
                {
                    "purpose": purpose,
                    "row_start": start,
                    "page_size": size,
                    "arrivals": len(rows),
                    "reported_total": total,
                }
            )
            return rows

        while True:
            rows = fetch(offset, width, "acquisition")
            assert expected is not None
            if width == 5000 and rows and len(rows) < min(width, expected - offset):
                for attempt in attempts:
                    attempt["discarded"] = True
                reasons.append("PAGE_SIZE_CAPPED")
                arrived.clear()
                boundaries.clear()
                offset = 0
                width = 1000
                continue
            if not rows and offset < expected:
                reasons.append("COUNT_SHORTFALL")
                break
            if rows and offset:
                boundaries.append(offset)
            arrived.extend(rows)
            offset += len(rows)
            if offset < expected:
                continue
            if expected == 0:
                coverage = not fetch(0, 1000, "empty-witness")
                break
            starts = dict.fromkeys(
                (1 if expected > 1 else 0, *(boundary - 1 for boundary in boundaries))
            )
            for start in starts:
                overlap = fetch(start, 1000, "overlap-witness")
                if not overlap:
                    reasons.append("COVERAGE_UNPROVEN")
                    break
                if canonical(overlap) != canonical(
                    arrived[start : start + len(overlap)]
                ):
                    raise CliError(INVALID_RESPONSE, "bank source overlap changed")
            else:
                terminal = fetch(expected, 1000, "terminal-witness")
                coverage = not terminal and len(arrived) == expected
            break

        selected = latest_rows(arrived)
        omitted = len(arrived) - len(selected)
        if omitted:
            reasons.append("SOURCE_ROWS_SELECTED")
        if not coverage and not reasons:
            reasons.append("COVERAGE_UNPROVEN")
        attempts.append(
            {
                "kind": "source_selection",
                "raw_rows": len(arrived),
                "selected_records": len(selected),
                "raw_coverage_complete": coverage,
                "selection_fields": ["bankId", "bankSwiftCode"],
                "selection_order": ["gmtModified", "gmtCreate"],
            }
        )
        evidence = AcquisitionEvidence(
            usable_incomplete=True,
            scope_complete=coverage,
            dataset_complete=coverage,
            reported_total=expected,
            collected_total=len(selected),
            arrivals=len(arrived),
            unique_count=len(selected),
            duplicate_count=omitted,
            total_semantics=SOURCE_ROW_OCCURRENCES,
            reasons=tuple(dict.fromkeys(reasons)),
            attempts=tuple(attempts),
        )
        return CustomListResult(selected, evidence)

    def scope(self, parameters: dict[str, Any]) -> str:
        validate_filters(parameters)
        return SCOPE

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        validate_filters(parameters)
        return [
            row
            for row in records
            if all(
                not parameters.get(parameter) or row.get(field) in parameters[parameter]
                for parameter, field in FILTERS
            )
        ]


adapter = Adapter()
