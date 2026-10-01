"""Capture store and the 1,000,000-record retention policy (ADR 0017)."""

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
    INVESTMENT_HOLDINGS,
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
    store.publish(replace(plan.capture_meta, row_count=1), [])
    with pytest.raises(CliError, match="coverage is invalid"):
        capture_store.read_capture(store, plan.index.captures[0])


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
