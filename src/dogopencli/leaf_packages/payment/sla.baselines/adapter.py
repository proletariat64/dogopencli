"""Verified SLA requests and parsing behind the local leaf interface."""

import json
from typing import Any

from dogopencli.collect import collect_scope, execute_bounded
from dogopencli.errors import INVALID_ARGUMENT, CliError
from dogopencli.jsonutil import canonical
from dogopencli.plugins.payment.sla import (
    FILTER_FIELDS,
    SLA_CAPABILITY,
    SLA_DETAIL,
    detail_body,
    parse_detail,
)

FILTERS = {
    "biz_category": "bizCategory",
    "creditor_currency": "creditorCurrency",
    "region_code": "regionCode",
    "status": "status",
    "biz_legal_entity": "bizLegalEntity",
}


def native_filters(parameters: dict[str, Any]) -> dict[str, str]:
    result = {}
    for flag, value in parameters.items():
        key = flag.replace("-", "_")
        if key not in FILTERS or value is None or value == []:
            continue
        values = value if isinstance(value, list) else [value]
        if len(values) != 1 or not isinstance(values[0], str) or not values[0].strip():
            raise CliError(
                INVALID_ARGUMENT, f"{flag} requires one nonempty value", exit_code=2
            )
        result[FILTERS[key]] = values[0]
    return result


class Adapter:
    def capability(self, parameters: dict[str, Any]) -> Any:
        native_filters(parameters)
        return SLA_CAPABILITY

    def scope(self, parameters: dict[str, Any]) -> str:
        return canonical(native_filters(parameters))

    def collector(
        self, capability: Any, transport: Any, scope: str, *, progress: Any = None
    ) -> Any:
        candidate = collect_scope(
            capability,
            transport,
            capability.default_scope,
            json.loads(scope),
            progress=progress,
        )
        return candidate

    def get(
        self, session: Any, parameters: dict[str, Any], identity: str
    ) -> dict[str, Any]:
        response = execute_bounded(
            SLA_DETAIL, session.transport(SLA_DETAIL), detail_body(identity)
        )
        return parse_detail(response.body, identity)

    def filter(
        self, records: list[dict[str, Any]], parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        filters = native_filters(parameters)
        if "bizLegalEntity" in filters:
            raise CliError(
                INVALID_ARGUMENT,
                "Business legal entity has no verified cached field; use --live",
                exit_code=2,
            )
        return [
            row
            for row in records
            if all(
                row.get(FILTER_FIELDS[key]) == value for key, value in filters.items()
            )
        ]


adapter = Adapter()
