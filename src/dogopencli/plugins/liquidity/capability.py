"""Transport-facing liquidity capabilities built from leaf specifications.

One capability object wraps a ListSpec/DetailSpec: it owns the exact request
construction (template + validated scope values + pagination fields) and the
formal response parsing (envelope, record container, reported total, typed
identity), while the shared core keeps transport, allowlist validation and
browser lifecycle. All liquidity requests route to the verified liquidity
origin through the declared application entry (ADR 0015).
"""

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ...browser.environment import LIQUIDITY_STARTUP_URL
from ...errors import (
    EXIT_USAGE,
    INVALID_ARGUMENT,
    INVALID_RESPONSE,
    REQUEST_NOT_ALLOWED,
    CliError,
)
from ...jsonutil import canonical
from ...temporal import normalize_clock
from .. import EndpointContract
from . import spec
from .envelope import dig, envelope_document
from .projection import project_record
from .retirement import refuse_retired


def _invalid(message: str) -> CliError:
    return CliError(INVALID_RESPONSE, message)


def _usage(message: str) -> CliError:
    return CliError(INVALID_ARGUMENT, message, exit_code=EXIT_USAGE)


def encode_scope(values: dict[str, Any]) -> str:
    """Canonical scope identity for cache namespaces and acquisition."""
    return ";".join(f"{field}={canonical(values[field])}" for field in sorted(values))


