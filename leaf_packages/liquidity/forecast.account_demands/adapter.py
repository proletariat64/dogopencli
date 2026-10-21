"""Account-scoped native inquiry with ordered, read-only ownership resolution."""

import json
import re
from dataclasses import replace
from datetime import datetime
from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.query import CustomListResult

LEAF = "forecast.account_demands"
PATH = "/passiveFundDemandList.json"
IDENTITY = ("id",)
INTRADAY = False
CASHFLOWS = False
TENANT = "GUAPW3SG"
LABELS = frozenset(f"{h:02}:{m:02}" for h in range(24) for m in (0, 15, 30, 45))


def fail(message: str, code: str = "INVALID_RESPONSE") -> None:
    raise CliError(code, message, exit_code=2 if code == "INVALID_ARGUMENT" else 1)


def valid_day(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}", value):
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return False
    return True


def values(parameters: dict, *, required: bool = True) -> dict:
    native = {
        field: parameters.get(option)
        for option, field in (
            ("alias", "aliasName"),
            ("entity", "entity"),
            ("bank", "bankId"),
            ("from_date", "startDate"),
            ("to_date", "endDate"),
        )
    }
    for field in ("aliasName", "entity", "bankId"):
        value = native[field]
        if value is None and (field != "aliasName" or not required):
            continue
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
            or "," in value
            or value.upper() == "ANY"
        ):
            fail(f"{field} requires one explicit value", "INVALID_ARGUMENT")
    for field in ("startDate", "endDate"):
        if native[field] is None and not required:
            continue
        if not valid_day(native[field]):
            fail("valid YYYYMMDD date bounds required", "INVALID_ARGUMENT")
    start, end = native["startDate"], native["endDate"]
    if (
        start is not None
        and end is not None
        and (start > end or (INTRADAY and start != end))
    ):
        fail(
            "ordered dates required; intraday accepts one day only", "INVALID_ARGUMENT"
        )
    return {key: value for key, value in native.items() if value is not None}


def validate_native(native: Any) -> None:
    if not isinstance(native, dict) or set(native) != {
        "aliasName",
        "entity",
        "bankId",
        "startDate",
        "endDate",
    }:
        fail("resolved account scope is invalid", "REQUEST_NOT_ALLOWED")
    checked = values(
        {
            "alias": native["aliasName"],
            "entity": native["entity"],
            "bank": native["bankId"],
            "from_date": native["startDate"],
            "to_date": native["endDate"],
        }
    )
    if checked != native:
        fail("resolved account scope is invalid", "REQUEST_NOT_ALLOWED")


class AccountsInquiry:
    name = "liquidity." + LEAF + ".accounts"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/queryintnalbkactlist.json",
        page_size=1000,
        one_based=False,
        allowed_page_sizes=(1000, 100, 10, 1),
        allowed_body_keys=frozenset({"tntInstId", "wallet", "bankAccountQueryVO"}),
        fixed_body_values=(("tntInstId", TENANT), ("wallet", False)),
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
            or type(page_size) is not int
            or page_size not in (1000, 100, 10, 1)
        ):
            fail("unverified account directory request", "REQUEST_NOT_ALLOWED")
        return {
            "tntInstId": TENANT,
            "wallet": False,
            "bankAccountQueryVO": json.dumps(
                {"tntInstId": TENANT, "rowStart": row_start, "pageSize": page_size}
            ),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict], None]:
        doc = parse_document(body)
        if type(doc.get("resultFlag")) is not bool:
            fail("account directory resultFlag is not boolean")
        if not doc["resultFlag"]:
            fail("account directory query failed", "BUSINESS_QUERY_FAILED")
        result = doc.get("result")
        if not isinstance(result, dict):
            fail("account directory result is not an object")
        if "success" in result and type(result["success"]) is not bool:
            fail("account directory success is not boolean")
        if result.get("success") is False:
            fail("account directory query failed", "BUSINESS_QUERY_FAILED")
        rows = result.get("bankAccountPropertyVOList")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            fail("account directory records must be objects")
        for row in rows:
            if row.get("tntInstId", TENANT) != TENANT:
                fail("account directory tenant differs from request")
        return rows, None


