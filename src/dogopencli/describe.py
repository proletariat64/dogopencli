"""Installed, offline data descriptions; no business environment is inspected."""

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from .annotations import guide_annotations
from .helpspec import BUSINESS_EXIT_CODES, REFRESH_OUTPUT, BizNode, document, opt
from .plugins import get_description


def description_nodes(queries: Iterable[BizNode]) -> Iterable[BizNode]:
    """Attach discovery and mirror registered query paths under describe."""
    groups: set[tuple[str, ...]] = set()
    for query in queries:
        path = ("describe", *query.path)
        command = "dogopencli " + " ".join(path)
        yield replace(query, next=(*query.next, command))
        for length in range(1, len(path)):
            prefix = path[:length]
            if prefix not in groups:
                groups.add(prefix)
                yield BizNode(prefix, "Discover offline business data descriptions.")
        yield BizNode(
            path,
            ("Describe the unprojected business data schema and reading guidance."),
            options=(
                opt("format", "Description format.", default="json", choices=("json",)),
            ),
            constraints=(
                (
                    "Offline installed contract; reads no config, cache, browser "
                    "or network."
                ),
            ),
            output=dict(REFRESH_OUTPUT),
            examples=(command,),
            next=("dogopencli help " + " ".join(query.path),),
            handler="cmd_describe",
        )


def describe(path: tuple[str, ...]) -> dict[str, Any]:
    """Assemble a fresh offline helper from a registered plugin description."""
    from .catalog import NODES

    node = NODES[path]
    detail = path[-1] == "get"
    help_doc = document(node)
    description = get_description(node)
    guide: dict[str, Any] = {
        "parameter_contract": (
            "Corresponding query help is authoritative; options below "
            "reuse its registered declarations."
        ),
        "options": help_doc["options"],
        "envelope": {
            "data": (
                "Unprojected successful data is described by data_schema; "
                "projections can omit any field, including identifiers."
            ),
            "meta": (
                "Actual query snapshot and quality information; projection "
                "never removes it. describe makes no claim about current "
                "local data."
            ),
            "error": (
                "Null on success. On failure data/meta are null and error has"
                " code, message and retryable. Check nonzero exit before "
                "consuming data."
            ),
        },
        "projection": "--fields selects comma-separated top-level record fields. "
        "Nested objects are retained as whole values; absent "
        "requested fields are omitted. Validate a projection as "
        "partial data, not against required fields of the unprojected"
        " schema.",
        "pagination": "Detail is one object; no --all, --limit or --offset."
        if detail
        else (
            "Default display: 100 rows, offset 0. --all returns every "
            "matched row and conflicts with explicit --limit/--offset. "
            "--limit must be positive; --offset nonnegative. has_more "
            "describes this display window, not source completeness."
        ),
        "annotations": guide_annotations(),
        "errors": help_doc["errors"],
        "exit_codes": {
            str(code): meaning for code, meaning in BUSINESS_EXIT_CODES.items()
        },
        "evolution": "Additive fields and annotations may appear within a version;"
        " consumers preserve unknown fields. Incompatible helper "
        "changes increment describe_version; incompatible capability "
        "schema changes increment schema_version. These do not "
        "version or alter query envelopes or help_version.",
    }
    guide.update(description["read_guide"])
    return {
        "describe_version": 1,
        "capability": ".".join(path),
        "schema_version": description["schema_version"],
        "data_schema": description["data_schema"],
        "read_guide": guide,
        "query_help": "dogopencli help " + " ".join(path),
    }