def decode_scope(scope: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if not scope:
        return values
    decoder = json.JSONDecoder()
    position = 0
    while position < len(scope):
        separator = scope.find("=", position)
        field = scope[position:separator]
        if separator < 0 or not field:
            raise _usage(f"malformed scope: {scope}")
        try:
            value, end = decoder.raw_decode(scope, separator + 1)
        except ValueError as error:
            raise _usage(f"malformed scope: {scope}") from error
        if field in values or (end < len(scope) and scope[end] != ";"):
            raise _usage(f"malformed scope: {scope}")
        values[field] = value
        position = end + 1
        if end < len(scope) and position == len(scope):
            raise _usage(f"malformed scope: {scope}")
    return values


def scope_values(
    options: tuple[spec.ScopeOption, ...],
    provided: Mapping[str, str | list[str] | None],
) -> tuple[dict[str, Any], tuple[str | None, str | None]]:
    """Validate CLI scope values into request fields plus the business window.

    Source filters and the business window are exact pass-throughs of the
    verified request shape; no undocumented filter is ever produced.
    """
    fields: dict[str, Any] = {}
    window_from: str | None = None
    window_to: str | None = None
    by_flag = {option.flag: option for option in options}
    unknown = sorted(set(provided) - set(by_flag))
    if unknown:
        raise _usage(f"unknown scope options: {unknown}")
    for option in options:
        public = option.public_flag
        raw = provided.get(option.flag)
        if raw is None or raw == []:
            if option.required:
                raise _usage(f"{public} is required")
            if option.default is not None:
                raw = option.default
            else:
                continue
        if option.repeat:
            items = list(raw) if isinstance(raw, list) else [raw]
            if not items or any(not str(item).strip() for item in items):
                raise _usage(
                    f"{public} must be nonempty",
                )
            value: Any = [str(item) for item in items]
        else:
            if isinstance(raw, list):
                raise _usage(
                    f"{public} accepts a single value",
                )
            text = str(raw)
            if not text.strip():
                raise _usage(
                    f"{public} must be nonempty",
                )
            if option.date:
                # Preferred YYYY-MM-DD and legacy compact YYYYMMDD normalize
                # to the existing internal compact form before scope and
                # request construction (Issue #127 decisions 7 and 9).
                if len(text) == 10 and text[4] == "-" and text[7] == "-":
                    text = text[:4] + text[5:7] + text[8:]
                try:
                    if len(text) != 8 or not text.isascii() or not text.isdigit():
                        raise ValueError
                    datetime.strptime(text, "%Y%m%d")
                except ValueError as error:
                    raise _usage(
                        f"{public} must be a valid calendar date"
                        " (YYYY-MM-DD preferred, YYYYMMDD accepted)",
                    ) from error
            if option.time:
                try:
                    text = normalize_clock(text)
                except ValueError as error:
                    raise _usage(
                        f"{public} must be a valid HH:mm:ss"
                        " (legacy compact HHmmss accepted)",
                    ) from error
            value = [text] if option.list_of_one else text
        if option.choices:
            values = value if isinstance(value, list) else [value]
            invalid = [item for item in values if item not in option.choices]
            if invalid:
                raise _usage(
                    f"{public} must be one of {', '.join(option.choices)}",
                )
        if option.window in ("from", "both"):
            window_from = value if isinstance(value, str) else None
        if option.window in ("to", "both"):
            window_to = value if isinstance(value, str) else None
        fields[option.field] = value
    if (window_from is None) != (window_to is None):
        raise _usage("the business window needs both bounds")
    if window_from is not None and window_to is not None and window_from > window_to:
        raise _usage("the business window start is after its end")
    if (
        "recordStartTime" in fields
        and "recordEndTime" in fields
        and fields["recordStartTime"] > fields["recordEndTime"]
    ):
        raise _usage("record creation time start is after its end")
    return fields, (window_from, window_to)


class LiquidityListCapability:
    """List inquiry: verified request construction and response parsing."""

    def __init__(self, list_spec: spec.ListSpec) -> None:
        self._spec = list_spec
        body_keys = set(list_spec.template)
        if list_spec.paged_request and not (
            list_spec.schema_version and list_spec.vo_field
        ):
            body_keys |= {"rowStart", "pageSize"}
        if list_spec.vo_field is not None:
            body_keys |= {list_spec.vo_field}
        for option in list_spec.scope_options:
            if not option.virtual and not (
                list_spec.schema_version and list_spec.vo_field
            ):
                body_keys.add(option.field)
        self._body_keys = frozenset(body_keys)

    @property
    def descriptor(self) -> spec.ListSpec:
        """Verified contract descriptor used by acquisition."""
        return self._spec

    @property
    def name(self) -> str:
        return self._spec.name

    @property
    def source_config_key(self) -> str:
        return "liquidity"

    @property
    def page_url(self) -> str:
        return LIQUIDITY_STARTUP_URL

    @property
    def contract(self) -> EndpointContract:
        refuse_retired(self._spec.path)
        return EndpointContract(
            method=self._spec.method,
            host=spec.HOST,
            path=self._spec.endpoint,
            page_size=self._spec.page_size,
            one_based=False,
            allowed_body_keys=self._body_keys,
            fixed_body_values=tuple(
                (key, value)
                for key, value in self._spec.template.items()
                if self._spec.schema_version
                and isinstance(value, (str, int))
                and not isinstance(value, bool)
            )
            + (
                (
                    (
                        self._spec.vo_field,
                        json.dumps(
                            {
                                **self._spec.template[self._spec.vo_field],
                                "rowStart": 0,
                                "pageSize": self._spec.page_size,
                            }
                        ),
                    ),
                )
                if self._spec.projection == "transfer_rules" and self._spec.vo_field
                else ()
            ),
            encoding=(
                spec.ENC_FORM if self._spec.encoding == spec.ENC_FORM else spec.ENC_JSON
            ),
            json_body_contracts=(
                (
                    (
                        self._spec.vo_field,
                        frozenset(self._spec.template[self._spec.vo_field])
                        | {"rowStart", "pageSize"},
                        tuple(self._spec.template[self._spec.vo_field].items()),
                        frozenset((1000, self._spec.page_size)),
                    ),
                )
                if self._spec.schema_version == "access-lists-v1"
                and self._spec.vo_field
                else ()
            ),
        )

    def page_body(
        self, scope: str, row_start: int, page_size: int | None = None
    ) -> dict[str, Any]:
        """One verified request body for the offset starting at row_start."""
        refuse_retired(self._spec.path)
        values = decode_scope(scope)
        if self._spec.projection == "funding_demands" and (
            row_start != 0 or page_size not in (None, self._spec.page_size)
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "funding demands have one fixed base request"
            )
        if self._spec.projection == "rule_status" and (
            row_start != 0 or page_size not in (None, self._spec.page_size)
        ):
            raise CliError(
                REQUEST_NOT_ALLOWED, "rule status has one fixed base request"
            )
        if self._spec.projection == "forecast_accuracy":
            from .forecast_accuracy import base_body

            if row_start != 0 or page_size not in (None, 5000):
                raise CliError(
                    REQUEST_NOT_ALLOWED, "accuracy has one fixed base request"
                )
            return base_body(values)
        if page_size is None:
            page_size = self._spec.page_size
        body = dict(self._spec.template)
        if self._spec.vo_field is not None:
            vo = dict(body.pop(self._spec.vo_field, {}))
            for option in self._spec.scope_options:
                if not option.virtual and option.field in values:
                    vo[option.field] = values[option.field]
            if self._spec.paged_request:
                vo["rowStart"] = row_start
                vo["pageSize"] = page_size
            body[self._spec.vo_field] = json.dumps(vo)
        else:
            for option in self._spec.scope_options:
                if not option.virtual and option.field in values:
                    body[option.field] = values[option.field]
            if self._spec.paged_request:
                body["rowStart"] = row_start
                body["pageSize"] = page_size
        if self._spec.projection in {"risk_events", "risk_anomalies"}:
            from .risk_batch import risk_request_dates

            body = risk_request_dates(body)
        if self._spec.projection == "strategy_results":
            from .investment_batch import strategy_wire_dates

            strategy_wire_dates(body)
        if self._spec.projection == "quotes":
            from .investment_batch import quote_wire_dates

            quote_wire_dates(body)
        if self._spec.projection == "rfq_subtasks":
            from .rfqs import rfq_wire_dates

            rfq_wire_dates(body)
        if self._spec.endpoint == "/queryEnquireRateList.json":
            from .interest_rates import wire_dates

            wire_dates(body)
        return body

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int | None]:
        """Envelope, record container and reported total of one response."""
        node = envelope_document(body, self._spec.envelope)
        if self._spec.require_inner_success:
            inner_success = dig(node, ("result", "success"))
            if not isinstance(inner_success, bool) or not inner_success:
                raise _invalid("inner result success marker is not true")
        rows = dig(node, self._spec.container)
        if self._spec.projection == "account_capacity":
            if not isinstance(rows, dict) or not rows:
                raise _invalid("capacity data is not a nonempty native object")
            rows = [rows]
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise _invalid("record container is not a list of objects")
        total: int | None = None
        if self._spec.total is not None:
            raw_total = dig(node, self._spec.total)
            if isinstance(raw_total, bool) or not isinstance(raw_total, int):
                raise _invalid("reported total is not an integer")
            if raw_total < 0:
                raise _invalid("reported total is negative")
            total = raw_total
        for path in self._spec.total_checks:
            other_total = dig(node, path)
            if (
                isinstance(other_total, bool)
                or not isinstance(other_total, int)
                or other_total != total
            ):
                raise _invalid("reported totals disagree")
        if self._spec.projection == "funding_demands" and (
            total is None
            or total > self._spec.page_size
            or len(rows) > self._spec.page_size
        ):
            raise _invalid(
                "funding demand scope exceeds the verified single-response limit"
                " of 5000; narrow the execution-time range"
            )
        if self._spec.projection == "rule_status":
            if (
                total is None
                or total > self._spec.page_size
                or len(rows) > self._spec.page_size
            ):
                raise _invalid(
                    "rule status scope exceeds the verified single-response"
                    " limit of 5000; narrow the trigger range"
                )
            if len(rows) != total:
                raise _invalid("rule status rows do not equal the reported total")
            seen_identities: set[tuple[str, ...]] = set()
            for row in rows:
                key = self.identity_key(row)
                if key in seen_identities:
                    raise _invalid("duplicate rule status native record identity")
                seen_identities.add(key)
        if self._spec.projection == "rfq_subtasks" and not rows and total != 0:
            raise _invalid("empty RFQ response does not cover its reported total")
        if self._spec.endpoint in (
            "/queryMarketRateRuleList.json",
            "/queryFinancialMarketRateRuleList.json",
        ):
            from .interest_rates import validate_rules

            validate_rules(rows, self._spec.template["rateCategory"])
        seen_raw: dict[tuple[str, ...], str] = {}
        for row in rows:
            identity = self.identity_key(row)
            if self._spec.projection in {"transfer_rules", "factor_definitions"}:
                content = canonical(row)
                if identity in seen_raw and seen_raw[identity] != content:
                    if self._spec.projection == "transfer_rules":
                        raise _invalid("conflicting content for transfer rule identity")
                    raise _invalid("conflicting native factor definition content")
                seen_raw[identity] = content
        if self._spec.projection == "realtime_network":
            from .realtime_network import validate_native_rows

            validate_native_rows(rows)
        if self._spec.projection:
            rows = [project_record(self._spec.projection, row) for row in rows]
        return list(rows), total

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        """Reject out-of-scope rows before live output or publication."""
        if self._spec.schema_version == "access-lists-v1":
            from .access_lists import BANK_BLACKLIST, latest_bank_rows

            bank_selection = self._spec.path == BANK_BLACKLIST.path
            if bank_selection:
                latest_bank_rows(rows)
            seen: dict[str, str] = {}
            for row in rows:
                identity = row.get(self._spec.identity[0])
                if not isinstance(identity, str) or not identity.strip():
                    raise _invalid(
                        "access-list native identity is not a nonempty string"
                    )
                if "tntInstId" in row and row["tntInstId"] not in ("", spec.TENANT):
                    raise _invalid("access-list row belongs to another tenant")
                content = canonical(row)
                if (
                    not bank_selection
                    and identity in seen
                    and seen[identity] != content
                ):
                    raise _invalid("conflicting access-list identity")
                seen[identity] = content
        if self._spec.endpoint == "/latestBalanceQuery.json":
            values = decode_scope(scope)
            entities = values.get("entitys")
            aliases = values.get("aliasNames")
            if not isinstance(entities, list) or not entities:
                raise _invalid("latest inquiry is missing its requested entity set")
            for record in rows:
                entity = record.get("entity")
                if (
                    not isinstance(entity, str)
                    or not entity.strip()
                    or entity not in entities
                ):
                    raise _invalid("latest balance entity is outside the requested set")
                if aliases and record.get("aliasName") not in aliases:
                    raise _invalid("latest balance alias is outside the requested set")
        if self._spec.projection == "funding_demands":
            from .funding_demands import validate_demand_rows_scope

            validate_demand_rows_scope(rows, decode_scope(scope))
        if self._spec.projection == "rule_status":
            from .rule_status import validate_rule_status_rows_scope

            validate_rule_status_rows_scope(rows, decode_scope(scope))
        if self._spec.projection == "decision_reports":
            from .decision_list import validate_decision_rows_scope

            validate_decision_rows_scope(rows, decode_scope(scope))
        if self._spec.projection == "swap_orders":
            from .operations_batch import validate_swap_rows_scope

            validate_swap_rows_scope(rows, decode_scope(scope))
        if self._spec.projection == "transfer_orders":
            from .transfer_list import validate_transfer_rows_scope

            validate_transfer_rows_scope(rows)
        if self._spec.projection == "strategy_results":
            from .investment_batch import validate_strategy_rows_scope

            validate_strategy_rows_scope(rows, decode_scope(scope))
        if self._spec.endpoint == "/queryEnquireRateList.json":
            from .interest_rates import validate_bank_scope

            validate_bank_scope(rows, decode_scope(scope))
        if not (self._spec.schema_version and self._spec.profile == spec.PROFILE_DATED):
            return
        # Use the native business-date parser so acquisition and
        # offline coverage interpret the same business day, not capture time.
        from .store import series_value

        values = decode_scope(scope)
        bounds: dict[str, str] = {}
        for option in self._spec.scope_options:
            if option.window is None:
                continue
            value = values.get(option.field)
            if not isinstance(value, str):
                raise _invalid("dated inquiry is missing its verified request window")
            keys = ("from", "to") if option.window == "both" else (option.window,)
            for key in keys:
                bounds[key] = value
        if "from" not in bounds or "to" not in bounds:
            raise _invalid("dated inquiry is missing its verified request window")
        for record in rows:
            day = series_value(self._spec, record, "")
            if not bounds["from"] <= day <= bounds["to"]:
                raise _invalid("record series date is outside the requested window")

    def identity_key(self, record: dict[str, Any]) -> tuple[str, ...]:
        """Typed identity: every declared field must be present and atomic."""
        if not self._spec.identity:
            # Content matching is not a business identity. Callers preserve
            # the multiplicity of identical rows within each acquisition.
            return (canonical(record),)
        key: list[str] = []
        for field in self._spec.identity:
            value = record.get(field)
            if (
                value is None
                or isinstance(value, (dict, list))
                or (
                    self._spec.schema_version
                    and (
                        isinstance(value, bool)
                        or not isinstance(value, (str, int))
                        or (isinstance(value, str) and not value.strip())
                    )
                )
            ):
                raise _invalid(f"record is missing identity field {field}")
            key.append(canonical(value))
        return tuple(key)


