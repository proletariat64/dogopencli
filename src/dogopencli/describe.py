"""Installed, offline data descriptions; no business environment is inspected."""

import json
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from .annotations import guide_annotations
from .helpspec import (
    BUSINESS_EXIT_CODES,
    REFRESH_OUTPUT,
    BizNode,
    contract,
    display_modes,
    document,
    opt,
)
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
                opt(
                    "format",
                    "Description format.",
                    default="json",
                    choices=("json", "text"),
                    argument_contract=contract("enum", modes=display_modes()),
                ),
            ),
            constraints=(
                (
                    "Offline installed contract; reads no config, cache, browser "
                    "or network."
                ),
            ),
            output={**REFRESH_OUTPUT, "formats": ["json", "text"]},
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
                "Null for usable data, including warned incomplete results."
                " Failures withhold data and carry code, message and retryable;"
                " meta may preserve quality and publication evidence."
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
        "quality": (
            "Default validated incomplete acquisitions can be published and read"
            " with warnings and exit 0. Check complete, dataset_complete and"
            " acquisition reasons; use --require-complete to reject gaps."
        ),
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
    guide.setdefault("metadata", {}).update(
        {
            "local_filters": "Explicit filters applied to the saved acquisition.",
            "requested_coverage": "Whether saved acquisition proves scope coverage; "
            "null is unknown.",
            "source_acquisition": "Original source quality before local filtering.",
            "variant": "Saved native contract variant.",
            "selection": "Frozen values selected for online enumeration, or null.",
            "cache_only_absence": "Optional explanation of unmatched local rows; "
            "no backend absence proof.",
            "acquisition": "Persisted acquisition counts, quality flags, reason codes"
            " and bounded attempt summaries; independent of local display filters.",
            "reported_total": "Native reported total, or null when unreported or"
            " unavailable for the combined query scope.",
            "collected_total": "Collected records before local filtering and display.",
            "missing_count": "Quantified count gap only for comparable native total"
            " units; otherwise null.",
            "coverage_ratio": "Collected/native total for comparable nonzero totals;"
            " otherwise null. Does not promise representativeness.",
            "warnings": "Optional structured quality warnings. Usable incomplete"
            " data has INCOMPLETE_RESULT warnings, error=null and exit 0 by default.",
        }
    )
    return {
        "describe_version": 1,
        "capability": ".".join(path),
        "schema_version": description["schema_version"],
        "data_schema": description["data_schema"],
        "read_guide": guide,
        "query_help": "dogopencli help " + " ".join(path),
    }


def render_text(description: dict[str, Any]) -> str:
    """Render the whole contract as an indented outline, retaining annotations."""
    lines: list[str] = []

    def append(label: str, value: Any, depth: int) -> None:
        prefix = "  " * depth + label + ":"
        if isinstance(value, dict) and value:
            lines.append(prefix)
            for key, item in value.items():
                append(key, item, depth + 1)
        elif isinstance(value, list) and value:
            lines.append(prefix)
            for index, item in enumerate(value):
                append(f"[{index}]", item, depth + 1)
        else:
            text = value if isinstance(value, str) else json.dumps(value)
            parts = text.splitlines() or [""]
            lines.append(prefix + " " + parts[0])
            lines.extend("  " * (depth + 1) + part for part in parts[1:])

    for key, value in description.items():
        if lines:
            lines.append("")
        append(key, value, 0)
    return "\n".join(lines) + "\n"
