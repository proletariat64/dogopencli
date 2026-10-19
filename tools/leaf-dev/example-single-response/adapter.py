"""Synthetic qualified whole-response List; run only in the fake CLI harness."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse


class Inquiry:
    name = "collection.sample.response.list"
    page_url = "https://leaf-handbook.invalid/app"
    contract = EndpointContract(
        method="POST",
        host="leaf-handbook.invalid",
        path="/response/query",
        page_size=2,
        one_based=False,
        allowed_body_keys=frozenset({"scope", "rowStart", "pageSize"}),
        fixed_body_values=(("scope", "all"), ("rowStart", 0)),
        total_semantics="unknown",
    )

    def page_body(self, scope: str, position: int, page_size: int) -> dict[str, Any]:
        if scope != "all" or position != 0 or page_size != 2:
            raise CliError(REQUEST_NOT_ALLOWED, "Unsupported sample request")
        return {"scope": scope, "rowStart": position, "pageSize": page_size}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], None]:
        try:
            value = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "Sample response is not JSON") from error
        if not isinstance(value, dict) or type(value.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "Sample success flag is invalid")
        if not value["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "Sample inquiry was rejected")
        rows = value.get("rows")
        if not isinstance(rows, list) or any(
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not row["id"].strip()
            for row in rows
        ):
            raise CliError(INVALID_RESPONSE, "Sample records are invalid")
        return rows, None


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return Inquiry()

    def scope(self, parameters: dict[str, Any]) -> str:
        return "all"

    def filter(self, records: list[dict], parameters: dict[str, Any]) -> list[dict]:
        return records


adapter = Adapter()
