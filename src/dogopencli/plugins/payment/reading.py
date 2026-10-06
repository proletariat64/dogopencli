"""Payment reading guidance and schema provider for registered queries."""

from typing import Any

from ...helpspec import BizNode
from . import channel, cost, sla
from .descriptions import data_schema

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


def description(node: BizNode) -> dict[str, Any]:
    """Return payment-owned schema and reading guide fragments."""
    path = node.path
    capability = ".".join(path)
    domain = path[1]
    detail = path[-1] == "get"
    mapping = {
        "channel": channel.FILTER_FIELDS,
        "cost": cost.FILTER_FIELDS,
        "sla": sla.FILTER_FIELDS,
    }[domain]
    command = "dogopencli " + " ".join(path)
    guide: dict[str, Any] = {
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
        "examples": [
            command + (" --id BASELINE_ID" if detail else " --all"),
            command
            + (" --id BASELINE_ID --fields id" if detail else " --limit 20 --offset 0"),
            command
            + (" --id BASELINE_ID" if detail else "")
            + " --require-fresh --require-complete",
        ],
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
            "--account-alias means bankAccountAliasName (deposit alias), "
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
        "schema_version": 1,
        "data_schema": data_schema(capability),
        "read_guide": guide,
    }
