"""Pure output views preserve native balance evidence."""

from copy import deepcopy

import pytest

from dogopencli.errors import INVALID_RESPONSE, CliError
from dogopencli.plugins.liquidity.balance_view import (
    export_balance_record,
    export_field_name,
    latest_statement_rows,
    update_notice,
)


def row(record_id="old", /, **changes):
    value = {
        "balId": record_id,
        "entity": "holder",
        "aliasName": "account",
        "currency": "USD",
        "statementCreateTime": "2026-10-12 09:00:00",
        "curBalance": "10",
        "leastDaytimeBalVo": {"valueDate": "20261012"},
    }
    value.update(changes)
    return value


def test_equal_amounts_keep_latest_without_mutating_native_records():
    old = row()
    new = row("new", statementCreateTime="2026-10-12T10:00:00", curBalance="10.00")
    records = [new, old]
    original = deepcopy(records)
    winners, changed = latest_statement_rows(records)
    assert winners == [new]
    assert winners[0] is new
    assert changed == 0
    assert records == original
    assert latest_statement_rows(list(reversed(records))) == ([new], 0)


def test_readable_nested_export_preserves_values_and_unknown_fields():
    native = row(
        leastDaytimeBalVo={
            "instradayBalance": "10.00",
            "valueDate": "20261012",
            "updateTime": None,
            "unexplained": "kept",
        },
        leastDayendBalVo=None,
        accountNo="",
        undocumented={"rawKey": 1},
    )
    original = deepcopy(native)
    exported = export_balance_record(native)
    assert exported["balance_record_id"] == "old"
    assert exported["account_holder_entity_id"] == "holder"
    assert exported["account_alias"] == "account"
    assert exported["intraday_balance"] == {
        "current_balance": "10.00",
        "value_date": "20261012",
        "updated_at": None,
        "unexplained": "kept",
    }
    assert exported["end_of_day_balance"] is None
    assert exported["account_number"] == ""
    assert exported["undocumented"] == {"rawKey": 1}
    assert "opening_balance" not in exported
    assert native == original
    assert export_field_name("leastDaytimeBalVo.instradayAvlBalance") == (
        "intraday_balance.current_available_balance"
    )


def test_daily_export_uses_authoritative_alias_and_native_balance_meaning():
    exported = export_balance_record(
        {
            "id": "source",
            "data": "old-alias",
            "aliasName": "authoritative",
            "entity": "holder",
            "currency": "USD",
            "balance": "12.00",
            "statisticalDate": "0001-01-01",
        },
        daily=True,
    )
    assert exported == {
        "source_id": "source",
        "account_alias": "authoritative",
        "account_holder_entity_id": "holder",
        "currency": "USD",
        "balance": "12.00",
        "statistical_date": "0001-01-01",
    }
    assert export_balance_record({"data": None}, daily=True) == {"account_alias": None}
    assert export_field_name("id", daily=True) == "source_id"
    assert export_field_name("unexplained") == "unexplained"


def test_update_notice_is_informational_and_contains_no_business_data():
    assert update_notice(0) is None
    assert update_notice(2) == {
        "code": "BANK_STATEMENT_UPDATED",
        "level": "info",
        "message": (
            "Normal bank statement update/adjustment; "
            "the latest statement is authoritative."
        ),
        "account_day_groups": 2,
    }


@pytest.mark.parametrize(
    "field",
    [
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
    ],
)
def test_every_outer_amount_change_counts_once_per_group(field):
    old = row(**{field: "10"})
    new = row("new", **{field: "11"}, statementCreateTime="2026-10-12T10:00:00")
    newest = dict(new, balId="newest", statementCreateTime="2026-10-12T11:00:00")
    assert latest_statement_rows([newest, old, new]) == ([newest], 1)


@pytest.mark.parametrize(
    "nested,field",
    [
        ("leastDaytimeBalVo", "instradayBalance"),
        ("leastDaytimeBalVo", "instradayAvlBalance"),
        ("leastDayendBalVo", "openBalance"),
        ("leastDayendBalVo", "openAvlBalance"),
        ("leastDayendBalVo", "closeBalance"),
        ("leastDayendBalVo", "closeAvlBalance"),
    ],
)
def test_every_nested_amount_participates_in_change_detection(nested, field):
    old = row(**{nested: {field: "10", "valueDate": "20261012"}})
    new = row(
        "new",
        **{nested: {field: "11", "valueDate": "20261012"}},
        statementCreateTime="2026-10-12T10:00:00",
    )
    assert latest_statement_rows([old, new]) == ([new], 1)
    equal = row(
        "equal",
        **{nested: {field: "10.00", "valueDate": "20261012"}},
        statementCreateTime="2026-10-12T10:00:00",
    )
    assert latest_statement_rows([equal, old]) == ([equal], 0)


