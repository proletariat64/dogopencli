# Collection SLA PR review validation

Observed: 2026-09-26
Scope: general
Status: snapshot

## Sources and scope

Review of [PR #30](https://github.com/proletariat64/dogopencli/pull/30), initially
`88726d5` against `origin/master`, following the operator's pasted Kimi review.
GitHub review threads, review submissions and PR conversation were also read.
Two GitHub inline findings were present, both from Greptile. Business operations
remain read-only; review fixes add no endpoints or arguments.

The earlier independent reviews reported zero findings but missed real defects.
Those reports describe that review run, not proof that this PR had no defects.
This follow-up supersedes its completion claim for the affected paths.

## Standards findings

| Finding | Assessment and disposition |
| --- | --- |
| Documentation index omitted reports and ADR 0008 | Confirmed. Index now includes all four branch research reports, ADR 0008, spec #27 and this review record. ADR 0006/0007 do not exist in the repository; no placeholder links added. |
| Documentation guidance still called collection cost-only and SLA deferred | Confirmed. Updated the tree and scope text, with an explicit pointer to authoritative root AGENTS.md scope. |
| Approximately 200 lines of CLI plumbing duplicate cost flow | Similar orchestration exists, but the proposed wholesale extraction is deferred. Cost publishes list rows; SLA validates and publishes distinct list/detail pairs, checks all cached pairs, and confirms absence only from complete scope. Shared transport, collection, cache reads/publication, display options, metadata and emitters are already reused. A generalized workflow would broaden this correctness patch without resolving either demonstrated bug. |
| Duplicate envelope parsing and numeric ID sorting | Envelope parsing is identical and is extracted into a shared helper with existing messages/behavior preserved. Sorting is not identical: SLA permits numeric ordering only for ASCII digits and uses original-string tie-breaking, while cost has different Unicode/tie behavior. Keep those domain ordering functions separate to preserve payment/cost behavior. |
| SLA parser tests not in unit directory | Not a specification violation: #27 explicitly selects public CLI + fake CDP + real SQLite, avoiding unnecessary new seams. Add regression cases there, checking observable failures and snapshot retention. No mirror-image parser unit tests added merely to change directory placement. |

## Spec findings

| Finding | Assessment and disposition |
| --- | --- |
| Permission failures not distinctly surfaced | Partly correct: there is no dedicated permission error code. However HTTP 403 is preserved in `error.message`, with failure exit, `BUSINESS_QUERY_FAILED`, no retry and no empty/NOT_FOUND result. #28 requires these failures to be distinct **from valid empty or confirmed missing records**, not a unique code for every failure subtype. Keep the existing shared error contract; strengthen CLI assertions and document the distinction. HTTP 401 stays AUTH_REQUIRED. Backend-specific permission envelopes remain unverified and cannot safely be inferred from arbitrary error prose. |
| WAL initialization fix changes shared cache | Confirmed cross-plugin fix, retained as an acceptance-discovered defect, not an unrelated refactor. The baseline race was reproduced; the retry is limited to cold WAL initialization and bounded. Prior acceptance included 112 cache/payment-cost/collection-SLA tests, 200 paired cold starts and the full 641-test suite. This follow-up reruns the full suite including payment and collection-cost regressions. |
| VA terminology and deep survey are outside #27 | Supporting research predates #27 and was explicitly requested by the operator. Retained as authorized sanitized evidence, with no VA commands or capability in this implementation. The PR description discloses that scope. |
| Numeric interpretation of stable string IDs undocumented | Ordering does not normalize or replace IDs; original strings remain stored/emitted. Added the exact numeric-first, string tie-break, then lexical ordering rule to public help and ADR 0008. |

## GitHub inline findings

- [Incomplete details pass validation](https://github.com/proletariat64/dogopencli/pull/30#discussion_r4108940400): confirmed. The old intersection-only comparison accepted omitted business fields. Detail validation now requires core field presence and complete nonnull holiday array shapes, including for live get. Pair validation requires every list field except the observed list-only `viewProcessInstanceRequired`, and checks values without replacing the detail with its list row. Explicit null is preserved where nullability is unverified; unknown extensions remain raw.
- [Empty scopes fail acquisition](https://github.com/proletariat64/dogopencli/pull/30#discussion_r4108940405): confirmed against #27/#28's explicit zero-total-success requirement. Accept omitted `resultDataList` only with successful, correctly paged explicit integer zero total. Null, nonzero omission and inconsistent rows remain errors. This is a defensive acceptance rule proven with synthetic SIT; no production empty scope was manufactured or claimed.

## Verification

Baseline regression run reproduced the defects: 21 failed and 3 passed in the
selected 24-case set before fixes. Additional permission evidence tests exercise
HTTP 403 across live list/get and failed detail refresh, checking non-retry, cache
preservation and explicit HTTP status. Unknown denial prose remains sanitized.

After fixes, 58 additional read-only production/local CLI checks passed: refresh
of the current 55 configurations and all details into a new private cache, complete
offline list, all 55 offline details, and one live detail with unchanged cache
digest. No permission/authentication block was observed. These are additional
executions, not new arguments or manufactured production failure cases.

Focused SLA, payment-cost and collection-cost public-CLI SIT: **167 passed in
183.09s**. The final description wording also passed the targeted offline
help/describe test. Follow-up independent Standards and Spec reviews each
reported zero additional actionable findings after verifying the corrections
and explicit dispositions above. Final integrated suite: **669 passed, 23
subtests passed in 263.20s**, including payment/cost/cache regressions. Ruff
lint and formatting (121 files), documentation guard (38 Markdown files), and
whitespace checks passed. Graph refreshed and changes analyzed against
`origin/master`; dynamic CLI test-gap warnings were checked against executed SIT.
Historical UAT is
recorded in [the implementation acceptance report](2026-09-26-collection-sla-implementation-uat.md).
New failure cases use the agreed synthetic SIT seam; they are not counted as new
production UAT. No production records are written to create failure conditions.
