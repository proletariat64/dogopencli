"""Native day-end balances composed through the shared List SDK."""

import re
from datetime import datetime
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
ORDER = "__dogopencli_dayend_order"
KEY = ("entity", "bankId", "aliasName", "currency", "valueDate")
AMOUNT = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


def invalid(message: str) -> None:
    raise CliError(INVALID_RESPONSE, message)


def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        invalid("invalid native " + field)
    return value


def date(value: Any) -> str:
    try:
        if not isinstance(value, str):
            raise ValueError
        fmt = "%Y-%m-%d" if "-" in value else "%Y%m%d"
        parsed = datetime.strptime(value, fmt)
        if parsed.strftime(fmt) != value:
            raise ValueError
        return parsed.strftime("%Y%m%d")
    except ValueError as error:
        raise CliError(INVALID_ARGUMENT, "invalid balance date", exit_code=2) from error


def resolve(parameters: dict, *, acquisition: bool = True) -> dict:
    aliases = parameters.get("account_alias") or []
    entities = parameters.get("entity") or ([] if aliases else ["ALIPAYGM"])
    for values in (aliases, entities):
        if not isinstance(values, list) or any(
            not isinstance(v, str) or not v.strip() for v in values
        ):
            raise CliError(INVALID_ARGUMENT, "invalid balance selector", exit_code=2)
    if "ANY" in aliases or ("ANY" in entities and entities != ["ANY"]):
        raise CliError(INVALID_ARGUMENT, "invalid ANY selection", exit_code=2)
    mode = "ANY" if entities == ["ANY"] else "explicit"
    if mode == "ANY" and (acquisition or "_resolved_entities" in parameters):
        entities = parameters.get("_resolved_entities", entities)
        if (
            entities == ["ANY"]
            or not isinstance(entities, list)
            or any(
                not isinstance(v, str) or not v.strip() or v == "ANY" for v in entities
            )
        ):
            raise CliError(
                INVALID_ARGUMENT, "ANY requires frozen entities", exit_code=2
            )
    start, end = parameters.get("from_date"), parameters.get("to_date")
    if (start is None) != (end is None) or (acquisition and start is None):
        raise CliError(
            INVALID_ARGUMENT, "from-date and to-date are required together", exit_code=2
        )
    if start is not None:
        start, end = date(start), date(end)
        if start > end:
            raise CliError(
                INVALID_ARGUMENT, "balance date window is reversed", exit_code=2
            )
    return {
        "aliases": sorted(set(aliases)),
        "entities": sorted(set(entities)),
        "mode": mode,
        "start": start,
        "end": end,
    }


