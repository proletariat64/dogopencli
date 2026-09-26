# Collection VA rule implementation and acceptance

Observed: 2026-09-26
Scope: general
Status: snapshot

Specification: [#31](https://github.com/proletariat64/dogopencli/issues/31)
(closed 2026-09-26; publish guarantee amended by ADR 0010). Tickets:
[#32](https://github.com/proletariat64/dogopencli/issues/32) (delivered,
closed), [#33](https://github.com/proletariat64/dogopencli/issues/33) (domain
filters; closed unimplemented, deferred). PR:
[#35](https://github.com/proletariat64/dogopencli/pull/35), merged to master
as `444a7d6`.

## Work plan

- [x] Recheck the native list/detail contract on the dedicated CDP session.
- [x] Implement the capability, failure-mode SIT and documentation slice.
- [x] Run read-only production UAT over every exposed argument.
- [x] Diagnose the refresh blocker, quantify it with a full read-only sweep.
- [x] Amend the publish guarantee and verify the amended behavior.
- [x] Address Greptile/Kimi review findings, merge PR #35, re-run gates on master.
- [x] Execute complete CLI acceptance on the shipped surface (#33 acceptance
  half); close #31–#33 with the deviation of record.

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
| Kimi: #31 prescribed a different remedy (list-only refresh, live-only detail get) | Valid and material | ADR 0010 now names that spec fallback, records why it was rejected, and states that the operator chose this remedy over it on 2026-09-26, making ADR 0010 the amendment of record. The amendment is also recorded in the #31 closing comment. |
| Kimi: `describe` omits the `assignFlows` caveat required by #31 | Valid | `assignInfo` description now carries "an empty `assignFlows` list does not prove assignment history is empty" plus the no-inference rule for counters. Regression test added. |

## Complete CLI acceptance (#33 acceptance half)

#33 combined the domain-filter slice with the final argument-inventory
reconciliation. No filter was ever exposed (#32 shipped without placeholders),
so the filter-dependent criteria were never executable; the acceptance half was
executed against the shipped surface instead: **37 additional read-only checks,
all passed**, with no production writes and no cache modification.

- Argument inventory from `help --format json` matches the accepted set
  exactly: list = `--limit/--offset/--all/--live/--require-fresh/
  --require-complete/--format/--fields`; get = `--id` plus the same six shared
  flags; refresh = none. Every one of the 14 capability arguments has an
  acceptance case in the 88-check UAT above or the 93-case SIT suite; no
  argument shipped without evidence.
- The five authentication-only globals (`--config-dir`, `--verbose`, `--quiet`,
  `--no-color`, `--version`) are rejected with exit 2 on all three VA business
  paths (15 cases).
- All nine filter-candidate flags, including the array-valued `--countries`
  and `--scene-codes`, stay unexposed on list and get (18 cases), and refresh
  rejects a business selector (1 case). Array-valued row fields are therefore
  excluded from filtering outright — no element-matching semantics were
  invented and nothing is stringified.
- Not executed, because no filter exists: per-filter local predicates,
  cached/live predicate agreement, filter-before-windowing composition, and the
  differentiated OR/case/literal-star/null/missing-field SIT. These remain
  valid inputs for a re-scoped filter ticket.

Against #31's minimum argument-level acceptance matrix, every row now has
recorded evidence: list default/`--live` (offline reads with digest unchanged;
live 911-row scope, default 100-row window, `--all`), get `--id`/`--live`
(all 911 offline; live healthy and refused; blank/missing rejection; synthetic
failure distinctions in SIT), refresh (complete list + all details with the
ADR 0010 amendment; offline get for every captured ID; preservation on
simulated failure in SIT), windowing boundaries and conflicts, both quality
flags (fresh success; `CACHE_STALE` in a copied cache; incomplete rejection on
the real partial snapshot), both formats and projections, and help/describe/
navigation with the inherited-global rejections above.

## Master revalidation and explicit argument matrix

On `cf3bc6e` (documentation-only changes since the production UAT on
`444a7d6`), the public help inventory still exposes exactly eight list options,
six get options, and no refresh options. A private copy of the operator snapshot
was used for 984 offline CLI invocations. The sweep returned 840 true details
and 71 `INCOMPLETE_RESULT` responses across all 911 IDs, with no list-row
substitution; all 71 refusal responses were rechecked with explicit exit-code,
error-code and null-data assertions. The first temporary runner incorrectly
expected exit 0 for those 71 known refusals; the corrected recheck found no CLI
failures. Eight additional format/projection assertions passed. The focused VA
SIT passed 93 tests. The private cache digest was unchanged after the offline
and live reads.

| Shipped argument | Executed UAT case and expected result |
| --- | --- |
| list `--limit` | Default 100, one-row and last-row windows; zero rejected. |
| list `--offset` | Second-row, last-row, at-end and beyond-end windows; negative value rejected. |
| list `--all` | All 911 unique rows, no `has_more`; conflict with limit or offset rejected. |
| list/get `--live` | After human SSO recovery, live default list returned 100 of 911; live `--all` returned 911; healthy get returned true detail; refused get returned `BUSINESS_QUERY_FAILED` with null data. |
| list/get `--require-fresh` | Fresh snapshot accepted; both paths returned `CACHE_STALE` with a zero-hour TTL in the private config; stale default read remained available. |
| list/get `--require-complete` | Both paths rejected the real partial snapshot with `INCOMPLETE_RESULT`. |
| list/get `--format` | JSON envelopes and table output accepted on both paths. |
| list/get `--fields` | Single and multiple field projections preserved metadata; unknown field omitted; empty selection rejected. |
| get `--id` | All 911 cached IDs checked; 840 true details, 71 explicit refusals; absent ID returned `NOT_FOUND`; missing and blank IDs rejected. |
| refresh collection va | No options exposed. The full 911-detail production refresh on the unchanged implementation remains the acceptance evidence above: 840 published, 71 refused, exit 1 `INCOMPLETE_RESULT`. |

The five authentication-only globals were rejected on each business path;
nine unshipped filter candidates were rejected on list and get, and refresh
rejected a business selector. These are negative boundary cases, not shipped
arguments. A transient `BROWSER_UNAVAILABLE` preceded an expired session;
after the operator completed the supported headed login, all four live cases
passed. No production write, arbitrary request or JavaScript entry point was
used in this revalidation.

## Issue closure (2026-09-26)

PR #35 merged to master as `444a7d6`; the merge commit's tree is identical to
reviewed commit `dee9678`. Post-merge gates on master: 764 passed, 23 subtests,
Ruff lint and format clean (128 files), doc-guard 42 files.

- **#32 closed as delivered.** Its criterion 5 ("publishes atomically only
  after all checks ... incomplete details preserve the prior snapshot") is
  superseded by ADR 0010 with operator approval: an explicit backend refusal
  publishes `detail=null` with `dataset_complete=false` and refresh exits 1
  `INCOMPLETE_RESULT`; every other failure still preserves the prior snapshot.
- **#31 closed with the same amendment of record** against story 7 and the
  acceptance-matrix refresh row; the matrix is fully reconciled above.
- **#33 closed: acceptance half complete (this section), filter slice
  unimplemented and deferred** at operator direction. Re-scope a new ticket
  from its criteria if filtering is wanted after the platform fix.
- The platform defect report (71 refused rule IDs) is with platform
  engineering, outside Git. A refresh reporting zero refusals is the trigger to
  revisit ADR 0010 tolerance.

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
