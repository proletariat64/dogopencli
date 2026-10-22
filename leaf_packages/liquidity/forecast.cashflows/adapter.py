"""Native forecast points, including models without a valid forecast yet."""

import re
from datetime import datetime

from dogopencli.contracts import EndpointContract
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse

TENANT = "GUAPW3SG"
VO = "cashFlowDataQueryVO"
IDENTITY = (
    "entity",
    "bankId",
    "bankAccountAliasName",
    "bankAccountNo",
    "accountType",
    "currency",
    "bankAccountFlowDateSourceType",
    "fundDirection",
    "expectValueDateTime",
    "extBizType",
    "subBizType",
    "originalBizNo",
    "gmtCreate",
)


def fail(message: str, code: str = "INVALID_RESPONSE") -> None:
    raise CliError(
        code,
        "forecast cashflows: " + message,
        exit_code=2 if code == "INVALID_ARGUMENT" else 1,
    )


def day(value: str) -> str:
    try:
        if not isinstance(value, str) or re.fullmatch(r"[0-9]{8}", value) is None:
            raise ValueError
        datetime.strptime(value, "%Y%m%d")
    except ValueError as error:
        raise CliError(
            "INVALID_ARGUMENT", "value dates must be YYYYMMDD", exit_code=2
        ) from error
    return value


def values(parameters: dict, *, required: bool = True) -> dict:
    result = {}
    for option, field in (
        ("account_alias", "aliasName"),
        ("currency", "currency"),
        ("inst_id", "instId"),
        ("from_date", "beginValueDay"),
        ("to_date", "endValueDay"),
    ):
        value = parameters.get(option)
        if value is None and not required:
            continue
        if value is None and option == "inst_id":
            value = "Z21"
        if not isinstance(value, str) or not value.strip():
            fail(
                "account, currency, entity and date bounds are required",
                "INVALID_ARGUMENT",
            )
        result[field] = day(value) if option in {"from_date", "to_date"} else value
    if (
        "beginValueDay" in result
        and "endValueDay" in result
        and result["beginValueDay"] > result["endValueDay"]
    ):
        fail("date bounds must be ordered", "INVALID_ARGUMENT")
    return result


class Inquiry:
    name = "liquidity.forecast.cashflows.list"
    page_url = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/queryCashFlowData.json",
        page_size=0,
        one_based=False,
        encoding="query",
        total_semantics="unknown",
        allowed_body_keys=frozenset({"tntInstId", VO}),
        fixed_body_values=(("tntInstId", TENANT),),
        json_body_contracts=(
            (
                VO,
                frozenset(
                    {
                        "instId",
                        "aliasName",
                        "currency",
                        "beginValueDay",
                        "endValueDay",
                        "minAmount",
                        "maxAmount",
                    }
                ),
                (("minAmount", None), ("maxAmount", None)),
                frozenset(),
            ),
        ),
    )

    def page_body(self, scope: str, position: int, page_size: int) -> dict:
        native = parse(scope)
        if position != 0 or page_size != 0:
            fail("unpaged source does not support pagination", "REQUEST_NOT_ALLOWED")
        inner = {
            **native,
            "aliasName": [native["aliasName"]],
            "currency": [native["currency"]],
            "minAmount": None,
            "maxAmount": None,
        }
        return {"tntInstId": TENANT, VO: canonical(inner)}

    def parse_rows(self, body: bytes) -> tuple[list[dict], None]:
        document = parse(body)
        if (
            not isinstance(document, dict)
            or type(document.get("resultFlag")) is not bool
        ):
            fail("invalid outer success marker")
        if not document["resultFlag"]:
            fail("native inquiry failed", "BUSINESS_QUERY_FAILED")
        result = document.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            fail("invalid inner success marker")
        if not result["success"]:
            fail("native inquiry failed", "BUSINESS_QUERY_FAILED")
        rows = result.get("bankAccountCashFlowVOList")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            fail("native rows must be objects")
        for field in ("actutalRecordNum", "currentRecordNum"):
            count = result.get(field)
            if type(count) is not int or count < 0:
                fail("invalid native count witness: " + field)
            if count != len(rows):
                fail(
                    "native count witness does not cover response rows",
                    "INCOMPLETE_RESULT",
                )
        for row in rows:
            if any(field not in row for field in IDENTITY):
                fail("native forecast point identity component is missing")
            if any(
                not isinstance(row[field], str)
                for field in IDENTITY
                if field != "gmtCreate"
            ):
                fail("forecast point dimensions must remain native strings")
            for field in ("gmtCreate", "gmtModified"):
                if row.get(field) is not None and type(row[field]) is not int:
                    fail("native timestamps must be milliseconds or null")
            if (
                not isinstance(row.get("expectValueDateTime"), str)
                or re.fullmatch(r"[0-9]{12}", row["expectValueDateTime"]) is None
            ):
                fail("forecast target must be native YYYYMMDDHHmm")
            try:
                datetime.strptime(row["expectValueDateTime"], "%Y%m%d%H%M")
            except ValueError as error:
                raise CliError(
                    "INVALID_RESPONSE", "invalid forecast target time"
                ) from error
        return rows, None

    def validate_rows_scope(self, rows: list[dict], scope: str) -> None:
        native = parse(scope)
        for row in rows:
            if (
                row["bankAccountAliasName"] != native["aliasName"]
                or row["entity"] != native["instId"]
                or row["currency"] != native["currency"]
                or not native["beginValueDay"]
                <= row["expectValueDateTime"][:8]
                <= native["endValueDay"]
            ):
                fail("native forecast point is outside requested scope")


class Adapter:
    def capability(self, parameters: dict) -> Inquiry:
        values(parameters)
        return Inquiry()

    def scope(self, parameters: dict) -> str:
        return canonical(values(parameters))

    def filter(self, records: list[dict], parameters: dict) -> list[dict]:
        scope = values(parameters, required=False)
        return [
            row
            for row in records
            if all(
                key not in scope or row[field] == scope[key]
                for key, field in (
                    ("aliasName", "bankAccountAliasName"),
                    ("instId", "entity"),
                    ("currency", "currency"),
                )
            )
            and (
                "beginValueDay" not in scope
                or row["expectValueDateTime"][:8] >= scope["beginValueDay"]
            )
            and (
                "endValueDay" not in scope
                or row["expectValueDateTime"][:8] <= scope["endValueDay"]
            )
        ]


adapter = Adapter()
