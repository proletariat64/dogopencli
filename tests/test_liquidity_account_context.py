"""Account context resolution boundary; CLI wiring is covered by integration."""

import pytest

from dogopencli.duckdog import AccountSourceUnavailable
from dogopencli.errors import AUTH_REQUIRED, CONFIG_ERROR, CliError
from dogopencli.plugins.liquidity.account_context import resolve_account_context


def test_explicit_ownership_never_reads_account_sources():
    def forbidden():
        raise AssertionError("unexpected account directory access")

    result = resolve_account_context(
        "A",
        "ENTITY",
        "BANK",
        duckdog_accounts=forbidden,
        cached_accounts=forbidden,
        live_accounts=forbidden,
    )
    assert (result.alias, result.entity, result.bank) == ("A", "ENTITY", "BANK")
    assert result.metadata["source"] == "explicit"


def test_first_source_first_match_preserves_explicit_constraints_and_warns():
    def forbidden():
        raise AssertionError("lower priority source accessed")

    result = resolve_account_context(
        "A",
        bank="B",
        cached_accounts=forbidden,
        live_accounts=forbidden,
        duckdog_accounts=lambda: [
            {"aliasName": "A", "instId": "WRONG", "bankId": "OTHER"},
            {"aliasName": "A", "instId": "SECOND", "bankId": "B"},
            {"aliasName": "A", "instId": "FIRST", "bankId": "B"},
        ],
    )
    assert (result.entity, result.bank) == ("SECOND", "B")
    warning = result.metadata["warnings"][0]
    assert warning["source"] == "duckdog"
    assert warning["match_count"] == 2
    assert warning["selected"] == {"aliasName": "A", "instId": "SECOND", "bankId": "B"}


@pytest.mark.parametrize(
    "alias,entity,bank",
    [("ANY", "E", "B"), ("A,B", "E", "B"), (" ", "E", "B"), ("A", " ", "B")],
)
def test_invalid_inputs_fail_before_any_source(alias, entity, bank):
    def forbidden():
        raise AssertionError("source read before validation")

    with pytest.raises(CliError) as caught:
        resolve_account_context(
            alias,
            entity,
            bank,
            cached_accounts=forbidden,
            live_accounts=forbidden,
            duckdog_accounts=forbidden,
        )
    assert caught.value.code == "INVALID_ARGUMENT"


def test_incomplete_first_match_falls_back_whole_record_without_cross_fill():
    result = resolve_account_context(
        "A",
        duckdog_accounts=lambda: [
            {"aliasName": "A", "instId": "E1"},
            {"aliasName": "A", "instId": "E2", "bankId": "B2"},
        ],
        cached_accounts=lambda: [{"aliasName": "A", "bankId": "CACHE"}],
        live_accounts=lambda: [{"aliasName": "A", "instId": "E3", "bankId": "B3"}],
    )
    assert (result.entity, result.bank) == ("E3", "B3")
    assert [item["status"] for item in result.metadata["sources"]] == [
        "missing_fields",
        "missing_fields",
        "selected",
    ]
    assert result.metadata["warnings"][0]["match_count"] == 2


def test_optional_source_unavailability_falls_back_but_storage_errors_propagate():
    def absent():
        raise AccountSourceUnavailable("not configured")

    def broken():
        raise CliError(CONFIG_ERROR, "database corrupt")

    result = resolve_account_context(
        "A",
        entity="E",
        duckdog_accounts=absent,
        cached_accounts=absent,
        live_accounts=lambda: [{"aliasName": "A", "instId": "E", "bankId": "B"}],
    )
    assert result.bank == "B"
    assert result.metadata["sources"][0]["status"] == "unavailable"
    with pytest.raises(CliError, match="database corrupt"):
        resolve_account_context(
            "A", duckdog_accounts=broken, cached_accounts=absent, live_accounts=absent
        )


def test_live_failure_preserves_auth_category_and_guides_recovery():
    def auth_failure():
        raise CliError(AUTH_REQUIRED, "session expired", retryable=True)

    with pytest.raises(CliError, match="dogopencli login --domain liquidity") as caught:
        resolve_account_context(
            "A",
            duckdog_accounts=lambda: [],
            cached_accounts=lambda: [],
            live_accounts=auth_failure,
        )
    assert caught.value.code == AUTH_REQUIRED
    assert caught.value.retryable


def test_unresolved_constraints_do_not_use_default_or_other_accounts():
    with pytest.raises(CliError) as caught:
        resolve_account_context(
            "A",
            bank="B",
            duckdog_accounts=lambda: [],
            cached_accounts=lambda: [],
            live_accounts=lambda: [
                {"aliasName": "OTHER", "instId": "Z21", "bankId": "B"},
                {"aliasName": "A", "instId": "Z21", "bankId": "OTHER"},
            ],
        )
    assert caught.value.code == "SOURCE_DATA_MISSING"


def test_missing_cache_slot_falls_back_without_using_display_codes():
    def no_cache():
        raise CliError("CACHE_MISS", "cash accounts slot absent")

    result = resolve_account_context(
        "A",
        duckdog_accounts=lambda: [
            {"aliasName": "A", "instCode": "Z21", "id": "10", "bankId": "B"}
        ],
        cached_accounts=no_cache,
        live_accounts=lambda: [
            {"aliasName": "A", "instId": "ENTITY", "bankId": "BANK"}
        ],
    )
    assert (result.entity, result.bank) == ("ENTITY", "BANK")
    assert result.metadata["sources"][1]["status"] == "unavailable"
