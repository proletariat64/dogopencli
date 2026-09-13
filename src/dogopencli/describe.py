"""Installed, offline data descriptions; no business environment is inspected."""

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from .helpspec import BUSINESS_EXIT_CODES, REFRESH_OUTPUT, BizNode, document, opt
from .plugins.payment import channel, cost, sla


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


ANNOTATIONS = {
    "x-evidence": {
        "description": (
            "Evidence for each independent aspect; observation is not a guarantee."
        ),
        "aspects": ["type", "presence", "nullability", "unit", "meaning"],
        "values": {
            "verified": "Supported by the verified contract or CLI behavior.",
            "observed": "Seen in supported fixtures or observations; not guaranteed.",
            "unknown": "Unresolved; do not infer a constraint or conversion.",
            "not_applicable": "This aspect does not apply to this field.",
        },
    },
    "x-annotation-vocabulary": "Schema-local definitions of the annotation keys.",
    "x-unit": "Unit name only when verified; no automatic conversion.",
    "x-observed-type": "Observed JSON type(s), not a restrictive type assertion.",
    "x-observed-values": (
        "Observed values, not an exhaustive enum; new values remain valid."
    ),
}

METADATA = {
    "source": "cache or live: where this query read its data.",
    "backend": ("Configured source kind (cdp or snapshot), independent of source."),
    "simulated": (
        "True marks simulated/export-derived channel snapshot-source records."
    ),
    "scope": "Query/cache scope, not proof of coverage outside that scope.",
    "snapshot_id": (
        "Cached content identity; null for live. Not historical "
        "retrieval or synchronization across domains."
    ),
    "dataset_id": (
        "Imported dataset identity, otherwise null; not a universal business key."
    ),
    "fetched_at": (
        "Capture time for CDP; earliest source observation for "
        "imported snapshots. TTL uses this time, not loaded_at."
    ),
    "loaded_at": (
        "Local cache publication/import time; null for live. Import "
        "does not make old observations fresh."
    ),
    "source_observed_from": (
        "Imported source observation interval start; null when unavailable."
    ),
    "source_observed_to": (
        "Imported source observation interval end; null when unavailable."
    ),
    "stale": (
        "Whether fetched_at exceeds configured TTL (default 72 "
        "hours); live reports false. Independent of complete."
    ),
    "complete": (
        "Backend coverage of the queried source scope; independent of"
        " display truncation and freshness."
    ),
    "dataset_complete": (
        "Coverage of the curated/imported dataset; can be true while "
        "complete is false; null for live."
    ),
    "matched_total": (
        "Number of matching records in the available source before "
        "display pagination, not proof of full production coverage."
    ),
    "returned_count": "Number of records in this display window (one for detail).",
    "has_more": (
        "More matched records remain after this window; false does "
        "not imply complete backend coverage."
    ),
    "query": (
        "Live SLA detail only: capability and requested id. Cached "
        "detail lacks this extra metadata."
    ),
}


def _filters(node: BizNode, mapping: dict[str, str]) -> list[dict[str, Any]]:
    filters = []
    for option in node.options:
        if option.kind != "append":
            continue
        words = option.name.split("_")
        request = words[0] + "".join(word.title() for word in words[1:])
        if request not in mapping and request + "List" in mapping:
            request += "List"
        filters.append(
            {
                "flag": option.flag,
                "request_field": request,
                "record_field": mapping.get(request),
            }
        )
    return filters


