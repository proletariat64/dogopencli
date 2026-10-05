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
from .. import EndpointContract
from . import spec
from .envelope import dig, envelope_document
from .projection import project_record


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
    for part in scope.split(";"):
        field, separator, raw = part.partition("=")
        if not separator or not field:
            raise _usage(f"malformed scope: {scope}")
        try:
            values[field] = json.loads(raw)
        except ValueError as error:
            raise _usage(f"malformed scope: {scope}") from error
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
        raw = provided.get(option.flag)
        if raw is None or raw == []:
            if option.required:
                raise _usage(f"--{option.flag.replace('_', '-')} is required")
            if option.default is not None:
                raw = option.default
            else:
                continue
        if option.repeat:
            items = list(raw) if isinstance(raw, list) else [raw]
            if not items or any(not str(item).strip() for item in items):
                raise _usage(
                    f"--{option.flag.replace('_', '-')} must be nonempty",
                )
            value: Any = [str(item) for item in items]
        else:
            if isinstance(raw, list):
                raise _usage(
                    f"--{option.flag.replace('_', '-')} accepts a single value",
                )
            text = str(raw)
            if not text.strip():
                raise _usage(
                    f"--{option.flag.replace('_', '-')} must be nonempty",
                )
            if option.date:
                try:
                    if len(text) != 8 or not text.isascii() or not text.isdigit():
                        raise ValueError
                    datetime.strptime(text, "%Y%m%d")
                except ValueError as error:
                    raise _usage(
                        f"--{option.flag.replace('_', '-')} must be a valid YYYYMMDD",
                    ) from error
            if option.time:
                try:
                    if len(text) != 6 or not text.isascii() or not text.isdigit():
                        raise ValueError
                    datetime.strptime(text, "%H%M%S")
                except ValueError as error:
                    raise _usage(
                        f"--{option.flag.replace('_', '-')} must be a valid HHmmss",
                    ) from error
            value = [text] if option.list_of_one else text
        if option.choices:
            values = value if isinstance(value, list) else [value]
            invalid = [item for item in values if item not in option.choices]
            if invalid:
                raise _usage(
                    f"--{option.flag.replace('_', '-')} must be one of"
                    f" {', '.join(option.choices)}",
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
        )

    def page_body(
        self, scope: str, row_start: int, page_size: int | None = None
    ) -> dict[str, Any]:
        """One verified request body for the offset starting at row_start."""
        values = decode_scope(scope)
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
        return body

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int | None]:
        """Envelope, record container and reported total of one response."""
        node = envelope_document(body, self._spec.envelope)
        if self._spec.require_inner_success:
            inner_success = dig(node, ("result", "success"))
            if not isinstance(inner_success, bool) or not inner_success:
                raise _invalid("inner result success marker is not true")
        rows = dig(node, self._spec.container)
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
        seen_raw: dict[tuple[str, ...], str] = {}
        for row in rows:
            identity = self.identity_key(row)
            if self._spec.projection == "transfer_rules":
                content = canonical(row)
                if identity in seen_raw and seen_raw[identity] != content:
                    raise _invalid("conflicting content for transfer rule identity")
                seen_raw[identity] = content
        if self._spec.projection:
            rows = [project_record(self._spec.projection, row) for row in rows]
        return list(rows), total

    def validate_rows_scope(self, rows: list[dict[str, Any]], scope: str) -> None:
        """Reject unverified dates before live output or complete publication."""
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
        if not (self._spec.schema_version and self._spec.profile == spec.PROFILE_DATED):
            return
        # Use the retention reader's native series parser so acquisition and
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
            + (("tntInstId", spec.TENANT),)
            if self._spec.schema_version and self._spec.sends_tenant
            else (),
            encoding=(
                spec.ENC_FORM if self._spec.encoding == spec.ENC_FORM else spec.ENC_JSON
            ),
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
            actual = detail.get(option.echo)
            if actual is None or isinstance(actual, (dict, list, bool)):
                raise _invalid("detail identity does not match the request")
            if self._spec.schema_version:
                # Versioned details echo the typed request identity exactly:
                # a native int never satisfies a requested string id.
                if type(actual) is not type(expected) or actual != expected:
                    raise _invalid("detail identity does not match the request")
            elif str(actual) != str(expected):
                raise _invalid("detail identity does not match the request")
        if self._spec.projection:
            return project_record(self._spec.projection, detail)
        return detail