def parse_document(body: bytes) -> dict:
    try:
        doc = parse(body)
    except (ValueError, UnicodeError) as error:
        raise CliError("INVALID_RESPONSE", "response is not valid JSON") from error
    if not isinstance(doc, dict):
        fail("response root must be an object")
    return doc


class BaselinesInquiry:
    name = "liquidity." + LEAF + ".baselines"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/bankAccountBaseLineQuery.json",
        page_size=1000,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "bankAccountBaseLineQuery"}),
        fixed_body_values=(("tntInstId", TENANT),),
        json_body_contracts=(
            (
                "bankAccountBaseLineQuery",
                frozenset({"tntInstId", "rowStart", "pageSize"}),
                (("tntInstId", TENANT),),
                frozenset({1000}),
            ),
        ),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict:
        if (
            scope
            or type(row_start) is not int
            or row_start < 0
            or row_start % 1000
            or type(page_size) is not int
            or page_size != 1000
        ):
            fail("unverified baseline directory request", "REQUEST_NOT_ALLOWED")
        return {
            "tntInstId": TENANT,
            "bankAccountBaseLineQuery": json.dumps(
                {"tntInstId": TENANT, "rowStart": row_start, "pageSize": page_size}
            ),
        }

    def parse_rows(self, body: bytes) -> tuple[list[dict], int]:
        document = baseline_document(body)
        rows, total = document["result"].get("data"), document.get("count")
        if (
            not isinstance(rows, list)
            or any(not isinstance(row, dict) for row in rows)
            or type(total) is not int
            or total < 0
        ):
            fail("baseline directory records or count are invalid")
        return rows, total


class OwnershipDetailInquiry:
    name = "liquidity." + LEAF + ".ownership_detail"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/bankAccountBaseLineDetail.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "aliasName"}),
        fixed_body_values=(("tntInstId", TENANT),),
    )

    def request_body(self, parameters: dict, identity: str) -> dict:
        if parameters or not isinstance(identity, str) or not identity.strip():
            fail("unverified ownership detail request", "REQUEST_NOT_ALLOWED")
        return {"tntInstId": TENANT, "aliasName": identity}

    def parse_detail(self, body: bytes, parameters: dict, identity: str) -> dict:
        self.request_body(parameters, identity)
        row = baseline_document(body)["result"].get("data")
        if not isinstance(row, dict) or row.get("aliasName") != identity:
            fail("ownership detail alias differs from lookup")
        if row.get("tntInstId", TENANT) != TENANT:
            fail("ownership detail tenant differs from request")
        return row


def baseline_document(body: bytes) -> dict:
    document = parse_document(body)
    if type(document.get("resultFlag")) is not bool:
        fail("baseline resultFlag must be boolean")
    if not document["resultFlag"]:
        fail("baseline ownership query failed", "BUSINESS_QUERY_FAILED")
    result = document.get("result")
    if not isinstance(result, dict):
        fail("baseline result must be an object")
    if "success" in result and type(result["success"]) is not bool:
        fail("baseline success must be boolean")
    if result.get("success") is False:
        fail("baseline ownership query failed", "BUSINESS_QUERY_FAILED")
    return document


def ownership_agrees(left: dict, right: dict) -> None:
    for field in ("aliasName", "currency", "instId", "bankId"):
        if field in ("instId", "bankId"):
            if any(
                row.get(field) is not None and not isinstance(row[field], str)
                for row in (left, right)
            ):
                fail("account source ownership field is malformed")
            if left.get(field) in (None, "") or right.get(field) in (None, ""):
                continue
        if field in right and right[field] != left.get(field):
            fail("account catalogs disagree on native ownership identity")


def catalog_index(rows: list[dict], *, baseline: bool = False) -> dict:
    indexed, aliases = {}, set()
    for row in rows:
        if any(
            not isinstance(row.get(key), str) or not row[key].strip()
            for key in ("aliasName", "currency")
        ):
            fail("account catalog requires native alias and currency")
        if row.get("tntInstId", TENANT) != TENANT:
            fail("account catalog tenant differs from request")
        if any(
            row.get(key) is not None and not isinstance(row[key], str)
            for key in ("instId", "bankId")
        ):
            fail("account catalog ownership field is malformed")
        key = (row["aliasName"], row["currency"])
        if key in indexed or (baseline and key[0] in aliases):
            fail("account catalog identities are ambiguous")
        indexed[key] = row
        aliases.add(key[0])
    return indexed