@pytest.mark.parametrize("first,second", [(None, ""), (None, "10"), ("", "10")])
def test_null_empty_and_absent_amounts_are_distinct(first, second):
    old = row(avlBalance=first)
    new = row("new", avlBalance=second, statementCreateTime="2026-10-12T10:00:00")
    assert latest_statement_rows([old, new]) == ([new], 1)
    absent = row()
    assert latest_statement_rows([absent, old])[1] == 1


def test_nonfinancial_changes_are_silent():
    old = row()
    new = row(
        "new",
        companyName="different",
        bankId="changed",
        leastDaytimeBalVo={"valueDate": "2026-10-12", "source": "new"},
        statementCreateTime="2026-10-12T10:00:00",
    )
    assert latest_statement_rows([new, old]) == ([new], 0)


def test_distinct_accounts_currencies_and_business_days_remain_separate():
    records = [
        row(),
        row("holder2", entity="other"),
        row("account2", aliasName="other"),
        row("eur", currency="EUR"),
        row("day2", leastDaytimeBalVo={"valueDate": "20261013"}),
    ]
    assert latest_statement_rows(records) == (records, 0)


def test_secondary_timestamp_and_canonical_id_break_ties_in_both_orders():
    old = row(
        "z",
        leastDaytimeBalVo={
            "valueDate": "20261012",
            "updateTime": "2026-10-12T10:00:00",
        },
    )
    new = row(
        "a",
        leastDaytimeBalVo={
            "valueDate": "20261012",
            "updateTime": "2026-10-12T11:00:00",
        },
    )
    assert latest_statement_rows([old, new]) == ([new], 0)
    assert latest_statement_rows([new, old]) == ([new], 0)
    tied = dict(new, balId="z")
    assert latest_statement_rows([new, tied]) == ([tied], 0)
    assert latest_statement_rows([tied, new]) == ([tied], 0)


def test_unknown_business_days_preserve_rows_without_fabricated_timestamps():
    records = [
        row(statementCreateTime=None, leastDaytimeBalVo={"valueDate": "bad"}),
        row("new", statementCreateTime="bad", leastDaytimeBalVo=None),
    ]
    assert latest_statement_rows(records) == (records, 0)


@pytest.mark.parametrize("invalid", [None, "", "bad-private-value", "2026-10-12"])
def test_invalid_primary_in_known_multiple_row_group_has_sanitized_error(invalid):
    with pytest.raises(CliError) as caught:
        latest_statement_rows([row(statementCreateTime=invalid), row("new")])
    assert caught.value.code == INVALID_RESPONSE
    assert caught.value.message == (
        "Balance statement ordering requires a valid statement timestamp."
    )
    assert caught.value.meta is None


@pytest.mark.parametrize("day", ["0001-01-01", "0999-12-31", "9999-12-31"])
def test_early_and_maximum_years_keep_latest_without_date_arithmetic(day):
    old = row(
        statementCreateTime=f"{day}T09:00:00",
        leastDaytimeBalVo={"valueDate": day.replace("-", "")},
    )
    new = row(
        "new",
        statementCreateTime=f"{day} 10:00:00",
        leastDaytimeBalVo={"valueDate": day},
    )
    assert latest_statement_rows([new, old]) == ([new], 0)


def test_invalid_business_date_falls_back_to_outer_statement_day():
    old = row(leastDaytimeBalVo={"valueDate": "not-a-day"})
    new = row("new", leastDaytimeBalVo={}, statementCreateTime="2026-10-12T10:00:00")
    assert latest_statement_rows([new, old]) == ([new], 0)
    separate = row(
        "next", leastDaytimeBalVo={}, statementCreateTime="2026-10-13T10:00:00"
    )
    assert latest_statement_rows([old, separate]) == ([old, separate], 0)


def test_offsets_order_actual_statement_instants_without_overflow():
    old = row(statementCreateTime="0001-01-01T00:00:00+02:00")
    new = row("new", statementCreateTime="0001-01-01T00:00:00+01:00")
    assert latest_statement_rows([old, new]) == ([new], 0)


