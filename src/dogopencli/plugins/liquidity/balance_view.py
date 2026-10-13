"""Readable, statement-aware output views without changing native evidence."""

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from dogopencli.errors import INVALID_RESPONSE, CliError

_AMOUNT_FIELDS = (
    "curBalance",
    "avlBalance",
    "openBalance",
    "openAvlBalance",
    "avlBalanceAfterAdj",
    "openAvlBalanceAfterAdj",
    "equvCurBalance",
    "equvAvlBalance",
    "equvOpenBalance",
    "equvOpenAvlBalance",
)
_NESTED_AMOUNTS = {
    "leastDaytimeBalVo": ("instradayBalance", "instradayAvlBalance"),
    "leastDayendBalVo": (
        "openBalance",
        "openAvlBalance",
        "closeBalance",
        "closeAvlBalance",
    ),
}


def _timestamp(value: Any) -> Decimal | None:
    if not isinstance(value, str) or not any(mark in value for mark in ("T", " ")):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        offset = parsed.utcoffset()
        seconds = (
            Decimal(
                parsed.toordinal() * 86400
                + parsed.hour * 3600
                + parsed.minute * 60
                + parsed.second
            )
            + Decimal(parsed.microsecond) / 1000000
        )
        if offset is not None:
            seconds -= Decimal(str(offset.total_seconds()))
        return seconds
    except (ValueError, OverflowError):
        return None


def _business_day(record: dict) -> date | None:
    intraday = record.get("leastDaytimeBalVo")
    value = intraday.get("valueDate") if isinstance(intraday, dict) else None
    if isinstance(value, str):
        try:
            if len(value) == 8 and value.isdigit():
                return date(int(value[:4]), int(value[4:6]), int(value[6:]))
            if len(value) == 10:
                return date.fromisoformat(value)
        except ValueError:
            pass
    value = record.get("statementCreateTime")
    if isinstance(value, str) and _timestamp(value) is not None:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    return None


def _amount(record: dict, field: str) -> Any:
    if field not in record:
        return ("absent",)
    value = record[field]
    if value is None:
        return ("null",)
    if value == "":
        return ("empty",)
    try:
        number = Decimal(str(value).replace(",", ""))
        if number.is_finite():
            return ("number", number)
    except InvalidOperation:
        pass
    return ("raw", type(value).__name__, repr(value))


def _financial_values(record: dict) -> tuple:
    values = [_amount(record, field) for field in _AMOUNT_FIELDS]
    for container, fields in _NESTED_AMOUNTS.items():
        nested = record.get(container)
        if isinstance(nested, dict):
            values.extend(_amount(nested, field) for field in fields)
        elif container not in record:
            values.extend(("absent",) for _ in fields)
        else:
            values.extend(("null",) for _ in fields)
    return tuple(values)


def latest_statement_rows(records: list[dict]) -> tuple[list[dict], int]:
    """Keep the latest statement per account/business day in the output only.

    Changed financial values generate a count, not an acquisition failure.
    Unknown business days remain separate. Multi-row groups need an explicit,
    parseable primary timestamp so ordering never invents authoritative times.
    """
    groups: dict[tuple, list[dict]] = {}
    for index, record in enumerate(records):
        for field in ("entity", "aliasName", "currency"):
            value = record.get(field)
            if not isinstance(value, str) or not value.strip():
                raise CliError(
                    INVALID_RESPONSE,
                    f"Balance account attribute {field} must be a nonempty string.",
                )
        day = _business_day(record)
        key = (
            (record.get("entity"), record.get("aliasName"), record.get("currency"), day)
            if day is not None
            else ("unknown-day", index)
        )
        groups.setdefault(key, []).append(record)
    winners = []
    changed = 0
    for group in groups.values():
        if len(group) == 1:
            winners.append(group[0])
            continue
        ranked = []
        for record in group:
            primary = _timestamp(record.get("statementCreateTime"))
            if primary is None:
                raise CliError(
                    INVALID_RESPONSE,
                    "Balance statement ordering requires a valid statement timestamp.",
                )
            intraday = record.get("leastDaytimeBalVo")
            secondary = (
                _timestamp(intraday.get("updateTime"))
                if isinstance(intraday, dict)
                else None
            )
            record_id = json.dumps(
                record.get("balId"), sort_keys=True, ensure_ascii=True
            )
            ranked.append(
                (
                    (
                        primary,
                        secondary is not None,
                        secondary or Decimal(0),
                        record_id,
                    ),
                    record,
                )
            )
        winners.append(max(ranked, key=lambda item: item[0])[1])
        first = _financial_values(group[0])
        changed += any(_financial_values(record) != first for record in group[1:])
    return winners, changed