class BalanceInquiry:
    name = "liquidity.cash.balances.dayend"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/dayendBalDetailQuery.json",
        page_size=500,
        one_based=False,
        allowed_body_keys=frozenset(
            {"tntInstId", "aliasName", "startDate", "endDate", "rowStart", "pageSize"}
        ),
        fixed_body_values=(("tntInstId", TENANT),),
        allowed_page_sizes=(500,),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict:
        context = parse(scope)
        if (
            not isinstance(context, dict)
            or set(context) != {"alias", "start", "end", "entities"}
            or page_size != 500
            or type(row_start) is not int
            or row_start < 0
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "invalid day-end request context")
        text(context["alias"], "aliasName")
        if (
            date(context["start"]) != context["start"]
            or date(context["end"]) != context["end"]
            or context["start"] > context["end"]
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "invalid day-end date context")
        self.context = context
        self.position = row_start
        return {
            "tntInstId": TENANT,
            "aliasName": context["alias"],
            "startDate": context["start"],
            "endDate": context["end"],
            "rowStart": row_start,
            "pageSize": page_size,
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict], int]:
        document = parse(body)
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            invalid("invalid day-end success marker")
        if not document["success"]:
            raise CliError(
                BUSINESS_QUERY_FAILED, "backend rejected day-end balance inquiry"
            )
        data = document.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            invalid("invalid day-end page")
        total = data.get("totalCount")
        if type(total) is not int or total < 0:
            invalid("invalid native day-end total")
        if (
            type(data.get("rowStart")) is not int
            or data["rowStart"] != self.position
            or type(data.get("pageSize")) is not int
            or data["pageSize"] != 500
        ):
            invalid("native day-end page echo mismatch")
        rows = []
        for row in data["data"]:
            if not isinstance(row, dict) or ORDER in row:
                invalid("invalid day-end record or reserved field collision")
            for field in KEY:
                text(row.get(field), field)
            if row["aliasName"] != self.context["alias"]:
                invalid("native day-end alias outside requested scope")
            if (
                self.context["entities"]
                and row["entity"] not in self.context["entities"]
            ):
                invalid("native day-end entity outside requested scope")
            try:
                parsed_date = datetime.strptime(row["valueDate"], "%Y%m%d")
            except ValueError as error:
                raise CliError(INVALID_RESPONSE, "invalid native valueDate") from error
            if (
                parsed_date.strftime("%Y%m%d") != row["valueDate"]
                or not self.context["start"] <= row["valueDate"] <= self.context["end"]
            ):
                invalid("native valueDate outside requested range")
            timestamp = row.get("updateTime")
            if not isinstance(timestamp, str) or not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", timestamp
            ):
                invalid("invalid native updateTime")
            try:
                parsed_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            except ValueError as error:
                raise CliError(INVALID_RESPONSE, "invalid native updateTime") from error
            if parsed_time.strftime("%Y-%m-%d %H:%M:%S") != timestamp:
                invalid("invalid native updateTime")
            for field in (
                "openBalance",
                "openAvlBalance",
                "closeBalance",
                "closeAvlBalance",
            ):
                if not isinstance(row.get(field), str) or not AMOUNT.fullmatch(
                    row[field]
                ):
                    invalid("invalid native " + field)
            rows.append({**row, ORDER: int(parsed_time.strftime("%Y%m%d%H%M%S"))})
        return rows, total


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


def enumerate_aliases(
    values: dict, tools: Any
) -> tuple[list[str], dict, tuple[str, ...]]:
    notes = []
    for source in ("duckdog", "cache", "live"):
        if source == "live":
            result = tools.collect("roster")
            if result.evidence is None:
                invalid("account directory acquisition missing")
            directory = {
                "records": result.records,
                "quality": {
                    "complete": result.evidence.scope_complete,
                    "dataset_complete": result.evidence.dataset_complete,
                    "acquisition": result.evidence.record(),
                },
            }
        else:
            directory = tools.account_directory(source)
        if directory is None:
            notes.append({"source": source, "status": "unavailable"})
            continue
        records, quality = directory["records"], directory["quality"]
        if not isinstance(records, list) or not isinstance(quality, dict):
            invalid("account directory is malformed")
        for item in records:
            if not isinstance(item, dict):
                invalid("account directory record is malformed")
            for field in ("aliasName", "instId", "bankId"):
                if (
                    field in item
                    and item[field] is not None
                    and not isinstance(item[field], str)
                ):
                    invalid("account directory field is malformed")
        note = {"source": source, "quality": quality, "status": "no_match"}
        notes.append(note)
        missing = any(
            not item.get("instId") or not item.get("aliasName")
            for item in records
            if not item.get("instId") or item.get("instId") in values["entities"]
        )
        matches = [
            item
            for item in records
            if item.get("instId") in values["entities"] and item.get("aliasName")
        ]
        if missing:
            note["status"] = "missing_fields"
            continue
        proven = (
            quality.get("complete") is True and quality.get("dataset_complete") is True
        )
        if not matches and not (source == "live" and proven):
            continue
        if quality.get("simulated") is True:
            invalid("simulated directory cannot enumerate production balances")
        bindings = {}
        for item in matches:
            alias = text(item["aliasName"], "directory aliasName")
            binding = (item["instId"], item.get("bankId"))
            if alias in bindings and bindings[alias] != binding:
                invalid("ambiguous account directory alias")
            bindings[alias] = binding
        note["status"] = "selected"
        reason = (
            ()
            if proven
            else (
                ("ACCOUNT_DIRECTORY_INCOMPLETE",)
                if quality.get("complete") is False
                or quality.get("dataset_complete") is False
                else ("COVERAGE_UNPROVEN",)
            )
        )
        return (
            sorted(bindings),
            {
                "source": source,
                "quality": quality,
                "sources": notes,
                "binding_semantics": "current-directory-not-historical-ownership",
            },
            reason,
        )
    raise CliError(
        "SOURCE_DATA_MISSING",
        "no usable account directory proves selected aliases",
        meta={"account_directory": {"sources": notes}},
    )