def test_daily_alias_presence_including_null_is_authoritative():
    assert export_balance_record(
        {"data": "fallback", "aliasName": None}, daily=True
    ) == {
        "account_alias": None,
    }


def test_empty_nested_object_does_not_warn_for_nonfinancial_structure_only():
    old = row()
    new = row("new", leastDayendBalVo={}, statementCreateTime="2026-10-12T10:00:00")
    assert latest_statement_rows([old, new]) == ([new], 0)


def test_utc_suffix_and_missing_value_date_use_statement_day():
    old = row(statementCreateTime="0001-01-01T09:00:00Z", leastDaytimeBalVo={})
    new = row("new", statementCreateTime="0001-01-01T10:00:00Z", leastDaytimeBalVo={})
    assert latest_statement_rows([new, old]) == ([new], 0)


def test_single_known_day_does_not_need_ordering_timestamp():
    native = row(statementCreateTime="invalid")
    assert latest_statement_rows([native]) == ([native], 0)


def test_different_changed_account_day_groups_have_separate_notice_count():
    first = row()
    second = row("b", currency="EUR")
    first_new = row("a-new", curBalance="11", statementCreateTime="2026-10-12T10:00:00")
    second_new = row(
        "b-new",
        currency="EUR",
        curBalance="12",
        statementCreateTime="2026-10-12T11:00:00",
    )
    assert latest_statement_rows([first, second, first_new, second_new]) == (
        [first_new, second_new],
        2,
    )


@pytest.mark.parametrize(
    "native,exported",
    [
        ("balId", "balance_record_id"),
        ("entity", "account_holder_entity_id"),
        ("aliasName", "account_alias"),
        ("accountNo", "account_number"),
        ("accountNumbers", "account_numbers"),
        ("accountType", "account_type"),
        ("bankId", "bank_id"),
        ("companyName", "company_name"),
        ("currency", "currency"),
        ("curBalance", "current_balance"),
        ("avlBalance", "current_available_balance"),
        ("openBalance", "opening_balance"),
        ("openAvlBalance", "opening_available_balance"),
        ("avlBalanceAfterAdj", "current_available_balance_after_adjustment"),
        ("openAvlBalanceAfterAdj", "opening_available_balance_after_adjustment"),
        ("avlBalanceSwitch", "available_balance_switch"),
        ("openAvlBalanceSwitch", "opening_available_balance_switch"),
        ("equvCurrency", "equivalent_currency"),
        ("equvCurBalance", "equivalent_current_balance"),
        ("equvAvlBalance", "equivalent_current_available_balance"),
        ("equvOpenBalance", "equivalent_opening_balance"),
        ("equvOpenAvlBalance", "equivalent_opening_available_balance"),
        ("statementCreateTime", "statement_created_at"),
        ("timeZone", "time_zone"),
        ("bizTag", "business_tag"),
        ("fundAttribute1", "fund_attribute_1"),
        ("digitalCurrency", "digital_currency"),
        ("blockChainAccountType", "blockchain_account_type"),
        ("colorType", "color_type"),
    ],
)
def test_all_core_export_names_match_readable_contract(native, exported):
    assert export_balance_record({native: None}) == {exported: None}
    assert export_field_name(native) == exported


def test_full_end_of_day_export_uses_balance_and_statement_time_names():
    native = {
        "leastDayendBalVo": {
            "entity": "holder",
            "aliasName": "account",
            "currency": "USD",
            "accountNo": "number",
            "bankId": "bank",
            "openBalance": "1",
            "openAvlBalance": "2",
            "closeBalance": "3",
            "closeAvlBalance": "4",
            "statementCreateTime": "created",
            "updateTime": "updated",
            "valueDate": "day",
            "timeZone": "zone",
            "source": "bank",
        }
    }
    assert export_balance_record(native) == {
        "end_of_day_balance": {
            "account_holder_entity_id": "holder",
            "account_alias": "account",
            "currency": "USD",
            "account_number": "number",
            "bank_id": "bank",
            "opening_balance": "1",
            "opening_available_balance": "2",
            "closing_balance": "3",
            "closing_available_balance": "4",
            "statement_created_at": "created",
            "updated_at": "updated",
            "value_date": "day",
            "time_zone": "zone",
            "source": "bank",
        }
    }
    assert export_field_name("leastDayendBalVo.closeAvlBalance") == (
        "end_of_day_balance.closing_available_balance"
    )
    assert export_field_name("unknown.nativeKey") == "unknown.nativeKey"
