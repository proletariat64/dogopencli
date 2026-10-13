"""Legacy latest selectors match only semantically identical scopes."""

import pytest

from dogopencli.cache import Cache
from dogopencli.plugins.liquidity import store as capture_store

T1 = "2026-10-01T00:00:00+00:00"


@pytest.mark.parametrize(
    "different", ["entitys", "aliasNames", "timeZone", "__selection", "__contract"]
)
def test_latest_scope_order_compatibility_never_broadens_other_dimensions(
    tmp_path, different
):
    from dogopencli.plugins.liquidity.capability import decode_scope, encode_scope
    from dogopencli.plugins.liquidity.leaves import list_leaf

    leaf = list_leaf(("cash", "balances"))
    resolved = leaf.resolve({"entity": ["E1", "E2"], "account": ["A1", "A2"]})
    values = decode_scope(resolved.scope_key)
    values["entitys"] = ["E2", "E1"]
    values["aliasNames"] = ["A2", "A1"]
    if different == "entitys":
        values[different] = ["E3", "E1"]
    elif different == "aliasNames":
        values[different] = ["A3", "A1"]
    elif different == "timeZone":
        values[different] = "GMT+00"
    elif different == "__selection":
        values[different] = "all-directory"
    else:
        values[different]["tenant"] = "other-tenant"
    store = Cache(tmp_path / "cache.sqlite3")
    plan = capture_store.plan_capture_publish(
        store,
        resolved.spec,
        encode_scope(values),
        (None, None),
        [{"balId": "B1", "entity": "E1", "aliasName": "A1", "currency": "USD"}],
        1,
        T1,
        T1,
    )
    capture_store.commit_plan(store, resolved.spec.name, plan, T1)
    selected, covered = capture_store.select_captures(
        plan.index, resolved.spec, resolved.scope_key, (None, None)
    )
    assert selected == []
    assert covered is False
