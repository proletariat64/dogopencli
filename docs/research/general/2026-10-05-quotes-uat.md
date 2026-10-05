# QUOTED investment quotes: production CLI UAT

Observed: 2026-10-05
Scope: general
Status: snapshot

Specification: [#98](https://github.com/proletariat64/dogopencli/issues/98), operator-confirmed QUOTED-only single-response contract. Implementation tested at `684348e`; this report separates native CLI UAT, local tests, static review and publication. The independent PR branch contains 78 supported/53 unsupported leaves, 131 total, excluding the separate #97 branch. Product-baselines was withdrawn by the operator; quote get remains unsupported. WIN is explicitly excluded because its backend is unimplemented.

## Verified request and source fidelity

A private independent SQLite cache and the dedicated headless Liquidity profile on CDP 9223 were used. Browser control was checked before each network operation; only the verified inquiry transport was used. No business mutations, broader fallback, credential changes or forbidden port were involved.

Populated scope: value dates 2026-01-01 through 2026-10-05. Empty scope: 2026-09-28 through 2026-10-05. Public ISO date arguments map to native YYYYMMDD. Each online operation made exactly one JSON POST `/quotationAnalysis.json`, fixed QUOTED, rowStart=0/pageSize=5000, native timeZone null. The operator-confirmed output time interpretation is UTC+08:00; source strings were not converted.

The populated refresh and live inquiries returned 338 rows with 338 unique quotationOrderId values. All 24 whitelisted fields were compared to the raw response from that same invocation; every source field in the whitelist was retained and every projected value was equal. No prior capture was substituted for this comparison. Native totalCount was absent; output reported_total stayed null, while collected counts describe observed records. The accepted protocol treats this explicit successful single-response dataset as complete without inventing a backend total or looping ignored offsets.

## Nine public CLI steps

| Step | Result |
| --- | --- |
| Populated strict refresh | PASS; 338 records in an independent exact-date-scope capture |
| Populated strict cached list | PASS; all 24 fields and identities matched the same native response |
| Populated list with browser factory disabled | PASS; same records and fetched_at; no browser access |
| Populated strict live list | PASS; same-invocation native fidelity; SQLite database and WAL hashes unchanged |
| Empty strict live list | PASS; explicit success/data=[]; database and WAL hashes unchanged |
| Empty strict refresh | PASS; separate exact-date-scope capture |
| Empty list with browser factory disabled | PASS; complete empty result |
| Populated offline list after empty refresh | PASS; original populated data and fetched_at unchanged |
| Describe with browser factory disabled | PASS; percent quote, minimum-deposit ticketSize, O/N, source UTC+08:00 and unknown curMaxLimitAvailable meaning exposed |

Four native business requests backed these nine CLI steps. Failed protocol/authentication, identity conflicts, identical duplicate partial/strict behavior, invalid public date bounds, WIN rejection and raw unknown/blank/null values are verified with synthetic public CLI/fake-CDP/SQLite tests, not manufactured production failures. No rate arithmetic, tenure/date reconciliation, currency filling or data repair was performed.

## Local validation and review

106 unique focused tests ultimately passed, including 19 new public quote tests. The combined gate initially had 105 passes and one obsolete global list-count assertion; it was corrected to 56, and the complete 13-test capability file passed. Seven public date-input cases also passed on the final implementation. The suite covered quote lifecycle, capability request rejection, existing strategy/benchmark date scopes, snapshot and field descriptions. Ruff lint, formatting of 287 Python files and doc guard passed. No full-suite or multi-Python claim is made.

Independent Standards and Spec reviews found no confirmed actionable findings. The explicitly authorized local Kimi review of `db6fdcd...684348e` completed with no confirmed Standards or Spec findings, confidence 4/5. Its first 15-minute invocation timed out; continuation of the same session produced the final result. This was static review only: shared history-store internals and generated CLI flags were not exhaustively inspected line by line; the executed focused tests and production UAT above supply separate evidence.

## Delivery boundary

Original #98 accounting is three accepted implemented candidates (pool balances, credit usage and QUOTED quotes) and one operator-withdrawn candidate (product baselines). Their production UAT remains separately documented; this quote report does not re-run the earlier two slices. No claim is made that arbitrary larger server datasets have no capacity limit. The accepted finite-range single-response contract and explicit date inputs are the supported behavior.

Raw responses, actual source rates/amounts, bank/account identifiers and credentials remain private and are excluded from Git and external review. Final PR status, remote checks, merge and release are separate steps; this report does not claim a default-branch merge or version release.