def ownership_row(
    cash: dict | None, baseline: dict | None, detail: dict | None
) -> dict:
    row = {}
    for source, native in (("cash", cash), ("baseline", baseline), ("detail", detail)):
        for key in ("aliasName", "currency", "instId", "bankId"):
            if (
                native is not None
                and key in native
                and (key not in row or source == "baseline")
            ):
                row[key] = native[key]
    return row


def live_directory(native: dict, tools: Any) -> dict:
    cash, baseline = tools.collect("accounts", ""), tools.collect("baselines", "")
    if any(
        "IDENTITY_CONTENT_CONFLICT" in result.evidence.reasons
        for result in (cash, baseline)
    ):
        fail("account catalog has conflicting native identity contents")
    cash_index = catalog_index(cash.records)
    baseline_index = catalog_index(baseline.records, baseline=True)
    for key in cash_index.keys() & baseline_index.keys():
        ownership_agrees(cash_index[key], baseline_index[key])
    identities = list(cash_index) + [
        key for key in baseline_index if key not in cash_index
    ]
    records, details = [], {"required": 0, "attempted": 0, "succeeded": 0}
    for key in identities:
        left, right = cash_index.get(key), baseline_index.get(key)
        row = ownership_row(left, right, None)
        relevant = row["aliasName"] == native["aliasName"] and all(
            option not in native
            or field not in row
            or row[field] in (None, "")
            or native[option] == row[field]
            for option, field in (("entity", "instId"), ("bankId", "bankId"))
        )
        absent = any(field not in row for field in ("instId", "bankId"))
        if relevant and right is not None and absent:
            details["required"] += 1
            details["attempted"] += 1
            detail = tools.detail("ownership_detail", row["aliasName"], parameters={})
            ownership_agrees(right, detail)
            if left is not None:
                ownership_agrees(left, detail)
            row = ownership_row(left, right, detail)
            details["succeeded"] += 1
        records.append(row)
    sources_complete = all(
        result.evidence.scope_complete and result.evidence.dataset_complete
        for result in (cash, baseline)
    )
    matched = len(cash_index.keys() & baseline_index.keys())
    inventories_match = matched == len(cash_index) == len(baseline_index)
    complete = sources_complete and inventories_match
    reasons = [*cash.evidence.reasons, *baseline.evidence.reasons]
    if not inventories_match:
        reasons.append("ACCOUNT_SOURCE_MISMATCH")
    return {
        "records": records,
        "quality": {
            "scope_complete": complete,
            "dataset_complete": complete,
            "reasons": list(dict.fromkeys(reasons)),
            "list_coverage": {
                "complete": complete,
                "matched": matched,
                "cash_only": len(cash_index) - matched,
                "baseline_only": len(baseline_index) - matched,
            },
            "sources": {
                "cash": cash.evidence.record(),
                "baseline": baseline.evidence.record(),
            },
            "ownership_detail_coverage": details,
            "ownership_precedence": (
                "baseline keys override cash; detail fills absent keys only"
            ),
        },
    }


