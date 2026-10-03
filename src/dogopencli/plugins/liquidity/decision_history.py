"""Bind decision history versions to their verified native sibling detail.

The history request uses the current detail's id, while historical versions
have different row ids. Native getDetail echoes the requested id and supplies
the stable reportId/groupId lineage echoed by each getHistory row. Both are
bounded allowlisted inquiries in the same authenticated session; only the
native history array is returned or published.
"""

from typing import Any

from ...errors import INVALID_RESPONSE, CliError
from ...inquiry import InquirySession
from . import spec
from .leaves import DetailLeaf, detail_leaf

HISTORY_PATH = ("operations", "decisions", "history")
LINEAGE_FIELDS = ("reportId", "groupId", "tntInstId")


def fetch_native_detail(
    session: InquirySession, leaf: DetailLeaf, values: dict[str, str]
) -> Any:
    """Acquire ordinary details or independently bound decision versions."""
    from .query import fetch_detail

    if (*leaf.spec.path, leaf.spec.action) != HISTORY_PATH:
        return fetch_detail(session.transport(leaf.capability), leaf, values)

    sibling = detail_leaf(("operations", "decisions", "get"))
    current = fetch_detail(session.transport(sibling.capability), sibling, values)
    if type(current.get("id")) is not int or current["id"] != int(values["id"]):
        raise CliError(INVALID_RESPONSE, "decision detail identity does not match")
    lineage: dict[str, str] = {}
    for field in LINEAGE_FIELDS:
        value = current.get(field)
        if not isinstance(value, str) or not value.strip():
            raise CliError(INVALID_RESPONSE, "decision detail lineage is invalid")
        lineage[field] = value
    if lineage["tntInstId"] != spec.TENANT:
        raise CliError(INVALID_RESPONSE, "decision detail tenant does not match")

    rows = fetch_detail(session.transport(leaf.capability), leaf, values)
    for row in rows:
        if any(row.get(field) != lineage[field] for field in LINEAGE_FIELDS):
            raise CliError(INVALID_RESPONSE, "decision history lineage does not match")
        if type(row.get("id")) is not int or type(row.get("version")) is not int:
            raise CliError(
                INVALID_RESPONSE, "decision history version identity is invalid"
            )
    return rows
