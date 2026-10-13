"""Verified FX Shield individual-trade RPC contract (2026-10-12 handoff)."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ...browser.environment import FX_STARTUP_URL
from ...errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    CliError,
)
from ...helpspec import LIVE, BizNode, contract, opt
from ...jsonutil import parse
from ...temporal import parse_iso_instant
from .. import EndpointContract, ParsedPage

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


def _bound(value: str, *, end: bool) -> int:
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
            "start": _bound(yesterday, end=False),
            "end": _bound(yesterday, end=True),
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
        start = _bound(args.transact_from, end=False)
        end = _bound(args.transact_to, end=True)
        if start > end:
            raise argument_error("trade time start must not follow end")
        query["transactTimeRange"] = {"start": start, "end": end}
    # Match the observed UI prerequisite and reject unbounded scans locally.
    scoped = any(
        key in query for key in ("p5Bcodes", "customerIds", "quoteOperationScene")
    )
    if scoped and "transactTimeRange" not in query:
        raise argument_error(
            "bcode, customer ID or scene requires both trade time bounds"
        )
    if not query.get("uniqueIds") and "transactTimeRange" not in query:
        raise argument_error("provide a trade ID or both trade time bounds")
    return query


@dataclass(frozen=True)
class TradeCapability:
    name: str = "fx.trade"
    cache_enabled: bool = True
    page_url: str = FX_STARTUP_URL
    contract: EndpointContract = EndpointContract(
        method="POST",
        host="app-ipay-qk.alipay.com",
        path=(
            "/ifxriskweb/api/function/RiskStandardTradeAdviceQueryFacade$14c56/"
            "pageQueryRiskStandardTradeAdvice"
        ),
        page_size=50,
        one_based=False,
        allowed_body_keys=frozenset({"queryRequest", "pageSize", "pageNo"}),
        encoding="json-array",
        nested_body_keys=(("queryRequest", QUERY_FIELDS),),
        has_identity=False,
        total_semantics="unknown",
    )

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
            # Backend messages can include SQL, identifiers and authentication.
            # Only a bounded machine code is safe to propagate.
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
            minimum = 1 if key == "pageSize" else 0
            if type(item) is not int or item < minimum:
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


FX_TRADE = TradeCapability()
LIVE_MODE = {
    "cache": {"available": False},
    "live": {"available": True, "role": "native-request"},
    "refresh": {"available": True, "role": "native-request"},
}
DISPLAY_MODE = {
    "cache": {"available": True, "role": "display"},
    "live": {"available": True, "role": "display"},
    "refresh": {"available": True, "role": "display"},
}


def native_option(name: str, summary: str, kind: str = "str", **kwargs: Any):
    return opt(
        name,
        summary,
        kind,
        argument_contract=contract("string", modes=LIVE_MODE),
        **kwargs,
    )


def display_option(name: str, summary: str, kind: str = "str", **kwargs: Any):
    value_type = {"int": "integer", "bool": "boolean"}.get(kind, "string")
    return opt(
        name,
        summary,
        kind,
        argument_contract=contract(value_type, modes=DISPLAY_MODE),
        **kwargs,
    )


GROUP_NODE = BizNode(("fx",), "Read-only foreign-exchange inquiries.")
TRADE_NODE = BizNode(
    ("fx", "trade"),
    "Replay temporary FX trades; --live queries the authenticated browser.",
    kind="runtimes",
    options=(
        LIVE,
        *(
            native_option(flag, f"Native {field} filter (repeatable).", "append")
            for flag, field in ARRAY_FILTERS
        ),
        native_option("scene", "Native quoteOperationScene; e.g. A+前报价."),
        native_option(
            "fulfilled", "P5 fulfilment: 1=fulfilled, 0=overdue.", choices=("0", "1")
        ),
        *(
            opt(
                name,
                "Inclusive trade time bound: calendar date in UTC+08:00 "
                "or ISO instant.",
                argument_contract=contract(
                    "datetime",
                    preferred_format="YYYY-MM-DD",
                    accepted_formats=(
                        "YYYY-MM-DD",
                        "YYYY-MM-DDTHH:mm:ssZ",
                        "YYYY-MM-DDTHH:mm:ss±HH:MM",
                    ),
                    modes={
                        **LIVE_MODE,
                        **{
                            mode: {
                                **LIVE_MODE[mode],
                                "default": {
                                    "kind": "previous_complete_calendar_day",
                                    "timezone": "GMT+08",
                                    "when": "trade_id and date bounds omitted",
                                },
                            }
                            for mode in ("live", "refresh")
                        },
                    },
                    timezone="UTC+08:00 for calendar dates",
                ),
            )
            for name in ("transact_from", "transact_to")
        ),
        display_option(
            "limit",
            "Display limit (default 100); zero displays all remaining rows.",
            "int",
            help_default=100,
        ),
        display_option("offset", "Display offset (default 0).", "int", help_default=0),
        display_option("fields", "Comma-separated top-level record projection."),
        opt(
            "require_complete",
            "Reject an acquisition without full coverage proof.",
            "bool",
            argument_contract=contract(
                "boolean",
                modes={
                    "cache": {"available": True, "role": "cache-policy"},
                    "live": {"available": True, "role": "cache-policy"},
                    "refresh": {"available": True, "role": "cache-policy"},
                },
            ),
        ),
        display_option(
            "format", "Result format.", default="json", choices=("json", "table")
        ),
    ),
    constraints=(
        "Default offline replay; --live never writes; "
        "refresh replaces one temporary slot.",
        "This queries RiskStandardTrade individual records, not TradeBatch aggregates.",
        "Online omitted ID/dates uses the previous complete GMT+08 day. "
        "Explicit dates must be paired. "
        "Bcode/customer ID/scene requires trade time bounds.",
        "Acquisition is bounded to 100 pages and 120 seconds; "
        "display pagination is separate.",
        "Offline business filters lack verified row mappings; use --live or refresh.",
        "Record identity and native total counting semantics remain "
        "unverified; complete stays false.",
    ),
    effects={
        "mutates": False,
        "network": True,
        "browser_required": True,
        "destructive": False,
    },
    output={
        "default_format": "json",
        "formats": ["json", "table"],
        "help_default_format": "json",
        "help_formats": ["json", "text"],
    },
    errors=(
        "INVALID_ARGUMENT",
        "AUTH_REQUIRED",
        "BROWSER_UNAVAILABLE",
        "LOCKED",
        "TIMEOUT",
        "BUSINESS_QUERY_FAILED",
        "INVALID_RESPONSE",
        "INCOMPLETE_RESULT",
    ),
    examples=(
        "dogopencli fx trade --live --transact-from 2026-10-03 "
        "--transact-to 2026-10-03 --bcode BCODE --scene 'A+前报价' "
        "--transaction-type SALE --fulfilled 1 --symbol USD/PHP",
    ),
    next=("dogopencli login --domain fx", "dogopencli auth check --domain fx"),
    handler="cmd_fx_trade",
)


def description(node: BizNode) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "data_schema": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        },
        "read_guide": {
            "summary": (
                "Native individual FX trades. Unknown fields, numeric "
                "precision and source timestamps are preserved. No verified "
                "row schema or stable identity is claimed."
            ),
            "quality": (
                "Identity and total counting unit remain unverified; "
                "complete=false even when all reported pages arrive. "
                "--require-complete rejects. Production CLI UAT is pending."
            ),
            "source": (
                "RiskStandardTrade; TradeBatch aggregate results "
                "are outside this command."
            ),
        },
    }
