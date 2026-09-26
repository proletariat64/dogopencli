# Collection VA rule partial detail tolerance

Status: accepted for implementation — amends ADR 0009 (issues #31–32)

Production UAT on the live VA rule scope (2026-09-26) fetched one complete
unfiltered 911-row list and then read-only every listed detail. 840 details
succeeded; 71 failed with HTTP 200 and `success=false` carrying one backend
error code, and five financial institutions had every one of their rules fail
while same-period institutions returned zero failures. The refusal is a
platform-side defect on `detail.json`, not a permission, transport, rate,
rule-status or null-result artifact; the list rows themselves are real and
the backend refuses only the detail read. ADR 0009 publishes only after every
detail succeeds, so this defect made the entire snapshot unobtainable — 840
readable details were forfeited to withhold 71.

Reconsideration is therefore limited to ADR 0009's all-or-nothing publish
rule. The observed failure distribution is evidence, not a hardcoded
invariant.

Refresh tolerates exactly one failure class: a detail response whose envelope
is a valid JSON object with HTTP 200 and `success` explicitly `false` — the
backend's declared refusal of that one detail. A missing or non-boolean
`success` is an unknown envelope shape, not a refusal. A refused rule is
published with its real list row and a null `detail`, so list coverage still
reflects the complete backend scope. Every other outcome aborts before
publication and preserves the previous snapshot unchanged: incomplete or
invalid list metadata, transport, authentication, lock and timeout failures,
unexpected HTTP status including 403, `resultObj` null, missing or mismatched,
invalid detail fields, and drift in any shared business field between a list
row and its true detail. A refusal is never stored as a detail, never merged
into the list row, and never attributed to a backend cause the envelope hides.

Quality metadata keeps the ADR 0003 meanings. `backend_complete` stays true
for a partial publish because the list proved complete scope coverage, so a
confirmed absent ID remains `NOT_FOUND`. `dataset_complete` is true only when
no detail was refused. `--require-complete` additionally rejects a snapshot
whose `dataset_complete` is false; this gate is local to VA rules and does not
change shared freshness or completeness semantics for payment or collection
cost and SLA queries.

A partial refresh publishes and then fails with `INCOMPLETE_RESULT` and exit
code 1, naming the counts (for example 840 published of 911 with 71 refused)
in the message rather than reporting success. Per-rule missing detail counts
are observable from `meta.dataset_complete` and from null `detail` values; no
new error code, envelope field or backend error context is introduced, and
`success_document` still withholds backend context.

Cached reads state the gap instead of papering over it. `get` on a rule whose
detail was refused is `INCOMPLETE_RESULT` with a refresh hint — never
`NOT_FOUND` (the rule exists), never a list row substituted for a detail, and
never an implicit refresh or fallback. Explicit live `get` keeps its ADR 0009
behavior and reports `BUSINESS_QUERY_FAILED` for the same refusal; only bulk
acquisition tolerates it.

This tolerance narrows issue #31's "failed refresh preserves the old snapshot"
criterion: the snapshot always reflects the most recent acquisition, not the
best one. If the backend degrades further, a later partial refresh replaces
details an earlier snapshot held; only non-refusal failures keep the previous
snapshot intact.

This tolerance is a response to an observed platform defect and is not a claim
that details are optional for a VA rule. The defect report with the affected
rule IDs went to platform engineering outside this repository; the IDs stay
out of Git. Once a refresh reports zero refusals, revisit whether tolerance
should remain.