def describe(path: tuple[str, ...]) -> dict[str, Any]:
    """Return a fresh deterministic helper document for a registered query."""
    from .catalog import NODES
    from .plugins.payment.descriptions import data_schema

    node = NODES[path]
    capability = ".".join(path)
    domain = path[1]
    detail = path[-1] == "get"
    mapping = {
        "channel": channel.FILTER_FIELDS,
        "cost": cost.FILTER_FIELDS,
        "sla": sla.FILTER_FIELDS,
    }[domain]
    help_doc = document(node)
    command = "dogopencli " + " ".join(path)
    guide: dict[str, Any] = {
        "parameter_contract": (
            "Corresponding query help is authoritative; options below "
            "reuse its registered declarations."
        ),
        "options": help_doc["options"],
        "filters": _filters(node, mapping),
        "filter_semantics": [
            (
                "Cached filters use exact equality: values of one field OR, "
                "different fields AND."
            ),
            (
                "Live cost/SLA filters accept one value per field. Channel "
                "scalar filters financialInstId, debitInstCountryCode and "
                "status accept one value; its verified array filters accept "
                "repeated values."
            ),
            (
                "Missing, null, empty string and empty array are distinct; "
                "none alone proves false, zero or an unsupported capability."
            ),
        ],
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
        "metadata": dict(METADATA),
        "access_modes": {
            "cached": (
                "Default: read the local snapshot, never implicitly refresh. "
                "Query first use can initialize/migrate cache; describe never"
                " does."
            ),
            "refresh": "Explicit dogopencli refresh payment "
            + domain
            + (
                " publishes a replacement local snapshot. SLA refresh "
                "collects the full list and every detail before publication."
            ),
            "live": (
                "--live reads through an existing authenticated CDP session, "
                "without launching a browser or updating cache. No fallback "
                "from unsupported snapshot sources."
            ),
        },
        "quality": [
            (
                "--require-fresh rejects stale cached data with CACHE_STALE; "
                "live does not use cached TTL."
            ),
            (
                "--require-complete checks backend complete, not "
                "dataset_complete or has_more; failure is INCOMPLETE_RESULT."
            ),
            (
                "An empty matching list is successful data, not an error; "
                "incomplete sources cannot establish absence in production."
            ),
            (
                "Channel snapshot-source data is simulated/export-derived, "
                "EXTERNAL only, and cannot establish current full production "
                "coverage even when dataset_complete is true."
            ),
            (
                "Snapshot identities do not offer historical reads or a "
                "synchronized snapshot across channel, cost and SLA."
            ),
        ],
        "projection": (
            "--fields selects comma-separated top-level record fields. "
            "Nested objects are retained as whole values; absent "
            "requested fields are omitted. Validate a projection as "
            "partial data, not against required fields of the unprojected"
            " schema."
        ),
        "pagination": "Detail is one object; no --all, --limit or --offset."
        if detail
        else (
            "Default display: 100 rows, offset 0. --all returns every "
            "matched row and conflicts with explicit --limit/--offset. "
            "--limit must be positive; --offset nonnegative. has_more "
            "describes this display window, not source completeness."
        ),
        "identifiers": [
            (
                "seqid, where returned, is a local position, not a stable "
                "business key across datasets or queries."
            ),
            (
                "Channel abilityId has no unqualified global uniqueness "
                "guarantee. Cost itemId is a configuration identifier, not a "
                "channel ID."
            ),
            (
                "No universal join key or verified one-to-one Channel/Cost "
                "association exists. SLA list id supplies detail --id."
            ),
        ],
        "interpretation": [
            (
                "Payment channels describe payment capability; costs describe"
                " channel cost configuration, not actual charges or aggregate"
                " spending; product SLA baselines are not observed arrival "
                "times or channel SLA rules."
            ),
            (
                "Preserve numeric amount precision and string amount "
                "representations. Transaction currency differs from fee/cost "
                "currency. cent does not establish division by 100."
            ),
            (
                "Unknown ratio scaling, time units and enum meanings remain "
                "unknown; no fee calculation or conversion is implied."
            ),
            (
                "Unknown extension fields remain permitted. Observed types "
                "and values do not establish required presence, "
                "non-nullability or exhaustive enums. Empty arrays do not "
                "prove their element type."
            ),
        ],
        "annotations": ANNOTATIONS,
        "errors": help_doc["errors"],
        "exit_codes": {
            str(code): meaning for code, meaning in BUSINESS_EXIT_CODES.items()
        },
        "examples": [
            command + (" --id BASELINE_ID" if detail else " --all"),
            command
            + (" --id BASELINE_ID --fields id" if detail else " --limit 20 --offset 0"),
            command
            + (" --id BASELINE_ID" if detail else "")
            + " --require-fresh --require-complete",
        ],
        "evolution": (
            "Additive fields and annotations may appear within a version;"
            " consumers preserve unknown fields. Incompatible helper "
            "changes increment describe_version; incompatible capability "
            "schema changes increment schema_version. These do not "
            "version or alter query envelopes or help_version."
        ),
    }
    if not detail:
        identity = {"channel": "abilityId", "cost": "itemId", "sla": "id"}[domain]
        guide["examples"].append(command + " --all --fields " + identity)
    if domain == "channel":
        guide["filter_notes"] = (
            "--financial-inst-id submits the bank suggest value exposed "
            "as financialInstCode; --debit-account-name and "
            "--debit-account-no target separate fields. Scope uses "
            "--payout-type."
        )
    elif domain == "cost":
        guide["filter_notes"] = (
            "--bank-account means bankAccountAliasName (deposit alias), "
            "never the full account number. legalEntityCode maps to "
            "legalEntity; financialInstCode maps to financialInst. "
            "transCurrencyCode is transaction currency, not cost "
            "currency. Scope is fixed "
            "costTypeCode=FUND_OUT_CHANNEL_TRANS_FEE; no scope option."
        )
    else:
        guide["filter_notes"] = (
            "--biz-legal-entity is list-only live passthrough: the list "
            "does not return its record field, cached use fails "
            "INVALID_ARGUMENT and its independent filtering effect is "
            "unverified."
        )
        guide["list_to_detail"] = {
            "steps": [
                "dogopencli payment sla baselines list --all",
                "dogopencli payment sla baselines get --id BASELINE_ID",
            ],
            "meaning": (
                "Replace synthetic BASELINE_ID with an id returned by the "
                "list. Detail is an object, never a substitute list row; "
                "cached absence is NOT_FOUND. Cached detail belongs to the "
                "shared SLA refresh snapshot. --live detail is an independent"
                " query and does not establish list-wide completeness or "
                "synchronized timing."
            ),
        }
    return {
        "describe_version": 1,
        "capability": capability,
        "schema_version": 1,
        "data_schema": data_schema(capability),
        "read_guide": guide,
        "query_help": "dogopencli help " + " ".join(path),
    }
