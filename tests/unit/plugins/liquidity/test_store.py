"""Capture store and the 1,000,000-record retention policy (ADR 0017)."""

import sqlite3
from dataclasses import replace

import pytest

from dogopencli.cache import Cache
from dogopencli.errors import INVALID_ARGUMENT, CliError
from dogopencli.plugins.liquidity import details as detail_store
from dogopencli.plugins.liquidity import spec as spec_mod
from dogopencli.plugins.liquidity import store as capture_store
from dogopencli.plugins.liquidity.leaves import (
    CASH_ACCOUNTS,
    CASH_STATEMENTS_INTRADAY,
    CASH_WATERLEVELS,
    FORECAST_ADJUSTMENTS,
    FORECAST_CASHFLOWS,
)
from dogopencli.plugins.liquidity.leaves import (
    INVESTMENT_HOLDINGS as NATIVE_HOLDINGS,
)

# These cases exercise the generic dated retention contract. Native holdings
# are query-date-scoped snapshots; their row valueDate is not a coverage axis.
INVESTMENT_HOLDINGS = replace(
    NATIVE_HOLDINGS, profile=spec_mod.PROFILE_DATED, series_field="valueDate"
)

T1 = "2026-10-01T00:00:00+00:00"
T2 = "2026-10-02T00:00:00+00:00"
T3 = "2026-10-03T00:00:00+00:00"


@pytest.mark.parametrize(
    "list_spec",
    [CASH_ACCOUNTS, CASH_WATERLEVELS, CASH_STATEMENTS_INTRADAY, FORECAST_CASHFLOWS],
)
def test_empty_capture_has_a_snapshot_and_retained_coverage(tmp_path, list_spec):
    store = Cache(tmp_path / "cache.sqlite3")
    window = ("20260930", "20260930") if list_spec.profile == "dated" else (None, None)
    for at in [T1, T2]:
        plan = capture_store.plan_capture_publish(
            store, list_spec, "scope", window, [], 0, at, at
        )
        capture_store.commit_plan(store, list_spec.name, plan, at)
    index = capture_store.read_index(store, list_spec.name)
    selected, covered = capture_store.select_captures(index, list_spec, "scope", window)
    assert covered
    assert len(selected) == 1
    assert selected[0].fetched_at == T2
    assert capture_store.read_capture(store, selected[0]) == []
    assert store.current(selected[0].namespace).row_count == 0