class Adapter:
    def history_contract(self, parameters: dict) -> dict:
        values = resolve(parameters)
        if not values["aliases"]:
            raise CliError(
                INVALID_ARGUMENT,
                "History requires explicit account aliases; "
                "current directory is not historical ownership",
                exit_code=2,
            )
        return {
            "time_basis": "valueDate",
            "interpretation": "calendar_date",
            "format": "%Y%m%d",
            "boundary": "inclusive",
            "timezone": None,
            "from_parameter": "from_date",
            "to_parameter": "to_date",
            "from": values["start"],
            "to": values["end"],
            "splitting": "explicit_windows",
            "cross_range_equivalence": False,
            "modification_time": "updateTime (native local format; timezone unknown)",
        }

    def query_capability(self, operation: str, name: str, parameters: dict) -> Any:
        resolve(parameters)
        return RosterInquiry() if name == "roster" else BalanceInquiry()

    def scope(self, parameters: dict) -> str:
        return canonical(resolve(parameters))

    def filter(self, records: list[dict], parameters: dict) -> list[dict]:
        values = resolve(parameters, acquisition=False)
        return [
            row
            for row in records
            if (
                not parameters.get("entity")
                or values["entities"] == ["ANY"]
                or row["entity"] in values["entities"]
            )
            and (not values["aliases"] or row["aliasName"] in values["aliases"])
            and (
                values["start"] is None
                or values["start"] <= row["valueDate"] <= values["end"]
            )
        ]

    def query_list(self, parameters: dict, tools: Any) -> CustomListResult:
        values = resolve(parameters)
        aliases = values["aliases"]
        directory, reasons = {"source": "explicit", "quality": {}}, ()
        if not aliases:
            aliases, directory, reasons = enumerate_aliases(values, tools)
        rows, attempts, arrivals = [], [], 0
        complete = True
        selection = {
            "composition": "cash-balance-dayend-v1",
            "source": "dayendBalDetailQuery.json",
            "entities": values["entities"],
            "aliases": aliases,
            "directory": directory,
            "planned_accounts": len(aliases),
            "queried_accounts": 0,
            "successful_accounts": 0,
            "incomplete_accounts": 0,
            "failed_accounts": 0,
            "successful_empty_accounts": 0,
            "query_execution_complete": False,
        }
        for alias in aliases:
            selection["queried_accounts"] += 1
            try:
                result = tools.collect(
                    "balances",
                    canonical(
                        {
                            "alias": alias,
                            "start": values["start"],
                            "end": values["end"],
                            "entities": values["entities"],
                        }
                    ),
                )
            except CliError as error:
                selection["failed_accounts"] += 1
                attempts.append({"alias": alias, "error": {"code": error.code}})
                failed = AcquisitionEvidence.for_collection(
                    complete=False,
                    reported_total=None,
                    collected_total=len(rows),
                    arrivals=arrivals,
                    reasons=(error.code,),
                    attempts=(dict(selection), *attempts),
                    usable_incomplete=False,
                )
                error.meta = {**(error.meta or {}), "acquisition": failed.record()}
                raise
            evidence = result.evidence
            if evidence is None:
                invalid("day-end acquisition evidence missing")
            account_complete = evidence.scope_complete and evidence.dataset_complete
            complete &= account_complete
            arrivals += evidence.arrivals or 0
            selection["successful_accounts"] += account_complete
            selection["incomplete_accounts"] += not account_complete
            selection["successful_empty_accounts"] += (
                account_complete and evidence.reported_total == 0 and not result.records
            )
            rows.extend(
                {k: v for k, v in row.items() if k != ORDER} for row in result.records
            )
            attempts.append({"alias": alias, "acquisition": evidence.record()})
        selection["query_execution_complete"] = complete
        evidence = AcquisitionEvidence.for_collection(
            complete=complete and not reasons,
            reasons=reasons,
            reported_total=None,
            collected_total=len(rows),
            arrivals=arrivals,
            attempts=(selection, *attempts),
            usable_incomplete=True,
        )
        return CustomListResult(rows, evidence)


adapter = Adapter()
