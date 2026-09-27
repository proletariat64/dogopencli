"""Shared acquisition and local matching for single-page configurations."""

from typing import Any

from ...errors import INVALID_RESPONSE, REQUEST_NOT_ALLOWED, CliError
from .. import EndpointContract


def validate_row(row: Any) -> None:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("id"), str)
        or not row["id"].strip()
    ):
        raise CliError(
            INVALID_RESPONSE, "configuration row requires nonempty string id"
        )


class ConfigurationListCapability:
    slug: str
    contract: EndpointContract
    default_scope = "all"
    request_filter_error = "backend configuration filters disabled"

    @property
    def command_path(self) -> str:
        return f"collection {self.slug}"

    @staticmethod
    def validate_row(row: Any) -> None:
        validate_row(row)

    def page_body(self, scope: str, page_num: int, page_size: int) -> dict[str, Any]:
        if (
            scope != self.default_scope
            or page_num != int(self.contract.one_based)
            or page_size != self.contract.page_size
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "only the verified first page is allowed"
            )
        return {
            "pageNo": int(self.contract.one_based),
            "pageSize": self.contract.page_size,
        }

    def request_filters(self, body: dict[str, Any]) -> dict[str, list[str]]:
        if body != self.page_body(
            self.default_scope, int(self.contract.one_based), self.contract.page_size
        ):
            raise CliError(REQUEST_NOT_ALLOWED, self.request_filter_error)
        return {}

    def filter_records(
        self, records: list[dict[str, Any]], filters: dict[str, list[str]]
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in records
            if all(row.get(field) in values for field, values in filters.items())
        ]

    def sort_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(records, key=lambda row: row["id"])

    def identity_key(self, record: dict[str, Any]) -> str:
        return record["id"]


ERRORS = (
    "INVALID_ARGUMENT",
    "CONFIG_ERROR",
    "CACHE_MISS",
    "CACHE_STALE",
    "INCOMPLETE_RESULT",
    "AUTH_REQUIRED",
    "BROWSER_UNAVAILABLE",
    "LOCKED",
    "TIMEOUT",
    "BUSINESS_QUERY_FAILED",
    "INVALID_RESPONSE",
)
