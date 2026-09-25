# Collection SLA configuration inquiries

Status: accepted for implementation — issues #27–29

Collection SLA uses `collection sla configs list/get` and `refresh collection sla`.
It models configuration targets, distinct from payment baselines and measured
order performance. The verified native entry and inquiry evidence are recorded in
[collection SLA research](../research/general/2026-09-23-collection-sla-query.md).

Use the existing shared restricted CDP transport, bounded recovery, offline cache,
output and command discovery. Register only the observed `search.json` POST and
`getDetailBySlaConfigId.json` GET under `/api/fundInSlaConfig/`. The sole production
source is `sources.collection_sla.kind=cdp`; synthetic responses belong to SIT.

The acquisition is one complete unfiltered `pageNo=0,pageSize=1000` request. Accept
only successful envelopes with matching metadata, total count and unique nonempty
string `slaConfigId` values. Overflow/truncation fails rather than inventing a
paging fallback. Explicit zero-total success may omit `resultDataList`; explicit
null or a missing list with a nonzero total fails. This defensive empty-shape
acceptance is tested synthetically, not claimed as observed production behavior.
No historical count is a permanent invariant.

Refresh fetches the actual detail for each list ID and validates its identity and
all list fields except the observed list-only `viewProcessInstanceRequired`.
Details must contain the core selector, SLA target and holiday fields; explicit
nulls remain raw because production nullability is unverified. A nonnull
`holidayLimit` must contain both complete string arrays. Missing fields or malformed
arrays fail validation; unknown fields are preserved. It atomically publishes distinct list/detail pairs to
`collection.sla.configs.list:configs:cdp` only after every check. Any error or
interruption preserves the previous snapshot. This is a consistency check, not a
claim of transactional isolation on the backend. Null or invalid live details are
errors; backend not-found behavior remains unverified.

Default queries read only this snapshot. Explicit live queries never modify it or
fall back. Freshness and completeness remain separate quality properties. Display
windows follow filtering and stable-ID sorting and do not change completeness.
ASCII digit-only IDs sort numerically first, with the original string as a
tie-breaker; other IDs sort lexically. Ordering never changes the stored/output
string ID (including leading zeros).

List selectors map `--business-line` to `businessCategory`, `--entity` to
`legalEntityCode`, `--currency` to `creditorCurrency` and `--region` to
`creditorRegion`. Values are repeatable, nonempty, case-sensitive literal strings;
whitespace-only values are invalid, with no trimming, case normalization or
wildcards. Missing/null fields cannot match. Repeated values use same-field OR;
different fields use AND. These predicates run locally on both cached and
complete live records before sorting/windowing. Live backend requests stay
unfiltered, since independent businessCategory filtering and backend combination
semantics remain unverified. Refresh has no selectors and get selects only by ID.
Matched/display counts remain independent from source freshness/completeness.

Preserve raw seconds, all holiday arrays, original timestamps and unknown fields.
Do not map collection field names onto payment models or calculate arrival times.
Validate through public CLI, fake CDP and a real local cache; all exposed arguments
also require sanitized read-only production UAT before full specification acceptance.

HTTP 401 is `AUTH_REQUIRED`; HTTP 403 remains `BUSINESS_QUERY_FAILED` with
`HTTP 403` retained in the message, is not retried, and never means an empty
scope or `NOT_FOUND`. Unknown backend business-error envelopes stay generic:
no verified collection-specific permission error code is available to classify.

Required detail-field presence is a client completeness policy, supported by the
observed schema and all-detail checks; it is not a permanent backend requiredness
guarantee. Missing keys cannot currently be distinguished from truncated detail,
so they fail with the previous snapshot intact. Explicit null remains distinct
from omission. If legitimate omission is observed, verify and record its contract
before changing this policy; retaining unknown fields does not establish that
known SLA targets can safely be omitted.
