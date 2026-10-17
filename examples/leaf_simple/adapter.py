"""Synthetic standard list: owned contract/parser, shared host mechanics.

The .invalid endpoint exists only in the offline handbook test harness.
No legacy business module or production endpoint is used by this example.
"""

from collections.abc import Callable
from typing import Any

from dogopencli.collect import CollectedScope, collect_scope
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse
from dogopencli.plugins import EndpointContract, ParsedPage


class SampleCapability:
    name = "collection.sample.records.list"
    page_url = "https://leaf-handbook.invalid/app"
    contract = EndpointContract(
        method="POST",
        host="leaf-handbook.invalid",
        path="/records/query",
        page_size=2,
        one_based=False,
        allowed_body_keys=frozenset({"scope", "pageNo", "pageSize"}),
        fixed_body_values=(("scope", "all"),),
    )

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if scope != "all" or page_size != self.contract.page_size or page_num < 0:
            raise CliError(REQUEST_NOT_ALLOWED, "Unsupported sample request")
        return {"scope": scope, "pageNo": page_num, "pageSize": page_size}

    def identity_key(self, record: dict[str, Any]) -> str:
        return record["id"]

    def parse_page(self, body: bytes) -> ParsedPage:
        try:
            value = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "Sample response is not JSON") from error
        if not isinstance(value, dict) or type(value.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "Sample success flag is invalid")
        if not value["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "Sample inquiry was rejected")
        rows = value.get("rows")
        page, size, total = (
            value.get("pageNo"),
            value.get("pageSize"),
            value.get("total"),
        )
        if (
            any(type(number) is not int for number in (page, size, total))
            or page < 0
            or size != self.contract.page_size
            or total < 0
            or not isinstance(rows, list)
            or any(
                not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not row["id"].strip()
                for row in rows
            )
        ):
            raise CliError(INVALID_RESPONSE, "Sample records or pagination are invalid")
        return ParsedPage(rows, page, size, total, -(-total // size))


CAPABILITY = SampleCapability()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> SampleCapability:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return "all"

    def collector(
        self,
        capability: SampleCapability,
        transport: Any,
        scope: str,
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> CollectedScope:
        return collect_scope(capability, transport, scope, progress=progress)

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
