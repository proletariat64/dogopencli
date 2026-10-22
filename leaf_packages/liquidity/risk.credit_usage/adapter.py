"""Published bank-counterparty limit usage via the host List SDK."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.domain_contracts import LIQUIDITY_STARTUP_URL
from dogopencli.errors import (
    BUSINESS_QUERY_FAILED,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from dogopencli.jsonutil import parse

TENANT = "GUAPW3SG"
METRIC = "CREDIT_USAGE_RATE"
SCOPE = f"{TENANT}:{METRIC}"


class Inquiry:
    name = "liquidity.risk.credit_usage.list"
    page_url = LIQUIDITY_STARTUP_URL
    contract = EndpointContract(
        method="POST",
        host="iliquidity.alipay.com",
        path="/api/metric/manyMetricQuery.json",
        page_size=0,
        one_based=False,
        allowed_body_keys=frozenset({"tntInstId", "metricName"}),
        fixed_body_values=(("tntInstId", TENANT), ("metricName", METRIC)),
        total_semantics="unknown",
    )

    def page_body(self, scope: str, position: int, page_size: int) -> dict[str, Any]:
        if (
            scope != SCOPE
            or type(position) is not int
            or position != 0
            or type(page_size) is not int
            or page_size != 0
        ):
            raise CliError(REQUEST_NOT_ALLOWED, "Metric has one fixed unpaged inquiry")
        return {"tntInstId": TENANT, "metricName": METRIC}

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], None]:
        try:
            document = parse(body)
        except (ValueError, UnicodeError) as error:
            raise CliError(
                INVALID_RESPONSE, "Metric response is not valid JSON"
            ) from error
        if not isinstance(document, dict) or type(document.get("success")) is not bool:
            raise CliError(INVALID_RESPONSE, "Metric success marker is not boolean")
        if not document["success"]:
            raise CliError(BUSINESS_QUERY_FAILED, "Backend rejected the metric inquiry")
        rows = document.get("data")
        if not isinstance(rows, list):
            raise CliError(INVALID_RESPONSE, "Metric records must be an array")
        for row in rows:
            if not isinstance(row, dict) or type(row.get("id")) is not int:
                raise CliError(INVALID_RESPONSE, "Metric id must be a native integer")
            if row.get("metricName") != METRIC:
                raise CliError(
                    INVALID_RESPONSE, "Metric name contradicts requested scope"
                )
            if "tntInstId" in row and row["tntInstId"] != TENANT:
                raise CliError(
                    INVALID_RESPONSE, "Metric tenant contradicts requested scope"
                )
        return rows, None


CAPABILITY = Inquiry()


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Inquiry:
        return CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return SCOPE

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return records


adapter = Adapter()