class RecordsInquiry:
    name = "liquidity." + LEAF + ".records"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path=PATH,
        page_size=0 if INTRADAY else 5000,
        one_based=False,
        allowed_body_keys=frozenset(
            {"aliasName", "entity", "bankId", "startDate", "endDate"}
            | (set() if INTRADAY else {"rowStart", "pageSize"})
        ),
        fixed_body_values=() if INTRADAY else (("pageSize", 5000),),
    )

    def page_body(self, scope: str, row_start: int, page_size: int) -> dict:
        if (
            type(row_start) is not int
            or row_start < 0
            or type(page_size) is not int
            or (INTRADAY and (row_start != 0 or page_size != 0))
            or (not INTRADAY and (row_start % 5000 or page_size != 5000))
        ):
            fail("unverified account inquiry page", "REQUEST_NOT_ALLOWED")
        try:
            native = parse(scope)
            validate_native(native)
        except (ValueError, UnicodeError, CliError) as error:
            raise CliError(
                "REQUEST_NOT_ALLOWED", "unverified account inquiry scope"
            ) from error
        return (
            native
            if INTRADAY
            else {**native, "rowStart": row_start, "pageSize": page_size}
        )

    def parse_rows(self, body: bytes) -> tuple[list[dict], int | None]:
        doc = parse_document(body)
        if type(doc.get("success")) is not bool:
            fail("account inquiry success is not boolean")
        if not doc["success"]:
            fail("account inquiry failed", "BUSINESS_QUERY_FAILED")
        data = doc.get("data")
        if INTRADAY:
            rows, total = data, None
        else:
            if (
                not isinstance(data, dict)
                or type(data.get("totalCount")) is not int
                or data["totalCount"] < 0
            ):
                fail("account inquiry requires nonnegative native totalCount")
            rows, total = data.get("data"), data["totalCount"]
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            fail("account inquiry records must be objects")
        for row in rows:
            if INTRADAY:
                if row.get("statisticalDate") not in LABELS:
                    fail("intraday label must be a fifteen-minute HH:mm label")
                for field in ("inflowAmount", "outflowAmount", "totalAmount"):
                    value = row.get(field)
                    if (
                        value is not None
                        and value != ""
                        and (
                            not isinstance(value, str)
                            or not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", value)
                        )
                    ):
                        fail("intraday amounts must remain native decimal strings")
        return rows, total

    def validate_rows_scope(self, rows: list[dict], scope: str) -> None:
        native = parse(scope)
        validate_native(native)
        if INTRADAY:
            return
        for row in rows:
            for output, request in (
                ("bankAccountAliasName" if CASHFLOWS else "aliasName", "aliasName"),
                ("entity", "entity"),
                ("bankId" if CASHFLOWS else "bankID", "bankId"),
            ):
                if row.get(output) != native[request]:
                    fail("account record is outside requested ownership scope")
            day = row.get("expectValueDate")
            if (
                not valid_day(day)
                or not native["startDate"] <= day <= native["endDate"]
            ):
                fail("account record is outside requested value-date scope")


def resolve(native: dict, tools: Any) -> tuple[dict, dict]:
    if native.get("entity") and native.get("bankId"):
        return native, {"source": "explicit", "sources": [], "warnings": []}
    notes, warnings = [], []
    for source in ("duckdog", "cache", "live"):
        if source == "live":
            try:
                directory = live_directory(native, tools)
            except CliError as error:
                if error.code in {"AUTH_REQUIRED", "BROWSER_UNAVAILABLE", "TIMEOUT"}:
                    raise CliError(
                        error.code,
                        error.message + "; restore connection, run "
                        "dogopencli login --domain liquidity, "
                        "then rerun the original query",
                        retryable=error.retryable,
                        exit_code=error.exit_code,
                        meta=error.meta,
                    ) from error
                raise
        else:
            directory = tools.account_directory(source)
        if directory is None:
            notes.append({"source": source, "status": "unavailable"})
            continue
        rows, quality = directory["records"], directory["quality"]
        if (
            not isinstance(rows, list)
            or any(not isinstance(row, dict) for row in rows)
            or not isinstance(quality, dict)
        ):
            fail("account directory is malformed")
        for warning in quality.get("warnings", []):
            if not isinstance(warning, dict):
                fail("account directory warning is malformed")
            warnings.append({**warning, "source": source})
        matches = [
            row
            for row in rows
            if row.get("aliasName") == native["aliasName"]
            and ("entity" not in native or row.get("instId") == native["entity"])
            and ("bankId" not in native or row.get("bankId") == native["bankId"])
        ]
        note = {
            "source": source,
            "status": "no_match",
            "match_count": len(matches),
            "quality": quality,
        }
        notes.append(note)
        if not matches:
            continue
        first = matches[0]
        if len(matches) > 1:
            warnings.append(
                {
                    "code": "ACCOUNT_CONTEXT_MULTIPLE_MATCHES",
                    "source": source,
                    "match_count": len(matches),
                    "selected": {
                        k: first.get(k) for k in ("aliasName", "instId", "bankId")
                    },
                    "message": "first matching source row selected",
                }
            )
        resolved = {
            **native,
            "entity": native.get("entity", first.get("instId")),
            "bankId": native.get("bankId", first.get("bankId")),
        }
        if any(
            value is not None and not isinstance(value, str)
            for value in (resolved["entity"], resolved["bankId"])
        ):
            fail("account directory ownership fields are malformed")
        if any(
            not value or not value.strip()
            for value in (resolved["entity"], resolved["bankId"])
        ):
            note["status"] = "missing_fields"
            continue
        validate_native(resolved)
        if quality.get("simulated") is True:
            note["status"] = "simulated_source_rejected"
            raise CliError(
                "INVALID_RESPONSE",
                "simulated account directory cannot resolve a production account query",
                meta={
                    "account_context": {
                        "source": source,
                        "directory_quality": quality,
                        "sources": notes,
                        "warnings": warnings,
                    }
                },
            )
        note["status"] = "selected"
        return resolved, {
            "source": source,
            "directory_quality": quality,
            "sources": notes,
            "warnings": warnings,
            "ownership_reference": (
                "current account directory; historical ownership is not established"
            ),
        }
    raise CliError(
        "SOURCE_DATA_MISSING",
        "no account directory record resolves alias and explicit ownership constraints",
        meta={"account_context": {"sources": notes, "warnings": warnings}},
    )


