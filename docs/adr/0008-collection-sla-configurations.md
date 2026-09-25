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
paging fallback. No historical count is a permanent invariant.

Refresh fetches the actual detail for each list ID and validates its identity and
all shared fields. It atomically publishes distinct list/detail pairs to
`collection.sla.configs.list:configs:cdp` only after every check. Any error or
interruption preserves the previous snapshot. This is a consistency check, not a
claim of transactional isolation on the backend. Null or invalid live details are
errors; backend not-found behavior remains unverified.

Default queries read only this snapshot. Explicit live queries never modify it or
fall back. Freshness and completeness remain separate quality properties. Display
windows follow stable-ID sorting and do not change completeness. The core slice
has no domain filter options; #29 supplies exact local selectors for both cached
and complete live records without claiming unverified backend filtering semantics.

Preserve raw seconds, all holiday arrays, original timestamps and unknown fields.
Do not map collection field names onto payment models or calculate arrival times.
Validate through public CLI, fake CDP and a real local cache; all exposed arguments
also require sanitized read-only production UAT before full specification acceptance.
