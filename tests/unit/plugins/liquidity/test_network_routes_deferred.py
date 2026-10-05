"""Batch F F4 (#119): network routes deferred declaration matches the evidence."""

from dogopencli.plugins.liquidity.leaves import (
    DEFERRED_BY_PATH,
    DETAIL_LEAVES,
    LIST_LEAVES,
)
from dogopencli.plugins.liquidity.spec import SETTINGS

LIST_PATH = ("network", "routes", "list")
GET_PATH = ("network", "routes", "get")
LIST_BLOCKER = (
    "no native global routes-list caller",
    "RealTimeNetwork",
    "queryWhaleRouteDetail",
    "quota",
    "not a global routes list",
)
GET_BLOCKER = ("queryWhaleRouteDetail", "never executed")


def test_routes_list_stays_deferred_with_the_named_blocker():
    leaf = DEFERRED_BY_PATH[LIST_PATH]
    assert leaf.kind == SETTINGS
    assert leaf.status == "unverified"
    for fragment in LIST_BLOCKER:
        assert fragment in leaf.reason
    assert ("network", "routes") not in LIST_LEAVES


def test_routes_get_stays_deferred_without_execution():
    leaf = DEFERRED_BY_PATH[GET_PATH]
    assert leaf.kind == SETTINGS
    assert leaf.status == "unverified"
    for fragment in GET_BLOCKER:
        assert fragment in leaf.reason
    assert GET_PATH not in DETAIL_LEAVES
