"""Synthetic independently scoped sources and an explicitly reviewed grouping."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import canonical, parse


class SourceInquiry:
    page_url = "https://leaf-handbook.invalid/app"

    def __init__(self, name: str) -> None:
        if name not in {"left", "right"}:
            raise CliError(INVALID_ARGUMENT, "Unknown sample source", exit_code=2)
        self.name = "collection.sample.sources." + name
        self.contract = EndpointContract(
            method="POST",
            host="leaf-handbook.invalid",
            path=f"/sources/{name}/query",
            page_size=2,
            one_based=False,
            allowed_body_keys=frozenset({"scope", "rowStart", "pageSize"}),
        )

    def page_body(self, scope: str, position: int, page_size: int) -> dict[str, Any]:
        if not scope.strip() or position < 0 or page_size != 2:
            raise CliError(REQUEST_NOT_ALLOWED, "Unsupported sample source request")
        return {"scope": scope, "rowStart": position, "pageSize": page_size}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int]:
        try:
            value = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(INVALID_RESPONSE, "Sample response is not JSON") from error
        if not isinstance(value, dict) or type(value.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "Sample success flag is invalid")
        if not value["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "Sample source inquiry was rejected")
        rows, total = value.get("rows"), value.get("total")
        if (
            type(total) is not int
            or total < 0
            or not isinstance(rows, list)
            or any(
                not isinstance(row, dict)
                or any(
                    not isinstance(row.get(key), str) or not row[key].strip()
                    for key in ("id", "parentRef")
                )
                for row in rows
            )
        ):
            raise CliError(
                INVALID_RESPONSE, "Sample source records or total are invalid"
            )
        return rows, total


class Adapter:
    def source_capability(self, name: str, parameters: dict[str, Any]) -> SourceInquiry:
        return SourceInquiry(name)

    def source_scope(self, name: str, parameters: dict[str, Any]) -> str:
        if name not in {"left", "right"}:
            raise CliError(INVALID_ARGUMENT, "Unknown sample source", exit_code=2)
        value = parameters.get(name + "_scope")
        if not isinstance(value, str) or not value.strip():
            raise CliError(
                INVALID_ARGUMENT, "Both source scopes are required", exit_code=2
            )
        return value

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(
            {name: self.source_scope(name, parameters) for name in ("left", "right")}
        )

    def assemble(
        self, records_by_source: dict[str, list[dict]], parameters: dict[str, Any]
    ) -> list[dict]:
        # This fixture's reviewed relation is child.parentRef -> root.parentRef.
        # Left first, then new right parents; each source's child order stays native.
        parents: dict[str, dict] = {}
        for name in ("left", "right"):
            for child in records_by_source[name]:
                reference = child["parentRef"]
                parent = parents.setdefault(
                    reference, {"parentRef": reference, "left": [], "right": []}
                )
                parent[name].append(child)
        return list(parents.values())

    def filter(self, records: list[dict], parameters: dict[str, Any]) -> list[dict]:
        return records


adapter = Adapter()