class LiquidityDetailCapability:
    """One allowlisted native detail/history inquiry (no pagination)."""

    def __init__(self, detail_spec: spec.DetailSpec) -> None:
        self._spec = detail_spec

    @property
    def name(self) -> str:
        return self._spec.name

    @property
    def source_config_key(self) -> str:
        return "liquidity"

    @property
    def page_url(self) -> str:
        return LIQUIDITY_STARTUP_URL

    @property
    def contract(self) -> EndpointContract:
        return EndpointContract(
            method=self._spec.method,
            host=spec.HOST,
            path=self._spec.endpoint,
            page_size=0,
            one_based=False,
            allowed_body_keys=frozenset(
                ({"tntInstId"} if self._spec.sends_tenant else set())
                | {option.field for option in self._spec.identity if not option.virtual}
                | set(self._spec.template)
            ),
            fixed_body_values=tuple(
                (key, value)
                for key, value in self._spec.template.items()
                if isinstance(value, (str, int)) and not isinstance(value, bool)
            )
            + (
                (("tntInstId", spec.TENANT),)
                if self._spec.schema_version and self._spec.sends_tenant
                else ()
            ),
            encoding=(self._spec.encoding),
        )

    def detail_body(self, values: dict[str, str]) -> dict[str, Any]:
        """Typed identity request: int options carry ints, never strings."""
        unknown = sorted(set(values) - {o.flag for o in self._spec.identity})
        if unknown:
            raise CliError(REQUEST_NOT_ALLOWED, f"unknown identity options: {unknown}")
        body: dict[str, Any] = dict(self._spec.template)
        for option in self._spec.identity:
            raw = values.get(option.flag)
            if raw is None or not raw.strip():
                raise _usage(
                    f"--{option.flag.replace('_', '-')} is required and nonempty",
                )
            if option.choices and raw not in option.choices:
                raise _usage(
                    f"--{option.flag.replace('_', '-')} must be one of "
                    + ", ".join(option.choices)
                )
            if option.virtual:
                continue
            if option.kind == "int":
                if not raw.isdigit():
                    raise _usage(
                        f"--{option.flag.replace('_', '-')} must be an integer",
                    )
                try:
                    body[option.field] = int(raw)
                except ValueError as error:
                    raise _usage(
                        f"--{option.flag.replace('_', '-')} must be an integer",
                    ) from error
            else:
                body[option.field] = raw
        if self._spec.sends_tenant:
            body.setdefault("tntInstId", spec.TENANT)
        return body

    def parse_detail(self, body: bytes, values: dict[str, str]) -> Any:
        """Genuine native detail with typed identity echo validation."""
        request_identity = self.detail_body(values)
        node = envelope_document(body, self._spec.envelope)
        if self._spec.require_inner_success:
            result = node.get("result")
            if not isinstance(result, dict) or result.get("success") is not True:
                raise _invalid("detail result requires boolean success")
        detail = dig(node, self._spec.container)
        if self._spec.container_list:
            if not isinstance(detail, list) or not all(
                isinstance(row, dict) for row in detail
            ):
                raise _invalid("detail payload is not a list of objects")
            echo_field = self._spec.echo_list_field
            if echo_field is not None:
                option = next(
                    (o for o in self._spec.identity if o.echo == echo_field), None
                )
                if option is not None:
                    expected: Any = request_identity[option.field]
                    for row in detail:
                        if row.get(echo_field) != expected:
                            raise _invalid("detail identity does not match the request")
            return detail
        if not isinstance(detail, dict):
            raise _invalid("detail payload is not an object")
        for option in self._spec.identity:
            if option.echo is None:
                continue
            expected = (
                values[option.flag]
                if option.virtual
                else request_identity[option.field]
            )
            actual = (
                dig(detail, option.echo)
                if isinstance(option.echo, tuple)
                else detail.get(option.echo)
            )
            if actual is None or isinstance(actual, (dict, list, bool)):
                raise _invalid("detail identity does not match the request")
            if self._spec.schema_version:
                # Versioned details echo the typed request identity exactly:
                # a native int never satisfies a requested string id.
                if type(actual) is not type(expected) or actual != expected:
                    raise _invalid("detail identity does not match the request")
            elif str(actual) != str(expected):
                raise _invalid("detail identity does not match the request")
        if self._spec.endpoint == "/queryFinancialInstRateRuleDetail.json":
            from .interest_rates import validate_rules

            validate_rules([detail], "FINANCIAL_INST_TYPE")
        if self._spec.name == "liquidity.network.realtime.get":
            if detail.get("tntInstId") not in (None, "", spec.TENANT):
                raise _invalid("network detail tenant contradicts requested source")
            if {"operationHistory", "routeDetails"}.intersection(detail):
                raise _invalid(
                    "native network payload collides with reserved association fields"
                )
        if self._spec.projection == "route_quota_detail":
            from .qualified_getters import validate_quota_context

            validate_quota_context(detail, request_identity)
        if self._spec.projection:
            return project_record(self._spec.projection, detail)
        return detail
