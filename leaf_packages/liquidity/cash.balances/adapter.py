"""Latest snapshots and daily observations through bounded named inquiries."""

import re
from datetime import datetime, timedelta
from decimal import Decimal
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
from dogopencli.result_policy import AcquisitionEvidence

TENANT = "GUAPW3SG"
BALANCE_AMOUNTS = (
    "curBalance",
    "avlBalance",
    "avlBalanceAfterAdj",
    "openBalance",
    "openAvlBalance",
    "openAvlBalanceAfterAdj",
    "equvCurBalance",
    "equvAvlBalance",
    "equvOpenBalance",
    "equvOpenAvlBalance",
)
AMOUNT = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


def invalid(message: str) -> None:
    raise CliError(INVALID_RESPONSE, message)


def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        invalid("missing native " + field)
    return value


def amount(value: Any) -> None:
    if value is None or type(value) is int:
        return
    if isinstance(value, Decimal) and value.is_finite():
        return
    if isinstance(value, str) and (not value.strip() or AMOUNT.fullmatch(value)):
        return
    invalid("invalid native balance amount")


def date(value: Any) -> datetime:
    if not isinstance(value, str):
        raise CliError(
            INVALID_ARGUMENT, "dates require YYYY-MM-DD or YYYYMMDD", exit_code=2
        )
    try:
        fmt = "%Y-%m-%d" if "-" in value else "%Y%m%d"
        parsed = datetime.strptime(value, fmt)
        if parsed.strftime(fmt) != value:
            raise ValueError
        return parsed
    except ValueError as error:
        raise CliError(INVALID_ARGUMENT, "invalid balance date", exit_code=2) from error


def resolve(parameters: dict) -> dict:
    entities = parameters.get("entity") or ["ALIPAYGM"]
    aliases = parameters.get("account_alias") or []
    for values in (entities, aliases):
        if not isinstance(values, list) or any(
            not isinstance(v, str) or not v.strip() for v in values
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "balance selectors require nonblank strings",
                exit_code=2,
            )
    if "ANY" in aliases or ("ANY" in entities and entities != ["ANY"]):
        raise CliError(
            INVALID_ARGUMENT, "ANY must be a single entity selector", exit_code=2
        )
    mode = "ANY" if entities == ["ANY"] else "explicit"
    if mode == "ANY" and "_resolved_entities" in parameters:
        entities = parameters["_resolved_entities"]
        if not isinstance(entities, list) or any(
            not isinstance(v, str) or not v.strip() or v == "ANY" for v in entities
        ):
            raise CliError(
                INVALID_ARGUMENT, "invalid frozen entity selector", exit_code=2
            )
    start, end = parameters.get("from_date"), parameters.get("to_date")
    if bool(start) != bool(end):
        raise CliError(
            INVALID_ARGUMENT, "from-date and to-date must be paired", exit_code=2
        )
    daily = start is not None
    if daily:
        start, end = date(start), date(end)
        if start > end:
            raise CliError(
                INVALID_ARGUMENT, "balance date window is reversed", exit_code=2
            )
        if (
            parameters.get("timezone") is not None
            or parameters.get("page_size") is not None
        ):
            raise CliError(
                INVALID_ARGUMENT,
                "daily mode has fixed timezone and no page size",
                exit_code=2,
            )
    elif parameters.get("timezone") not in (None, "GMT+08"):
        raise CliError(INVALID_ARGUMENT, "only GMT+08 is qualified", exit_code=2)
    width = parameters.get("page_size") or 100
    if type(width) is not int or not 1 <= width <= 100:
        raise CliError(INVALID_ARGUMENT, "page-size must be 1 through 100", exit_code=2)
    return {
        "entities": sorted(set(entities)),
        "mode": mode,
        "aliases": sorted(set(aliases)),
        "start": start,
        "end": end,
        "daily": daily,
        "width": width,
    }