_FIELD_NAMES = {
    "balId": "balance_record_id",
    "entity": "account_holder_entity_id",
    "aliasName": "account_alias",
    "accountNo": "account_number",
    "accountNumbers": "account_numbers",
    "accountType": "account_type",
    "bankId": "bank_id",
    "companyName": "company_name",
    "currency": "currency",
    "curBalance": "current_balance",
    "avlBalance": "current_available_balance",
    "openBalance": "opening_balance",
    "openAvlBalance": "opening_available_balance",
    "avlBalanceAfterAdj": "current_available_balance_after_adjustment",
    "openAvlBalanceAfterAdj": "opening_available_balance_after_adjustment",
    "avlBalanceSwitch": "available_balance_switch",
    "openAvlBalanceSwitch": "opening_available_balance_switch",
    "equvCurrency": "equivalent_currency",
    "equvCurBalance": "equivalent_current_balance",
    "equvAvlBalance": "equivalent_current_available_balance",
    "equvOpenBalance": "equivalent_opening_balance",
    "equvOpenAvlBalance": "equivalent_opening_available_balance",
    "statementCreateTime": "statement_created_at",
    "timeZone": "time_zone",
    "leastDaytimeBalVo": "intraday_balance",
    "leastDayendBalVo": "end_of_day_balance",
    "bizTag": "business_tag",
    "fundAttribute1": "fund_attribute_1",
    "digitalCurrency": "digital_currency",
    "blockChainAccountType": "blockchain_account_type",
    "colorType": "color_type",
}
_NESTED_NAMES = {
    **_FIELD_NAMES,
    "instradayBalance": "current_balance",
    "instradayAvlBalance": "current_available_balance",
    "closeBalance": "closing_balance",
    "closeAvlBalance": "closing_available_balance",
    "valueDate": "value_date",
    "updateTime": "updated_at",
    "source": "source",
}
_DAILY_NAMES = {
    **_FIELD_NAMES,
    "id": "source_id",
    "data": "account_alias",
    "statisticalDate": "statistical_date",
    "balance": "balance",
}


def export_field_name(native_field: str, *, daily: bool = False) -> str:
    """Map known native field paths; leave unexplained names unchanged."""
    names = _DAILY_NAMES if daily else _FIELD_NAMES
    first, separator, rest = native_field.partition(".")
    exported = names.get(first, first)
    if separator:
        nested = _NESTED_NAMES.get(rest, rest) if first in _NESTED_AMOUNTS else rest
        return f"{exported}.{nested}"
    return exported


def export_balance_record(record: dict, *, daily: bool = False) -> dict:
    """Rename output fields only, preserving native values and unknown keys."""
    exported = {}
    for field, value in record.items():
        if daily and field == "data" and "aliasName" in record:
            continue
        if field in _NESTED_AMOUNTS and isinstance(value, dict):
            value = {_NESTED_NAMES.get(key, key): item for key, item in value.items()}
        exported[export_field_name(field, daily=daily)] = value
    return exported


def update_notice(changed_groups: int) -> dict | None:
    """Return a data-free informational notice, not an incomplete-result warning."""
    if changed_groups <= 0:
        return None
    return {
        "code": "BANK_STATEMENT_UPDATED",
        "level": "info",
        "message": (
            "Normal bank statement update/adjustment; "
            "the latest statement is authoritative."
        ),
        "account_day_groups": changed_groups,
    }