def test_capture_rejects_snapshot_count_mismatch(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    plan = capture_store.plan_capture_publish(
        store, CASH_WATERLEVELS, "", (None, None), [], 0, T1, T1
    )
    capture_store.commit_plan(store, CASH_WATERLEVELS.name, plan, T1)
    with sqlite3.connect(tmp_path / "cache.sqlite3") as connection:
        connection.execute(
            "UPDATE snapshots SET row_count=1 WHERE namespace=?",
            (plan.capture_meta.namespace,),
        )
    with pytest.raises(CliError) as rejected:
        capture_store.read_capture(store, plan.index.captures[0])
    assert rejected.value.code == "INVALID_RESPONSE"


def test_cashflow_retention_uses_native_datetime_day(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    rows = [
        {"expectValueDate": "", "expectValueDateTime": "202609292359"},
        {"expectValueDate": "", "expectValueDateTime": "202609300001"},
    ]
    plan = capture_store.plan_capture_publish(
        store, FORECAST_CASHFLOWS, "", ("20260929", "20260930"), rows, 2, T1, T1, cap=1
    )
    capture_store.commit_plan(store, FORECAST_CASHFLOWS.name, plan, T1)
    assert plan.eviction.retained_from == "20260930"
    entry = plan.index.captures[0]
    assert entry.window_from == "20260930"
    assert capture_store.read_capture(store, entry) == rows[1:]
    assert not capture_store.select_captures(
        plan.index, FORECAST_CASHFLOWS, "", ("20260929", "20260930")
    )[1]


@pytest.mark.parametrize("value", ["", "202602301200", "202609302460", "20269301200"])
def test_cashflow_invalid_native_time_rejects_publication(tmp_path, value):
    store = Cache(tmp_path / "cache.sqlite3")
    with pytest.raises(CliError, match="series time"):
        capture_store.plan_capture_publish(
            store,
            FORECAST_CASHFLOWS,
            "",
            ("20260930", "20260930"),
            [{"expectValueDateTime": value}],
            1,
            T1,
            T1,
        )
    assert capture_store.read_index(store, FORECAST_CASHFLOWS.name) is None


def holding(index, day):
    return {"investmentNo": f"H{index:03d}", "valueDate": day, "amount": "1.00"}


def adjustment(index):
    return {"id": index, "aliasName": "A1", "valueDate": "20260930"}


def publish_dated(store, window, rows, fetched_at, cap=spec_mod.RETENTION_CAP):
    plan = capture_store.plan_capture_publish(
        store,
        INVESTMENT_HOLDINGS,
        "",
        window,
        rows,
        len(rows),
        fetched_at,
        fetched_at,
        cap=cap,
    )
    capture_store.commit_plan(store, INVESTMENT_HOLDINGS.name, plan, fetched_at)
    return plan


def test_dated_publish_and_coverage_selection(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    publish_dated(store, ("20260929", "20260929"), [holding(1, "20260929")], T1)
    publish_dated(store, ("20260930", "20260930"), [holding(2, "20260930")], T2)
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    assert index is not None and len(index.captures) == 2
    selected, covered = capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260929", "20260930")
    )
    assert covered and len(selected) == 2
    _, covered = capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260928", "20260930")
    )
    assert not covered


def test_dated_same_window_refresh_replaces_atomically(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    first = publish_dated(store, ("20260929", "20260929"), [holding(1, "20260929")], T1)
    second = publish_dated(
        store, ("20260930", "20260930"), [holding(2, "20260930")], T2
    )
    publish_dated(store, ("20260929", "20260929"), [holding(3, "20260929")], T3)
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    assert index is not None and len(index.captures) == 2
    # The replacement reuses the namespace with the new generation only.
    replaced = store.current(first.capture_meta.namespace)
    assert replaced is not None and replaced.fetched_at == T3
    assert store.current(second.capture_meta.namespace) is not None
    rows = []
    for entry in index.captures:
        rows.extend(capture_store.read_capture(store, entry))
    assert {row["investmentNo"] for row in rows} == {"H002", "H003"}


def test_eviction_trims_the_oldest_capture_with_tie_break(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    day1 = [holding(i, "20260929") for i in range(3)]
    day2 = [holding(i + 10, "20260930") for i in range(3)]
    publish_dated(store, ("20260929", "20260929"), day1, T1, cap=4)
    plan = publish_dated(store, ("20260930", "20260930"), day2, T2, cap=4)
    assert plan.eviction is not None
    assert plan.eviction.dropped == 2
    assert plan.eviction.retained == 4
    # Same-day boundary split: lowest identities evict first.
    assert plan.eviction.retained_from == "20260929"
    assert plan.eviction.tie_break == '"H002"'
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    assert index is not None
    rows = []
    for entry in index.captures:
        rows.extend(capture_store.read_capture(store, entry))
    assert {row["investmentNo"] for row in rows} == {
        "H002",
        "H010",
        "H011",
        "H012",
    }
    # The index keeps the truthful eviction record.
    assert index.evictions and index.evictions[-1]["dropped"] == 2


def test_eviction_drops_whole_oldest_captures(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    first = publish_dated(
        store, ("20260929", "20260929"), [holding(1, "20260929")], T1, cap=2
    )
    publish_dated(store, ("20260930", "20260930"), [holding(2, "20260930")], T2, cap=2)
    plan = publish_dated(
        store, ("20261001", "20261001"), [holding(3, "20261001")], T3, cap=2
    )
    assert plan.eviction is not None and plan.eviction.dropped == 1
    assert store.current(first.capture_meta.namespace) is None
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    assert index is not None
    _, covered = capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260929", "20260929")
    )
    assert not covered  # evicted coverage is missing, never an empty result


def test_unknown_series_ordering_rejects_before_any_write(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    publish_dated(store, ("20260929", "20260929"), [holding(1, "20260929")], T1)
    bad = [{"investmentNo": "H100"}]  # no valueDate: unknown ordering
    with pytest.raises(CliError, match="series time"):
        capture_store.plan_capture_publish(
            store,
            INVESTMENT_HOLDINGS,
            "",
            ("20260930", "20260930"),
            bad,
            1,
            T2,
            T2,
        )
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    assert index is not None and len(index.captures) == 1


def test_history_captures_retain_by_capture_time(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")

    def publish(rows, at, cap=spec_mod.RETENTION_CAP):
        plan = capture_store.plan_capture_publish(
            store,
            FORECAST_ADJUSTMENTS,
            "",
            (None, None),
            rows,
            len(rows),
            at,
            at,
            cap=cap,
        )
        capture_store.commit_plan(store, FORECAST_ADJUSTMENTS.name, plan, at)
        return plan

    publish([adjustment(1), adjustment(2)], T1, cap=3)
    plan = publish([adjustment(3), adjustment(4)], T2, cap=3)
    assert plan.eviction is not None
    assert plan.eviction.dropped == 1
    assert plan.eviction.retained_from == T1  # capture time is the axis
    index = capture_store.read_index(store, FORECAST_ADJUSTMENTS.name)
    assert index is not None and len(index.captures) == 2
    rows = []
    for entry in index.captures:
        rows.extend(capture_store.read_capture(store, entry))
    assert {row["id"] for row in rows} == {2, 3, 4}


def test_snapshot_replaces_scope_and_rejects_overflow(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")

    def publish(rows, at, cap=spec_mod.RETENTION_CAP):
        plan = capture_store.plan_capture_publish(
            store,
            CASH_ACCOUNTS,
            "",
            (None, None),
            rows,
            len(rows),
            at,
            at,
            cap=cap,
        )
        capture_store.commit_plan(store, CASH_ACCOUNTS.name, plan, at)
        return plan

    rows1 = [{"id": "A1", "currency": "USD"}]
    rows2 = [{"id": "A2", "currency": "SGD"}, {"id": "A3", "currency": "USD"}]
    first = publish(rows1, T1)
    publish(rows2, T2)
    index = capture_store.read_index(store, CASH_ACCOUNTS.name)
    assert index is not None and len(index.captures) == 1
    replaced = store.current(first.capture_meta.namespace)
    assert replaced is not None and replaced.fetched_at == T2
    selected, covered = capture_store.select_captures(
        index, CASH_ACCOUNTS, "", (None, None)
    )
    assert covered and len(selected) == 1
    with pytest.raises(CliError) as error:
        capture_store.plan_capture_publish(
            store, CASH_ACCOUNTS, "", (None, None), rows2, 2, T3, T3, cap=1
        )
    assert error.value.code == INVALID_ARGUMENT
    # Rejected overflow preserves the previous valid cache.
    index = capture_store.read_index(store, CASH_ACCOUNTS.name)
    assert index is not None and index.captures[0].row_count == 2


def test_detail_store_upsert_and_cap(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    name = "liquidity.investment.holdings.get"
    detail_store.upsert_detail(
        store, name, "investment_no=H1", {"orderId": "H1"}, T1, T1
    )
    snapshot = detail_store.upsert_detail(
        store, name, "investment_no=H2", {"orderId": "H2"}, T2, T2
    )
    stored = detail_store.read_details(store, name)
    assert set(stored) == {"investment_no=H1", "investment_no=H2"}
    assert stored["investment_no=H1"].fetched_at == T1
    assert snapshot.row_count == 2
    with pytest.raises(CliError) as error:
        detail_store.upsert_detail(
            store, name, "investment_no=H3", {"orderId": "H3"}, T3, T3, cap=2
        )
    assert error.value.code == INVALID_ARGUMENT
    # An upsert of an existing key under the cap still succeeds.
    detail_store.upsert_detail(
        store, name, "investment_no=H1", {"orderId": "H1+"}, T3, T3, cap=2
    )
    assert detail_store.read_details(store, name)["investment_no=H1"].detail == {
        "orderId": "H1+"
    }


def test_snapshot_cap_counts_all_scopes_and_preserves_cache(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    rows = [{"accountNo": "A"}, {"accountNo": "B"}]
    plan = capture_store.plan_capture_publish(
        store, CASH_ACCOUNTS, "scope-a", (None, None), rows, 2, T1, T1, cap=3
    )
    capture_store.commit_plan(store, CASH_ACCOUNTS.name, plan, T1)
    before = capture_store.read_index(store, CASH_ACCOUNTS.name)
    with pytest.raises(CliError, match="across scopes"):
        capture_store.plan_capture_publish(
            store, CASH_ACCOUNTS, "scope-b", (None, None), rows, 2, T2, T2, cap=3
        )
    assert capture_store.read_index(store, CASH_ACCOUNTS.name) == before
    # Same-scope replacement does not double-count the prior generation.
    capture_store.plan_capture_publish(
        store, CASH_ACCOUNTS, "scope-a", (None, None), rows, 2, T2, T2, cap=3
    )


@pytest.mark.parametrize("first_basis", ["accrual", "cash"])
def test_retention_splits_capture_with_its_own_return_variant(tmp_path, first_basis):
    from dogopencli.plugins.liquidity.leaves import list_leaf

    cache = Cache(tmp_path / "cache.sqlite3")
    leaf = list_leaf(("investment", "returns"))
    second_basis = "cash" if first_basis == "accrual" else "accrual"
    for basis, day, fetched in (
        (first_basis, "20260929", T1),
        (second_basis, "20260930", T2),
    ):
        resolved = leaf.resolve({"basis": basis, "from_date": day, "to_date": day})
        rows = (
            [{"investmentNo": f"H{i}", "transactionDate": day} for i in range(2)]
            if basis == "accrual"
            else [{"transactionId": f"T{i}", "settlementDate": day} for i in range(2)]
        )
        plan = capture_store.plan_capture_publish(
            cache,
            resolved.spec,
            resolved.scope_key,
            resolved.window,
            rows,
            2,
            fetched,
            fetched,
            cap=3,
        )
        capture_store.commit_plan(cache, resolved.spec.name, plan, fetched)
    assert plan.eviction.dropped == 1
    index = capture_store.read_index(cache, resolved.spec.name)
    assert sum(entry.row_count for entry in index.captures) == 3
    older = next(entry for entry in index.captures if entry.fetched_at == T1)
    assert len(capture_store.read_capture(cache, older)) == 1


def test_eviction_keeps_newer_records_from_overlapping_captures(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    wide = [holding(1, "20260929"), holding(2, "20260930"), holding(3, "20261001")]
    publish_dated(store, ("20260929", "20261001"), wide, T1, cap=3)
    plan = publish_dated(
        store, ("20260930", "20260930"), [holding(9, "20260930")], T2, cap=3
    )
    assert plan.eviction is not None and plan.eviction.dropped == 1
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    assert index is not None
    rows = []
    for entry in index.captures:
        rows.extend(capture_store.read_capture(store, entry))
    # Retention ranks records, not captures: the oldest record evicts and the
    # newer same-day acquisition survives even though its capture is shorter.
    assert {row["investmentNo"] for row in rows} == {"H002", "H003", "H009"}


def test_partial_day_eviction_does_not_claim_full_coverage(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    day = [holding(index, "20260929") for index in (1, 2, 3)]
    plan = publish_dated(store, ("20260929", "20260929"), day, T1, cap=2)
    assert plan.eviction is not None and plan.eviction.dropped == 1
    entry = plan.index.captures[0]
    assert entry.row_count == 2
    # The day lost records, so coverage starts the next day instead of
    # reporting a partial day as complete.
    assert entry.window_from == "20260930"
    _, covered = capture_store.select_captures(
        plan.index, INVESTMENT_HOLDINGS, "", ("20260929", "20260929")
    )
    assert not covered


def test_clean_day_boundary_keeps_its_own_coverage(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    rows = [holding(1, "20260929"), holding(2, "20260930"), holding(3, "20260930")]
    plan = publish_dated(store, ("20260929", "20260930"), rows, T1, cap=2)
    assert plan.eviction is not None and plan.eviction.retained_from == "20260930"
    entry = plan.index.captures[0]
    # Whole days evicted: the first fully retained day still counts as covered.
    assert entry.window_from == "20260930"
    _, covered = capture_store.select_captures(
        plan.index, INVESTMENT_HOLDINGS, "", ("20260930", "20260930")
    )
    assert covered


def test_trimmed_capture_is_replaced_by_its_own_window_refresh(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    day = [holding(index, "20260929") for index in (1, 2, 3)]
    first = publish_dated(store, ("20260929", "20260929"), day, T1, cap=2)
    trimmed = first.index.captures[0]
    assert trimmed.window_from == "20260930"
    publish_dated(store, ("20260929", "20260929"), [holding(7, "20260929")], T2)
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    assert index is not None
    # One namespace, one index entry: refreshing the acquisition window
    # replaces the trimmed capture instead of leaving a second entry whose
    # indexed row count no longer matches the stored snapshot.
    assert [entry.namespace for entry in index.captures] == [trimmed.namespace]
    rows = capture_store.read_capture(store, index.captures[0])
    assert [row["investmentNo"] for row in rows] == ["H007"]


def test_eviction_prefers_the_newer_correction_of_one_record(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    stale = {"investmentNo": "H001", "valueDate": "20260930", "amount": "OLD"}
    corrected = {"investmentNo": "H001", "valueDate": "20260930", "amount": "NEW"}
    # The older capture's namespace sorts after the newer one's, so a
    # namespace tie-break would evict the correction and keep the stale copy.
    publish_dated(store, ("20260930", "20261001"), [stale], T1, cap=1)
    plan = publish_dated(store, ("20260929", "20260930"), [corrected], T2, cap=1)
    assert plan.eviction is not None and plan.eviction.dropped == 1
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    assert index is not None
    rows = []
    for entry in index.captures:
        rows.extend(capture_store.read_capture(store, entry))
    assert [row["amount"] for row in rows] == ["NEW"]


@pytest.mark.parametrize("empty_newer", [False, True])
@pytest.mark.parametrize("later_eviction", [False, True])
@pytest.mark.parametrize("same_fetch_time", [False, True])
def test_eviction_preserves_newer_complete_day(
    tmp_path, empty_newer, later_eviction, same_fetch_time
):
    store = Cache(tmp_path / "cache.sqlite3")
    older_rows = [holding(i, "20260929") for i in (1, 2)]
    newer_rows = [] if empty_newer else [{**row, "amount": "NEW"} for row in older_rows]
    publish_dated(store, ("20260928", "20260930"), older_rows, T1)
    fetched = T1 if same_fetch_time else T2
    cap = len(older_rows) + len(newer_rows) - 1
    publish_dated(
        store,
        ("20260929", "20260929"),
        newer_rows,
        fetched,
        cap=spec_mod.RETENTION_CAP if later_eviction else cap,
    )
    if later_eviction:
        publish_dated(
            store,
            ("20261001", "20261001"),
            [holding(3, "20261001")],
            T3,
            cap=cap + 1,
        )
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    older = next(e for e in index.captures if e.window_from == "20260928")
    newer = next(e for e in index.captures if e.window_from == "20260929")
    assert older.missing_days == ("20260929",)
    assert newer.missing_days == ()
    assert capture_store.read_capture(store, newer) == newer_rows
    assert capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260929", "20260929")
    )[1]


def test_detail_key_canonicalizes_integer_identities():
    from dogopencli.plugins.liquidity.leaves import detail_leaf

    typed = detail_leaf(("network", "account-capabilities", "get")).spec.identity
    assert detail_store.detail_key({"id": "007"}, typed) == "id=7"
    assert detail_store.detail_key({"id": "7"}, typed) == "id=7"
    textual = detail_leaf(("investment", "holdings", "get")).spec.identity
    assert detail_store.detail_key({"investment_no": "007"}, textual) == (
        "investment_no=007"
    )


@pytest.mark.parametrize("empty_first", [True, False])
def test_overflow_preserves_empty_day_coverage(tmp_path, empty_first):
    store = Cache(tmp_path / "cache.sqlite3")
    empty = (("20260928", "20260928"), [])
    populated = (("20260929", "20260929"), [holding(1, "20260929")])
    first, second = (empty, populated) if empty_first else (populated, empty)
    publish_dated(store, *first, T1, cap=1)
    publish_dated(store, *second, T2, cap=1)
    publish_dated(store, ("20260930", "20260930"), [holding(2, "20260930")], T3, cap=1)
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    selected, covered = capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", empty[0]
    )
    assert covered
    assert len(selected) == 1
    assert capture_store.read_capture(store, selected[0]) == []


@pytest.mark.parametrize("overlap_rows", [[], [holding(9, "20260929")]])
def test_overlapping_capture_cannot_mask_evicted_day(tmp_path, overlap_rows):
    store = Cache(tmp_path / "cache.sqlite3")
    publish_dated(store, ("20260928", "20260929"), overlap_rows, T1)
    day = [holding(i, "20260929") for i in (1, 2, 3)]
    publish_dated(store, ("20260929", "20260929"), day, T2, cap=2)
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    assert not capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260929", "20260929")
    )[1]
    # Complete reacquisition restores coverage without retaining a false gap.
    publish_dated(store, ("20260929", "20260929"), day, T3)
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    assert capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260929", "20260929")
    )[1]


def test_new_empty_capture_survives_overflow(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    publish_dated(
        store,
        ("20260929", "20260929"),
        [holding(1, "20260929"), holding(2, "20260929")],
        T1,
    )
    publish_dated(store, ("20260930", "20260930"), [], T2, cap=1)
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    selected, covered = capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260930", "20260930")
    )
    assert covered
    assert capture_store.read_capture(store, selected[0]) == []


def test_eviction_does_not_invalidate_another_scope(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    plan = capture_store.plan_capture_publish(
        store, INVESTMENT_HOLDINGS, "other", ("20260929", "20260929"), [], 0, T1, T1
    )
    capture_store.commit_plan(store, INVESTMENT_HOLDINGS.name, plan, T1)
    publish_dated(
        store,
        ("20260929", "20260929"),
        [holding(1, "20260929"), holding(2, "20260929")],
        T2,
        cap=1,
    )
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    assert capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "other", ("20260929", "20260929")
    )[1]


@pytest.mark.parametrize("earlier_rows", [[], [holding(9, "20260930")]])
def test_later_eviction_preserves_unaffected_earlier_day(tmp_path, earlier_rows):
    store = Cache(tmp_path / "cache.sqlite3")
    publish_dated(store, ("20260928", "20260930"), earlier_rows, T1)
    publish_dated(store, ("20260929", "20260929"), [holding(1, "20260929")], T2)
    publish_dated(
        store,
        ("20260930", "20260930"),
        [holding(2, "20260930")],
        T3,
        cap=1 + len(earlier_rows),
    )
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    selected, covered = capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260928", "20260928")
    )
    assert covered
    assert capture_store.read_capture(store, selected[0]) == earlier_rows
    assert not capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260929", "20260929")
    )[1]


def test_trimmed_capture_preserves_empty_days_before_and_after_loss(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    publish_dated(
        store,
        ("20260928", "20260930"),
        [holding(1, "20260929"), holding(2, "20260929")],
        T1,
        cap=1,
    )
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    for day in ("20260928", "20260930"):
        assert capture_store.select_captures(
            index, INVESTMENT_HOLDINGS, "", (day, day)
        )[1]
    assert not capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260929", "20260929")
    )[1]


@pytest.mark.parametrize("missing_days", [None, ["bad"], ["20260230"], [1]])
def test_invalid_cached_missing_days_rejects_coverage(tmp_path, missing_days):
    store = Cache(tmp_path / "cache.sqlite3")
    plan = publish_dated(store, ("20260928", "20260930"), [], T1)
    record = plan.index.captures[0].record()
    record["missing_days"] = missing_days
    with pytest.raises(CliError, match="missing days are invalid"):
        capture_store.CaptureEntry.from_record(record)


def test_legacy_capture_defaults_to_no_missing_days(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    plan = publish_dated(store, ("20260928", "20260930"), [], T1)
    record = plan.index.captures[0].record()
    del record["missing_days"]
    assert capture_store.CaptureEntry.from_record(record).missing_days == ()


def test_eviction_preserves_empty_day_between_lost_record_days(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    publish_dated(
        store,
        ("20260929", "20261003"),
        [
            holding(1, "20260929"),
            holding(2, "20261001"),
            holding(3, "20261003"),
        ],
        T1,
        cap=1,
    )
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    for day in ("20260930", "20261002", "20261003"):
        assert capture_store.select_captures(
            index, INVESTMENT_HOLDINGS, "", (day, day)
        )[1]
    for day in ("20260929", "20261001"):
        assert not capture_store.select_captures(
            index, INVESTMENT_HOLDINGS, "", (day, day)
        )[1]


def test_all_records_evicted_preserves_verified_empty_days(tmp_path):
    store = Cache(tmp_path / "cache.sqlite3")
    publish_dated(store, ("20260928", "20260930"), [holding(1, "20260929")], T1)
    publish_dated(store, ("20261001", "20261001"), [holding(2, "20261001")], T2, cap=1)
    index = capture_store.read_index(store, INVESTMENT_HOLDINGS.name)
    for day in ("20260928", "20260930"):
        selected, covered = capture_store.select_captures(
            index, INVESTMENT_HOLDINGS, "", (day, day)
        )
        assert covered
        assert capture_store.read_capture(store, selected[0]) == []
    assert not capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260929", "20260929")
    )[1]


def test_latest_partial_dated_capture_revokes_older_complete_coverage(tmp_path):
    from dogopencli.result_policy import AcquisitionEvidence

    cache = Cache(tmp_path / "cache.sqlite3")
    publish_dated(cache, ("20260928", "20260930"), [holding(1, "20260929")], T1)
    partial = AcquisitionEvidence.for_collection(
        complete=False,
        reported_total=2,
        collected_total=1,
    )
    plan = capture_store.plan_capture_publish(
        cache,
        INVESTMENT_HOLDINGS,
        "",
        ("20260929", "20260929"),
        [holding(2, "20260929")],
        2,
        T2,
        T2,
        acquisition=partial,
    )
    capture_store.commit_plan(cache, INVESTMENT_HOLDINGS.name, plan, T2)
    index = capture_store.read_index(cache, INVESTMENT_HOLDINGS.name)
    assert not capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260928", "20260930")
    )[1]
    assert capture_store.select_captures(
        index, INVESTMENT_HOLDINGS, "", ("20260928", "20260928")
    )[1]
    assert capture_store.read_capture(cache, index.captures[-1]) == [
        holding(2, "20260929")
    ]
    assert index.captures[-1].evidence.reasons == ("COUNT_SHORTFALL",)


@pytest.mark.parametrize("new_reasons", [(), ("DUPLICATE_ROWS",)])
def test_dated_refresh_quality_uses_only_current_window_authority(
    tmp_path, new_reasons
):
    from dogopencli.result_policy import AcquisitionEvidence, evaluate_result

    cache = Cache(tmp_path / "cache.sqlite3")
    old_rows = [holding(1, "20260929"), holding(2, "20260930")]
    partial = AcquisitionEvidence.for_collection(
        complete=False, reported_total=3, collected_total=2
    )
    old = capture_store.plan_capture_publish(
        cache,
        INVESTMENT_HOLDINGS,
        "",
        ("20260929", "20260930"),
        old_rows,
        3,
        T1,
        T1,
        acquisition=partial,
    )
    capture_store.commit_plan(cache, INVESTMENT_HOLDINGS.name, old, T1)
    window = ("20260929", "20260929")
    new = capture_store.plan_capture_publish(
        cache,
        INVESTMENT_HOLDINGS,
        "",
        window,
        [holding(3, "20260929")],
        1,
        T2,
        T2,
        acquisition=AcquisitionEvidence(
            scope_complete=True,
            dataset_complete=True,
            collected_total=1,
            reported_total=1,
            reasons=new_reasons,
        ),
    )
    evidence = capture_store.retained_evidence(new, INVESTMENT_HOLDINGS, "", window)
    assert evidence.scope_complete and evidence.dataset_complete
    assert evidence.reasons == new_reasons
    assert evidence.reported_total == 1
    decision = evaluate_result(evidence, mode="refresh", require_complete=True)
    assert decision.publishable and decision.exit_code == 0
    assert bool(decision.warnings) is bool(new_reasons)
    if new_reasons:
        assert decision.warnings[0]["reason_codes"] == list(new_reasons)

    # The older acquisition still owns the second day and keeps its gap.
    entries, covered = capture_store.select_captures(
        new.index, INVESTMENT_HOLDINGS, "", ("20260929", "20260930")
    )
    wider = capture_store.query_evidence(
        entries, covered, 2, window=("20260929", "20260930")
    )
    assert not wider.scope_complete
    assert "COUNT_SHORTFALL" in wider.reasons
    assert evaluate_result(wider, mode="cache", require_complete=True).exit_code == 1


def test_trim_inherits_acquisition_gap_and_reports_retention_separately(tmp_path):
    from dogopencli.result_policy import AcquisitionEvidence

    cache = Cache(tmp_path / "cache.sqlite3")
    partial = AcquisitionEvidence.for_collection(
        complete=False,
        reported_total=3,
        collected_total=2,
    )
    plan = capture_store.plan_capture_publish(
        cache,
        FORECAST_ADJUSTMENTS,
        "",
        (None, None),
        [adjustment(1), adjustment(2)],
        3,
        T1,
        T1,
        cap=1,
        acquisition=partial,
    )
    capture_store.commit_plan(cache, FORECAST_ADJUSTMENTS.name, plan, T1)
    index = capture_store.read_index(cache, FORECAST_ADJUSTMENTS.name)
    entry = index.captures[0]
    snapshot = cache.current(entry.namespace)
    assert entry.evidence == partial
    assert snapshot.backend_complete is False
    assert snapshot.acquisition == partial.record()
    assert capture_store.read_capture(cache, entry) == [adjustment(2)]
    final = capture_store.retained_evidence(
        plan, FORECAST_ADJUSTMENTS, "", (None, None)
    )
    assert final.scope_complete is False
    assert final.reasons == ("COUNT_SHORTFALL", "RETENTION_GAP")
    assert final.collected_total == 1


def test_cached_capture_rejects_quality_disagreement_with_index(tmp_path):
    from dogopencli.result_policy import AcquisitionEvidence

    cache = Cache(tmp_path / "cache.sqlite3")
    evidence = AcquisitionEvidence.for_collection(
        complete=False,
        reported_total=2,
        collected_total=1,
    )
    plan = capture_store.plan_capture_publish(
        cache,
        CASH_ACCOUNTS,
        "",
        (None, None),
        [{"aliasName": "A1"}],
        2,
        T1,
        T1,
        acquisition=evidence,
    )
    capture_store.commit_plan(cache, CASH_ACCOUNTS.name, plan, T1)
    with sqlite3.connect(tmp_path / "cache.sqlite3") as connection:
        connection.execute(
            "UPDATE snapshots SET backend_complete=1 WHERE namespace=?",
            (plan.capture_meta.namespace,),
        )
    entry = capture_store.read_index(cache, CASH_ACCOUNTS.name).captures[0]
    with pytest.raises(CliError) as rejected:
        capture_store.read_capture(cache, entry)
    assert rejected.value.code == "INVALID_RESPONSE"


def test_history_retention_without_reported_total_uses_acquired_row_count(tmp_path):
    from dogopencli.result_policy import AcquisitionEvidence

    cache = Cache(tmp_path / "cache.sqlite3")
    evidence = AcquisitionEvidence.for_collection(
        complete=True,
        reported_total=None,
        collected_total=2,
    )
    plan = capture_store.plan_capture_publish(
        cache,
        FORECAST_ADJUSTMENTS,
        "",
        (None, None),
        [adjustment(1), adjustment(2)],
        None,
        T1,
        T1,
        cap=1,
        acquisition=evidence,
    )
    capture_store.commit_plan(cache, FORECAST_ADJUSTMENTS.name, plan, T1)
    index = capture_store.read_index(cache, FORECAST_ADJUSTMENTS.name)
    assert not capture_store.select_captures(
        index,
        FORECAST_ADJUSTMENTS,
        "",
        (None, None),
    )[1]
    final = capture_store.retained_evidence(
        plan, FORECAST_ADJUSTMENTS, "", (None, None)
    )
    assert final.scope_complete is False
    assert final.reasons == ("RETENTION_GAP",)
    assert final.reported_total is None


def test_actual_legacy_master_reader_accepts_old_index_and_rejects_new_format(
    tmp_path,
    monkeypatch,
):
    import importlib.util
    import sys
    from pathlib import Path

    from dogopencli.jsonutil import canonical
    from dogopencli.result_policy import AcquisitionEvidence

    module_name = "dogopencli.plugins.liquidity._legacy_master_index_reader"
    module_spec = importlib.util.spec_from_file_location(
        module_name,
        Path(__file__).with_name("legacy_master_index_reader.py"),
    )
    legacy_reader = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, module_name, legacy_reader)
    module_spec.loader.exec_module(legacy_reader)

    cache = Cache(tmp_path / "cache.sqlite3")
    rows = [{"aliasName": "A1"}, {"aliasName": "A2"}]
    complete = capture_store.plan_capture_publish(
        cache,
        CASH_ACCOUNTS,
        "",
        (None, None),
        rows,
        2,
        T1,
        T1,
    )
    capture_store.commit_plan(cache, CASH_ACCOUNTS.name, complete, T1)
    # Re-create an index with the actual legacy serializer, rather than assuming
    # that today's serializer happens to produce a legacy-compatible shape.
    index_namespace = legacy_reader.index_namespace(CASH_ACCOUNTS.name)
    index_meta = cache.current(index_namespace)
    legacy_entry = legacy_reader.CaptureEntry.from_record(
        complete.index.captures[0].record()
    )
    cache.publish(
        replace(index_meta, row_count=1),
        [(1, canonical(legacy_entry.record()))],
    )
    before = (tmp_path / "cache.sqlite3").read_bytes()
    old_index = legacy_reader.read_index(cache, CASH_ACCOUNTS.name)
    assert len(old_index.captures) == 1
    assert old_index.captures[0].row_count == 2
    assert (
        capture_store.read_index(cache, CASH_ACCOUNTS.name)
        .captures[0]
        .evidence.scope_complete
        is True
    )
    assert (tmp_path / "cache.sqlite3").read_bytes() == before

    partial = capture_store.plan_capture_publish(
        cache,
        CASH_ACCOUNTS,
        "",
        (None, None),
        rows[:1],
        2,
        T2,
        T2,
        acquisition=AcquisitionEvidence.for_collection(
            complete=False,
            reported_total=2,
            collected_total=1,
        ),
    )
    capture_store.commit_plan(cache, CASH_ACCOUNTS.name, partial, T2)
    new_index = capture_store.read_index(cache, CASH_ACCOUNTS.name)
    assert new_index.captures[0].evidence.scope_complete is False
    assert capture_store.read_capture(cache, new_index.captures[0]) == rows[:1]
    after = (tmp_path / "cache.sqlite3").read_bytes()
    with pytest.raises(CliError, match="cached capture index is invalid") as rejected:
        legacy_reader.read_index(cache, CASH_ACCOUNTS.name)
    assert rejected.value.code == "INVALID_RESPONSE"
    assert (tmp_path / "cache.sqlite3").read_bytes() == after


@pytest.mark.parametrize(
    "backend_complete,dataset_complete", [(False, True), (True, False), (False, False)]
)
def test_legacy_capture_inherits_existing_false_snapshot_quality_without_rewrite(
    tmp_path,
    backend_complete,
    dataset_complete,
):
    from dogopencli.jsonutil import canonical

    cache_path = tmp_path / "cache.sqlite3"
    cache = Cache(cache_path)
    plan = capture_store.plan_capture_publish(
        cache,
        CASH_ACCOUNTS,
        "",
        (None, None),
        [{"aliasName": "A1"}],
        1,
        T1,
        T1,
    )
    capture_store.commit_plan(cache, CASH_ACCOUNTS.name, plan, T1)
    old_entry = plan.index.captures[0].record()
    for key in ("acquisition", "requested_from", "requested_to"):
        old_entry.pop(key)
    index_namespace = capture_store.index_namespace(CASH_ACCOUNTS.name)
    with sqlite3.connect(cache_path) as connection:
        connection.execute(
            "UPDATE snapshots SET backend_complete=?,dataset_complete=?,"
            "acquisition=NULL WHERE namespace=?",
            (backend_complete, dataset_complete, plan.capture_meta.namespace),
        )
        connection.execute("DELETE FROM records WHERE namespace=?", (index_namespace,))
        connection.execute(
            "INSERT INTO records VALUES (?,?,?)",
            (index_namespace, 1, canonical(old_entry)),
        )
        connection.execute(
            "UPDATE snapshots SET row_count=1 WHERE namespace=?", (index_namespace,)
        )
    before = cache_path.read_bytes()
    index = capture_store.read_index(cache, CASH_ACCOUNTS.name)
    selected, complete = capture_store.select_captures(
        index, CASH_ACCOUNTS, "", (None, None)
    )
    assert complete is False
    evidence = selected[0].evidence
    assert evidence.scope_complete is backend_complete
    assert evidence.dataset_complete is dataset_complete
    assert evidence.reasons == ("COVERAGE_UNPROVEN",)
    assert capture_store.read_capture(cache, selected[0]) == [{"aliasName": "A1"}]
    assert cache_path.read_bytes() == before


@pytest.mark.parametrize("reported_total", [None, 2])
def test_snapshot_rejects_lost_record_even_when_storage_counts_are_adjusted(
    tmp_path,
    reported_total,
):
    from dogopencli.jsonutil import canonical

    cache_path = tmp_path / "cache.sqlite3"
    cache = Cache(cache_path)
    rows = [{"aliasName": "A1"}, {"aliasName": "A2"}]
    plan = capture_store.plan_capture_publish(
        cache,
        CASH_ACCOUNTS,
        "",
        (None, None),
        rows,
        reported_total,
        T1,
        T1,
    )
    capture_store.commit_plan(cache, CASH_ACCOUNTS.name, plan, T1)
    corrupted_entry = plan.index.captures[0].record()
    corrupted_entry["row_count"] = 1
    with sqlite3.connect(cache_path) as connection:
        connection.execute(
            "UPDATE snapshots SET row_count=1 WHERE namespace=?",
            (plan.capture_meta.namespace,),
        )
        connection.execute(
            "DELETE FROM records WHERE namespace=? AND seqid=2",
            (plan.capture_meta.namespace,),
        )
        connection.execute(
            "UPDATE records SET body=? WHERE namespace=? AND seqid=2",
            (
                canonical(corrupted_entry),
                capture_store.index_namespace(CASH_ACCOUNTS.name),
            ),
        )
    before = cache_path.read_bytes()
    index = capture_store.read_index(cache, CASH_ACCOUNTS.name)
    with pytest.raises(CliError) as rejected:
        capture_store.read_capture(cache, index.captures[0])
    assert rejected.value.code == "INVALID_RESPONSE"
    assert cache_path.read_bytes() == before