class BalanceInquiry:
    page_url = LIQUIDITY_STARTUP_URL

    def __init__(self, daily: bool) -> None:
        self.daily = daily
        self.name = "liquidity.cash.balances." + ("daily" if daily else "latest")
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/balStatisticalQuery.json" if daily else "/latestBalanceQuery.json",
            page_size=100,
            one_based=False,
            allowed_body_keys=frozenset(
                {
                    "tntInstId",
                    "balanceType",
                    "aliasNames",
                    "queryStartDate",
                    "queryDate",
                }
                if daily
                else {
                    "tntInstId",
                    "entitys",
                    "aliasNames",
                    "timeZone",
                    "rowStart",
                    "pageSize",
                }
            ),
            fixed_body_values=(("tntInstId", TENANT), ("balanceType", "day"))
            if daily
            else (("tntInstId", TENANT), ("timeZone", "GMT+08")),
            allowed_page_sizes=tuple(range(1, 101)),
        )

    def request_body(self, parameters: dict) -> dict:
        if self.daily:
            if set(parameters) != {"aliases", "start", "end"}:
                raise CliError(REQUEST_NOT_ALLOWED, "unknown daily balance context")
            aliases = parameters["aliases"]
            start, end = date(parameters["start"]), date(parameters["end"])
            if (
                not isinstance(aliases, list)
                or not 1 <= len(aliases) <= 30
                or any(not isinstance(a, str) or not a.strip() for a in aliases)
                or not 0 <= (end - start).days <= 6
            ):
                raise CliError(REQUEST_NOT_ALLOWED, "unverified daily balance chunk")
            return {
                "tntInstId": TENANT,
                "balanceType": "day",
                "aliasNames": aliases,
                "queryStartDate": start.strftime("%Y%m%d"),
                "queryDate": end.strftime("%Y%m%d"),
            }
        if set(parameters) != {"entities", "aliases", "offset", "width"}:
            raise CliError(REQUEST_NOT_ALLOWED, "unknown latest balance context")
        if (
            not parameters["entities"]
            or "ANY" in parameters["entities"]
            or type(parameters["offset"]) is not int
            or parameters["offset"] < 0
            or type(parameters["width"]) is not int
            or not 1 <= parameters["width"] <= 100
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified latest balance scope")
        return {
            "tntInstId": TENANT,
            "entitys": parameters["entities"],
            "aliasNames": parameters["aliases"],
            "timeZone": "GMT+08",
            "rowStart": parameters["offset"],
            "pageSize": parameters["width"],
        }

    def parse_inquiry(self, body: bytes, parameters: dict) -> dict:
        try:
            document = parse(body)
        except ValueError as error:
            raise CliError(INVALID_RESPONSE, "invalid balance JSON") from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            invalid("invalid balance success marker")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected balance inquiry")
        data = document.get("data")
        rows = (
            data if self.daily else data.get("data") if isinstance(data, dict) else None
        )
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            invalid("balance rows must be objects")
        if not self.daily:
            if type(data.get("totalCount")) is not int or data["totalCount"] < 0:
                invalid("latest total must be nonnegative integer")
        return document


class RosterInquiry:
    name = "liquidity.cash.balances.roster"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/queryintnalbkactlist.json",
        page_size=1000,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "wallet", "bankAccountQueryVO"}),
        fixed_body_values=(("tntInstId", TENANT), ("wallet", False)),
        allowed_page_sizes=(1000, 100, 10, 1),
        json_body_contracts=(
            (
                "bankAccountQueryVO",
                frozenset({"tntInstId", "rowStart", "pageSize"}),
                (("tntInstId", TENANT),),
                frozenset({1000, 100, 10, 1}),
            ),
        ),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict:
        if (
            scope
            or type(row_start) is not int
            or row_start < 0
            or page_size not in (1000, 100, 10, 1)
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "unverified roster request")
        return {
            "tntInstId": TENANT,
            "wallet": False,
            "bankAccountQueryVO": canonical(
                {"tntInstId": TENANT, "rowStart": row_start, "pageSize": page_size}
            ),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict], None]:
        document = parse(body)
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            invalid("invalid roster success marker")
        if not document["resultFlag"]:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected roster inquiry")
        result = document.get("result")
        if not isinstance(result, dict) or (
            "success" in result and type(result["success"]) is not bool
        ):
            invalid("invalid roster result")
        if result.get("success") is False:
            raise CliError(BUSINESS_QUERY_FAILED, "backend rejected roster inquiry")
        rows = result.get("bankAccountPropertyVOList")
        if not isinstance(rows, list):
            invalid("invalid roster rows")
        for row in rows:
            if not isinstance(row, dict):
                invalid("invalid roster record")
            for field in ("aliasName", "instId", "currency"):
                text(row.get(field), field)
            if row.get("tntInstId", TENANT) != TENANT:
                invalid("roster tenant mismatch")
        return rows, None


