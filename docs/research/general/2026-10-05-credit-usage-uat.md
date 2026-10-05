# Credit usage: implementation and production CLI UAT

Observed: 2026-10-05
Scope: general
Status: snapshot

Specification: [#98](https://github.com/proletariat64/dogopencli/issues/98).
The [operator clarification](2026-10-05-credit-usage-semantics.md) and
[reading contract](../../design/liquidity-credit-usage-v0.1.0.md) govern this
slice. It preserves native business data without checking amount, currency,
date, allocation or used/available business rules.

## Implemented behavior

Implementation `77bf820`, integrated as `709a704`, adds
`liquidity cash credit-usage list` and explicit refresh. The native credit line
and all nested account members remain separate source records. Shared flags,
display grouping, both amount families, original strings (including thousands
separators), null, blank, missing and unknown business values are retained.
No totals, exchange rates, account caps, upstream tree nodes or observation times
are inferred. API success, structure, identity, parent link, tenant and pagination
checks remain. Existing credit-lines settings and pool-balances behavior remain
unchanged; credit usage has an independent runtime capture namespace.

The #98 branch now has 77 supported leaves (55 lists and 22 detail/history;
32 settings, 38 runtimes and 7 reference) and 56 unsupported, 133 total.
Two of four candidates are implemented and production-UAT verified: pool balances
and credit usage. Product baselines and investment quotes remain unsupported;
#98 stays open. These counts use the independent v0.2.6 baseline and exclude the
separately unmerged #97 changes. No default-branch merge or release is claimed.

## Production inquiry evidence

The existing dedicated Liquidity browser passed a fresh headless authentication
check. Public CLI UAT ran against `709a704`; the subsequent `37ba822` / `f79e66d`
change only corrected the projection module's documentation of raw-value behavior.

Eight planned CLI steps ultimately passed, with one initial strict-live rejection
and a single same-scope recheck. The successful refresh and live recheck each
returned 84/84 credit lines and 667 members: 35 shared and 49 nonshared lines.
466 members had blank/unknown creditCurrency, preserved without inference.

| Check | Result |
| --- | --- |
| Existing credit-lines strict settings refresh | Complete baseline capture established |
| Existing settings cached read | Baseline records and capture time recorded |
| Credit-usage strict refresh | Complete 84/84 lines, 667 members |
| Cached credit usage | Every projected field and native parent/member identity matches the same response |
| Disconnected credit usage | Same data and fetched_at; a browser factory that raises was never invoked |
| Strict live recheck | Complete 84/84 lines, 667 members; same-response fields/identities match; database and WAL hashes unchanged |
| Existing settings after credit operations | Data and fetched_at unchanged; no runtime usedAmount fields introduced |
| Offline describe | Succeeds without browser access; usage observation time remains unknown |

The first strict-live attempt returned 83 records / 636 members while both native
counts still reported 84. Exactly one parent from the prior complete capture was
absent; the reason is unknown. The CLI correctly returned INCOMPLETE_RESULT with
COUNT_SHORTFALL, and an additional strict cached read proved the complete capture
remained unchanged. One recheck of the exact same query returned 84/84 and passed
the remaining checks. No scope expansion, fallback, invented filter, suppressed
warning or business-value repair was used. This source inconsistency is retained
as evidence; the successful recheck does not prove it can never recur.

Explicit successful empty collection and safe partial/strict publication behavior
are covered with fake CDP. No verified native empty-scope filter exists, so no
production filter was invented. Raw responses, real source amounts and account
identifiers remain private and are excluded from Git and external review payloads.

## Local checks and reviews

201 focused tests passed: 55 credit/cash-forecast tests (including 15 new public
credit CLI tests), 125 existing specification/snapshot/projection/fields/catalog
tests, and 21 pool-balances public CLI regressions. The full suite and other Python
versions were not run. Ruff lint/format and the documentation guard passed.

Independent Spec review found no implementation defects. Standards review found
one low-severity stale module statement about amount validation; `37ba822` corrects
it to explicitly describe the raw credit-usage exception. No functional code
changed in that follow-up.

After explicit user authorization for the credit payload, local Kimi completed
review of `43802bd...c738a73` with no Standards or Spec findings and overall
confidence **4/5**. This was static review only: Kimi did not execute the 201
focused tests or eight-step production UAT reported above. Those remain separate
coordinator-run evidence.

Remote Kimi reviewed the full PR at `c738a73` and found only one low-severity stale
pool-design paragraph that still called credit usage unsupported. This follow-up
corrects that paragraph to the current 2/4 enabled state. Publication, remote
checks and release remain separate from local review and production results.
