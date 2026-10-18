"""Bounded RiskStandardTrade inquiry; identity and totals remain unproven."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.domain_contracts import FX_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    CliError,
)
from dogopencli.jsonutil import canonical, parse
from dogopencli.temporal import parse_iso_instant

QUERY_FIELDS = frozenset(
    {
        "p5Bcodes",
        "uniqueIds",
        "quoteOperationScene",
        "transactionTypeList",
        "p5TimeOverDue",
        "quoteSymbolList",
        "transactTimeRange",
        "customerIds",
        "subCustomerIds",
    }
)
ARRAY_FILTERS = (
    ("bcode", "p5Bcodes"),
    ("trade_id", "uniqueIds"),
    ("symbol", "quoteSymbolList"),
    ("transaction_type", "transactionTypeList"),
    ("customer_id", "customerIds"),
    ("account_id", "subCustomerIds"),
)
UTC8 = timezone(timedelta(hours=8))


def argument_error(message: str) -> CliError:
    return CliError(INVALID_ARGUMENT, message, exit_code=2)


def time_bound(value: str, *, end: bool) -> int:
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            instant = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC8)
            if end:
                instant += timedelta(days=1, milliseconds=-1)
        else:
            instant = parse_iso_instant(value)
        return int(instant.timestamp() * 1000)
    except (ValueError, OverflowError) as error:
        raise argument_error(
            "trade time must be YYYY-MM-DD (UTC+08:00) or ISO 8601 "
            "with seconds and an explicit offset"
        ) from error


def query_request(args: Any) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if not args.trade_id and args.transact_from is None and args.transact_to is None:
        yesterday = (datetime.now(UTC8) - timedelta(days=1)).date().isoformat()
        query["transactTimeRange"] = {
            "start": time_bound(yesterday, end=False),
            "end": time_bound(yesterday, end=True),
        }
    for flag, field in ARRAY_FILTERS:
        values = getattr(args, flag)
        if "ANY" in values:
            raise argument_error(
                "FX ANY enumeration is not registered; use explicit values"
            )
        if any(not value.strip() for value in values):
            raise argument_error(f"--{flag.replace('_', '-')} must be nonempty")
        if values:
            query[field] = list(dict.fromkeys(values))
    if args.scene is not None:
        if args.scene == "ANY":
            raise argument_error(
                "FX ANY enumeration is not registered; use explicit values"
            )
        if not args.scene.strip():
            raise argument_error("--scene must be nonempty")
        query["quoteOperationScene"] = args.scene
    if args.fulfilled is not None:
        query["p5TimeOverDue"] = int(args.fulfilled)
    if bool(args.transact_from) != bool(args.transact_to):
        raise argument_error("--transact-from and --transact-to must be paired")
    if args.transact_from is not None and args.transact_to is not None:
        start, end = (
            time_bound(args.transact_from, end=False),
            time_bound(args.transact_to, end=True),
        )
        if start > end:
            raise argument_error("trade time start must not follow end")
        query["transactTimeRange"] = {"start": start, "end": end}
    if (
        any(key in query for key in ("p5Bcodes", "customerIds", "quoteOperationScene"))
        and "transactTimeRange" not in query
    ):
        raise argument_error(
            "bcode, customer ID or scene requires both trade time bounds"
        )
    if not query.get("uniqueIds") and "transactTimeRange" not in query:
        raise argument_error("provide a trade ID or both trade time bounds")
    return query


@dataclass(frozen=True)
class TradeInquiry:
    name: str = "fx.trade"
    page_url: str = FX_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="app-ipay-qk.alipay.com",
        path="/ifxriskweb/api/function/RiskStandardTradeAdviceQueryFacade$14c56/pageQueryRiskStandardTradeAdvice",
        page_size=50,
        one_based=False,
        allowed_body_keys=frozenset({"queryRequest", "pageSize", "pageNo"}),
        encoding="json-array",
        nested_body_keys=(("queryRequest", QUERY_FIELDS),),
        has_identity=False,
        total_semantics="unknown",
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        return {"queryRequest": parse(scope), "pageSize": page_size, "pageNo": page_num}

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            wrapper = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "invalid FX response JSON") from error
        if not isinstance(wrapper, dict) or type(wrapper.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "invalid FX response wrapper")
        if not wrapper["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "FX request failed")
        result = wrapper.get("result")
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "invalid FX business result")
        if not result["success"]:
            code = result.get("fvCode")
            suffix = (
                f" ({code})"
                if isinstance(code, str) and re.fullmatch(r"[A-Z0-9_]{1,64}", code)
                else ""
            )
            raise CliError(BUSINESS_QUERY_FAILED, f"FX trade query failed{suffix}")
        value = result.get("value")
        if not isinstance(value, dict):
            raise CliError(INVALID_RESPONSE, "missing FX page value")
        for key in ("totalCount", "currentPage", "pageSize"):
            item = value.get(key)
            if type(item) is not int or item < (1 if key == "pageSize" else 0):
                raise CliError(INVALID_RESPONSE, "invalid FX pagination metadata")
        rows = value.get("items")
        if not isinstance(rows, list) or any(
            not isinstance(row, dict) or not row for row in rows
        ):
            raise CliError(INVALID_RESPONSE, "invalid FX trade records")
        size, total = value["pageSize"], value["totalCount"]
        if len(rows) > size or len(rows) > total:
            raise CliError(INVALID_RESPONSE, "FX page exceeds reported capacity")
        return ParsedPage(rows, value["currentPage"], size, total, -(-total // size))


FX_TRADE = TradeInquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        return FX_TRADE

    def scope(self, parameters: dict[str, Any]) -> str:
        values = {key.replace("-", "_"): value for key, value in parameters.items()}
        for flag, _ in ARRAY_FILTERS:
            values.setdefault(flag, [])
            if values[flag] is None:
                values[flag] = []
        for flag in ("scene", "fulfilled", "transact_from", "transact_to"):
            values.setdefault(flag, None)
        return canonical(query_request(SimpleNamespace(**values)))

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if any(value is not None and value != [] for value in parameters.values()):
            raise CliError(
                INVALID_ARGUMENT,
                "FX cached filters have no verified row mapping; use --live",
                exit_code=2,
            )
        return records


adapter = Adapter()