def merge(rows: list[dict], incoming: list[dict], fields: tuple[str, ...]) -> None:
    seen = {canonical([row[field] for field in fields]): row for row in rows}
    for row in incoming:
        key = canonical([row[field] for field in fields])
        if key in seen:
            if canonical(seen[key]) != canonical(row):
                invalid("conflicting balance identity")
        else:
            rows.append(row)
            seen[key] = row


class Adapter:
    def query_capability(self, operation: str, name: str, parameters: dict) -> Any:
        resolve(parameters)
        if operation != "list" or name not in ("latest", "daily", "roster"):
            raise CliError(REQUEST_NOT_ALLOWED, "unknown cash balance inquiry")
        return RosterInquiry() if name == "roster" else BalanceInquiry(name == "daily")

    def scope(self, parameters: dict) -> str:
        values = resolve(parameters)
        return canonical(
            {
                **values,
                "start": values["start"].strftime("%Y%m%d")
                if values["start"]
                else None,
                "end": values["end"].strftime("%Y%m%d") if values["end"] else None,
            }
        )

    def filter(self, records: list[dict], parameters: dict) -> list[dict]:
        values = resolve(parameters)
        rows = records
        if parameters.get("entity") and values["entities"] != ["ANY"]:
            rows = [row for row in rows if row.get("entity") in values["entities"]]
        if parameters.get("account_alias"):
            rows = [row for row in rows if row.get("aliasName") in values["aliases"]]
        if values["daily"]:
            if any("statisticalDate" not in row for row in rows):
                raise CliError(
                    INVALID_ARGUMENT,
                    "saved capture has no daily date axis",
                    exit_code=2,
                )
            rows = [
                row
                for row in rows
                if values["start"].strftime("%Y-%m-%d")
                <= row["statisticalDate"]
                <= values["end"].strftime("%Y-%m-%d")
            ]
        return rows

    def query_list(self, parameters: dict, tools: Any) -> CustomListResult:
        values = resolve(parameters)
        if values["entities"] == ["ANY"]:
            raise CliError(
                INVALID_ARGUMENT,
                "ANY entity selector has no frozen values",
                exit_code=2,
            )
        if not values["entities"]:
            return CustomListResult(
                [],
                AcquisitionEvidence.for_collection(
                    complete=True,
                    reported_total=0,
                    collected_total=0,
                    attempts=(
                        {
                            "composition": "cash-balance-selection-v1",
                            "mode": values["mode"],
                            "entities": [],
                            "accounts": [],
                        },
                    ),
                ),
            )
        return (
            self.daily(values, tools) if values["daily"] else self.latest(values, tools)
        )

    def latest(self, values: dict, tools: Any) -> CustomListResult:
        rows, attempts = [], []
        expected, arrivals, offset = None, 0, 0
        while True:
            document = tools.inquire(
                "latest",
                {
                    "entities": values["entities"],
                    "aliases": values["aliases"],
                    "offset": offset,
                    "width": values["width"],
                },
            )
            data = document["data"]
            native, total = data["data"], data["totalCount"]
            if expected is None:
                expected = total
            if (
                expected != total
                or len(native) > values["width"]
                or offset + len(native) > total
            ):
                invalid("latest balance total or page bounds changed")
            for row in native:
                identity = row.get("balId")
                if type(identity) not in (str, int) or (
                    isinstance(identity, str) and not identity.strip()
                ):
                    invalid("latest balance requires native balId")
                if row.get("entity") not in values["entities"] or (
                    values["aliases"] and row.get("aliasName") not in values["aliases"]
                ):
                    invalid("latest balance outside requested scope")
                if row.get("tntInstId", TENANT) not in ("", TENANT):
                    invalid("latest balance tenant mismatch")
                for field in BALANCE_AMOUNTS:
                    if field in row:
                        amount(row[field])
                for field in ("leastDayendBalVo", "leastDaytimeBalVo"):
                    child = row.get(field)
                    if child is not None:
                        if not isinstance(child, dict):
                            invalid("invalid nested balance")
                        for key, value in child.items():
                            if "alance" in key:
                                amount(value)
            arrivals += len(native)
            merge(rows, native, ("balId",))
            attempts.append(
                {
                    "kind": "latest_page",
                    "offset": offset,
                    "arrivals": len(native),
                    "reported_total": total,
                }
            )
            offset += values["width"]
            if offset >= expected or not native:
                break
        complete = len(rows) == expected and arrivals == len(rows)
        evidence = AcquisitionEvidence.for_collection(
            complete=complete,
            reported_total=expected,
            collected_total=len(rows),
            arrivals=arrivals,
            attempts=(
                {
                    "composition": "cash-balance-selection-v1",
                    "mode": values["mode"],
                    "entities": values["entities"],
                    "accounts": values["aliases"],
                    "timezone": "GMT+08",
                },
                *attempts,
            ),
        )
        return CustomListResult(rows, evidence)

    def daily(self, values: dict, tools: Any) -> CustomListResult:
        roster = tools.collect("roster")
        if roster.evidence is None:
            invalid("roster evidence missing")
        binding = {}
        for row in roster.records:
            alias = row["aliasName"]
            item = {
                "aliasName": alias,
                "entity": row["instId"],
                "currency": row["currency"],
            }
            if alias in binding and binding[alias] != item:
                invalid("ambiguous current account binding")
            binding[alias] = item
        for alias in values["aliases"]:
            if (
                alias not in binding
                or binding[alias]["entity"] not in values["entities"]
            ):
                invalid("requested alias lacks selected current binding")
        selected = {
            alias: item
            for alias, item in binding.items()
            if item["entity"] in values["entities"]
            and (not values["aliases"] or alias in values["aliases"])
        }
        aliases = sorted(selected)
        planned = -(-len(aliases) // 30) * -(
            -((values["end"] - values["start"]).days + 1) // 7
        )
        if planned > 1000:
            raise CliError(
                INVALID_ARGUMENT, "daily scope exceeds 1000 chunks", exit_code=2
            )
        rows, attempts, arrivals = [], [], 0
        for offset in range(0, len(aliases), 30):
            batch = aliases[offset : offset + 30]
            first = values["start"]
            while first <= values["end"]:
                last = min(first + timedelta(days=6), values["end"])
                context = {
                    "aliases": batch,
                    "start": first.strftime("%Y%m%d"),
                    "end": last.strftime("%Y%m%d"),
                }
                native = tools.inquire("daily", context)["data"]
                composed = []
                for row in native:
                    text(row.get("id"), "id")
                    alias = text(row.get("data"), "data")
                    if alias not in batch:
                        invalid("daily alias outside chunk")
                    observed = row.get("statisticalDate")
                    try:
                        observed_date = datetime.strptime(observed, "%Y-%m-%d")
                    except (ValueError, TypeError) as error:
                        raise CliError(
                            INVALID_RESPONSE, "invalid native daily date"
                        ) from error
                    if (
                        observed_date.strftime("%Y-%m-%d") != observed
                        or not first <= observed_date <= last
                    ):
                        invalid("daily date outside chunk")
                    if "balance" not in row:
                        invalid("daily row lacks balance")
                    amount(row["balance"])
                    item = selected[alias]
                    if any(
                        field in row and row[field] != value
                        for field, value in item.items()
                    ):
                        invalid("native daily labels contradict current binding")
                    composed.append({**row, **item})
                arrivals += len(composed)
                merge(
                    rows,
                    composed,
                    ("entity", "aliasName", "currency", "statisticalDate"),
                )
                attempts.append(
                    {
                        "kind": "daily_chunk",
                        "start": context["start"],
                        "end": context["end"],
                        "alias_count": len(batch),
                        "arrivals": len(native),
                        "succeeded": True,
                    }
                )
                first = last + timedelta(days=1)
        source_complete = (
            roster.evidence.scope_complete and roster.evidence.dataset_complete
        )
        evidence = AcquisitionEvidence.for_collection(
            complete=source_complete and len(attempts) == planned,
            reported_total=None,
            collected_total=len(rows),
            arrivals=arrivals,
            attempts=(
                {
                    "composition": "cash-balance-selection-v1",
                    "mode": values["mode"],
                    "entities": values["entities"],
                    "accounts": [selected[a] for a in aliases],
                    "timezone": "GMT+08",
                    "binding_semantics": "current-roster-not-historical-ownership",
                    "planned_chunks": planned,
                    "succeeded_chunks": len(attempts),
                    "dependencies": [{"acquisition": roster.evidence.record()}],
                },
                *attempts,
            ),
            reasons=() if source_complete else ("DEPENDENCY_INCOMPLETE",),
        )
        return CustomListResult(rows, evidence)


adapter = Adapter()