class Adapter:
    def query_capability(self, operation: str, name: str, parameters: dict) -> Any:
        values(parameters)
        if operation != "list" or name not in {
            "accounts",
            "baselines",
            "ownership_detail",
            "records",
        }:
            fail("undeclared account inquiry", "REQUEST_NOT_ALLOWED")
        return {
            "accounts": AccountsInquiry,
            "baselines": BaselinesInquiry,
            "ownership_detail": OwnershipDetailInquiry,
            "records": RecordsInquiry,
        }[name]()

    def scope(self, parameters: dict) -> str:
        return canonical(values(parameters))

    def query_list(self, parameters: dict, tools: Any) -> CustomListResult:
        native, context = resolve(values(parameters), tools)
        source = tools.collect("records", canonical(native))
        evidence = source.evidence
        complete = evidence.scope_complete and evidence.dataset_complete
        reasons = list(evidence.reasons)
        if (
            INTRADAY
            and source.records
            and {row["statisticalDate"] for row in source.records} != LABELS
        ):
            complete = False
            reasons.append("INTRADAY_SLOT_GAP")
        for note in context["sources"]:
            quality = note.get("quality", {})
            directory_reasons = quality.get("reasons", [])
            if not isinstance(directory_reasons, list) or any(
                not isinstance(reason, str) for reason in directory_reasons
            ):
                fail("account directory quality reasons are malformed")
            reasons.extend(directory_reasons)
            if (
                quality.get("scope_complete") is False
                or quality.get("complete") is False
                or quality.get("dataset_complete") is False
            ):
                complete = False
                reasons.append("ACCOUNT_DIRECTORY_INCOMPLETE")
        evidence = replace(
            evidence,
            scope_complete=complete,
            dataset_complete=complete,
            reasons=tuple(dict.fromkeys(reasons)),
            attempts=(
                *evidence.attempts,
                {"kind": "account_context", **context},
                {
                    "kind": "account_records",
                    "scope": native,
                    "acquisition": source.evidence.record(),
                },
            ),
        )
        return CustomListResult(source.records, evidence)

    def filter(self, records: list[dict], parameters: dict) -> list[dict]:
        native = values(parameters, required=False)
        if INTRADAY:
            return records
        alias = "bankAccountAliasName" if CASHFLOWS else "aliasName"
        bank = "bankId" if CASHFLOWS else "bankID"
        return [
            row
            for row in records
            if all(
                key not in native or row.get(field) == native[key]
                for key, field in (
                    ("aliasName", alias),
                    ("entity", "entity"),
                    ("bankId", bank),
                )
            )
            and (
                "startDate" not in native
                or row["expectValueDate"] >= native["startDate"]
            )
            and ("endDate" not in native or row["expectValueDate"] <= native["endDate"])
        ]


adapter = Adapter()
