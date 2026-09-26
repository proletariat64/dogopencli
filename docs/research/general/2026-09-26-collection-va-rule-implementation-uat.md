# Collection VA rule implementation and acceptance

Observed: 2026-09-26
Scope: general
Status: snapshot

Specification: [#31](https://github.com/proletariat64/dogopencli/issues/31).
Ticket: [#32](https://github.com/proletariat64/dogopencli/issues/32).

## Work plan

- [x] Recheck the native list/detail contract on the dedicated CDP session.
- [x] Implement the capability, failure-mode SIT and documentation slice.
- [x] Run read-only production UAT over every exposed argument.
- [x] Diagnose the refresh blocker, quantify it with a full read-only sweep.
- [x] Amend the publish guarantee and verify the amended behavior.
- [ ] Run final gates on the integrated branch, review, merge and PR.

## Boundaries

Production business operations stayed inquiry-only: the verified `list.json`
POST and `detail.json` GET under `/ivostro/api/virtualAccountRule/`, plus the
native page reads. Browser port 9222 only; CDP 9330–9340 were never used. No
business create/edit/approve/delete/sync call and no arbitrary request or
JavaScript entry point was exercised. Human SSO stayed human-operated. Rule IDs,
account values, credentials and raw responses stay out of Git; this document
records counts, positions and aggregates only.

## Environment preparation

Every VA command initially returned `CONFIG_ERROR: missing
[sources.collection_va] configuration` because the operator config predated the
README-documented `[sources.collection_va] kind = "cdp"` entry; adding that
documented entry restored the contract. Two further preparation defects were
observed:

- `auth check` reported `authenticated: true, healthy: true` while the session
  was actually expired, then the next real query hit `auth_redirect` to the
  login origin. Because `login` keys its human-flow decision off this probe, a
  false positive short-circuits the only recovery path a human can complete.
- An interrupted `login` left the dedicated profile in headed mode (ownership
  file `mode=headed`), after which `refresh` failed with "target page never
  became ready". Re-running `login` switched the profile back to headless
  and re-verified authentication; no browser state was edited by hand.

## First UAT phase: 24 cases before the blocker

Twenty-three argument-validation cases (empty/missing `--id`, windowing on
`get`, unknown flags, `--limit 0`, negative `--offset`, `--all` conflicts, empty
`--fields`, unknown-field projection) plus one live full-scope list matched
#31 exactly. Offline reads returned `CACHE_MISS` with a refresh hint and left the
four unrelated snapshots untouched.

`refresh collection va` then failed and, under ADR 0009's all-or-nothing
publish, nothing was cached.

## Blocking defect and quantification

Triage used three steps: repeat runs to prove determinism, per-rule
`collection va rules get --live` to isolate whether the failure was global or
row-specific, and raw-envelope inspection of one failing request.

A read-only sweep then fetched the complete list and every detail with no cache
writes: **911 details attempted, 840 succeeded, 71 failed (7.8%)**. All 71
failures were identical in shape — HTTP 200, envelope `success=false`, no
`resultObj`, one backend error name — and never a timeout, transport reset or
permission response. The failures clustered by `financialInst`: five
institutions (2, 3, 4, 12 and 14 rules) had **every** rule fail, several others
failed partially, and seven same-period institutions with at least 20 rules each
had zero failures. Permission, rule status, rate limiting, transport failure and
"null result" explanations were each checked and excluded with the collected
data. The engineer-facing defect report, including the 71 rule IDs, was produced
outside Git for platform engineering; it also asks the platform to expose a
readable reason when `success=false`.

That report is a platform defect. The CLI change below is a tolerance decision,
not a fix.

## Specification amendment

ADR 0009 required every detail to succeed before anything published, so one
platform defect withheld all 840 readable details.
[ADR 0010](../../adr/0010-collection-va-partial-detail-tolerance.md) narrows
that guarantee to one failure class — an explicit `success=false` refusal of a
single detail — and keeps every other failure aborting before publication. A
refused rule publishes its real list row with a null `detail`;
`backend_complete` stays true, `dataset_complete` becomes false,
`--require-complete` rejects such a snapshot for VA rules only, `get` on a
detail-less rule is `INCOMPLETE_RESULT` and never its list row, and live `get`
still reports `BUSINESS_QUERY_FAILED`. A partial refresh publishes and then
exits 1 with `INCOMPLETE_RESULT` naming the counts. `CONTEXT.md` adds the
resulting term 详情拒绝 (Detail Refusal), distinct from a missing record and
from incomplete list coverage.

## Partial publish verification against production

On the amended build, `refresh collection va` returned exit 1 with
`INCOMPLETE_RESULT` and the message
`published 840/911 collection VA rule details; 71 refused by the backend`.
The published snapshot held 911 rows with exactly 71 null details,
`backend_complete=true` and `dataset_complete=false`, and the 71 refused
positions in stable ID order were **identical to the independent read-only
sweep's 71 failure positions** — the tolerated class matched the observed defect
with no extra or missing rule.

| Public surface | Executed acceptance | Outcome |
| --- | --- | --- |
| `refresh collection va` | Actual complete 911-row acquisition plus all details; partial publish, counts and exit status | Pass |
| `list` default, `--all` | 911 rows, unique IDs, stable ID order, `matched_total`, `has_more`, `source=cache` | Pass |
| `get --id` for every ID | All 911 offline reads: 840 details returned, 71 `INCOMPLETE_RESULT` with no data, no anomaly, no list-row substitution | Pass |
| Refusal cross-check | Cached refused set equals the read-only sweep set | Pass |
| `--limit` / `--offset` | `1`, boundary and beyond-end window; `--limit 0` and negative offset rejected; `--all` conflicts rejected | Pass |
| `--require-complete` | Fails `INCOMPLETE_RESULT` on the real partial snapshot for both list and get | Pass |
| `--require-fresh` | Succeeds on the fresh snapshot; `CACHE_STALE` at `ttl_hours=0` in a copied private cache, list and get | Pass |
| Stale snapshot default read | Remains readable with `meta.stale=true`; copy equals the operator snapshot | Pass |
| `--format`, `--fields` | JSON and table for list/get; single/multiple projection with metadata preserved; empty selection rejected; unknown field omitted | Pass |
| `--live` list | Default window 100 rows with `matched_total=911` and `has_more=true`; `--live --all` returns the same 911 scope as the cache | Pass |
| `--live` get | One healthy ID returns its true detail; one refused ID returns `BUSINESS_QUERY_FAILED` with no data — tolerance is never applied to live reads | Pass |
| Absent ID | Confirmed `NOT_FOUND` against the partial snapshot, because list coverage stayed complete | Pass |
| Argument validation | Empty/missing `--id`, windowing on `get`, unknown flag rejected locally | Pass |
| Help, `describe`, navigation | `--help`, `help PATH`, JSON and text forms for list/get/refresh; every surface states the refusal semantics; `describe` for both query leaves; bare group navigation | Pass |

Cache protection was verified rather than assumed: the operator cache digest was
byte-identical before and after every live and offline read, and freshness
rejection used a copied cache under a temporary config so nothing in the real one
moved. Failure shapes that would require breaking production — auth loss, 400/403
at the detail stage, malformed envelopes, interruption, lock contention — remain
synthetic SIT coverage.

## Engineering gates and review

- Public-CLI VA SIT: **92 passed**. One #31-era case asserted that a detail
  business failure always aborts the refresh; ADR 0010 narrows that assertion, so
  it now covers only non-refusal envelope shapes, and new cases cover partial
  publication, the refusal boundary, `--require-complete`, and the
  detail-less `get` answer.
- Full suite after the change: **762 passed, 1 skipped, 23 subtests passed**.
- Ruff lint passed; `ruff format --check` passed over 127 files; documentation
  guard passed over 41 Markdown files.
- Impact analysis on `cli.py`, `va_rule.py` and `cached_query.py` before the
  edits: 68 changed nodes, 474 nodes within two hops, 73 files. The shared
  surface actually touched is `plugins/envelope.py`, whose new predicate is only
  consulted by VA refresh; payment, cost and SLA gate output is unchanged in the
  full suite.

## Review findings and disposition (PR #35)

Greptile reviewed the pushed branch (confidence 4/5, two P2 findings) and an
independent Kimi review reported three standards judgement calls and two spec
findings.

| Finding | Verdict | Action |
| --- | --- | --- |
| Greptile: `describe` still said "any failure preserves the old snapshot" | Valid | `va_rule_reading.py` refresh guidance now states the null-detail partial publish, `INCOMPLETE_RESULT`, and that a partial refresh replaces the snapshot. Regression test added. |
| Greptile: cached `get --id` validates all stored pairs | Valid observation, not material | Measured on the real 911-row snapshot: snapshot read 26 ms, JSON parse 9.6 ms, whole-snapshot validation 1.2 ms. The validation the finding targets costs about 4% of one read, and the coverage and uniqueness checks need every row regardless. No change; single-row lookup would trade a cache-integrity guarantee for microseconds. |
| Kimi: `va_rule.py`, `cli.py` and the SIT file replicate the SLA shape a third time | Valid, deferred | No change in this slice; a shared pair-refresh skeleton is a post-merge refactor candidate. |
| Kimi: `is_business_refusal` name undersells that it raises | Valid | Docstring now says it is not a pure predicate and why an unknown shape still raises `INVALID_RESPONSE`. Name kept: callers read it as a gate on tolerance, which is its only role. |
| Kimi: ADR 0010 cites ADR 0003 for the flag meanings | Valid | Corrected: ADR 0005 records the two flag meanings; ADR 0003 supplies the completeness policy and the all-or-nothing detail-refresh precedent that ADR 0010 narrows. |
| Kimi: #31 prescribed a different remedy (list-only refresh, live-only detail get) | Valid and material | ADR 0010 now names that spec fallback, records why it was rejected, and states that the operator chose this remedy over it on 2026-09-26, making ADR 0010 the amendment of record. The #31 issue itself still needs the matching comment. |
| Kimi: `describe` omits the `assignFlows` caveat required by #31 | Valid | `assignInfo` description now carries "an empty `assignFlows` list does not prove assignment history is empty" plus the no-inference rule for counters. Regression test added. |

## Remaining evidence limits

- The real 911-detail refresh used about 11 minutes of the shared 900-second
  acquisition budget. Scope growth or transient retries can therefore trip
  `TIMEOUT`, which publishes nothing; no budget constant was widened in this
  slice because it is shared with payment and collection queries.
- 911 rows and 71 refusals are a current observation, not an invariant; the
  1000-row page remains observed capacity rather than a server guarantee.
- A refresh always replaces the snapshot with the latest acquisition, so a later
  run with more refusals can lose details an earlier snapshot held. Only
  non-refusal failures preserve the previous snapshot.
- Backend not-found semantics stay unverified: `resultObj=null` on a successful
  envelope remains `INVALID_RESPONSE`, and a refusal is stored as an explicit
  absence of detail, never as a guessed reason.
- `success_document` still hides backend error context, which is the right
  privacy default but made this triage need raw-envelope probing; a
  sanitized-diagnostic follow-up for VA is worth its own ticket, as is the
  `auth check` false positive.
- Institution-level clustering is reported as aggregates only; the identified
  rule IDs live solely in the uncommitted defect report.
