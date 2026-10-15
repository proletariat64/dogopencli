# R06 account intraday CLI UAT

Observed: 2026-10-16
Scope: general
Status: snapshot

This records production inquiry-only public CLI validation of D03 from issue
#191 on code head `6602651958dced5b04f3f35ef30819f9fd192854`. The original four
R06 leaves were merged in PR #192. T0, Hours Maximum and Daily Maximum remain
separately gated; this is not an eight-leaf completion claim. No release or
production business write is included.

## Environment and sample

The CLI used the task-owned bootstrap configuration, headless Chrome, permitted
CDP port 43357 and its existing isolated profile. Authentication was verified
for Liquidity. No credentials, profile contents, raw transaction rows, account
numbers or native money values are included here.

The busy-account sample came from the read-only DI hot-account investigation:
the highest transaction-count HKD context, matched by exact native account
number and currency. Business day 20261010 returned 96 canonical native slots,
95 nonzero. Every amount field remained its native string. The source has no
currency or timezone field; HKD is an account reference, not an invented
statistics field. Explicit alias, entity and bank were supplied.

## Public CLI lifecycle

Fourteen public CLI operations passed:

- Before the first live query, the new D03 slot returned CACHE_MISS.
- Strict live returned 96 rows with complete acquisition. A second offline
  read still returned CACHE_MISS, proving live did not publish the slot.
- Strict refresh reported published=true. Strict default offline replay returned
  the same 96 rows, in the same order, with exact native string values.
- Field projection returned the expected statisticalDate/totalAmount pairs
  without changing acquisition completeness.
- The qualified older-day inquiry returned native empty data in strict live.
  Strict empty refresh reported published=false; the previous nonempty snapshot
  still replayed identically afterward.
- A nonmatching explicit offline alias returned an empty local match with
  complete=false, retaining the distinction from native absence.
- Leaf prune removed the D03 slot and the next offline call returned CACHE_MISS.
  A final strict refresh and offline read restored the exact nonempty snapshot.

Record equality was checked in memory; money was never converted to binary
floats. No synthetic slots or recomputed demand aggregates were published.
Malformed responses, sparse-slot partial/strict handling, null/empty/absent
amounts, authentication failures and query rejection use local fake-CDP tests,
not fabricated production-failure claims.

## Account-autofill boundary

A separately authorized public cash-account refresh was attempted to populate
local autofill. It failed after 846 of 3,718 required details and reported
BUSINESS_QUERY_FAILED with published=false. A bounded follow-up found a
then-current baseline account at ordinal 847 repeatedly returning HTTP 200,
outer resultFlag=false, inner success=false and errorCode999. Neighboring, first
and final account controls succeeded in the same authenticated session. The
underlying backend cause remains unknown.

The existing hard-failure policy preserved the cache; no account was silently
dropped and no cash-only directory was substituted for the composite cache.
The native error was not relabeled as successful emptiness or expired login.
Cache-backed alias-only production autofill therefore remains unverified in
this run. Existing ordered-resolution behavior and its warning/error branches
are covered locally; these explicit-ownership production checks do not prove
every directory-resolution source.

## Local checks and review

The integrated code passed 3,522 tests and 28 subtests. Ruff lint, format and
documentation guards are reported separately from production UAT. Two-axis
review found zero Standards and zero Spec findings for the implemented D03
slice. Manual Open Code Review plugin execution on the code head completed
all eight selected source files with zero findings, no failed files and no
reused reviews. Remote CI and Greptile are separate gates.
