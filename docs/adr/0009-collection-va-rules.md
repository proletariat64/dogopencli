# Collection VA rule inquiries

Status: accepted for implementation — issues #31–32

Collection VA rules use `collection va rules list/get` and
`refresh collection va`. They model the rules that add business dimensions
(entity, scene, area) on top of bank-account VA rules for later VA assignment
matching; they are distinct from bank-account VA rules, VA pools, capacity
monitoring and PTR libraries. The verified native entry and inquiry evidence
are recorded in the
[collection VA rule research](../research/general/2026-09-23-collection-va-rule-query.md)
and the
[contract recheck](../research/general/2026-09-26-collection-va-rule-contract-recheck.md).

Use the existing shared restricted CDP transport, bounded recovery, offline
cache, output and command discovery. Register only the observed `list.json`
POST and `detail.json` GET under `/ivostro/api/virtualAccountRule/`. The sole
production source is `sources.collection_va.kind=cdp`; synthetic responses
belong to SIT.

The acquisition is one complete unfiltered one-based `pageNo=1,pageSize=1000`
request. Accept only successful envelopes whose integer `pageNo`/`pageSize`
echo the request and whose `totalCount` is a nonnegative integer matching the
row count, with unique nonempty string `vaRuleId` values. Overflow beyond one
page, truncation, duplicates or invalid metadata fail with
`INCOMPLETE_RESULT`; no multi-page fallback is verified and none is invented.
Explicit zero-total success may omit `resultDataList`; a null or missing list
with a nonzero total fails. The 1000-row page is an observed capacity at the
current scale, not a server-side guarantee; observed totals (907 at the first
study, 911 at the recheck) are evidence snapshots, never hardcoded invariants.

Refresh fetches the true detail for each list ID through
`detail.json?vaRuleId=` and requires the returned `resultObj` to be a nonnull
object whose `vaRuleId` matches the request. Details must contain the core
business fields (`assembleStrategy`, `assignInfo`, `bankRuleId`,
`clientEntity`, `creditAreas`, `entity`, `memo`, `regionType`, `ruleStatus`,
`sceneCodes`, `vaRuleId`); explicit null values remain raw because production
nullability is unverified. `vaWarningInfo` is optional — not every observed
detail carries one — so notification content is never required, and its
contact details never enter fixtures, logs or docs. Each list row must agree
with its true detail on all eight shared business fields. List rows and
details stay distinct raw objects, and the differently named list `countries`
and detail `creditAreas` are never merged, renamed or equated. Refresh
atomically publishes the validated rule/detail pairs to
`collection.va.rules.list:rules:cdp` only after every check. Any error or
interruption preserves the previous snapshot. This is a consistency check, not
a claim of transactional isolation on the backend.

Default queries read only this snapshot. Explicit live queries never modify it
or fall back. Freshness and completeness remain separate quality properties.
The list exposes no filters; live fetches the complete unfiltered scope, then
stable-ID sorting precedes display windowing: ASCII digit-only IDs sort
numerically with the original string as tie-breaker, other IDs sort lexically
afterward, and stored/output string IDs never change. Refresh stays
unfiltered; get selects only by ID.

A null or invalid live detail — including a successful envelope with
`resultObj=null` — is `INVALID_RESPONSE`; backend not-found semantics remain
unverified. A confirmed absent ID in a complete local snapshot is `NOT_FOUND`,
following the payment SLA baseline and collection SLA configuration
precedents; absence cannot be confirmed in an incomplete snapshot, which is
`INCOMPLETE_RESULT`. HTTP 401 is `AUTH_REQUIRED`; HTTP 403 remains
`BUSINESS_QUERY_FAILED` with `HTTP 403` retained in the message, is not
retried, and never means an empty scope or `NOT_FOUND`. Unknown backend
business-error envelopes stay generic: no verified VA-specific permission
error code is available to classify.

The related bank-account rule lookup (`bankAccountVaRule/detail.json`) that
the native detail page issues is excluded: the single observation returned
`resultObj=null`, its semantics are unverified, and it is never queried or
merged into a VA rule detail. `bankRuleId` references that distinct object; it
is not a VA rule ID and is never accepted as one.

Preserve raw business fields, original timestamps and unknown extensions; do
not rename fields across the list/detail boundary or infer assignment state
from `assignInfo` counters. Validate through public CLI, fake CDP and a real
local cache; all exposed arguments also require sanitized read-only production
UAT before full specification acceptance.

Required detail-field presence is a client completeness policy, supported by
the observed schema and all-detail checks; it is not a permanent backend
requiredness guarantee. Missing keys cannot currently be distinguished from
truncated detail, so they fail with the previous snapshot intact. If
legitimate omission is observed, verify and record its contract before
changing this policy; retaining unknown fields does not establish that known
business fields can safely be omitted.
