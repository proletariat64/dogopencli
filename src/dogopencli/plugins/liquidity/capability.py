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
            if option.date and (len(text) != 8 or not text.isdigit()):
                raise _usage(
                    f"--{option.flag.replace('_', '-')} must be YYYYMMDD",
                )
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
    return fields, (window_from, window_to)


class LiquidityListCapability:
    """List inquiry: verified request construction and response parsing."""

    def __init__(self, list_spec: spec.ListSpec) -> None:
        self._spec = list_spec
        body_keys = set(list_spec.template)
        if list_spec.paged_request:
            body_keys |= {"rowStart", "pageSize"}
        if list_spec.vo_field is not None:
            body_keys |= {list_spec.vo_field}
        for option in list_spec.scope_options:
            if not option.virtual:
                body_keys.add(option.field)
        self._body_keys = frozenset(body_keys)

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
            page_size=spec.PAGE_SIZE,
            one_based=False,
            allowed_body_keys=self._body_keys,
            encoding=(
                spec.ENC_FORM if self._spec.encoding == spec.ENC_FORM else spec.ENC_JSON
            ),
        )

    def page_body(
        self, scope: str, row_start: int, page_size: int = spec.PAGE_SIZE
    ) -> dict[str, Any]:
        """One verified request body for the offset starting at row_start."""
        values = decode_scope(scope)
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
        return body

    def parse_rows(self, body: bytes) -> tuple[list[dict[str, Any]], int | None]:
        """Envelope, record container and reported total of one response."""
        node = envelope_document(body, self._spec.envelope)
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
        for row in rows:
            self.identity_key(row)
        return list(rows), total

    def identity_key(self, record: dict[str, Any]) -> tuple[str, ...]:
        """Typed identity: every declared field must be present and atomic."""
        key: list[str] = []
        for field in self._spec.identity:
            value = record.get(field)
            if value is None or isinstance(value, (dict, list)):
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
                | {option.field for option in self._spec.identity}
            ),
            encoding=(
                spec.ENC_FORM if self._spec.encoding == spec.ENC_FORM else spec.ENC_JSON
            ),
        )

    def detail_body(self, values: dict[str, str]) -> dict[str, Any]:
        """Typed identity request: int options carry ints, never strings."""
        unknown = sorted(set(values) - {o.flag for o in self._spec.identity})
        if unknown:
            raise CliError(REQUEST_NOT_ALLOWED, f"unknown identity options: {unknown}")
        body: dict[str, Any] = {}
        for option in self._spec.identity:
            raw = values.get(option.flag)
            if raw is None or not raw.strip():
                raise _usage(
                    f"--{option.flag.replace('_', '-')} is required and nonempty",
                )
            if option.kind == "int":
                if not raw.isdigit():
                    raise _usage(
                        f"--{option.flag.replace('_', '-')} must be an integer",
                    )
                body[option.field] = int(raw)
            else:
                body[option.field] = raw
        if self._spec.sends_tenant:
            body.setdefault("tntInstId", spec.TENANT)
        return body

    def parse_detail(self, body: bytes, values: dict[str, str]) -> Any:
        """Genuine native detail with typed identity echo validation."""
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
                    expected: Any = values[option.flag]
                    if option.kind == "int":
                        expected = int(expected)
                    for row in detail:
                        if row.get(echo_field) != expected:
                            raise _invalid("detail identity does not match the request")
            return detail
        if not isinstance(detail, dict):
            raise _invalid("detail payload is not an object")
        for option in self._spec.identity:
            if option.echo is None:
                continue
            expected = values[option.flag]
            if option.kind == "int":
                expected = str(int(expected))
            actual = detail.get(option.echo)
            if actual is not None and str(actual) != str(expected):
                raise _invalid("detail identity does not match the request")
        return detail
