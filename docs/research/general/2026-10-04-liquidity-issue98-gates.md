# Liquidity issue 98: bounded inquiry gates

Observed: 2026-10-04
Scope: general
Status: snapshot

Specification: [#98](https://github.com/proletariat64/dogopencli/issues/98), parent
[#72](https://github.com/proletariat64/dogopencli/issues/72). Independent baseline:
`c15e35f` / v0.2.6, 75 supported and 58 unsupported leaves (133 total).

## Delivery boundary

This change records current native evidence and updates deferred reasons. No
candidate is enabled, no new command or cache contract is introduced, and no
production CLI UAT is claimed. Existing cash pools and credit-lines settings
projections and caches retain their contracts. Issue #98 remains open: evaluating
candidates does not complete their implementation or accept their deferral.

## Current native evidence

The dedicated headless browser on CDP 9223 passed Liquidity authentication.
The current UI bundle SHA256 is
`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`.
Static callers were inspected before bounded inquiry requests. Seven business inquiries were sent: two cash, three baseline and two quote queries.
Raw responses,
identifiers and authentication data remain private; only contract fields and
aggregate counts are recorded here. No mutation, permission repair, forbidden
port, all-history query or alternate business-object fallback was used.

| Candidate | Current bounded inquiry | Remaining gate |
| --- | --- | --- |
| cash pool-balances list | JSON POST `/cashPoolList.json`, BANK, tenant GUAPW3SG, rowStart 0/pageSize 100; success, 43/43 unique pools, 358 members unique within each parent | Parent valueDate does not prove member balance dates or synchronization. Original/equivalent currency association and balance observation contract remain unverified |
| cash credit-usage list | GET `/queryBankCreditLineByParams.json`, tenant GUAPW3SG, JSON-string bankCreditLineQuery with rowStart 0/pageSize 100; success, 84/84 unique lines, 667 members | Shared/merged usage ownership, amount/currency association and actual usage observation time remain unverified |
| network product-baselines list | JSON POST `/api/product/timeliness/payment/getAll.json`, tenant GUAPW3SG, rowStart 0/pageSize 10; RUN, INIT and PAUSE independently succeeded with 0/0 rows | No nonempty schema, typed identity/version or populated completeness proof; empty scopes do not establish global absence |
| investment quotes list | JSON POST `/quotationAnalysis.json`, rowStart 0/pageSize 10, QUOTED and WIN separately, value dates 20260927–20261004, native timeZone null; both success true with data [] and no top-level totalCount | No complete-empty proof, nonempty schema/identity/version or verified date/timezone semantics |

### Pool balances

All 43 parents contain valueDate and configuration gmtModified. Members have no
observed balance date/time field; 9 have nonempty billing configuration and 41
have timeZone. Billing configuration and timeZone do not identify when a balance
was observed. The UI labels parent currency as USD and displays both currency
and bankCurrency for members, with separate equivalent USD columns. This does
not establish the exact native amount/currency association or that parent dates
apply to every member amount. No daily or realtime capability is enabled.

The current CashPoolMaint expansion fetches `/cashPoolDetail.json` independently
by parent id without a balance date. Its initial yesterday-valued moment objects
are not proof of a supported business-date filter on cashPoolList. A separate
cash-pool report component has different endpoints and explicit date formatting;
it was not substituted for this candidate.

### Credit usage

Current date fields are configuration gmtCreate/gmtModified and validity
start/expiry; sampled validity and timezone fields are empty. No reliable usage
observation date/time was found. The UI groups members by mergeFlag and displays
usedCreditAmount once through rowSpan. Repeated member values must not be summed.
That rendering proves a shared display, not accounting ownership, conversion or
observation-time semantics. No field is synthesized from fetched_at or validity.

### Product baselines

RUN, INIT and PAUSE are the three current native UI tabs. The caller expects
`data.data` and `data.totalCount`; these bounded scopes explicitly returned zero
rows. Static table labels describe configured payment entities, countries,
currencies, limits, service windows and product types, not actual payment speed.
No guessed filters, identities or version fields are introduced.

### Quotes

Both native variants succeeded with an empty data array but omitted top-level
totalCount. This is not accepted as complete-empty acquisition. The bounded range
was the native UI default: browser date 20261004, seven days earlier through that
date (20260927–20261004), page width 10. The exact caller reads the named timezone
cookie; it was absent, so timeZone was null. No GMT+08 or environment fallback
was substituted. Two preliminary metadata lookups sent no business inquiry.
No broader date retry was made.

Current source uses JSON POST
`/quotationAnalysis.json`, QUOTED/WIN variants and explicit value-date bounds.
The UI reads top-level data and totalCount; a missing total must not be silently
converted into complete zero rows. Quote records cannot be replaced by quote
groups, RFQs or offers.

## Validation

Candidates evaluated: **4/4**; enabled: **0/4**; deferred: **4/4**. New commands: **0**;
old unsupported leaves enabled: **0**; deferred reasons updated: **4**.

Existing focused discovery/help tests passed: **2 passed, 45 deselected**
(`test_liquidity_cli_sit.py -k "deferred_leaf or kind_in_help"`). Repository Ruff
lint and format checks passed. Documentation guard passed. No synthetic business
fixtures were added to justify unverified contracts. Native probes above are independent of local
fake-CDP testing and are not production acceptance of an enabled CLI leaf.

Historical context:
[Cash/forecast business probe](2026-10-02-cash-forecast-business-probe.md) and
[initial Liquidity probes](2026-10-01-liquidity-live-probes.md).
