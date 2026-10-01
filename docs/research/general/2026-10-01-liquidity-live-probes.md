# Liquidity v0.2.1 live inquiry evidence

Observed: 2026-10-01
Scope: general
Status: snapshot

## Method and coverage

All 134 original business leaves were audited individually; there are 400 business-request observations across 183 leaf/variant cases and 99 distinct native probe labels. These counts include source-discovered variants outside the original draft and do not mean every candidate succeeded. Unsupported or unproven read-only requests were not sent. Status counts: {'observed': 67, 'failed': 6, 'empty-scope': 14, 'projection-pending': 5, 'unverified': 30, 'filter-unverified': 2, 'semantics-pending': 1, 'identity-unavailable': 8, 'partial-permission': 1}. Kind counts after live-source corrections: {'reference': 14, 'runtimes': 65, 'settings': 55}.

Observed UTC interval: `2026-10-01T00:03:14.851Z` through `2026-10-01T00:16:53.897Z`. Authenticated production origin: `https://iliquidity.alipay.com`, tenant `GUAPW3SG`. Date scopes include 2026-10-01 and one bounded previous-day comparison, 2026-09-30; ledger comparisons include 2026-09-29. Selected GMT+08 comes from the source-supported environment/default, not a claim about the user's saved preferences. Entity/account filters use accessible native metadata. These observations are scoped to the signed-in user and selected filters.

Reviewed native UI inquiry caller and request wrapper before each request. GET and POST were both used with their exact query/form/JSON encoding. Three sequential repeats were attempted for successful base cases; failures stopped early. Later date and offset comparisons normally have one repeat. Timing is browser fetch wall time through decoded response completion, with first-byte timing retained privately. Report median/min/max and sample count; no p95 claim. Byte counts are decoded HTTP response payload bytes, not compressed wire transfer. Each request had a 25-second timeout and 5 MiB streaming cap. Requested first pages were normally 10 rows, but actual row counts are reported. No business mutation, report export, regression execution, capability test, decision generation, or external DI query occurred. All 103 internal leaf page-metadata queries succeeded; four external DI iframe leaves were excluded: ActBal, ActLog, ActDailyLog, HistoricalAccuracyMonitor.

Response field types below are observations of the first three records per response, recursive through depth seven. They are samples, not complete schemas or nullability guarantees. Counts use the primary record container, never a sum of nested arrays. Detail envelope count=0 does not mean the detail is absent. Backend totals are reported scope totals and are not independently proven complete. Private raw responses and source snippets remain in ignored `tmp/`, with directory mode 0700 and file mode 0600. This report contains field names and measurements only.

## Findings

- Products ignored `rowStart`: requests at offsets 0 and 10 both returned the same 908 complete row objects, 3,929,601 decoded bytes. Treat this observed route as a single response, not an offset collector. The two keys `incrementProductId` and `incrementProductCode` each had 908 unique values in the sample. This does not prove all tenant catalogue scopes are complete.
- Ordinary cash accounts and wallet-flag accounts returned identical sampled records and totals. Do not expose a verified wallet filter or reuse that data as wallet balances.
- Calendars returned about 493 KB for ten primary records because nested day lists are substantial. Pools returned about 229 KB for ten primary records. Nested size and object amplification matter independently of row count.
- Two-page comparisons sometimes overlapped exact row objects, including balances, forecast results/accuracy, realtime network, transfer rules, SLA and countries. Deduplication alone cannot prove no missing rows; a stable identity, ordering and convergence contract is required before complete refresh.
- Province and treasury-transfer queries returned HTTP 200 with business failure and named missing privileges. Account detail, quote-group detail, RFQ and per-account capacity also returned business failures. Credit-line query hit the 25-second timeout. No bypass or invented retry payload was used.
- Empty current-day prices/returns/decisions/transfers did not prove empty datasets. Previous-day probes returned populated client-price, cost-price, factor-value, return, decision, transfer, asset-trade and intraday-statement schemas. Other empty scopes remain unproven for record schema.
- Holdings detail uses native `investmentNo` as the request field `orderId`, via the actual PortfolioDetail route. Compound detail uses `orderNo` as `compoundOrderNo`; forward detail uses `orderNo` as `forwardId`. Ledger customer detail requires the compound native `customerNo` and `version`. These are typed mappings, not interchangeable generic IDs.
- Product definitions contain configured interest rules, process/status and version fields. Product list/get/history kinds are corrected to `settings`. Entity-maintenance list/get are also `settings`, consistent with maintained entity information. The original domain-oriented command paths remain stable.

## Actual SQLite cache measurement

The existing JSON-record SQLite cache was exercised against the actual 908 product records in a separate private database using existing Cache.read/Cache.publish. Database size: 5,005,312 bytes. Read/decode/identity validation/currency filter/deterministic sort/100-row window took 25.7, 21.8 and 24.0 ms. Sort/canonical hash/row serialization took 320, 328 and 325 ms; atomic publication took 34.7, 32.8 and 32.5 ms. Incremental Python tracemalloc peak was 19,004,291 bytes, excluding native SQLite allocations and process RSS. Source fetch was 10,785 ms for the measured source response. This is same-process evidence; it excludes CLI startup, complete domain parsing, concurrent readers and failure tests. It supports SQLite for this actual settings scope. It supplies no million-row capacity result.

Current cache stores each row as JSON text, then fetches and decodes an entire namespace before Python filtering/sorting/limiting. Runtime scale risk therefore includes application materialization, not just SQLite capacity. There is no measured justification for the earlier suggested 1M-row/1-GiB threshold; that suggestion is withdrawn. No storage-engine change is included in this phase. No package or native binary was downloaded or duplicated.

## Accepted policy after the final design interview

On 2026-10-01 the user selected a product cap of 1,000,000 retained primary records per liquidity leaf. Time-series overflow evicts oldest records with a warning and explicit retained coverage; non-time-series overflow fails refresh. This supersedes the earlier no-cutoff proposal as a product decision, not as a measured SQLite capacity finding. The 908-record benchmark and all live observations above are unchanged. See [ADR 0017](../../adr/0017-liquidity-one-million-record-retention.md).

## Every original leaf

Statuses are evidence states, not delivered CLI support. `observed` still requires release gates; all other states carry specific unresolved boundaries.

| Candidate leaf after `dogopencli liquidity` | Kind | Evidence status |
| --- | --- | --- |
| `cash accounts list` | `reference` | observed |
| `cash accounts get` | `reference` | failed |
| `cash balances list` | `runtimes` | observed |
| `cash statements intraday list` | `runtimes` | observed |
| `cash statements end-of-day list` | `runtimes` | empty-scope |
| `cash groups list` | `settings` | projection-pending |
| `cash groups get` | `settings` | unverified |
| `cash group-balances list` | `runtimes` | projection-pending |
| `cash wallets list` | `reference` | filter-unverified |
| `cash wallets get` | `reference` | filter-unverified |
| `cash wallet-balances list` | `runtimes` | unverified |
| `cash pools list` | `settings` | projection-pending |
| `cash pools get` | `settings` | projection-pending |
| `cash pool-balances list` | `runtimes` | projection-pending |
| `cash credit-lines list` | `settings` | failed |
| `cash credit-lines get` | `settings` | unverified |
| `cash credit-usage list` | `runtimes` | unverified |
| `cash waterlevels list` | `runtimes` | observed |
| `forecast results list` | `runtimes` | observed |
| `forecast results get` | `runtimes` | unverified |
| `forecast cashflows list` | `runtimes` | observed |
| `forecast accuracy list` | `runtimes` | semantics-pending |
| `forecast adjustments list` | `runtimes` | observed |
| `operations demands list` | `runtimes` | empty-scope |
| `operations demands get` | `runtimes` | identity-unavailable |
| `operations decisions list` | `runtimes` | observed |
| `operations decisions get` | `runtimes` | observed |
| `operations decisions history` | `runtimes` | observed |
| `operations executions list` | `runtimes` | empty-scope |
| `operations executions get` | `runtimes` | identity-unavailable |
| `operations rule-status list` | `runtimes` | unverified |
| `operations transfers list` | `runtimes` | observed |
| `operations transfers get` | `runtimes` | observed |
| `operations swaps list` | `runtimes` | empty-scope |
| `operations swaps get` | `runtimes` | unverified |
| `operations forwards list` | `runtimes` | observed |
| `operations forwards get` | `runtimes` | observed |
| `operations asset-trades list` | `runtimes` | observed |
| `operations asset-trades get` | `runtimes` | unverified |
| `operations prefunds list` | `runtimes` | observed |
| `operations prefunds get` | `runtimes` | observed |
| `investment products list` | `settings` | observed |
| `investment products get` | `settings` | observed |
| `investment products history` | `settings` | observed |
| `investment offers list` | `runtimes` | unverified |
| `investment holdings list` | `runtimes` | observed |
| `investment holdings get` | `runtimes` | observed |
| `investment transactions list` | `runtimes` | observed |
| `investment transactions get` | `runtimes` | observed |
| `investment investable-funds list` | `runtimes` | empty-scope |
| `investment interest-rates list` | `runtimes` | observed |
| `investment interest-rates get` | `runtimes` | unverified |
| `investment rfqs list` | `runtimes` | failed |
| `investment rfqs get` | `runtimes` | identity-unavailable |
| `investment quotes list` | `runtimes` | empty-scope |
| `investment quotes get` | `runtimes` | unverified |
| `investment quote-groups list` | `settings` | observed |
| `investment quote-groups get` | `settings` | failed |
| `investment quote-sessions list` | `runtimes` | unverified |
| `investment strategies list` | `settings` | observed |
| `investment strategies get` | `settings` | observed |
| `investment benchmarks list` | `settings` | observed |
| `investment benchmarks get` | `settings` | unverified |
| `investment benchmark-values list` | `runtimes` | empty-scope |
| `investment strategy-results list` | `runtimes` | empty-scope |
| `investment strategy-results get` | `runtimes` | identity-unavailable |
| `investment compound-ledger list` | `runtimes` | observed |
| `investment compound-ledger get` | `runtimes` | observed |
| `investment returns list` | `runtimes` | observed |
| `risk events list` | `runtimes` | empty-scope |
| `risk events get` | `runtimes` | identity-unavailable |
| `risk metrics list` | `runtimes` | observed |
| `risk anomalies list` | `runtimes` | empty-scope |
| `risk anomalies get` | `runtimes` | identity-unavailable |
| `risk account-capacity list` | `runtimes` | failed |
| `risk thresholds list` | `settings` | observed |
| `risk thresholds get` | `settings` | observed |
| `risk sla list` | `settings` | observed |
| `risk sla get` | `settings` | observed |
| `rules transfer list` | `settings` | observed |
| `rules transfer get` | `settings` | observed |
| `rules treasury-transfer list` | `settings` | failed |
| `rules treasury-transfer get` | `settings` | identity-unavailable |
| `rules funding list` | `settings` | observed |
| `rules funding get` | `settings` | unverified |
| `rules operation list` | `settings` | observed |
| `rules operation get` | `settings` | observed |
| `rules realtime list` | `settings` | observed |
| `rules realtime get` | `settings` | observed |
| `rules action-mapping list` | `settings` | observed |
| `rules action-mapping get` | `settings` | unverified |
| `rules fx-settlement list` | `settings` | observed |
| `rules fx-settlement get` | `settings` | unverified |
| `rules notification list` | `settings` | observed |
| `rules notification get` | `settings` | observed |
| `rules forecast list` | `settings` | observed |
| `rules forecast get` | `settings` | unverified |
| `rules waterlevel list` | `settings` | observed |
| `rules waterlevel get` | `settings` | observed |
| `rules monitoring list` | `settings` | empty-scope |
| `rules monitoring get` | `settings` | identity-unavailable |
| `network routes list` | `settings` | unverified |
| `network routes get` | `settings` | unverified |
| `network bank-baselines list` | `settings` | observed |
| `network bank-baselines get` | `settings` | observed |
| `network product-baselines list` | `settings` | empty-scope |
| `network product-baselines get` | `settings` | unverified |
| `network account-capabilities list` | `settings` | observed |
| `network account-capabilities get` | `settings` | observed |
| `ledger customers list` | `reference` | observed |
| `ledger customers get` | `reference` | observed |
| `ledger accounts list` | `reference` | observed |
| `ledger accounts get` | `reference` | unverified |
| `ledger balances list` | `runtimes` | observed |
| `pricing client-prices list` | `runtimes` | observed |
| `pricing client-prices get` | `runtimes` | unverified |
| `pricing cost-prices list` | `runtimes` | observed |
| `pricing factors list` | `settings` | unverified |
| `pricing factors get` | `settings` | unverified |
| `pricing factor-values list` | `runtimes` | observed |
| `pricing strategies list` | `settings` | observed |
| `pricing strategies get` | `settings` | unverified |
| `pricing valuations list` | `runtimes` | empty-scope |
| `pricing valuations get` | `runtimes` | unverified |
| `pricing bills list` | `runtimes` | empty-scope |
| `pricing bills get` | `runtimes` | unverified |
| `reference entities list` | `settings` | observed |
| `reference entities get` | `settings` | unverified |
| `reference banks list` | `reference` | observed |
| `reference banks get` | `reference` | unverified |
| `reference areas list` | `reference` | partial-permission |
| `reference business-lines list` | `reference` | observed |
| `reference calendars list` | `reference` | observed |
| `reference calendars get` | `reference` | unverified |

## Candidate limitations

- `cash accounts get`: Business failure or transport timeout; do not publish as usable inquiry.
- `cash statements end-of-day list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `cash groups list`: Same native response observed; separate settings/runtime projections and identities must be validated.
- `cash groups get`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.
- `cash group-balances list`: Same native response observed; separate settings/runtime projections and identities must be validated.
- `cash wallets list`: Native wallet flag returned identical first-page account data; wallet membership not established.
- `cash wallets get`: Native wallet flag returned identical first-page account data; wallet membership not established.
- `cash wallet-balances list`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.
- `cash pools list`: Same native response observed; separate settings/runtime projections and identities must be validated.
- `cash pools get`: Same native response observed; separate settings/runtime projections and identities must be validated.
- `cash pool-balances list`: Same native response observed; separate settings/runtime projections and identities must be validated.
- `cash credit-lines list`: Business failure or transport timeout; do not publish as usable inquiry.
- `cash credit-lines get`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.
- `cash credit-usage list`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.
- `forecast results get`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.
- `forecast accuracy list`: Populated native accuracy query observed; accuracy measure/time semantics not established by identical-looking record schema.
- `operations demands list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `operations demands get`: Native getter reviewed; no usable observed parent row with its typed identity.
- `operations executions list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `operations executions get`: Native getter reviewed; no usable observed parent row with its typed identity.
- `operations rule-status list`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `operations swaps list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `operations swaps get`: UI getSwapOrderDetail is local Redux reducer copying complete list row; no backend detail call. Read exact row by verified dealId identity only after source row schema validates.
- `operations asset-trades get`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `investment offers list`: ProductPoolView listing reference product rows may include dated/rate terms. Must inspect live schema and separate runtime fields before exposing offers; no independent inquiry identified.
- `investment investable-funds list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `investment interest-rates get`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `investment rfqs list`: Business failure or transport timeout; do not publish as usable inquiry.
- `investment rfqs get`: Native getter reviewed; no usable observed parent row with its typed identity.
- `investment quotes list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `investment quotes get`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `investment quote-groups get`: Business failure or transport timeout; do not publish as usable inquiry.
- `investment quote-sessions list`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `investment benchmarks get`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `investment benchmark-values list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `investment strategy-results list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `investment strategy-results get`: Native getter reviewed; no usable observed parent row with its typed identity.
- `risk events list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `risk events get`: Native getter reviewed; no usable observed parent row with its typed identity.
- `risk anomalies list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `risk anomalies get`: Native getter reviewed; no usable observed parent row with its typed identity.
- `risk account-capacity list`: Business failure or transport timeout; do not publish as usable inquiry.
- `rules treasury-transfer list`: Business failure or transport timeout; do not publish as usable inquiry.
- `rules treasury-transfer get`: Native getter reviewed; no usable observed parent row with its typed identity.
- `rules funding get`: No native caller, safe payload and identity contract established.
- `rules action-mapping get`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.
- `rules fx-settlement get`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.
- `rules forecast get`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.
- `rules monitoring list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `rules monitoring get`: Native getter reviewed; no usable observed parent row with its typed identity.
- `network routes list`: Native same response provides mixedconfig/runtime fields; choose kind-specific projection and confirm identity.
- `network routes get`: Native same response provides mixedconfig/runtime fields; choose kind-specific projection and confirm identity.
- `network product-baselines list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `network product-baselines get`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.
- `ledger accounts get`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `pricing client-prices get`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `pricing factors list`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `pricing factors get`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `pricing strategies get`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `pricing valuations list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `pricing valuations get`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `pricing bills list`: Query succeeded only for tested dates/scopes; row schema and detail identity remain unverified.
- `pricing bills get`: Native UI mapping and exact bounded payload not yet proven; do not probe inferred request.
- `reference entities get`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.
- `reference banks get`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.
- `reference areas list`: Cities and countries queried; province denied ILIQUIDITY_PARA_PROVINCE_QUERY.
- `reference calendars get`: No verified independent leaf contract; proposed draft leaf must remain unavailable until native caller/identity verified. Existing list-row view alone does not establish separate server get contract.

## Request measurements

| Native probe leaf / variant | Result | Transport | Primary rows / backend total | Decoded bytes | Median [min, max] ms; repeats |
| --- | --- | --- | --- | --- | --- |
| `cash accounts get` / None | failed | `GET /queryaccountbyid.json` | ? / ? | 371 | 258.7 [258.7, 258.7]; n=1 |
| `cash accounts list` / None | populated | `GET /queryintnalbkactlist.json` | 10 / 3691 | 9981 | 795.2 [737.6, 872.1]; n=3 |
| `cash accounts list` / offset10 | populated | `GET /queryintnalbkactlist.json` | 10 / 3691 | 10064 | 760.2 [760.2, 760.2]; n=1 |
| `cash balances list` / None | populated | `POST /latestBalanceQuery.json` | 10 / 12 | 14626 | 1925.3 [1846, 1964.6]; n=3 |
| `cash balances list` / offset10 | populated | `POST /latestBalanceQuery.json` | 2 / 12 | 3010 | 1864 [1864, 1864]; n=1 |
| `cash credit-lines list` / None | failed | `GET /queryBankCreditLineByParams.json` | ? / ? | ? | 25004.6 [25004.6, 25004.6]; n=1 |
| `cash groups list` / None | populated | `GET /bankAccountGroupQuery.json` | 1 / 1 | 2207 | 465.6 [360.3, 1089.8]; n=3 |
| `cash groups list` / offset10 | empty | `GET /bankAccountGroupQuery.json` | 0 / 1 | 147 | 307.8 [307.8, 307.8]; n=1 |
| `cash pools configuration list` / None | populated | `POST /cashPoolList.json` | 10 / 43 | 228952 | 5360 [5194.9, 5407.8]; n=3 |
| `cash pools configuration list` / offset10 | populated | `POST /cashPoolList.json` | 10 / 43 | 69881 | 2058.2 [2058.2, 2058.2]; n=1 |
| `cash pools get` / None | populated | `POST /cashPoolDetail.json` | 1 / ? | 3910 | 1314.8 [1228, 1400.1]; n=3 |
| `cash statements end-of-day list` / None | empty | `POST /bankAccountDetailDayQuery.json` | 0 / 0 | 149 | 268.9 [257.7, 294.5]; n=3 |
| `cash statements end-of-day list` / previous-day:None | empty | `POST /bankAccountDetailDayQuery.json` | 0 / 0 | 149 | 408 [408, 408]; n=1 |
| `cash statements intraday list` / None | empty | `POST /bankAccountDetailQuery.json` | 0 / 0 | 149 | 267.6 [250, 286.2]; n=3 |
| `cash statements intraday list` / previous-day:None | populated | `POST /bankAccountDetailQuery.json` | 5 / 5 | 2845 | 482.4 [482.4, 482.4]; n=1 |
| `cash wallets list` / None | populated | `GET /queryintnalbkactlist.json` | 10 / 3691 | 9981 | 665.6 [659.5, 751.7]; n=3 |
| `cash waterlevels list` / None | populated | `POST /bufferReportList.json` | 1 / 1 | 1741 | 384.9 [383.8, 386.2]; n=3 |
| `cash waterlevels list` / offset10 | empty | `POST /bufferReportList.json` | 0 / 1 | 150 | 387.9 [387.9, 387.9]; n=1 |
| `forecast accuracy list` / None | populated | `GET /bankCashForecastRecordAccuracyQuery.json` | 10 / 4855 | 7847 | 1591.7 [1576.6, 1603]; n=3 |
| `forecast accuracy list` / offset10 | populated | `GET /bankCashForecastRecordAccuracyQuery.json` | 10 / 4855 | 7857 | 1591.6 [1591.6, 1591.6]; n=1 |
| `forecast adjustments list` / None | populated | `GET /bankCashForecastAdjustmentQuery.json` | 10 / 13 | 4612 | 376.5 [369, 2667.8]; n=3 |
| `forecast adjustments list` / offset10 | populated | `GET /bankCashForecastAdjustmentQuery.json` | 3 / 13 | 1507 | 340.7 [340.7, 340.7]; n=1 |
| `forecast cashflows list` / None | empty | `GET /queryCashFlowData.json` | 0 / ? | 190 | 549.8 [529.4, 567.3]; n=3 |
| `forecast cashflows list` / previous-day:None | populated | `GET /queryCashFlowData.json` | 1 / ? | 871 | 828.9 [828.9, 828.9]; n=1 |
| `forecast results list` / None | populated | `GET /bankCashForecastRecordQuery.json` | 10 / 4855 | 7847 | 1839.8 [1622.3, 4046.8]; n=3 |
| `forecast results list` / offset10 | populated | `GET /bankCashForecastRecordQuery.json` | 10 / 4855 | 7857 | 1796.8 [1796.8, 1796.8]; n=1 |
| `investment benchmark-values list` / history | empty | `POST /queryStrategyBenchmarkList.json` | 0 / 0 | 148 | 303.1 [296.2, 303.8]; n=3 |
| `investment benchmark-values list` / previous-day:history | empty | `POST /queryStrategyBenchmarkList.json` | 0 / 0 | 148 | 124 [124, 124]; n=1 |
| `investment benchmarks list` / offset10 | populated | `POST /queryStrategyBenchmarkRuleList.json` | 10 / 50 | 4202 | 364 [364, 364]; n=1 |
| `investment benchmarks list` / rules | populated | `POST /queryStrategyBenchmarkRuleList.json` | 10 / 50 | 5049 | 303.3 [293.8, 329.3]; n=3 |
| `investment compound-ledger get` / None | populated | `POST /compoundOrderDetail.json` | 1 / ? | 4370 | 361.6 [272, 380]; n=3 |
| `investment compound-ledger list` / None | populated | `POST /compoundOrderList.json` | 10 / 16 | 7351 | 328.4 [323.8, 338.1]; n=3 |
| `investment compound-ledger list` / offset10 | populated | `POST /compoundOrderList.json` | 6 / 16 | 4392 | 470.3 [470.3, 470.3]; n=1 |
| `investment holdings get` / None | populated | `POST /queryIncrementOrderDetail.json` | 1 / ? | 4275 | 341.6 [329.1, 357.7]; n=3 |
| `investment holdings list` / None | populated | `POST /portfolioQueryList.json` | 10 / 1076 | 11837 | 1161.6 [1074.9, 1163.6]; n=3 |
| `investment holdings list` / offset10 | populated | `POST /portfolioQueryList.json` | 10 / 1076 | 11761 | 1195.8 [1195.8, 1195.8]; n=1 |
| `investment interest-rates list` / bank-quoted | empty | `POST /queryEnquireRateList.json` | 0 / 0 | 148 | 516 [490.1, 529.7]; n=3 |
| `investment interest-rates list` / market | populated | `POST /incrementBaseRateList.json` | 4 / 4 | 1039 | 342 [265.9, 434.4]; n=3 |
| `investment interest-rates list` / offset10 | empty | `POST /incrementBaseRateList.json` | 0 / 4 | 148 | 149.5 [149.5, 149.5]; n=1 |
| `investment interest-rates list` / previous-day:bank-quoted | empty | `POST /queryEnquireRateList.json` | 0 / 0 | 148 | 370.8 [370.8, 370.8]; n=1 |
| `investment investable-funds list` / None | empty | `POST /queryInvestableFundList.json` | 0 / 0 | 149 | 288 [276.8, 289.3]; n=3 |
| `investment investable-funds list` / previous-day:None | empty | `POST /queryInvestableFundList.json` | 0 / 0 | 149 | 493.8 [493.8, 493.8]; n=1 |
| `investment products get` / None | populated | `POST /incrementProductDetail.json` | 1 / ? | 7357 | 128 [123.7, 255.3]; n=3 |
| `investment products history` / None | populated | `POST /incrementProductHistoryQuery.json` | 5 / ? | 24591 | 309.6 [303, 324.9]; n=3 |
| `investment products list` / None | populated | `POST /incrementProductsPage.json` | 908 / 908 | 3929601 | 10760.5 [10550.8, 10785.1]; n=4 |
| `investment products list` / offset10 | populated | `POST /incrementProductsPage.json` | 908 / 908 | 3929602 | 10279.6 [10279.6, 10279.6]; n=1 |
| `investment quote-groups get` / None | failed | `POST /queryQuotationDetail.json` | ? / ? | 324 | 106.9 [106.9, 106.9]; n=1 |
| `investment quote-groups list` / None | populated | `POST /queryQuotationGroup.json` | 54 / ? | 54204 | 137.2 [133.8, 165.6]; n=3 |
| `investment quotes list` / QUOTED | empty | `POST /quotationAnalysis.json` | 0 / ? | 98 | 1497.7 [1485.7, 1525]; n=3 |
| `investment quotes list` / WIN | empty | `POST /quotationAnalysis.json` | 0 / ? | 98 | 1608.9 [1476.4, 1626.2]; n=3 |
| `investment quotes list` / previous-day:QUOTED | empty | `POST /quotationAnalysis.json` | 0 / ? | 98 | 1449.9 [1449.9, 1449.9]; n=1 |
| `investment quotes list` / previous-day:WIN | empty | `POST /quotationAnalysis.json` | 0 / ? | 98 | 1722.2 [1722.2, 1722.2]; n=1 |
| `investment returns list` / accrual | empty | `POST /accrualBaseList.json` | 0 / 0 | 149 | 409 [380.9, 1703.2]; n=3 |
| `investment returns list` / cash | empty | `POST /cashBaseList.json` | 0 / 0 | 148 | 444.8 [420.8, 615.4]; n=3 |
| `investment returns list` / previous-day:accrual | populated | `POST /accrualBaseList.json` | 10 / 112 | 5497 | 757.7 [757.7, 757.7]; n=1 |
| `investment returns list` / previous-day:cash | populated | `POST /cashBaseList.json` | 3 / 3 | 2315 | 771.2 [771.2, 771.2]; n=1 |
| `investment rfqs list` / None | failed | `POST /rfq/subInquiryTask/querySubInquiryTask.json` | ? / ? | 330 | 2532.9 [2532.9, 2532.9]; n=1 |
| `investment strategies get` / None | populated | `POST /queryIncrementStrategyRuleDetail.json` | 1 / ? | 1119 | 317.6 [311.9, 336.8]; n=3 |
| `investment strategies list` / None | populated | `POST /queryIncrementStrategyRuleList.json` | 2 / 2 | 1938 | 361.8 [344.6, 389.8]; n=3 |
| `investment strategies list` / offset10 | empty | `POST /queryIncrementStrategyRuleList.json` | 0 / 0 | 148 | 126 [126, 126]; n=1 |
| `investment strategy-results list` / FUND_DECISION_TASK | empty | `POST /api/increment/decision/task/queryPage.json` | 0 / 0 | 148 | 127.6 [126, 133.3]; n=3 |
| `investment strategy-results list` / PRODUCT_DECISION_TASK | empty | `POST /api/increment/decision/task/queryPage.json` | 0 / 0 | 148 | 116.6 [115.6, 130.4]; n=3 |
| `investment strategy-results list` / previous-day:FUND_DECISION_TASK | empty | `POST /api/increment/decision/task/queryPage.json` | 0 / 0 | 148 | 135 [135, 135]; n=1 |
| `investment strategy-results list` / previous-day:PRODUCT_DECISION_TASK | empty | `POST /api/increment/decision/task/queryPage.json` | 0 / 0 | 148 | 171.4 [171.4, 171.4]; n=1 |
| `investment transactions get` / None | populated | `POST /queryIncrementOrderDetail.json` | 1 / ? | 4702 | 334 [329, 457.3]; n=3 |
| `investment transactions list` / None | populated | `POST /queryIncrementOrderList.json` | 10 / 2237 | 14621 | 791.6 [790, 3137.4]; n=3 |
| `investment transactions list` / offset10 | populated | `POST /queryIncrementOrderList.json` | 10 / 2237 | 14943 | 760.8 [760.8, 760.8]; n=1 |
| `ledger accounts list` / INNER | populated | `POST /bookCustomerAccount/queryList.json` | 10 / 2620 | 2815 | 301.9 [275.8, 309.3]; n=3 |
| `ledger accounts list` / OUTER | populated | `POST /bookCustomerAccount/queryList.json` | 10 / 105 | 2810 | 325.9 [297, 525]; n=3 |
| `ledger accounts list` / offset10 | populated | `POST /bookCustomerAccount/queryList.json` | 10 / 105 | 2831 | 318.4 [318.4, 318.4]; n=1 |
| `ledger balances list` / INNER | populated | `POST /balanceBookquery.json` | 10 / 2620 | 3262 | 1543 [1456.7, 3042.7]; n=3 |
| `ledger balances list` / OUTER | populated | `POST /balanceBookquery.json` | 10 / 105 | 3700 | 419.7 [400.8, 444.9]; n=3 |
| `ledger balances list` / offset10 | populated | `POST /balanceBookquery.json` | 10 / 105 | 3707 | 1012.8 [1012.8, 1012.8]; n=1 |
| `ledger customers get` / None | populated | `GET /bookCustomer/detail.json` | 1 / ? | 1292 | 320.5 [301.8, 341.7]; n=3 |
| `ledger customers list` / None | populated | `POST /bookCustomer/queryList.json` | 8 / 8 | 2254 | 309.8 [298.3, 324.1]; n=3 |
| `ledger customers list` / offset10 | empty | `POST /bookCustomer/queryList.json` | 0 / 8 | 151 | 392.3 [392.3, 392.3]; n=1 |
| `network account-capabilities get` / None | populated | `POST /serviceInfoDetail.json` | 1 / ? | 866 | 287.6 [263.1, 299.3]; n=3 |
| `network account-capabilities list` / None | populated | `POST /serviceInfoQuery.json` | 10 / 29 | 7320 | 306.4 [286.6, 307.6]; n=3 |
| `network account-capabilities list` / offset10 | populated | `POST /serviceInfoQuery.json` | 10 / 29 | 7410 | 150 [150, 150]; n=1 |
| `network bank-baselines get` / None | populated | `GET /bankAccountBaseLineDetail.json` | 1 / ? | 1953 | 286.3 [275.4, 311]; n=3 |
| `network bank-baselines list` / None | populated | `GET /bankAccountBaseLineQuery.json` | 10 / 3690 | 5239 | 495.8 [448.9, 842.2]; n=3 |
| `network bank-baselines list` / offset10 | populated | `GET /bankAccountBaseLineQuery.json` | 10 / 3690 | 5156 | 281.4 [281.4, 281.4]; n=1 |
| `network product-baselines list` / None | empty | `POST /api/product/timeliness/payment/getAll.json` | 0 / 0 | 365 | 906.4 [894.9, 2099.3]; n=3 |
| `network realtime get` / None | populated | `POST /api/ai/decision/network/detail.json` | 1 / ? | 1032 | 298.1 [280.4, 302.6]; n=3 |
| `network realtime list` / None | populated | `POST /api/ai/decision/network/queryDecisionNetwork.json` | 10 / 204 | 9521 | 307.5 [257.5, 331.7]; n=3 |
| `network realtime list` / offset10 | populated | `POST /api/ai/decision/network/queryDecisionNetwork.json` | 10 / 204 | 10457 | 156.2 [156.2, 156.2]; n=1 |
| `operations asset-trades list` / None | empty | `POST /assetTransferOrderListQuery.json` | 0 / 0 | 149 | 254.1 [245.1, 278.2]; n=3 |
| `operations asset-trades list` / previous-day:None | populated | `POST /assetTransferOrderListQuery.json` | 2 / 2 | 6220 | 440.7 [440.7, 440.7]; n=1 |
| `operations decisions get` / None | populated | `POST /api/ai/decision/report/getDetail.json` | 1 / ? | 4090 | 410.4 [276.1, 416.9]; n=3 |
| `operations decisions history` / None | populated | `POST /api/ai/decision/report/getHistory.json` | 1 / ? | 1563 | 271.9 [269.7, 485.9]; n=3 |
| `operations decisions list` / None | empty | `POST /api/ai/decision/report/getAllNew.json` | 0 / 0 | 149 | 171.5 [167.9, 181.6]; n=3 |
| `operations decisions list` / previous-day:None | populated | `POST /api/ai/decision/report/getAllNew.json` | 10 / 264 | 14876 | 451.8 [451.8, 451.8]; n=1 |
| `operations demands list` / FUND_REQUIRE | empty | `GET /riskActionTaskQuery.json` | 0 / 0 | 142 | 3916.5 [3895.9, 8650.4]; n=3 |
| `operations demands list` / previous-day:FUND_REQUIRE | empty | `GET /riskActionTaskQuery.json` | 0 / 0 | 142 | 12467.6 [12467.6, 12467.6]; n=1 |
| `operations executions list` / INSTRUCTION_ACCOUNT_FLOW,INSTRUCTION_ACCOUNT_FLOW_MANUAL | empty | `GET /riskActionTaskQuery.json` | 0 / 0 | 142 | 3899.7 [3881.2, 8577.9]; n=3 |
| `operations executions list` / REAL_TIME_INITIATIVE_SUPPLEMENT,REAL_TIME_PASSIVE_SUPPLEMENT,REAL_TIME_INITIATIVE_COLLECTION | empty | `GET /riskActionTaskQuery.json` | 0 / 0 | 142 | 3737.6 [3715.8, 9307.9]; n=3 |
| `operations executions list` / previous-day:INSTRUCTION_ACCOUNT_FLOW,INSTRUCTION_ACCOUNT_FLOW_MANUAL | empty | `GET /riskActionTaskQuery.json` | 0 / 0 | 142 | 12548.6 [12548.6, 12548.6]; n=1 |
| `operations executions list` / previous-day:REAL_TIME_INITIATIVE_SUPPLEMENT,REAL_TIME_PASSIVE_SUPPLEMENT,REAL_TIME_INITIATIVE_COLLECTION | empty | `GET /riskActionTaskQuery.json` | 0 / 0 | 142 | 12557.6 [12557.6, 12557.6]; n=1 |
| `operations forwards get` / None | populated | `POST /forwardOrderDetail.json` | 1 / ? | 606 | 298.2 [258.1, 298.4]; n=3 |
| `operations forwards list` / None | populated | `POST /forwardOrderList.json` | 10 / 17 | 5265 | 302.1 [290.8, 310.5]; n=3 |
| `operations forwards list` / offset10 | populated | `POST /forwardOrderList.json` | 7 / 17 | 3405 | 455.3 [455.3, 455.3]; n=1 |
| `operations prefunds get` / None | populated | `GET /queryPreFundingOrderDetail.json` | 1 / ? | 2097 | 312.2 [308.2, 327.6]; n=3 |
| `operations prefunds list` / APPROVED,CLOSED | populated | `GET /queryPreFundingOrderList.json` | 10 / 70 | 24368 | 454.4 [403.6, 475.7]; n=3 |
| `operations prefunds list` / SUBMITTED,REJECTED,CLOSED_SUBMITTED | populated | `GET /queryPreFundingOrderList.json` | 10 / 22 | 25079 | 440.4 [408.6, 479.5]; n=3 |
| `operations prefunds list` / offset10 | populated | `GET /queryPreFundingOrderList.json` | 10 / 70 | 34821 | 383.2 [383.2, 383.2]; n=1 |
| `operations swaps list` / None | empty | `POST /swapOrderQuery.json` | 0 / 0 | 148 | 323.5 [280.8, 325.4]; n=3 |
| `operations swaps list` / previous-day:None | empty | `POST /swapOrderQuery.json` | 0 / 0 | 148 | 330.1 [330.1, 330.1]; n=1 |
| `operations transfers get` / None | populated | `POST /transferOrderQueryDetail.json` | 1 / ? | 2538 | 289.2 [277, 1759.3]; n=3 |
| `operations transfers list` / None | empty | `POST /transferOrderQuery.json` | 0 / 0 | 147 | 273.6 [267.5, 318]; n=3 |
| `operations transfers list` / previous-day:None | populated | `POST /transferOrderQuery.json` | 10 / 3705 | 31236 | 936.4 [936.4, 936.4]; n=1 |
| `pricing bills list` / DEPOSIT | empty | `POST /accountBookQuery.json` | 0 / 0 | 147 | 271.5 [254.9, 289]; n=3 |
| `pricing bills list` / previous-day:DEPOSIT | empty | `POST /accountBookQuery.json` | 0 / 0 | 147 | 121.7 [121.7, 121.7]; n=1 |
| `pricing client-prices list` / ACTIVATED | empty | `GET /getClientPriceList.json` | 0 / 0 | 147 | 471.8 [467.3, 503.5]; n=3 |
| `pricing client-prices list` / DEPRECATED,WAIT_FOR_AUDIT,DRAFT | empty | `GET /getClientPriceList.json` | 0 / 0 | 147 | 477.9 [463.1, 492]; n=3 |
| `pricing client-prices list` / previous-day:ACTIVATED | empty | `GET /getClientPriceList.json` | 0 / 0 | 147 | 169.7 [169.7, 169.7]; n=1 |
| `pricing client-prices list` / previous-day:DEPRECATED,WAIT_FOR_AUDIT,DRAFT | populated | `GET /getClientPriceList.json` | 10 / 34 | 8008 | 215.7 [215.7, 215.7]; n=1 |
| `pricing cost-prices list` / None | empty | `GET /costPriceList.json` | 0 / 0 | 142 | 1346.3 [1196.5, 1350.2]; n=3 |
| `pricing cost-prices list` / previous-day:None | populated | `GET /costPriceList.json` | 10 / 800 | 4713 | 688.7 [688.7, 688.7]; n=1 |
| `pricing factor-values list` / None | empty | `GET /costFactorList.json` | 0 / 0 | 142 | 1514.6 [1401.5, 1540.2]; n=3 |
| `pricing factor-values list` / previous-day:None | populated | `GET /costFactorList.json` | 10 / 470 | 4308 | 801.7 [801.7, 801.7]; n=1 |
| `pricing strategies list` / None | populated | `POST /pricingStrategyQuery.json` | 10 / 78 | 10143 | 538.9 [494.4, 570.1]; n=3 |
| `pricing strategies list` / offset10 | populated | `POST /pricingStrategyQuery.json` | 10 / 78 | 10486 | 1758.1 [1758.1, 1758.1]; n=1 |
| `pricing valuations list` / None | empty | `GET /getFeeOrderList.json` | 0 / 0 | 147 | 285.1 [260, 285.7]; n=3 |
| `pricing valuations list` / previous-day:None | empty | `GET /getFeeOrderList.json` | 0 / 0 | 147 | 416.4 [416.4, 416.4]; n=1 |
| `reference areas cities list` / None | populated | `GET /queryParaCity.json` | 10 / 161 | 2175 | 315.9 [313.8, 373.3]; n=3 |
| `reference areas cities list` / offset10 | populated | `GET /queryParaCity.json` | 10 / 161 | 2160 | 301.8 [301.8, 301.8]; n=1 |
| `reference areas countries list` / None | populated | `GET /queryParaCountry.json` | 10 / 52 | 2666 | 315.1 [302.9, 328.4]; n=3 |
| `reference areas countries list` / offset10 | populated | `GET /queryParaCountry.json` | 10 / 52 | 2590 | 317.6 [317.6, 317.6]; n=1 |
| `reference areas provinces list` / None | failed | `GET /queryParaProvince.json` | ? / ? | 172 | 339.5 [339.5, 339.5]; n=1 |
| `reference banks list` / None | populated | `GET /queryParaBank.json` | 10 / 927 | 3983 | 341.6 [331.3, 544.8]; n=3 |
| `reference business-lines list` / None | populated | `GET /bankAccountBusinessLineQuery.json` | 10 / 335 | 3549 | 312.4 [312, 322.3]; n=3 |
| `reference business-lines list` / offset10 | populated | `GET /bankAccountBusinessLineQuery.json` | 10 / 335 | 3520 | 333.4 [333.4, 333.4]; n=1 |
| `reference calendars list` / None | populated | `GET /queryCalendars.json` | 10 / 270 | 492669 | 5514.1 [3702.5, 6277.7]; n=3 |
| `reference calendars list` / offset10 | populated | `GET /queryCalendars.json` | 10 / 270 | 335459 | 4863 [4863, 4863]; n=1 |
| `reference entities list` / None | populated | `GET /entityMaintQuery.json` | 10 / 71 | 2874 | 467.9 [345, 480.4]; n=3 |
| `risk account-capacity list` / None | failed | `GET /api/fund/capacity/queryFundCapacityByAliasName.json` | ? / ? | 395 | 264.6 [264.6, 264.6]; n=1 |
| `risk anomalies list` / None | empty | `POST /api/risk/event/getAll.json` | 0 / 0 | 148 | 277.9 [253.8, 360.3]; n=3 |
| `risk anomalies list` / previous-day:None | empty | `POST /api/risk/event/getAll.json` | 0 / 0 | 148 | 263.6 [263.6, 263.6]; n=1 |
| `risk events list` / None | empty | `POST /api/risk/event/getAll.json` | 0 / 0 | 148 | 272.4 [268.8, 279.2]; n=3 |
| `risk events list` / previous-day:None | empty | `POST /api/risk/event/getAll.json` | 0 / 0 | 148 | 250.9 [250.9, 250.9]; n=1 |
| `risk metrics list` / BREAK_EVEN_RATE | envelope-only | `POST /api/metric/singleMetricQuery.json` | ? / ? | 394 | 255.3 [241.1, 266.6]; n=3 |
| `risk metrics list` / CONCENTRATION_RATE | populated | `POST /api/metric/manyMetricQuery.json` | 95 / ? | 28378 | 1045.9 [1001.6, 1051.6]; n=3 |
| `risk metrics list` / CREDIT_USAGE_RATE | populated | `POST /api/metric/manyMetricQuery.json` | 93 / ? | 39278 | 1010.3 [966.5, 1031]; n=3 |
| `risk metrics list` / CURRENCY_T3_LCR | empty | `POST /api/metric/manyMetricQuery.json` | 0 / ? | 98 | 340.2 [295.4, 421.5]; n=3 |
| `risk metrics list` / GEO_BALANCE_RATE | envelope-only | `POST /api/metric/singleMetricQuery.json` | ? / ? | 405 | 258.9 [251.5, 272.4]; n=3 |
| `risk metrics list` / SINO_FOREIGN_BALANCE_RATE | envelope-only | `POST /api/metric/singleMetricQuery.json` | ? / ? | 412 | 263.6 [249.8, 268.5]; n=3 |
| `risk metrics list` / TOTAL_T3_LCR | envelope-only | `POST /api/metric/singleMetricQuery.json` | ? / ? | 365 | 263.5 [259.5, 314]; n=3 |
| `risk metrics list` / open-balance | envelope-only | `POST /api/metric/openBalanceQuery.json` | ? / ? | 335 | 276.7 [266.3, 278.6]; n=3 |
| `risk sla get` / None | populated | `POST /api/risk/sla/slaConfigDetailQuery.json` | 1 / ? | 1573 | 165.7 [150.9, 172.1]; n=3 |
| `risk sla list` / None | populated | `POST /api/risk/sla/slaConfigPageQuery.json` | 10 / 49 | 4737 | 128.9 [125, 138]; n=3 |
| `risk sla list` / offset10 | populated | `POST /api/risk/sla/slaConfigPageQuery.json` | 10 / 49 | 4672 | 151.8 [151.8, 151.8]; n=1 |
| `risk thresholds get` / None | populated | `POST /api/risk/benchmark/riskEventBenchmarkDetailDetail.json` | 1 / ? | 1399 | 268.7 [246.9, 272.8]; n=3 |
| `risk thresholds list` / None | populated | `POST /api/risk/benchmark/riskEventBenchmarkQuery.json` | 10 / 21 | 11250 | 482.8 [473.9, 674.2]; n=3 |
| `risk thresholds list` / offset10 | populated | `POST /api/risk/benchmark/riskEventBenchmarkQuery.json` | 10 / 21 | 15369 | 465.5 [465.5, 465.5]; n=1 |
| `rules action-mapping list` / None | populated | `GET /clientAgreementConfigQuery.json` | 10 / 225 | 5064 | 735.8 [336.1, 880.2]; n=3 |
| `rules action-mapping list` / offset10 | populated | `GET /clientAgreementConfigQuery.json` | 10 / 225 | 4903 | 208.1 [208.1, 208.1]; n=1 |
| `rules forecast list` / None | populated | `GET /bankCashForecastRuleQuery.json` | 4 / 4 | 8098 | 662.3 [562.9, 830.6]; n=3 |
| `rules forecast list` / offset10 | empty | `GET /bankCashForecastRuleQuery.json` | 0 / 4 | 142 | 553.3 [553.3, 553.3]; n=1 |
| `rules forecast-filter list` / None | populated | `GET /queryAllBankCashForecastFilter.json` | 10 / 261 | 3553 | 320 [317.2, 321.3]; n=3 |
| `rules forecast-filter list` / offset10 | populated | `GET /queryAllBankCashForecastFilter.json` | 10 / 261 | 3516 | 295.9 [295.9, 295.9]; n=1 |
| `rules funding list` / None | populated | `GET /fundRiskActionRelationQuery.json` | 10 / 123 | 9003 | 932.8 [851.2, 1524.6]; n=3 |
| `rules funding list` / offset10 | populated | `GET /fundRiskActionRelationQuery.json` | 10 / 123 | 9275 | 716.2 [716.2, 716.2]; n=1 |
| `rules fx-settlement list` / None | populated | `GET /fxBankAccountConfigQuery.json` | 10 / 1071 | 5197 | 628 [283.1, 738.4]; n=3 |
| `rules fx-settlement list` / offset10 | populated | `GET /fxBankAccountConfigQuery.json` | 10 / 1071 | 4926 | 307.3 [307.3, 307.3]; n=1 |
| `rules monitoring list` / None | empty | `GET /queryRules.json` | 0 / 0 | 220 | 285.6 [273.4, 296.2]; n=3 |
| `rules notification get` / None | populated | `GET /messageNoticeConfigDetail.json` | 1 / ? | 716 | 292.9 [292.1, 293.4]; n=3 |
| `rules notification list` / None | populated | `GET /messageNoticeConfigQuery.json` | 10 / 17 | 6100 | 349.8 [321, 370.1]; n=3 |
| `rules notification list` / offset10 | populated | `GET /messageNoticeConfigQuery.json` | 7 / 17 | 4433 | 150.6 [150.6, 150.6]; n=1 |
| `rules operation get` / None | populated | `GET /riskActionRuleDetail.json` | 1 / ? | 933 | 291.4 [288.7, 952.9]; n=3 |
| `rules operation list` / None | populated | `GET /riskActionRuleListQuery.json` | 10 / 235 | 8564 | 692.1 [367.7, 874.1]; n=3 |
| `rules operation list` / offset10 | populated | `GET /riskActionRuleListQuery.json` | 10 / 235 | 8647 | 337.9 [337.9, 337.9]; n=1 |
| `rules realtime get` / None | populated | `POST /api/realtime/rule/getDetail.json` | 1 / ? | 981 | 313.4 [304.3, 445.4]; n=3 |
| `rules realtime list` / None | populated | `POST /api/realtime/rule/getAll.json` | 10 / 15 | 8490 | 302.6 [300.5, 324.9]; n=3 |
| `rules realtime list` / offset10 | populated | `POST /api/realtime/rule/getAll.json` | 5 / 15 | 3727 | 135.6 [135.6, 135.6]; n=1 |
| `rules transfer get` / None | populated | `GET /queryTransferRuleDetail.json` | 1 / ? | 3322 | 311.6 [304.9, 644.2]; n=3 |
| `rules transfer list` / None | populated | `GET /transferRuleQuery.json` | 10 / ? | 18063 | 733.7 [553.6, 915.8]; n=3 |
| `rules transfer list` / offset10 | populated | `GET /transferRuleQuery.json` | 10 / ? | 18179 | 510.3 [510.3, 510.3]; n=1 |
| `rules transfer-config list` / None | populated | `GET /transferConfigQuery.json` | 10 / 748 | 7887 | 316.8 [313.1, 324.2]; n=3 |
| `rules transfer-config list` / offset10 | populated | `GET /transferConfigQuery.json` | 10 / 748 | 7733 | 314 [314, 314]; n=1 |
| `rules treasury-transfer list` / None | failed | `GET /queryTreasuryTransferRuleList.json` | ? / ? | 249 | 293.4 [293.4, 293.4]; n=1 |
| `rules waterlevel get` / None | populated | `GET /bankAccountBufferListByAliasName.json` | 2 / 0 | 1489 | 306.7 [277.6, 308]; n=3 |
| `rules waterlevel list` / None | populated | `GET /bankAccountBufferQuery.json` | 10 / 533 | 7386 | 1805.5 [1761.6, 4204.1]; n=3 |
| `rules waterlevel list` / offset10 | populated | `GET /bankAccountBufferQuery.json` | 10 / 533 | 7382 | 1758.2 [1758.2, 1758.2]; n=1 |

## Sampled record schemas and request identities

### cash accounts get / None

Source: `GET /queryaccountbyid.json`. Probe IDs: `core-35-r1`. Record container: `None`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `id`.

Native identity binding (field names only): `{"parameter": "id", "rowfield": "id", "source_leaf": "cash accounts list", "source_path": "$.result.bankAccountPropertyVOList"}`.

Published UI bundle character offsets: 1486792, 2816626.

No populated record schema verified in this case.

### cash accounts list / None

Source: `GET /queryintnalbkactlist.json`. Probe IDs: `core-18-r1`, `core-18-r2`, `core-18-r3`. Record container: `$.result.bankAccountPropertyVOList`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankAccountQueryVO`, `wallet`.

Published UI bundle character offsets: 1486674, 2766570, 2767272.

Sample fields: `accHolder` (str); `accPurpose` (str); `accUser` (str); `accountName` (str); `accountNo` (str); `accountType` (str); `aliasName` (str); `bankId` (str); `bankShortName` (str); `bankSwiftCode` (str); `closeDate` (str); `currency` (str); `currencyCode` (str); `dolLimit` (str); `dolLimitCurrency` (str); `dolMasterAccountNo` (str); `entityCode` (str); `fyOfIntPymt` (str); `gmtCreat` (str); `gmtModified` (str); `id` (str); `innerAccountNo` (str); `innerAccountShortName` (str); `instId` (str); `intBasis` (str); `intPymtDt` (str); `intPymtDtBefore` (str); `intPymtDtLast` (str); `intPymtDtMiddle` (str); `isDirect` (str); `isEcr` (str); `isFloating` (str); `masterAccountFlag` (str); `masterBankId` (str); `msdOfInt` (str); `odDolFlag` (str); `odLimit` (str); `odLimitCurrency` (str); `odMasterAccountNo` (str); `openDate` (str); `operator` (str); `rate` (str); `remark1` (str); `remark2` (str); `remark3` (str); `rnpFlag` (str); `statementSource` (str); `status` (str); `system` (str); `tntInstId` (str).

### cash accounts list / offset10

Source: `GET /queryintnalbkactlist.json`. Probe IDs: `page-two-78-r1`. Record container: `$.result.bankAccountPropertyVOList`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankAccountQueryVO`, `wallet`.

Published UI bundle character offsets: 1486674, 2766570, 2767272.

Sample fields: `accHolder` (str); `accPurpose` (str); `accUser` (str); `accountName` (str); `accountNo` (str); `accountType` (str); `aliasName` (str); `bankId` (str); `bankShortName` (str); `bankSwiftCode` (str); `closeDate` (str); `currency` (str); `currencyCode` (str); `dolLimit` (str); `dolLimitCurrency` (str); `dolMasterAccountNo` (str); `entityCode` (str); `fyOfIntPymt` (str); `gmtCreat` (str); `gmtModified` (str); `id` (str); `innerAccountNo` (str); `innerAccountShortName` (str); `instId` (str); `intBasis` (str); `intPymtDt` (str); `intPymtDtBefore` (str); `intPymtDtLast` (str); `intPymtDtMiddle` (str); `isDirect` (str); `isEcr` (str); `isFloating` (str); `masterAccountFlag` (str); `masterBankId` (str); `msdOfInt` (str); `odDolFlag` (str); `odLimit` (str); `odLimitCurrency` (str); `odMasterAccountNo` (str); `openDate` (str); `operator` (str); `rate` (str); `remark1` (str); `remark2` (str); `remark3` (str); `rnpFlag` (str); `statementSource` (str); `status` (str); `system` (str); `tntInstId` (str).

### cash balances list / None

Source: `POST /latestBalanceQuery.json`. Probe IDs: `core-25-r1`, `core-25-r2`, `core-25-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `entitys`, `timeZone`.

Published UI bundle character offsets: 1513765, 4109728, 4110397.

Sample fields: `accountNo` (str); `accountNumbers` (str); `accountType` (str); `aliasName` (str); `avlBalance` (str); `avlBalanceAfterAdj` (str); `avlBalanceSwitch` (bool); `balId` (str); `bankId` (str); `bizTag` (str); `blockChainAccountType` (str); `colorType` (str); `companyName` (str); `curBalance` (str); `currency` (str); `digitalCurrency` (str); `entity` (str); `equvAvlBalance` (str); `equvCurBalance` (str); `equvCurrency` (str); `equvOpenAvlBalance` (str); `equvOpenBalance` (str); `fundAttribute1` (str); `leastDayendBalVo` (dict); `leastDayendBalVo.accountNo` (str); `leastDayendBalVo.aliasName` (str); `leastDayendBalVo.bankId` (str); `leastDayendBalVo.closeAvlBalance` (str); `leastDayendBalVo.closeBalance` (str); `leastDayendBalVo.currency` (str); `leastDayendBalVo.entity` (str); `leastDayendBalVo.openAvlBalance` (str); `leastDayendBalVo.openBalance` (str); `leastDayendBalVo.source` (str); `leastDayendBalVo.statementCreateTime` (str); `leastDayendBalVo.timeZone` (str); `leastDayendBalVo.updateTime` (str); `leastDayendBalVo.valueDate` (str); `leastDaytimeBalVo` (dict); `leastDaytimeBalVo.accountNo` (str); `leastDaytimeBalVo.aliasName` (str); `leastDaytimeBalVo.bankId` (str); `leastDaytimeBalVo.currency` (str); `leastDaytimeBalVo.entity` (str); `leastDaytimeBalVo.instradayAvlBalance` (str); `leastDaytimeBalVo.instradayBalance` (str); `leastDaytimeBalVo.source` (str); `leastDaytimeBalVo.statementCreateTime` (str); `leastDaytimeBalVo.timeZone` (str); `leastDaytimeBalVo.updateTime` (str); `leastDaytimeBalVo.valueDate` (str); `openAvlBalance` (str); `openAvlBalanceAfterAdj` (str); `openAvlBalanceSwitch` (bool); `openBalance` (str); `statementCreateTime` (str); `timeZone` (str).

### cash balances list / offset10

Source: `POST /latestBalanceQuery.json`. Probe IDs: `page-two-85-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `entitys`, `timeZone`.

Published UI bundle character offsets: 1513765, 4109728, 4110397.

Sample fields: `accountNo` (str); `accountNumbers` (str); `accountType` (str); `aliasName` (str); `avlBalance` (str); `avlBalanceAfterAdj` (str); `avlBalanceSwitch` (bool); `balId` (str); `bankId` (str); `bizTag` (str); `blockChainAccountType` (str); `colorType` (str); `companyName` (str); `curBalance` (str); `currency` (str); `digitalCurrency` (str); `entity` (str); `equvAvlBalance` (str); `equvCurBalance` (str); `equvCurrency` (str); `equvOpenAvlBalance` (str); `equvOpenBalance` (str); `fundAttribute1` (str); `leastDayendBalVo` (dict); `leastDayendBalVo.accountNo` (str); `leastDayendBalVo.aliasName` (str); `leastDayendBalVo.bankId` (str); `leastDayendBalVo.closeAvlBalance` (str); `leastDayendBalVo.closeBalance` (str); `leastDayendBalVo.currency` (str); `leastDayendBalVo.entity` (str); `leastDayendBalVo.openAvlBalance` (str); `leastDayendBalVo.openBalance` (str); `leastDayendBalVo.source` (str); `leastDayendBalVo.statementCreateTime` (str); `leastDayendBalVo.timeZone` (str); `leastDayendBalVo.updateTime` (str); `leastDayendBalVo.valueDate` (str); `leastDaytimeBalVo` (dict); `leastDaytimeBalVo.accountNo` (str); `leastDaytimeBalVo.aliasName` (str); `leastDaytimeBalVo.bankId` (str); `leastDaytimeBalVo.currency` (str); `leastDaytimeBalVo.entity` (str); `leastDaytimeBalVo.instradayAvlBalance` (str); `leastDaytimeBalVo.instradayBalance` (str); `leastDaytimeBalVo.source` (str); `leastDaytimeBalVo.statementCreateTime` (str); `leastDaytimeBalVo.timeZone` (str); `leastDaytimeBalVo.updateTime` (str); `leastDaytimeBalVo.valueDate` (str); `openAvlBalance` (str); `openAvlBalanceAfterAdj` (str); `openAvlBalanceSwitch` (bool); `openBalance` (str); `statementCreateTime` (str); `timeZone` (str).

### cash credit-lines list / None

Source: `GET /queryBankCreditLineByParams.json`. Probe IDs: `core-37-r1`. Record container: `None`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankCreditLineQuery`.

Published UI bundle character offsets: 1474908, 2510923, 2502819.

No populated record schema verified in this case.

### cash groups list / None

Source: `GET /bankAccountGroupQuery.json`. Probe IDs: `core-07-r1`, `core-07-r3`, `core-07-r2`. Record container: `$.result.data`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankAccountManageUnitQueryVO`.

Published UI bundle character offsets: 1499262, 5709626, 5710020.

Sample fields: `currentBalance` (str); `forecastBalance` (str); `gmtCreate` (str); `gmtModified` (str); `groupName` (str); `id` (str); `lastDayClosingBalance` (str); `memberList` (list); `memberList[]` (dict); `memberList[].accountNo` (str); `memberList[].accountUsageType` (str); `memberList[].aliasName` (str); `memberList[].bankAccountGroupId` (str); `memberList[].bankId` (str); `memberList[].currencyCode` (str); `memberList[].currentBalance` (str); `memberList[].currentBalanceTime` (str); `memberList[].entity` (str); `memberList[].equiCurrentBalance` (str); `memberList[].equiForecastBalance` (str); `memberList[].equiLastDayClosingBalance` (str); `memberList[].forecastBalance` (str); `memberList[].forecastTime` (str); `memberList[].gmtCreate` (str); `memberList[].gmtModified` (str); `memberList[].id` (str); `memberList[].lastDayClosingBalance` (str); `memberList[].memo` (str); `memo` (str); `operator` (str); `tntInstId` (str); `type` (str); `userGroupCode` (str); `valueDate` (str); `version` (str).

### cash groups list / offset10

Source: `GET /bankAccountGroupQuery.json`. Probe IDs: `page-two-68-r1`. Record container: `$.result.data`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankAccountManageUnitQueryVO`.

Published UI bundle character offsets: 1499262, 5709626, 5710020.

No populated record schema verified in this case.

### cash pools configuration list / None

Source: `POST /cashPoolList.json`. Probe IDs: `core-20-r1`, `core-20-r2`, `core-20-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `cashPoolCategory`.

Published UI bundle character offsets: 1512850, 4967014, 4967459.

Sample fields: `cashPoolCapacity` (str); `cashPoolCategory` (str); `cashPoolDetailUrl` (str); `cashPoolMemberVOS` (list); `cashPoolMemberVOS[]` (dict); `cashPoolMemberVOS[].aliasName` (str); `cashPoolMemberVOS[].avlCreditAmount` (str); `cashPoolMemberVOS[].avlSubLimit` (str); `cashPoolMemberVOS[].balanceUpdateType` (str); `cashPoolMemberVOS[].bankCurrency` (str); `cashPoolMemberVOS[].bankId` (str); `cashPoolMemberVOS[].billingTimeType` (str); `cashPoolMemberVOS[].billingTimeValue` (str); `cashPoolMemberVOS[].cashPoolId` (str); `cashPoolMemberVOS[].cashPoolName` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS` (list); `cashPoolMemberVOS[].closeAviBalance` (str); `cashPoolMemberVOS[].closeBalance` (str); `cashPoolMemberVOS[].creditAmount` (str); `cashPoolMemberVOS[].creditRateExtType` (str); `cashPoolMemberVOS[].creditRateSource` (str); `cashPoolMemberVOS[].creditRateType` (str); `cashPoolMemberVOS[].creditRateValue` (str); `cashPoolMemberVOS[].currency` (str); `cashPoolMemberVOS[].currentAviBalance` (str); `cashPoolMemberVOS[].currentBalance` (str); `cashPoolMemberVOS[].debitRateExtType` (str); `cashPoolMemberVOS[].debitRateSource` (str); `cashPoolMemberVOS[].debitRateType` (str); `cashPoolMemberVOS[].debitRateValue` (str); `cashPoolMemberVOS[].entity` (str); `cashPoolMemberVOS[].equvCloseAviBalance` (str); `cashPoolMemberVOS[].equvCloseBalance` (str); `cashPoolMemberVOS[].equvCurrentAviBalance` (str); `cashPoolMemberVOS[].equvCurrentBalance` (str); `cashPoolMemberVOS[].expectBalance` (str); `cashPoolMemberVOS[].id` (str); `cashPoolMemberVOS[].isShare` (str); `cashPoolMemberVOS[].masterAccount` (str); `cashPoolMemberVOS[].memo` (str); `cashPoolMemberVOS[].operator` (str); `cashPoolMemberVOS[].outFlowCapability` (str); `cashPoolMemberVOS[].penaltyRateExtType` (str); `cashPoolMemberVOS[].penaltyRateSource` (str); `cashPoolMemberVOS[].penaltyRateType` (str); `cashPoolMemberVOS[].penaltyRateValue` (str); `cashPoolMemberVOS[].subLimit` (str); `cashPoolMemberVOS[].timeZone` (str); `cashPoolMemberVOS[].tntInstId` (str); `cashPoolName` (str); `cashPoolRequest` (null); `cashPoolType` (str); `cashpoolCapacityVO` (null); `closeAviBalance` (str); `closeBalance` (str); `currentAviBalance` (str); `currentBalance` (str); `entity` (list); `entity[]` (str); `gmtModified` (str); `haircutRatio` (str); `id` (str); `isDelete` (null); `mainCurrency` (str); `memo` (str); `operationStrategyRuleVO` (null); `operator` (str); `pageNo` (int); `pageSize` (int); `processId` (str); `processStatus` (str); `processType` (null); `rowStart` (int); `startindex` (int); `status` (str); `tntInstId` (str); `totalSize` (int); `valueDate` (str); `waterlevelRuleEditVO` (null); `waterlevelRuleVO` (null).

### cash pools configuration list / offset10

Source: `POST /cashPoolList.json`. Probe IDs: `page-two-80-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `cashPoolCategory`.

Published UI bundle character offsets: 1512850, 4967014, 4967459.

Sample fields: `cashPoolCapacity` (str); `cashPoolCategory` (str); `cashPoolDetailUrl` (str); `cashPoolMemberVOS` (list); `cashPoolMemberVOS[]` (dict); `cashPoolMemberVOS[].aliasName` (str); `cashPoolMemberVOS[].avlCreditAmount` (str); `cashPoolMemberVOS[].avlSubLimit` (str); `cashPoolMemberVOS[].balanceUpdateType` (str); `cashPoolMemberVOS[].bankCurrency` (str); `cashPoolMemberVOS[].bankId` (str); `cashPoolMemberVOS[].billingTimeType` (str); `cashPoolMemberVOS[].billingTimeValue` (str); `cashPoolMemberVOS[].cashPoolId` (str); `cashPoolMemberVOS[].cashPoolName` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS` (list); `cashPoolMemberVOS[].closeAviBalance` (str); `cashPoolMemberVOS[].closeBalance` (str); `cashPoolMemberVOS[].creditAmount` (str); `cashPoolMemberVOS[].creditRateExtType` (str); `cashPoolMemberVOS[].creditRateSource` (str); `cashPoolMemberVOS[].creditRateType` (str); `cashPoolMemberVOS[].creditRateValue` (str); `cashPoolMemberVOS[].currency` (str); `cashPoolMemberVOS[].currentAviBalance` (str); `cashPoolMemberVOS[].currentBalance` (str); `cashPoolMemberVOS[].debitRateExtType` (str); `cashPoolMemberVOS[].debitRateSource` (str); `cashPoolMemberVOS[].debitRateType` (str); `cashPoolMemberVOS[].debitRateValue` (str); `cashPoolMemberVOS[].entity` (str); `cashPoolMemberVOS[].equvCloseAviBalance` (str); `cashPoolMemberVOS[].equvCloseBalance` (str); `cashPoolMemberVOS[].equvCurrentAviBalance` (str); `cashPoolMemberVOS[].equvCurrentBalance` (str); `cashPoolMemberVOS[].expectBalance` (str); `cashPoolMemberVOS[].id` (str); `cashPoolMemberVOS[].isShare` (str); `cashPoolMemberVOS[].masterAccount` (str); `cashPoolMemberVOS[].memo` (str); `cashPoolMemberVOS[].operator` (str); `cashPoolMemberVOS[].outFlowCapability` (str); `cashPoolMemberVOS[].penaltyRateExtType` (str); `cashPoolMemberVOS[].penaltyRateSource` (str); `cashPoolMemberVOS[].penaltyRateType` (str); `cashPoolMemberVOS[].penaltyRateValue` (str); `cashPoolMemberVOS[].subLimit` (str); `cashPoolMemberVOS[].timeZone` (str); `cashPoolMemberVOS[].tntInstId` (str); `cashPoolName` (str); `cashPoolRequest` (null); `cashPoolType` (str); `cashpoolCapacityVO` (null); `closeAviBalance` (str); `closeBalance` (str); `currentAviBalance` (str); `currentBalance` (str); `entity` (list); `entity[]` (str); `gmtModified` (str); `haircutRatio` (str); `id` (str); `isDelete` (null); `mainCurrency` (str); `memo` (str); `operationStrategyRuleVO` (null); `operator` (str); `pageNo` (int); `pageSize` (int); `processId` (str); `processStatus` (str); `processType` (null); `rowStart` (int); `startindex` (int); `status` (str); `tntInstId` (str); `totalSize` (int); `valueDate` (str); `waterlevelRuleEditVO` (null); `waterlevelRuleVO` (null).

### cash pools get / None

Source: `POST /cashPoolDetail.json`. Probe IDs: `core-44-r1`, `core-44-r2`, `core-44-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json-body`. Top-level request fields: `tntInstId`, `id`, `inUse`, `cashPoolCategory`.

Native identity binding (field names only): `{"parameter": "id", "rowfield": "id", "source_leaf": "cash pools configuration list", "source_path": "$.data.data"}`.

Published UI bundle character offsets: 1513398, 4959800.

Sample fields: `cashPoolCapacity` (str); `cashPoolCategory` (str); `cashPoolDetailUrl` (str); `cashPoolMemberVOS` (list); `cashPoolMemberVOS[]` (dict); `cashPoolMemberVOS[].aliasName` (str); `cashPoolMemberVOS[].avlCreditAmount` (str); `cashPoolMemberVOS[].avlSubLimit` (str); `cashPoolMemberVOS[].balanceUpdateType` (str); `cashPoolMemberVOS[].bankCurrency` (str); `cashPoolMemberVOS[].bankId` (str); `cashPoolMemberVOS[].billingTimeType` (str); `cashPoolMemberVOS[].billingTimeValue` (str); `cashPoolMemberVOS[].cashPoolId` (str); `cashPoolMemberVOS[].cashPoolName` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS` (list); `cashPoolMemberVOS[].closeAviBalance` (str); `cashPoolMemberVOS[].closeBalance` (str); `cashPoolMemberVOS[].creditAmount` (str); `cashPoolMemberVOS[].creditRateExtType` (str); `cashPoolMemberVOS[].creditRateSource` (str); `cashPoolMemberVOS[].creditRateType` (str); `cashPoolMemberVOS[].creditRateValue` (str); `cashPoolMemberVOS[].currency` (str); `cashPoolMemberVOS[].currentAviBalance` (str); `cashPoolMemberVOS[].currentBalance` (str); `cashPoolMemberVOS[].debitRateExtType` (str); `cashPoolMemberVOS[].debitRateSource` (str); `cashPoolMemberVOS[].debitRateType` (str); `cashPoolMemberVOS[].debitRateValue` (str); `cashPoolMemberVOS[].entity` (str); `cashPoolMemberVOS[].equvCloseAviBalance` (str); `cashPoolMemberVOS[].equvCloseBalance` (str); `cashPoolMemberVOS[].equvCurrentAviBalance` (str); `cashPoolMemberVOS[].equvCurrentBalance` (str); `cashPoolMemberVOS[].expectBalance` (str); `cashPoolMemberVOS[].id` (str); `cashPoolMemberVOS[].isShare` (str); `cashPoolMemberVOS[].masterAccount` (str); `cashPoolMemberVOS[].memo` (str); `cashPoolMemberVOS[].operator` (str); `cashPoolMemberVOS[].outFlowCapability` (str); `cashPoolMemberVOS[].penaltyRateExtType` (str); `cashPoolMemberVOS[].penaltyRateSource` (str); `cashPoolMemberVOS[].penaltyRateType` (str); `cashPoolMemberVOS[].penaltyRateValue` (str); `cashPoolMemberVOS[].subLimit` (str); `cashPoolMemberVOS[].timeZone` (str); `cashPoolMemberVOS[].tntInstId` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[]` (dict); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].beginTime` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].calendarCode` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].calendarConditionVos` (list); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].calendarType` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].cashPoolMemberId` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].conditionLogical` (int); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].currency` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].customCalendarId` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].customeType` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].days` (list); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].endTime` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].exclude` (bool); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].followActionAccountType` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].id` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].interval` (int); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].operator` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepTargetBalanceFrom` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepTargetBalanceTo` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingAmount` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingDirection` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq` (dict); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.beginTime` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.calendarCode` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.calendarConditionVos` (list); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.calendarType` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.conditionLogical` (int); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.customCalendarId` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.customeType` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.days` (list); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.endTime` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.exclude` (bool); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.followActionAccountType` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.interval` (int); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.timePoint` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingFreq.type` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].sweepingType` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].timePoint` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].timeZone` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].tntInstId` (str); `cashPoolMemberVOS[].cashPoolSwapRuleVOS[].type` (str); `cashPoolName` (str); `cashPoolRequest` (null); `cashPoolType` (str); `cashpoolCapacityVO` (null); `closeAviBalance` (str); `closeBalance` (str); `currentAviBalance` (str); `currentBalance` (str); `entity` (list); `entity[]` (str); `gmtModified` (str); `haircutRatio` (str); `id` (str); `isDelete` (null); `mainCurrency` (str); `memo` (str); `operationStrategyRuleVO` (null); `operator` (str); `pageNo` (int); `pageSize` (int); `processId` (str); `processStatus` (str); `processType` (null); `rowStart` (int); `startindex` (int); `status` (str); `tntInstId` (str); `totalSize` (int); `valueDate` (str); `waterlevelRuleEditVO` (null); `waterlevelRuleVO` (null).

### cash statements end-of-day list / None

Source: `POST /bankAccountDetailDayQuery.json`. Probe IDs: `core-27-r1`, `core-27-r2`, `core-27-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `instIds`, `bankAccountAliasName`, `currency`, `timeZone`, `queryDateBegin`, `queryDateEnd`.

Published UI bundle character offsets: 1517783, 4127893, 4136370.

No populated record schema verified in this case.

### cash statements end-of-day list / previous-day:None

Source: `POST /bankAccountDetailDayQuery.json`. Probe IDs: `previous-day-87-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `instIds`, `bankAccountAliasName`, `currency`, `timeZone`, `queryDateBegin`, `queryDateEnd`.

Published UI bundle character offsets: 1517783, 4127893, 4136370.

No populated record schema verified in this case.

### cash statements intraday list / None

Source: `POST /bankAccountDetailQuery.json`. Probe IDs: `core-26-r1`, `core-26-r2`, `core-26-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `instIds`, `bankAccountAliasName`, `currency`, `timeZone`, `queryDateBegin`, `queryDateEnd`.

Published UI bundle character offsets: 1517591, 4151857, 4160546.

No populated record schema verified in this case.

### cash statements intraday list / previous-day:None

Source: `POST /bankAccountDetailQuery.json`. Probe IDs: `previous-day-86-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `instIds`, `bankAccountAliasName`, `currency`, `timeZone`, `queryDateBegin`, `queryDateEnd`.

Published UI bundle character offsets: 1517591, 4151857, 4160546.

Sample fields: `accountType` (str); `amount` (str); `bankAccountAliasName` (str); `bankId` (str); `bankTransNo` (str); `currency` (str); `date` (str); `end2EndId` (str); `fundDirection` (str); `instId` (str); `memo` (str); `otherAccountName` (str); `otherAccountNo` (str); `otherBankName` (str); `transDate` (str); `transDetail` (str); `transTime` (str); `transType` (str); `valueDate` (str).

### cash wallets list / None

Source: `GET /queryintnalbkactlist.json`. Probe IDs: `core-19-r1`, `core-19-r2`, `core-19-r3`. Record container: `$.result.bankAccountPropertyVOList`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankAccountQueryVO`, `wallet`.

Published UI bundle character offsets: 1486674, 6416948, 6417718.

Sample fields: `accHolder` (str); `accPurpose` (str); `accUser` (str); `accountName` (str); `accountNo` (str); `accountType` (str); `aliasName` (str); `bankId` (str); `bankShortName` (str); `bankSwiftCode` (str); `closeDate` (str); `currency` (str); `currencyCode` (str); `dolLimit` (str); `dolLimitCurrency` (str); `dolMasterAccountNo` (str); `entityCode` (str); `fyOfIntPymt` (str); `gmtCreat` (str); `gmtModified` (str); `id` (str); `innerAccountNo` (str); `innerAccountShortName` (str); `instId` (str); `intBasis` (str); `intPymtDt` (str); `intPymtDtBefore` (str); `intPymtDtLast` (str); `intPymtDtMiddle` (str); `isDirect` (str); `isEcr` (str); `isFloating` (str); `masterAccountFlag` (str); `masterBankId` (str); `msdOfInt` (str); `odDolFlag` (str); `odLimit` (str); `odLimitCurrency` (str); `odMasterAccountNo` (str); `openDate` (str); `operator` (str); `rate` (str); `remark1` (str); `remark2` (str); `remark3` (str); `rnpFlag` (str); `statementSource` (str); `status` (str); `system` (str); `tntInstId` (str).

### cash waterlevels list / None

Source: `POST /bufferReportList.json`. Probe IDs: `core-47-r1`, `core-47-r2`, `core-47-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `aliasNameList`, `pageSize`, `rowStart`.

Published UI bundle character offsets: 11806644, 1649160, 8912590.

Sample fields: `accountType` (str); `aliasName` (str); `bankId` (str); `curAvlBal` (str); `curAvlBalValueTime` (str); `curBufferUpdateTime` (str); `curBufferValueTime` (str); `curCollectionBufferVO` (dict); `curCollectionBufferVO.collectionBuffer` (str); `curCollectionBufferVO.collectionManualBuffer` (str); `curCollectionBufferVO.collectionManualBufferReason` (str); `curCollectionBufferVO.collectionSafetyBuffer` (str); `curCollectionBufferVO.collectionStructureBuffer` (str); `curSafetyBufferVO` (dict); `curSafetyBufferVO.safetyBuffer` (str); `curSafetyBufferVO.safetyManualBuffer` (str); `curSafetyBufferVO.safetyManualBufferReason` (str); `curSafetyBufferVO.safetyPassiveSafetyBuffer` (str); `curSupplementBufferVO` (dict); `curSupplementBufferVO.supplementBuffer` (str); `curSupplementBufferVO.supplementManualBuffer` (str); `curSupplementBufferVO.supplementManualBufferReason` (str); `curSupplementBufferVO.supplementSafetyBuffer` (str); `curSupplementBufferVO.supplementStructureBuffer` (str); `currency` (str); `entity` (str); `preEodAvlBalValueTime` (str); `preEodBufferUpdateTime` (str); `preEodBufferValueTime` (str); `preEodCollectionBufferVO` (dict); `preEodCollectionBufferVO.collectionBuffer` (str); `preEodCollectionBufferVO.collectionManualBuffer` (str); `preEodCollectionBufferVO.collectionManualBufferReason` (str); `preEodCollectionBufferVO.collectionSafetyBuffer` (str); `preEodCollectionBufferVO.collectionStructureBuffer` (str); `preEodSafetyBufferVO` (dict); `preEodSafetyBufferVO.safetyBuffer` (str); `preEodSafetyBufferVO.safetyManualBuffer` (str); `preEodSafetyBufferVO.safetyManualBufferReason` (str); `preEodSafetyBufferVO.safetyPassiveSafetyBuffer` (str); `preEodSupplementBufferVO` (dict); `preEodSupplementBufferVO.supplementBuffer` (str); `preEodSupplementBufferVO.supplementManualBuffer` (str); `preEodSupplementBufferVO.supplementManualBufferReason` (str); `preEodSupplementBufferVO.supplementSafetyBuffer` (str); `preEodSupplementBufferVO.supplementStructureBuffer` (str); `prveEodAvlBal` (str); `timeZone` (str); `valueDate` (str).

### cash waterlevels list / offset10

Source: `POST /bufferReportList.json`. Probe IDs: `page-two-103-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `aliasNameList`, `pageSize`, `rowStart`.

Published UI bundle character offsets: 11806644, 1649160, 8912590.

No populated record schema verified in this case.

### forecast accuracy list / None

Source: `GET /bankCashForecastRecordAccuracyQuery.json`. Probe IDs: `core-36-r1`, `core-36-r2`, `core-36-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankCashForecastRecordQueryVo`.

Published UI bundle character offsets: 1495554, 4661090, 4652805.

Sample fields: `accountNo` (str); `autoFlag` (str); `bankAccountAliasName` (str); `bankId` (str); `baseValueDate` (str); `cashFlowTransIn` (str); `cashFlowTransOut` (str); `cashForecastType` (str); `currency` (str); `forecastBalance` (str); `forecastBatchNo` (int); `forecastRuleId` (str); `forecastTaskId` (str); `gmtCreate` (int); `gmtModified` (int); `id` (str); `instId` (str); `isCoverIod` (str); `isNeedReview` (str); `lastestFlag` (int); `minimumBalance` (str); `minimumBalanceValueTime` (str); `openBalance` (str); `pageNo` (int); `pageSize` (int); `recordCreateTime` (str); `rowStart` (int); `startindex` (int); `tntInstId` (str); `totalSize` (int); `valueDate` (str).

### forecast accuracy list / offset10

Source: `GET /bankCashForecastRecordAccuracyQuery.json`. Probe IDs: `page-two-93-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankCashForecastRecordQueryVo`.

Published UI bundle character offsets: 1495554, 4661090, 4652805.

Sample fields: `accountNo` (str); `autoFlag` (str); `bankAccountAliasName` (str); `bankId` (str); `baseValueDate` (str); `cashFlowTransIn` (str); `cashFlowTransOut` (str); `cashForecastType` (str); `currency` (str); `forecastBalance` (str); `forecastBatchNo` (int); `forecastRuleId` (str); `forecastTaskId` (str); `gmtCreate` (int); `gmtModified` (int); `id` (str); `instId` (str); `isCoverIod` (str); `isNeedReview` (str); `lastestFlag` (int); `minimumBalance` (str); `minimumBalanceValueTime` (str); `openBalance` (str); `pageNo` (int); `pageSize` (int); `recordCreateTime` (str); `rowStart` (int); `startindex` (int); `tntInstId` (str); `totalSize` (int); `valueDate` (str).

### forecast adjustments list / None

Source: `GET /bankCashForecastAdjustmentQuery.json`. Probe IDs: `core-17-r1`, `core-17-r2`, `core-17-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankCashForecastAdjustmentQueryVO`.

Published UI bundle character offsets: 1492814, 4688302, 4688623.

Sample fields: `accountNo` (str); `aliasName` (str); `amount` (str); `bankId` (str); `currency` (str); `entity` (str); `fundDirection` (str); `gmtCreate` (str); `gmtModified` (str); `id` (int); `lastOperator` (str); `memo` (str); `operator` (str); `pageNo` (int); `pageSize` (int); `rowStart` (int); `startindex` (int); `timeZone` (str); `tntInstId` (str); `totalSize` (int); `valueDate` (str); `valueTime` (str).

### forecast adjustments list / offset10

Source: `GET /bankCashForecastAdjustmentQuery.json`. Probe IDs: `page-two-77-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankCashForecastAdjustmentQueryVO`.

Published UI bundle character offsets: 1492814, 4688302, 4688623.

Sample fields: `accountNo` (str); `aliasName` (str); `amount` (str); `bankId` (str); `currency` (str); `entity` (str); `fundDirection` (str); `gmtCreate` (str); `gmtModified` (str); `id` (int); `lastOperator` (str); `memo` (str); `operator` (str); `pageNo` (int); `pageSize` (int); `rowStart` (int); `startindex` (int); `timeZone` (str); `tntInstId` (str); `totalSize` (int); `valueDate` (str); `valueTime` (str).

### forecast cashflows list / None

Source: `GET /queryCashFlowData.json`. Probe IDs: `core-41-r1`, `core-41-r2`, `core-41-r3`. Record container: `$.result.bankAccountCashFlowVOList`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `cashFlowDataQueryVO`.

Published UI bundle character offsets: 1490620, 5603632, 5599360.

No populated record schema verified in this case.

### forecast cashflows list / previous-day:None

Source: `GET /queryCashFlowData.json`. Probe IDs: `previous-day-97-r1`. Record container: `$.result.bankAccountCashFlowVOList`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `cashFlowDataQueryVO`.

Published UI bundle character offsets: 1490620, 5603632, 5599360.

Sample fields: `accountType` (str); `amount` (dict); `amount.amount` (float); `amount.cent` (int); `amount.centFactor` (int); `amount.currency` (str); `amount.currencyCode` (str); `amount.currencyValue` (str); `amountStr` (str); `bankAccountAliasName` (str); `bankAccountFlowDateSourceType` (str); `bankAccountFlowDateSourceTypeStr` (str); `bankAccountNo` (str); `bankId` (str); `currency` (str); `entity` (str); `expectValueDate` (str); `expectValueDateTime` (str); `expectValueTime` (str); `extBizType` (str); `fundDirection` (str); `gmtCreate` (int); `gmtCreateStr` (str); `gmtModified` (int); `gmtModifiedStr` (str); `originalBizNo` (str); `status` (str); `subBizType` (str); `timeZone` (str).

### forecast results list / None

Source: `GET /bankCashForecastRecordQuery.json`. Probe IDs: `core-28-r1`, `core-28-r2`, `core-28-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankCashForecastRecordQueryVo`.

Published UI bundle character offsets: 1492027, 4239591, 4240616.

Sample fields: `accountNo` (str); `autoFlag` (str); `bankAccountAliasName` (str); `bankId` (str); `baseValueDate` (str); `cashFlowTransIn` (str); `cashFlowTransOut` (str); `cashForecastType` (str); `currency` (str); `forecastBalance` (str); `forecastBatchNo` (int); `forecastRuleId` (str); `forecastTaskId` (str); `gmtCreate` (int); `gmtModified` (int); `id` (str); `instId` (str); `isCoverIod` (str); `isNeedReview` (str); `lastestFlag` (int); `minimumBalance` (str); `minimumBalanceValueTime` (str); `openBalance` (str); `pageNo` (int); `pageSize` (int); `recordCreateTime` (str); `rowStart` (int); `startindex` (int); `tntInstId` (str); `totalSize` (int); `valueDate` (str).

### forecast results list / offset10

Source: `GET /bankCashForecastRecordQuery.json`. Probe IDs: `page-two-88-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankCashForecastRecordQueryVo`.

Published UI bundle character offsets: 1492027, 4239591, 4240616.

Sample fields: `accountNo` (str); `autoFlag` (str); `bankAccountAliasName` (str); `bankId` (str); `baseValueDate` (str); `cashFlowTransIn` (str); `cashFlowTransOut` (str); `cashForecastType` (str); `currency` (str); `forecastBalance` (str); `forecastBatchNo` (int); `forecastRuleId` (str); `forecastTaskId` (str); `gmtCreate` (int); `gmtModified` (int); `id` (str); `instId` (str); `isCoverIod` (str); `isNeedReview` (str); `lastestFlag` (int); `minimumBalance` (str); `minimumBalanceValueTime` (str); `openBalance` (str); `pageNo` (int); `pageSize` (int); `recordCreateTime` (str); `rowStart` (int); `startindex` (int); `tntInstId` (str); `totalSize` (int); `valueDate` (str).

### investment benchmark-values list / history

Source: `POST /queryStrategyBenchmarkList.json`. Probe IDs: `business-22-r1`, `business-22-r2`, `business-22-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `valueDateStart`, `valueDateEnd`.

Published UI bundle character offsets: 1519659, 9391819.

No populated record schema verified in this case.

### investment benchmark-values list / previous-day:history

Source: `POST /queryStrategyBenchmarkList.json`. Probe IDs: `previous-day-22-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `valueDateStart`, `valueDateEnd`.

Published UI bundle character offsets: 1519659, 9391819.

No populated record schema verified in this case.

### investment benchmarks list / offset10

Source: `POST /queryStrategyBenchmarkRuleList.json`. Probe IDs: `page-two-21-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `valueDateStart`, `valueDateEnd`.

Published UI bundle character offsets: 1519070, 9389500.

Sample fields: `aliasNameList` (list); `aliasNameList[]` (str); `colorType` (str); `currency` (str); `effectiveDate` (str); `floatDirection` (str); `floatValue` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `lastOperator` (str); `methodType` (str); `operator` (str); `periodNum` (int); `productTerm` (str); `rateProvide` (str); `strategyBenchmarkType` (str); `value` (str); `valueType` (str).

### investment benchmarks list / rules

Source: `POST /queryStrategyBenchmarkRuleList.json`. Probe IDs: `business-21-r1`, `business-21-r2`, `business-21-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `valueDateStart`, `valueDateEnd`.

Published UI bundle character offsets: 1519070, 9389500.

Sample fields: `aliasNameList` (list); `aliasNameList[]` (str); `colorType` (str); `currency` (str); `effectiveDate` (str); `floatDirection` (str); `floatValue` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `lastOperator` (str); `methodType` (str); `operator` (str); `periodNum` (int); `productTerm` (str); `rateProvide` (str); `strategyBenchmarkType` (str); `value` (str); `valueType` (str).

### investment compound-ledger get / None

Source: `POST /compoundOrderDetail.json`. Probe IDs: `business-62-r1`, `business-62-r2`, `business-62-r3`. Record container: `$.data`; total path: `None`.

Encoding: `form`. Top-level request fields: `compoundOrderNo`.

Native identity binding (field names only): `{"leaf": "investment compound-ledger list", "row_field": "orderNo", "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 8399375, 8590451.

Sample fields: `actualIncomeRate` (str); `actualInterestAmount` (str); `actualNetIncomeAmount` (str); `currency` (str); `expectIncomeRate` (str); `expectInterestAmount` (str); `expectNetIncomeAmount` (str); `expireDate` (str); `fixInterestAmount` (str); `fxGainLoss` (str); `incrementCompoundDetailUrl` (str); `interestRate` (str); `lastOperator` (str); `memo` (str); `operator` (str); `orderNo` (str); `orderStatus` (str); `portfolioAmount` (str); `portfolioStrategyName` (str); `processId` (str); `subTransactionOrderVo` (dict); `subTransactionOrderVo.forwardOrderVo` (dict); `subTransactionOrderVo.forwardOrderVo.actualRate` (str); `subTransactionOrderVo.forwardOrderVo.bookId` (str); `subTransactionOrderVo.forwardOrderVo.buyAliasName` (str); `subTransactionOrderVo.forwardOrderVo.buyAmount` (str); `subTransactionOrderVo.forwardOrderVo.buyCurrency` (str); `subTransactionOrderVo.forwardOrderVo.buyInst` (str); `subTransactionOrderVo.forwardOrderVo.currencyPair` (str); `subTransactionOrderVo.forwardOrderVo.expectRate` (str); `subTransactionOrderVo.forwardOrderVo.hedgeOrderId` (str); `subTransactionOrderVo.forwardOrderVo.lastOperator` (str); `subTransactionOrderVo.forwardOrderVo.memo` (str); `subTransactionOrderVo.forwardOrderVo.operator` (str); `subTransactionOrderVo.forwardOrderVo.orderNo` (str); `subTransactionOrderVo.forwardOrderVo.orderStatus` (str); `subTransactionOrderVo.forwardOrderVo.sellAliasName` (str); `subTransactionOrderVo.forwardOrderVo.sellAmount` (str); `subTransactionOrderVo.forwardOrderVo.sellCurrency` (str); `subTransactionOrderVo.forwardOrderVo.sellInst` (str); `subTransactionOrderVo.forwardOrderVo.tradeDate` (str); `subTransactionOrderVo.forwardOrderVo.valueDate` (str); `subTransactionOrderVo.incrementOrderVOS` (list); `subTransactionOrderVo.incrementOrderVOS[]` (dict); `subTransactionOrderVo.incrementOrderVOS[].aliasName` (str); `subTransactionOrderVo.incrementOrderVOS[].amount` (str); `subTransactionOrderVo.incrementOrderVOS[].bankDetailVos` (list); `subTransactionOrderVo.incrementOrderVOS[].bankId` (str); `subTransactionOrderVo.incrementOrderVOS[].buyOrderNo` (str); `subTransactionOrderVo.incrementOrderVOS[].canRedeemAmount` (str); `subTransactionOrderVo.incrementOrderVOS[].compoundId` (str); `subTransactionOrderVo.incrementOrderVOS[].currency` (str); `subTransactionOrderVo.incrementOrderVOS[].cusipNo` (str); `subTransactionOrderVo.incrementOrderVOS[].enquireRateGetMethodVO` (null); `subTransactionOrderVo.incrementOrderVOS[].expireDate` (str); `subTransactionOrderVo.incrementOrderVOS[].fileUrlList` (list); `subTransactionOrderVo.incrementOrderVOS[].fileUrlList[]` (str); `subTransactionOrderVo.incrementOrderVOS[].fundsAccount` (str); `subTransactionOrderVo.incrementOrderVOS[].gainLoss` (str); `subTransactionOrderVo.incrementOrderVOS[].incrementCollateralInfoVO` (null); `subTransactionOrderVo.incrementOrderVOS[].incrementProductVo` (null); `subTransactionOrderVo.incrementOrderVOS[].incrementRiskType` (str); `subTransactionOrderVo.incrementOrderVOS[].instId` (str); `subTransactionOrderVo.incrementOrderVOS[].interestToReceive` (str); `subTransactionOrderVo.incrementOrderVOS[].lastOperator` (str); `subTransactionOrderVo.incrementOrderVOS[].maxTenor` (str); `subTransactionOrderVo.incrementOrderVOS[].memo` (str); `subTransactionOrderVo.incrementOrderVOS[].nav` (str); `subTransactionOrderVo.incrementOrderVOS[].operator` (str); `subTransactionOrderVo.incrementOrderVOS[].orderId` (str); `subTransactionOrderVo.incrementOrderVOS[].orderStatus` (str); `subTransactionOrderVo.incrementOrderVOS[].overnightDepositBuyAliasName` (str); `subTransactionOrderVo.incrementOrderVOS[].overnightDepositRedeemAliasName` (str); `subTransactionOrderVo.incrementOrderVOS[].overnightTermDepositPositionOrderId` (str); `subTransactionOrderVo.incrementOrderVOS[].principalToReceive` (str); `subTransactionOrderVo.incrementOrderVOS[].processId` (str); `subTransactionOrderVo.incrementOrderVOS[].productAttribute` (str); `subTransactionOrderVo.incrementOrderVOS[].productCode` (str); `subTransactionOrderVo.incrementOrderVOS[].productId` (str); `subTransactionOrderVo.incrementOrderVOS[].productTerm` (str); `subTransactionOrderVo.incrementOrderVOS[].productType` (str); `subTransactionOrderVo.incrementOrderVOS[].rateValue` (str); `subTransactionOrderVo.incrementOrderVOS[].redeemAliasName` (str); `subTransactionOrderVo.incrementOrderVOS[].redeemReason` (str); `subTransactionOrderVo.incrementOrderVOS[].redeemedAmount` (str); `subTransactionOrderVo.incrementOrderVOS[].redemptionFee` (str); `subTransactionOrderVo.incrementOrderVOS[].remainingRedeemedShares` (str); `subTransactionOrderVo.incrementOrderVOS[].settlementAccount` (str); `subTransactionOrderVo.incrementOrderVOS[].shares` (str); `subTransactionOrderVo.incrementOrderVOS[].source` (str); `subTransactionOrderVo.incrementOrderVOS[].transactionDate` (str); `subTransactionOrderVo.incrementOrderVOS[].transactionType` (str); `subTransactionOrderVo.incrementOrderVOS[].valueDate` (str); `subTransactionOrderVo.incrementOrderVOS[].virtualAccount` (str); `subTransactionOrderVo.swapOrderVOS` (list); `subTransactionOrderVo.swapOrderVOS[]` (dict); `subTransactionOrderVo.swapOrderVOS[].bookId` (str); `subTransactionOrderVo.swapOrderVOS[].counterParty` (str); `subTransactionOrderVo.swapOrderVOS[].dealId` (str); `subTransactionOrderVo.swapOrderVOS[].decisionMode` (str); `subTransactionOrderVo.swapOrderVOS[].drAlisName` (str); `subTransactionOrderVo.swapOrderVOS[].env` (str); `subTransactionOrderVo.swapOrderVOS[].errorCode` (str); `subTransactionOrderVo.swapOrderVOS[].errorMsg` (str); `subTransactionOrderVo.swapOrderVOS[].expectFarLegFxRate` (str); `subTransactionOrderVo.swapOrderVOS[].expectNearLegFxRate` (str); `subTransactionOrderVo.swapOrderVOS[].farLegCreditAliasName` (str); `subTransactionOrderVo.swapOrderVOS[].farLegCreditAmount` (str); `subTransactionOrderVo.swapOrderVOS[].farLegCreditCcy` (str); `subTransactionOrderVo.swapOrderVOS[].farLegCreditEntity` (str); `subTransactionOrderVo.swapOrderVOS[].farLegCreditSettlementAccount` (str); `subTransactionOrderVo.swapOrderVOS[].farLegDebitAliasName` (str); `subTransactionOrderVo.swapOrderVOS[].farLegDebitAmount` (str); `subTransactionOrderVo.swapOrderVOS[].farLegDebitCcy` (str); `subTransactionOrderVo.swapOrderVOS[].farLegDebitEntity` (str); `subTransactionOrderVo.swapOrderVOS[].farLegDebitSettlementAccount` (str); `subTransactionOrderVo.swapOrderVOS[].farLegFxRate` (str); `subTransactionOrderVo.swapOrderVOS[].farLegValueDate` (str); `subTransactionOrderVo.swapOrderVOS[].firstApproval` (str); `subTransactionOrderVo.swapOrderVOS[].fourthApproval` (str); `subTransactionOrderVo.swapOrderVOS[].gapId` (str); `subTransactionOrderVo.swapOrderVOS[].gmtCreate` (int); `subTransactionOrderVo.swapOrderVOS[].gmtModified` (int); `subTransactionOrderVo.swapOrderVOS[].gmtReturn` (null); `subTransactionOrderVo.swapOrderVOS[].gmtSend` (null); `subTransactionOrderVo.swapOrderVOS[].hedgeOrderId` (str); `subTransactionOrderVo.swapOrderVOS[].instCode` (str); `subTransactionOrderVo.swapOrderVOS[].memo` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegCreditAliasName` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegCreditAmount` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegCreditCcy` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegCreditEntity` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegCreditSettlementAccount` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegDebitAliasName` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegDebitAmount` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegDebitCcy` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegDebitEntity` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegDebitSettlementAccount` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegFxRate` (str); `subTransactionOrderVo.swapOrderVOS[].nearLegValueDate` (str); `subTransactionOrderVo.swapOrderVOS[].needReview` (bool); `subTransactionOrderVo.swapOrderVOS[].nodeNum` (int); `subTransactionOrderVo.swapOrderVOS[].operationTaskId` (str); `subTransactionOrderVo.swapOrderVOS[].operator` (str); `subTransactionOrderVo.swapOrderVOS[].orderId` (str); `subTransactionOrderVo.swapOrderVOS[].orderSource` (str); `subTransactionOrderVo.swapOrderVOS[].processCode` (str); `subTransactionOrderVo.swapOrderVOS[].processId` (str); `subTransactionOrderVo.swapOrderVOS[].reportId` (str); `subTransactionOrderVo.swapOrderVOS[].secondApproval` (str); `subTransactionOrderVo.swapOrderVOS[].source` (str); `subTransactionOrderVo.swapOrderVOS[].status` (str); `subTransactionOrderVo.swapOrderVOS[].thirdApproval` (str); `subTransactionOrderVo.swapOrderVOS[].tntInstId` (str); `subTransactionOrderVo.swapOrderVOS[].tradeDate` (str); `valueDate` (str).

### investment compound-ledger list / None

Source: `POST /compoundOrderList.json`. Probe IDs: `business-03-r1`, `business-03-r2`, `business-03-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1520877, 8394970.

Sample fields: `actualIncomeRate` (str); `actualInterestAmount` (str); `actualNetIncomeAmount` (str); `currency` (str); `expectIncomeRate` (str); `expectInterestAmount` (str); `expectNetIncomeAmount` (str); `expireDate` (str); `fixInterestAmount` (str); `fxGainLoss` (str); `incrementCompoundDetailUrl` (str); `interestRate` (str); `lastOperator` (str); `memo` (str); `operator` (str); `orderNo` (str); `orderStatus` (str); `portfolioAmount` (str); `portfolioStrategyName` (str); `processId` (str); `subTransactionOrderVo` (dict); `subTransactionOrderVo.forwardOrderVo` (null); `subTransactionOrderVo.incrementOrderVOS` (list); `subTransactionOrderVo.swapOrderVOS` (list); `valueDate` (str).

### investment compound-ledger list / offset10

Source: `POST /compoundOrderList.json`. Probe IDs: `page-two-03-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1520877, 8394970.

Sample fields: `actualIncomeRate` (str); `actualInterestAmount` (str); `actualNetIncomeAmount` (str); `currency` (str); `expectIncomeRate` (str); `expectInterestAmount` (str); `expectNetIncomeAmount` (str); `expireDate` (str); `fixInterestAmount` (str); `fxGainLoss` (str); `incrementCompoundDetailUrl` (str); `interestRate` (str); `lastOperator` (str); `memo` (str); `operator` (str); `orderNo` (str); `orderStatus` (str); `portfolioAmount` (str); `portfolioStrategyName` (str); `processId` (str); `subTransactionOrderVo` (dict); `subTransactionOrderVo.forwardOrderVo` (null); `subTransactionOrderVo.incrementOrderVOS` (list); `subTransactionOrderVo.swapOrderVOS` (list); `valueDate` (str).

### investment holdings get / None

Source: `POST /queryIncrementOrderDetail.json`. Probe IDs: `business-23-r1`, `business-23-r2`, `business-23-r3`. Record container: `$.data`; total path: `None`.

Encoding: `form`. Top-level request fields: `orderId`.

Native identity binding (field names only): `{"leaf": "investment holdings list", "row_field": "investmentNo", "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 1515566, 8581000, 7314105, 7304627.

Sample fields: `aliasName` (str); `amount` (str); `bankDetailVos` (list); `bankId` (str); `buyOrderNo` (str); `canRedeemAmount` (str); `compoundId` (str); `currency` (str); `cusipNo` (str); `enquireRateGetMethodVO` (null); `expireDate` (str); `fileUrlList` (list); `fundsAccount` (str); `gainLoss` (str); `incrementCollateralInfoVO` (null); `incrementProductVo` (dict); `incrementProductVo.bankId` (str); `incrementProductVo.benchmarkUpdateTime` (str); `incrementProductVo.calender` (str); `incrementProductVo.collateralProductType` (str); `incrementProductVo.collateralType` (str); `incrementProductVo.currency` (str); `incrementProductVo.cutoffTime` (str); `incrementProductVo.debitBenchmarkUpdateTime` (str); `incrementProductVo.debitCalender` (str); `incrementProductVo.debitRateGetMethod` (str); `incrementProductVo.debitRepricingOffset` (str); `incrementProductVo.debitRepricingPeriod` (str); `incrementProductVo.detailReason` (str); `incrementProductVo.fileUrlList` (list); `incrementProductVo.fundIssuanceCountries` (str); `incrementProductVo.gmtCreate` (int); `incrementProductVo.gmtModified` (int); `incrementProductVo.incrementAccounts` (list); `incrementProductVo.incrementAccounts[]` (dict); `incrementProductVo.incrementAccounts[].aliasName` (str); `incrementProductVo.incrementAccounts[].direct` (str); `incrementProductVo.incrementAccounts[].expireDateRule` (null); `incrementProductVo.incrementAccounts[].incrementInvestmentRule` (null); `incrementProductVo.incrementAccounts[].instId` (str); `incrementProductVo.incrementAccounts[].redeemAliasName` (str); `incrementProductVo.incrementAccounts[].settlementAccount` (str); `incrementProductVo.incrementAccounts[].timeCondition` (null); `incrementProductVo.incrementAccounts[].timeZone` (str); `incrementProductVo.incrementAccounts[].virtualAccount` (str); `incrementProductVo.incrementAccounts[].virtualMode` (bool); `incrementProductVo.incrementDebitRateRules` (list); `incrementProductVo.incrementInterestRule` (dict); `incrementProductVo.incrementInterestRule.interestCalculationBasic` (str); `incrementProductVo.incrementInterestRule.interestCalculationDateRule` (str); `incrementProductVo.incrementInterestRule.interestCalculationFrequency` (str); `incrementProductVo.incrementInterestRule.interestCalculationMethod` (str); `incrementProductVo.incrementInterestRule.interestCalculationNum` (str); `incrementProductVo.incrementInterestRule.interestDaysCalculationType` (str); `incrementProductVo.incrementInterestRule.interestEntryDate` (str); `incrementProductVo.incrementInterestRule.interestIntervalType` (str); `incrementProductVo.incrementInterestRule.settlementDate` (str); `incrementProductVo.incrementProductClass` (str); `incrementProductVo.incrementProductCode` (str); `incrementProductVo.incrementProductId` (str); `incrementProductVo.incrementProductName` (str); `incrementProductVo.incrementProductType` (str); `incrementProductVo.incrementProductTypeCode` (str); `incrementProductVo.incrementRateRules` (list); `incrementProductVo.incrementRateRules[]` (dict); `incrementProductVo.incrementRateRules[].aliasNameList` (list); `incrementProductVo.incrementRateRules[].currency` (str); `incrementProductVo.incrementRateRules[].endDate` (str); `incrementProductVo.incrementRateRules[].gmtCreate` (int); `incrementProductVo.incrementRateRules[].gmtModified` (int); `incrementProductVo.incrementRateRules[].incrementProductId` (str); `incrementProductVo.incrementRateRules[].interestCalculationTierRule` (str); `incrementProductVo.incrementRateRules[].interestCalculationType` (str); `incrementProductVo.incrementRateRules[].ladderRateRules` (list); `incrementProductVo.incrementRateRules[].ladderRateRules[]` (dict); `incrementProductVo.incrementRateRules[].ladderRateRules[].currency` (str); `incrementProductVo.incrementRateRules[].ladderRateRules[].floatDirection` (str); `incrementProductVo.incrementRateRules[].ladderRateRules[].floatValue` (str); `incrementProductVo.incrementRateRules[].ladderRateRules[].inquiryAmount` (str); `incrementProductVo.incrementRateRules[].ladderRateRules[].intervalEndData` (str); `incrementProductVo.incrementRateRules[].ladderRateRules[].intervalStartData` (str); `incrementProductVo.incrementRateRules[].ladderRateRules[].rate` (str); `incrementProductVo.incrementRateRules[].ladderRateRules[].rateCalculateType` (str); `incrementProductVo.incrementRateRules[].ladderRateRules[].ratePeriod` (str); `incrementProductVo.incrementRateRules[].ladderRateRules[].rateProvide` (str); `incrementProductVo.incrementRateRules[].lastOperator` (str); `incrementProductVo.incrementRateRules[].operator` (str); `incrementProductVo.incrementRateRules[].rateRuleId` (str); `incrementProductVo.incrementRateRules[].rateRuleType` (str); `incrementProductVo.incrementRateRules[].startDate` (str); `incrementProductVo.incrementRateRules[].status` (str); `incrementProductVo.incrementRateRules[].tntInstId` (str); `incrementProductVo.incrementRebateRule` (null); `incrementProductVo.incrementRiskType` (str); `incrementProductVo.interestRolloverType` (str); `incrementProductVo.isin` (str); `incrementProductVo.lastOperator` (str); `incrementProductVo.maxTenor` (str); `incrementProductVo.memo` (str); `incrementProductVo.navType` (str); `incrementProductVo.nextRolloverDate` (str); `incrementProductVo.oldIncrementProduct` (null); `incrementProductVo.operator` (str); `incrementProductVo.principalInterestSettlementType` (str); `incrementProductVo.processFlag` (str); `incrementProductVo.processId` (str); `incrementProductVo.productAttribute` (str); `incrementProductVo.productTerm` (str); `incrementProductVo.rateGetMethod` (str); `incrementProductVo.repricingOffset` (str); `incrementProductVo.repricingPeriod` (str); `incrementProductVo.rolloverDateType` (str); `incrementProductVo.settlementTime` (str); `incrementProductVo.stableCoin` (str); `incrementProductVo.status` (str); `incrementProductVo.tntInstId` (str); `incrementProductVo.totalExpenseRatio` (str); `incrementProductVo.version` (int); `incrementRiskType` (str); `instId` (str); `interestToReceive` (str); `lastOperator` (str); `maxTenor` (str); `memo` (str); `nav` (str); `operator` (str); `orderId` (str); `orderStatus` (str); `overnightDepositBuyAliasName` (str); `overnightDepositRedeemAliasName` (str); `overnightTermDepositPositionOrderId` (str); `principalToReceive` (str); `processId` (str); `productAttribute` (str); `productCode` (str); `productId` (str); `productTerm` (str); `productType` (str); `rateValue` (str); `redeemAliasName` (str); `redeemReason` (str); `redeemedAmount` (str); `redemptionFee` (str); `remainingRedeemedShares` (str); `settlementAccount` (str); `shares` (str); `source` (str); `transactionDate` (str); `transactionType` (str); `valueDate` (str); `virtualAccount` (str).

### investment holdings list / None

Source: `POST /portfolioQueryList.json`. Probe IDs: `business-00-r1`, `business-00-r2`, `business-00-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `date`, `status`.

Published UI bundle character offsets: 1515950, 8569479, 8570503.

Sample fields: `accumulateIncomeAmount` (str); `accumulateIncomeInterestDate` (str); `aliasName` (str); `amount` (str); `bankId` (str); `bankInvestment` (str); `canRedeem` (str); `collateralProductType` (str); `collateralType` (str); `currency` (str); `expiryDate` (str); `h2hStatus` (str); `inactiveDate` (str); `instId` (str); `interestEstimate` (str); `interestRate` (str); `investmentNo` (str); `maxTenor` (str); `nav` (str); `outstandingAmount` (str); `productAum` (str); `productCode` (str); `productHoldingProportion` (str); `productNature` (str); `productTenor` (str); `productType` (str); `productUsdAum` (str); `productValueDate` (str); `rebateRate` (str); `redeemAliasName` (str); `redemptionCost` (str); `remainingRedeemedShares` (str); `riskType` (str); `settlementAccount` (str); `shares` (str); `source` (str); `status` (str); `tntInstId` (str); `totalCollateralFaceValue` (str); `totalCollateralRemainingFaceValue` (str); `totalCollateralShares` (str); `totalRemainingCollateralShares` (str); `valueDate` (str).

### investment holdings list / offset10

Source: `POST /portfolioQueryList.json`. Probe IDs: `page-two-00-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `date`, `status`.

Published UI bundle character offsets: 1515950, 8569479, 8570503.

Sample fields: `accumulateIncomeAmount` (str); `accumulateIncomeInterestDate` (str); `aliasName` (str); `amount` (str); `bankId` (str); `bankInvestment` (str); `canRedeem` (str); `collateralProductType` (str); `collateralType` (str); `currency` (str); `expiryDate` (str); `h2hStatus` (str); `inactiveDate` (str); `instId` (str); `interestEstimate` (str); `interestRate` (str); `investmentNo` (str); `maxTenor` (str); `nav` (str); `outstandingAmount` (str); `productAum` (str); `productCode` (str); `productHoldingProportion` (str); `productNature` (str); `productTenor` (str); `productType` (str); `productUsdAum` (str); `productValueDate` (str); `rebateRate` (str); `redeemAliasName` (str); `redemptionCost` (str); `remainingRedeemedShares` (str); `riskType` (str); `settlementAccount` (str); `shares` (str); `source` (str); `status` (str); `tntInstId` (str); `totalCollateralFaceValue` (str); `totalCollateralRemainingFaceValue` (str); `totalCollateralShares` (str); `totalRemainingCollateralShares` (str); `valueDate` (str).

### investment interest-rates list / bank-quoted

Source: `POST /queryEnquireRateList.json`. Probe IDs: `business-19-r1`, `business-19-r2`, `business-19-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `beginDate`, `endDate`.

Published UI bundle character offsets: 1522812, 8369069.

No populated record schema verified in this case.

### investment interest-rates list / market

Source: `POST /incrementBaseRateList.json`. Probe IDs: `business-18-r1`, `business-18-r2`, `business-18-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `beginDate`, `endDate`, `timeZone`, `currency`, `productTerm`, `isPage`.

Published UI bundle character offsets: 1514899, 8367000.

Sample fields: `currency` (str); `effectiveDate` (str); `processId` (str); `processStatus` (str); `rateName` (str); `ratePeriod` (str); `rateProvide` (str); `rateType` (str); `rateValue` (str); `sourceType` (str).

### investment interest-rates list / offset10

Source: `POST /incrementBaseRateList.json`. Probe IDs: `page-two-18-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `beginDate`, `endDate`, `timeZone`, `currency`, `productTerm`, `isPage`.

Published UI bundle character offsets: 1514899, 8367000.

No populated record schema verified in this case.

### investment interest-rates list / previous-day:bank-quoted

Source: `POST /queryEnquireRateList.json`. Probe IDs: `previous-day-19-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `beginDate`, `endDate`.

Published UI bundle character offsets: 1522812, 8369069.

No populated record schema verified in this case.

### investment investable-funds list / None

Source: `POST /queryInvestableFundList.json`. Probe IDs: `business-38-r1`, `business-38-r2`, `business-38-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `reportDate`, `startForecastDate`, `endForecastDate`.

Published UI bundle character offsets: 8386634, 8387658.

No populated record schema verified in this case.

### investment investable-funds list / previous-day:None

Source: `POST /queryInvestableFundList.json`. Probe IDs: `previous-day-33-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `reportDate`, `startForecastDate`, `endForecastDate`.

Published UI bundle character offsets: 8386634, 8387658.

No populated record schema verified in this case.

### investment products get / None

Source: `POST /incrementProductDetail.json`. Probe IDs: `business-61-r1`, `business-61-r2`, `business-61-r3`. Record container: `$.data`; total path: `None`.

Encoding: `form`. Top-level request fields: `tntInstId`, `incrementProductId`.

Native identity binding (field names only): `{"leaf": "investment products list", "row_field": "incrementProductId", "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 9289093, 9096287.

Sample fields: `bankId` (str); `benchmarkUpdateTime` (str); `calender` (str); `collateralProductType` (str); `collateralType` (str); `currency` (str); `cutoffTime` (str); `debitBenchmarkUpdateTime` (str); `debitCalender` (str); `debitRateGetMethod` (str); `debitRepricingOffset` (str); `debitRepricingPeriod` (str); `detailReason` (str); `fileUrlList` (list); `fileUrlList[]` (str); `fundIssuanceCountries` (str); `gmtCreate` (int); `gmtModified` (int); `incrementAccounts` (list); `incrementAccounts[]` (dict); `incrementAccounts[].aliasName` (str); `incrementAccounts[].direct` (str); `incrementAccounts[].expireDateRule` (null); `incrementAccounts[].incrementInvestmentRule` (null); `incrementAccounts[].instId` (str); `incrementAccounts[].redeemAliasName` (str); `incrementAccounts[].settlementAccount` (str); `incrementAccounts[].timeCondition` (null); `incrementAccounts[].timeZone` (str); `incrementAccounts[].virtualAccount` (str); `incrementAccounts[].virtualMode` (bool); `incrementDebitRateRules` (list); `incrementInterestRule` (dict); `incrementInterestRule.interestCalculationBasic` (str); `incrementInterestRule.interestCalculationDateRule` (str); `incrementInterestRule.interestCalculationFrequency` (str); `incrementInterestRule.interestCalculationMethod` (str); `incrementInterestRule.interestCalculationNum` (str); `incrementInterestRule.interestDaysCalculationType` (str); `incrementInterestRule.interestEntryDate` (str); `incrementInterestRule.interestIntervalType` (str); `incrementInterestRule.settlementDate` (str); `incrementProductClass` (str); `incrementProductCode` (str); `incrementProductId` (str); `incrementProductName` (str); `incrementProductType` (str); `incrementProductTypeCode` (str); `incrementRateRules` (list); `incrementRateRules[]` (dict); `incrementRateRules[].aliasNameList` (list); `incrementRateRules[].aliasNameList[]` (str); `incrementRateRules[].currency` (str); `incrementRateRules[].endDate` (str); `incrementRateRules[].gmtCreate` (int); `incrementRateRules[].gmtModified` (int); `incrementRateRules[].incrementProductId` (str); `incrementRateRules[].interestCalculationTierRule` (str); `incrementRateRules[].interestCalculationType` (str); `incrementRateRules[].ladderRateRules` (list); `incrementRateRules[].ladderRateRules[]` (dict); `incrementRateRules[].ladderRateRules[].currency` (str); `incrementRateRules[].ladderRateRules[].floatDirection` (str); `incrementRateRules[].ladderRateRules[].floatValue` (str); `incrementRateRules[].ladderRateRules[].inquiryAmount` (str); `incrementRateRules[].ladderRateRules[].intervalEndData` (str); `incrementRateRules[].ladderRateRules[].intervalStartData` (str); `incrementRateRules[].ladderRateRules[].rate` (str); `incrementRateRules[].ladderRateRules[].rateCalculateType` (str); `incrementRateRules[].ladderRateRules[].ratePeriod` (str); `incrementRateRules[].ladderRateRules[].rateProvide` (str); `incrementRateRules[].lastOperator` (str); `incrementRateRules[].operator` (str); `incrementRateRules[].rateRuleId` (str); `incrementRateRules[].rateRuleType` (str); `incrementRateRules[].startDate` (str); `incrementRateRules[].status` (str); `incrementRateRules[].tntInstId` (str); `incrementRebateRule` (null); `incrementRiskType` (str); `interestRolloverType` (str); `isin` (str); `lastOperator` (str); `maxTenor` (str); `memo` (str); `navType` (str); `nextRolloverDate` (str); `oldIncrementProduct` (null); `operator` (str); `principalInterestSettlementType` (str); `processFlag` (str); `processId` (str); `productAttribute` (str); `productTerm` (str); `rateGetMethod` (str); `repricingOffset` (str); `repricingPeriod` (str); `rolloverDateType` (str); `settlementTime` (str); `stableCoin` (str); `status` (str); `tntInstId` (str); `totalExpenseRatio` (str); `version` (int).

### investment products history / None

Source: `POST /incrementProductHistoryQuery.json`. Probe IDs: `business-27-r1`, `business-27-r2`, `business-27-r3`. Record container: `$.data`; total path: `None`.

Encoding: `form`. Top-level request fields: `incrementProductCode`, `tntInstId`.

Native identity binding (field names only): `{"leaf": "investment products list", "row_field": "incrementProductCode", "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 1515661, 9093457, 9137098.

Sample fields: `bankId` (str); `benchmarkUpdateTime` (str); `calender` (str); `collateralProductType` (str); `collateralType` (str); `currency` (str); `cutoffTime` (str); `debitBenchmarkUpdateTime` (str); `debitCalender` (str); `debitRateGetMethod` (str); `debitRepricingOffset` (str); `debitRepricingPeriod` (str); `detailReason` (str); `fileUrlList` (list); `fileUrlList[]` (str); `fundIssuanceCountries` (str); `gmtCreate` (int); `gmtModified` (int); `incrementAccounts` (list); `incrementAccounts[]` (dict); `incrementAccounts[].aliasName` (str); `incrementAccounts[].direct` (str); `incrementAccounts[].expireDateRule` (null); `incrementAccounts[].incrementInvestmentRule` (null); `incrementAccounts[].instId` (str); `incrementAccounts[].redeemAliasName` (str); `incrementAccounts[].settlementAccount` (str); `incrementAccounts[].timeCondition` (null); `incrementAccounts[].timeZone` (str); `incrementAccounts[].virtualAccount` (str); `incrementAccounts[].virtualMode` (bool); `incrementDebitRateRules` (list); `incrementInterestRule` (dict); `incrementInterestRule.interestCalculationBasic` (str); `incrementInterestRule.interestCalculationDateRule` (str); `incrementInterestRule.interestCalculationFrequency` (str); `incrementInterestRule.interestCalculationMethod` (str); `incrementInterestRule.interestCalculationNum` (str); `incrementInterestRule.interestDaysCalculationType` (str); `incrementInterestRule.interestEntryDate` (str); `incrementInterestRule.interestIntervalType` (str); `incrementInterestRule.settlementDate` (str); `incrementProductClass` (str); `incrementProductCode` (str); `incrementProductId` (str); `incrementProductName` (str); `incrementProductType` (str); `incrementProductTypeCode` (str); `incrementRateRules` (list); `incrementRateRules[]` (dict); `incrementRateRules[].aliasNameList` (list); `incrementRateRules[].aliasNameList[]` (str); `incrementRateRules[].currency` (str); `incrementRateRules[].endDate` (str); `incrementRateRules[].gmtCreate` (int); `incrementRateRules[].gmtModified` (int); `incrementRateRules[].incrementProductId` (str); `incrementRateRules[].interestCalculationTierRule` (str); `incrementRateRules[].interestCalculationType` (str); `incrementRateRules[].ladderRateRules` (list); `incrementRateRules[].ladderRateRules[]` (dict); `incrementRateRules[].ladderRateRules[].currency` (str); `incrementRateRules[].ladderRateRules[].floatDirection` (str); `incrementRateRules[].ladderRateRules[].floatValue` (str); `incrementRateRules[].ladderRateRules[].inquiryAmount` (str); `incrementRateRules[].ladderRateRules[].intervalEndData` (str); `incrementRateRules[].ladderRateRules[].intervalStartData` (str); `incrementRateRules[].ladderRateRules[].rate` (str); `incrementRateRules[].ladderRateRules[].rateCalculateType` (str); `incrementRateRules[].ladderRateRules[].ratePeriod` (str); `incrementRateRules[].ladderRateRules[].rateProvide` (str); `incrementRateRules[].lastOperator` (str); `incrementRateRules[].operator` (str); `incrementRateRules[].rateRuleId` (str); `incrementRateRules[].rateRuleType` (str); `incrementRateRules[].startDate` (str); `incrementRateRules[].status` (str); `incrementRateRules[].tntInstId` (str); `incrementRebateRule` (null); `incrementRiskType` (str); `interestRolloverType` (str); `isin` (str); `lastOperator` (str); `maxTenor` (str); `memo` (str); `navType` (str); `nextRolloverDate` (str); `oldIncrementProduct` (null); `operator` (str); `principalInterestSettlementType` (str); `processFlag` (str); `processId` (str); `productAttribute` (str); `productTerm` (str); `rateGetMethod` (str); `repricingOffset` (str); `repricingPeriod` (str); `rolloverDateType` (str); `settlementTime` (str); `stableCoin` (str); `status` (str); `tntInstId` (str); `totalExpenseRatio` (str); `version` (int).

### investment products list / None

Source: `POST /incrementProductsPage.json`. Probe IDs: `business-01-r1`, `business-01-r2`, `business-01-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1514708, 9286026, 9286555.

Sample fields: `bankId` (str); `benchmarkUpdateTime` (str); `calender` (str); `collateralProductType` (str); `collateralType` (str); `currency` (str); `cutoffTime` (str); `debitBenchmarkUpdateTime` (str); `debitCalender` (str); `debitRateGetMethod` (str); `debitRepricingOffset` (str); `debitRepricingPeriod` (str); `detailReason` (str); `fileUrlList` (list); `fundIssuanceCountries` (str); `gmtCreate` (int); `gmtModified` (int); `incrementAccounts` (list); `incrementAccounts[]` (dict); `incrementAccounts[].aliasName` (str); `incrementAccounts[].direct` (str); `incrementAccounts[].expireDateRule` (null); `incrementAccounts[].incrementInvestmentRule` (null); `incrementAccounts[].instId` (str); `incrementAccounts[].redeemAliasName` (str); `incrementAccounts[].settlementAccount` (str); `incrementAccounts[].timeCondition` (null); `incrementAccounts[].timeZone` (str); `incrementAccounts[].virtualAccount` (str); `incrementAccounts[].virtualMode` (bool); `incrementDebitRateRules` (list); `incrementInterestRule` (dict); `incrementInterestRule.interestCalculationBasic` (str); `incrementInterestRule.interestCalculationDateRule` (str); `incrementInterestRule.interestCalculationFrequency` (str); `incrementInterestRule.interestCalculationMethod` (str); `incrementInterestRule.interestCalculationNum` (str); `incrementInterestRule.interestDaysCalculationType` (str); `incrementInterestRule.interestEntryDate` (str); `incrementInterestRule.interestIntervalType` (str); `incrementInterestRule.settlementDate` (str); `incrementProductClass` (str); `incrementProductCode` (str); `incrementProductId` (str); `incrementProductName` (str); `incrementProductType` (str); `incrementProductTypeCode` (str); `incrementRateRules` (list); `incrementRateRules[]` (dict); `incrementRateRules[].aliasNameList` (list); `incrementRateRules[].aliasNameList[]` (str); `incrementRateRules[].currency` (str); `incrementRateRules[].endDate` (str); `incrementRateRules[].gmtCreate` (int); `incrementRateRules[].gmtModified` (int); `incrementRateRules[].incrementProductId` (str); `incrementRateRules[].interestCalculationTierRule` (str); `incrementRateRules[].interestCalculationType` (str); `incrementRateRules[].ladderRateRules` (list); `incrementRateRules[].ladderRateRules[]` (dict); `incrementRateRules[].lastOperator` (str); `incrementRateRules[].operator` (str); `incrementRateRules[].rateRuleId` (str); `incrementRateRules[].rateRuleType` (str); `incrementRateRules[].startDate` (str); `incrementRateRules[].status` (str); `incrementRateRules[].tntInstId` (str); `incrementRebateRule` (null); `incrementRiskType` (str); `interestRolloverType` (str); `isin` (str); `lastOperator` (str); `maxTenor` (str); `memo` (str); `navType` (str); `nextRolloverDate` (str); `oldIncrementProduct` (null); `operator` (str); `principalInterestSettlementType` (str); `processFlag` (str); `processId` (str); `productAttribute` (str); `productTerm` (str); `rateGetMethod` (str); `repricingOffset` (str); `repricingPeriod` (str); `rolloverDateType` (str); `settlementTime` (str); `stableCoin` (str); `status` (str); `tntInstId` (str); `totalExpenseRatio` (str); `version` (int).

### investment products list / offset10

Source: `POST /incrementProductsPage.json`. Probe IDs: `page-two-01-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1514708, 9286026, 9286555.

Sample fields: `bankId` (str); `benchmarkUpdateTime` (str); `calender` (str); `collateralProductType` (str); `collateralType` (str); `currency` (str); `cutoffTime` (str); `debitBenchmarkUpdateTime` (str); `debitCalender` (str); `debitRateGetMethod` (str); `debitRepricingOffset` (str); `debitRepricingPeriod` (str); `detailReason` (str); `fileUrlList` (list); `fundIssuanceCountries` (str); `gmtCreate` (int); `gmtModified` (int); `incrementAccounts` (list); `incrementAccounts[]` (dict); `incrementAccounts[].aliasName` (str); `incrementAccounts[].direct` (str); `incrementAccounts[].expireDateRule` (null); `incrementAccounts[].incrementInvestmentRule` (null); `incrementAccounts[].instId` (str); `incrementAccounts[].redeemAliasName` (str); `incrementAccounts[].settlementAccount` (str); `incrementAccounts[].timeCondition` (null); `incrementAccounts[].timeZone` (str); `incrementAccounts[].virtualAccount` (str); `incrementAccounts[].virtualMode` (bool); `incrementDebitRateRules` (list); `incrementInterestRule` (dict); `incrementInterestRule.interestCalculationBasic` (str); `incrementInterestRule.interestCalculationDateRule` (str); `incrementInterestRule.interestCalculationFrequency` (str); `incrementInterestRule.interestCalculationMethod` (str); `incrementInterestRule.interestCalculationNum` (str); `incrementInterestRule.interestDaysCalculationType` (str); `incrementInterestRule.interestEntryDate` (str); `incrementInterestRule.interestIntervalType` (str); `incrementInterestRule.settlementDate` (str); `incrementProductClass` (str); `incrementProductCode` (str); `incrementProductId` (str); `incrementProductName` (str); `incrementProductType` (str); `incrementProductTypeCode` (str); `incrementRateRules` (list); `incrementRateRules[]` (dict); `incrementRateRules[].aliasNameList` (list); `incrementRateRules[].aliasNameList[]` (str); `incrementRateRules[].currency` (str); `incrementRateRules[].endDate` (str); `incrementRateRules[].gmtCreate` (int); `incrementRateRules[].gmtModified` (int); `incrementRateRules[].incrementProductId` (str); `incrementRateRules[].interestCalculationTierRule` (str); `incrementRateRules[].interestCalculationType` (str); `incrementRateRules[].ladderRateRules` (list); `incrementRateRules[].ladderRateRules[]` (dict); `incrementRateRules[].lastOperator` (str); `incrementRateRules[].operator` (str); `incrementRateRules[].rateRuleId` (str); `incrementRateRules[].rateRuleType` (str); `incrementRateRules[].startDate` (str); `incrementRateRules[].status` (str); `incrementRateRules[].tntInstId` (str); `incrementRebateRule` (null); `incrementRiskType` (str); `interestRolloverType` (str); `isin` (str); `lastOperator` (str); `maxTenor` (str); `memo` (str); `navType` (str); `nextRolloverDate` (str); `oldIncrementProduct` (null); `operator` (str); `principalInterestSettlementType` (str); `processFlag` (str); `processId` (str); `productAttribute` (str); `productTerm` (str); `rateGetMethod` (str); `repricingOffset` (str); `repricingPeriod` (str); `rolloverDateType` (str); `settlementTime` (str); `stableCoin` (str); `status` (str); `tntInstId` (str); `totalExpenseRatio` (str); `version` (int).

### investment quote-groups get / None

Source: `POST /queryQuotationDetail.json`. Probe IDs: `business-32-r1`. Record container: `None`; total path: `None`.

Encoding: `form`. Top-level request fields: `quotationGroupId`.

Native identity binding (field names only): `{"leaf": "investment quote-groups list", "row_field": "quotationGroupId", "source_path": "data[0]"}`.

Published UI bundle character offsets: 9901722.

No populated record schema verified in this case.

### investment quote-groups list / None

Source: `POST /queryQuotationGroup.json`. Probe IDs: `business-28-r1`, `business-28-r2`, `business-28-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json`. Top-level request fields: `pageSize`, `rowStart`.

Published UI bundle character offsets: 1529440, 9893934.

Sample fields: `bankId` (str); `contactInfoList` (list); `contactInfoList[]` (dict); `contactInfoList[].emailAddress` (str); `contactInfoList[].memo` (str); `contactInfoList[].name` (str); `contactInformation` (str); `contactMethod` (str); `department` (str); `detailReason` (str); `fileDownloadUrl` (str); `fileKey` (str); `fileName` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `isReview` (bool); `lastModifiedTime` (str); `lastOperator` (str); `memo` (str); `operationHistoryList` (list); `operator` (str); `processId` (str); `processStatus` (str); `quotationGroupId` (str); `quotationGroupName` (str); `reviewLink` (str); `status` (str); `tntInstId` (str); `version` (int).

### investment quotes list / QUOTED

Source: `POST /quotationAnalysis.json`. Probe IDs: `business-30-r1`, `business-30-r2`, `business-30-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json`. Top-level request fields: `pageSize`, `rowStart`, `dataType`, `startValueDate`, `endValueDate`, `timeZone`.

Published UI bundle character offsets: 1532010, 11130076.

No populated record schema verified in this case.

### investment quotes list / WIN

Source: `POST /quotationAnalysis.json`. Probe IDs: `business-31-r1`, `business-31-r2`, `business-31-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json`. Top-level request fields: `pageSize`, `rowStart`, `dataType`, `startValueDate`, `endValueDate`, `timeZone`.

Published UI bundle character offsets: 1532010, 11130076.

No populated record schema verified in this case.

### investment quotes list / previous-day:QUOTED

Source: `POST /quotationAnalysis.json`. Probe IDs: `previous-day-27-r1`. Record container: `$.data`; total path: `None`.

Encoding: `json`. Top-level request fields: `pageSize`, `rowStart`, `dataType`, `startValueDate`, `endValueDate`, `timeZone`.

Published UI bundle character offsets: 1532010, 11130076.

No populated record schema verified in this case.

### investment quotes list / previous-day:WIN

Source: `POST /quotationAnalysis.json`. Probe IDs: `previous-day-28-r1`. Record container: `$.data`; total path: `None`.

Encoding: `json`. Top-level request fields: `pageSize`, `rowStart`, `dataType`, `startValueDate`, `endValueDate`, `timeZone`.

Published UI bundle character offsets: 1532010, 11130076.

No populated record schema verified in this case.

### investment returns list / accrual

Source: `POST /accrualBaseList.json`. Probe IDs: `business-42-r1`, `business-42-r2`, `business-42-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `queryBeginTime`, `queryEndTime`, `transactionId`.

Published UI bundle character offsets: 9558400.

No populated record schema verified in this case.

### investment returns list / cash

Source: `POST /cashBaseList.json`. Probe IDs: `business-43-r1`, `business-43-r2`, `business-43-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `settlementDateBegin`, `settlementDateEnd`, `postingDateBegin`, `postingDateEnd`.

Published UI bundle character offsets: 9560100.

No populated record schema verified in this case.

### investment returns list / previous-day:accrual

Source: `POST /accrualBaseList.json`. Probe IDs: `previous-day-36-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `queryBeginTime`, `queryEndTime`, `transactionId`.

Published UI bundle character offsets: 9558400.

Sample fields: `accrualBaseAmount` (str); `aliasName` (str); `bankId` (str); `colorType` (str); `currency` (str); `instCode` (str); `interestAmount` (str); `interestRate` (str); `investmentAliasName` (str); `investmentNo` (str); `nav` (str); `productAttribute` (str); `productCode` (str); `settlementAccount` (str); `shares` (str); `subInterestAmount` (str); `subInterestRate` (str); `subRebateAmount` (str); `subRebateRate` (str); `transactionDate` (str).

### investment returns list / previous-day:cash

Source: `POST /cashBaseList.json`. Probe IDs: `previous-day-37-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `settlementDateBegin`, `settlementDateEnd`, `postingDateBegin`, `postingDateEnd`.

Published UI bundle character offsets: 9560100.

Sample fields: `accountingEntityCode` (str); `aliasName` (str); `bankId` (str); `colorType` (str); `currency` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `instId` (str); `interestIncome` (str); `interestRate` (str); `interestType` (str); `lastOperate` (str); `operate` (str); `postingDate` (str); `principalAmount` (str); `productAttribute` (str); `productCode` (str); `settlementAccount` (str); `settlementDate` (str); `transactionId` (str); `valueDate` (str); `virtualAccount` (str).

### investment rfqs list / None

Source: `POST /rfq/subInquiryTask/querySubInquiryTask.json`. Probe IDs: `business-29-r1`. Record container: `None`; total path: `None`.

Encoding: `json`. Top-level request fields: `pageSize`, `rowStart`, `inquiryStartDate`, `inquiryEndDate`.

Published UI bundle character offsets: 1530050, 9918712.

No populated record schema verified in this case.

### investment strategies get / None

Source: `POST /queryIncrementStrategyRuleDetail.json`. Probe IDs: `business-69-r1`, `business-69-r2`, `business-69-r3`. Record container: `$.data`; total path: `None`.

Encoding: `form`. Top-level request fields: `strategyRuleCode`.

Native identity binding (field names only): `{"leaf": "investment strategies list", "row_field": "strategyRuleCode", "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 9349903, 9318320.

Sample fields: `canUsedCashPool` (str); `currencyStrategyRuleVoList` (list); `currencyStrategyRuleVoList[]` (dict); `currencyStrategyRuleVoList[].bankId` (str); `currencyStrategyRuleVoList[].depositCurrency` (str); `currencyStrategyRuleVoList[].originalCurrency` (str); `currencyStrategyRuleVoList[].productTermList` (list); `currencyStrategyRuleVoList[].productTermList[]` (str); `defaultExecutionStrategy` (str); `earlyRedemptionRatio` (str); `gmtCreate` (str); `gmtModified` (str); `lastOperator` (str); `marketExpectation` (str); `marketExpectationMode` (str); `memo` (str); `operator` (str); `productStrategyRuleVoList` (list); `status` (str); `strategyRuleCode` (str); `subStrategyRuleList` (list); `subStrategyRuleList[]` (str); `tenorStrategyRuleVoList` (list); `tenorStrategyRuleVoList[]` (dict); `tenorStrategyRuleVoList[].bankId` (str); `tenorStrategyRuleVoList[].productTermList` (list); `tenorStrategyRuleVoList[].productTermList[]` (str).

### investment strategies list / None

Source: `POST /queryIncrementStrategyRuleList.json`. Probe IDs: `business-20-r1`, `business-20-r2`, `business-20-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`.

Published UI bundle character offsets: 1523391, 9351729.

Sample fields: `canUsedCashPool` (str); `currencyStrategyRuleVoList` (list); `currencyStrategyRuleVoList[]` (dict); `currencyStrategyRuleVoList[].bankId` (str); `currencyStrategyRuleVoList[].depositCurrency` (str); `currencyStrategyRuleVoList[].originalCurrency` (str); `currencyStrategyRuleVoList[].productTermList` (list); `currencyStrategyRuleVoList[].productTermList[]` (str); `defaultExecutionStrategy` (str); `earlyRedemptionRatio` (str); `gmtCreate` (str); `gmtModified` (str); `lastOperator` (str); `marketExpectation` (str); `marketExpectationMode` (str); `memo` (str); `operator` (str); `productStrategyRuleVoList` (list); `status` (str); `strategyRuleCode` (str); `subStrategyRuleList` (list); `subStrategyRuleList[]` (str); `tenorStrategyRuleVoList` (list); `tenorStrategyRuleVoList[]` (dict); `tenorStrategyRuleVoList[].bankId` (str); `tenorStrategyRuleVoList[].productTermList` (list); `tenorStrategyRuleVoList[].productTermList[]` (str).

### investment strategies list / offset10

Source: `POST /queryIncrementStrategyRuleList.json`. Probe IDs: `page-two-20-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`.

Published UI bundle character offsets: 1523391, 9351729.

No populated record schema verified in this case.

### investment strategy-results list / FUND_DECISION_TASK

Source: `POST /api/increment/decision/task/queryPage.json`. Probe IDs: `business-39-r1`, `business-39-r2`, `business-39-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `taskType`, `triggerStartDate`, `triggerEndDate`.

Published UI bundle character offsets: 11435946, 11449996.

No populated record schema verified in this case.

### investment strategy-results list / PRODUCT_DECISION_TASK

Source: `POST /api/increment/decision/task/queryPage.json`. Probe IDs: `business-40-r1`, `business-40-r2`, `business-40-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `taskType`, `triggerStartDate`, `triggerEndDate`.

Published UI bundle character offsets: 11435946, 11449996.

No populated record schema verified in this case.

### investment strategy-results list / previous-day:FUND_DECISION_TASK

Source: `POST /api/increment/decision/task/queryPage.json`. Probe IDs: `previous-day-34-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `taskType`, `triggerStartDate`, `triggerEndDate`.

Published UI bundle character offsets: 11435946, 11449996.

No populated record schema verified in this case.

### investment strategy-results list / previous-day:PRODUCT_DECISION_TASK

Source: `POST /api/increment/decision/task/queryPage.json`. Probe IDs: `previous-day-35-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `taskType`, `triggerStartDate`, `triggerEndDate`.

Published UI bundle character offsets: 11435946, 11449996.

No populated record schema verified in this case.

### investment transactions get / None

Source: `POST /queryIncrementOrderDetail.json`. Probe IDs: `business-24-r1`, `business-24-r2`, `business-24-r3`. Record container: `$.data`; total path: `None`.

Encoding: `form`. Top-level request fields: `orderId`.

Native identity binding (field names only): `{"leaf": "investment transactions list", "row_field": "orderId", "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 1515566, 9461736.

Sample fields: `aliasName` (str); `amount` (str); `bankDetailVos` (list); `bankId` (str); `buyOrderNo` (str); `canRedeemAmount` (str); `compoundId` (str); `currency` (str); `cusipNo` (str); `enquireRateGetMethodVO` (null); `expireDate` (str); `fileUrlList` (list); `fundsAccount` (str); `gainLoss` (str); `incrementCollateralInfoVO` (dict); `incrementCollateralInfoVO.collateralProductType` (str); `incrementCollateralInfoVO.collateralType` (str); `incrementCollateralInfoVO.remainingCollateralFaceValueAmount` (str); `incrementCollateralInfoVO.remainingCollateralShares` (str); `incrementCollateralInfoVO.totalCollateralFaceValueAmount` (str); `incrementCollateralInfoVO.totalCollateralShares` (str); `incrementProductVo` (dict); `incrementProductVo.bankId` (str); `incrementProductVo.benchmarkUpdateTime` (str); `incrementProductVo.calender` (str); `incrementProductVo.collateralProductType` (str); `incrementProductVo.collateralType` (str); `incrementProductVo.currency` (str); `incrementProductVo.cutoffTime` (str); `incrementProductVo.debitBenchmarkUpdateTime` (str); `incrementProductVo.debitCalender` (str); `incrementProductVo.debitRateGetMethod` (str); `incrementProductVo.debitRepricingOffset` (str); `incrementProductVo.debitRepricingPeriod` (str); `incrementProductVo.detailReason` (str); `incrementProductVo.fileUrlList` (list); `incrementProductVo.fundIssuanceCountries` (str); `incrementProductVo.gmtCreate` (int); `incrementProductVo.gmtModified` (int); `incrementProductVo.incrementAccounts` (list); `incrementProductVo.incrementAccounts[]` (dict); `incrementProductVo.incrementAccounts[].aliasName` (str); `incrementProductVo.incrementAccounts[].direct` (str); `incrementProductVo.incrementAccounts[].expireDateRule` (dict); `incrementProductVo.incrementAccounts[].expireDateRule.beginTime` (str); `incrementProductVo.incrementAccounts[].expireDateRule.calendarCode` (str); `incrementProductVo.incrementAccounts[].expireDateRule.calendarConditionVos` (list); `incrementProductVo.incrementAccounts[].expireDateRule.calendarConditionVos[]` (dict); `incrementProductVo.incrementAccounts[].expireDateRule.calendarType` (str); `incrementProductVo.incrementAccounts[].expireDateRule.conditionLogical` (int); `incrementProductVo.incrementAccounts[].expireDateRule.customCalendarId` (str); `incrementProductVo.incrementAccounts[].expireDateRule.customeType` (str); `incrementProductVo.incrementAccounts[].expireDateRule.days` (list); `incrementProductVo.incrementAccounts[].expireDateRule.endTime` (str); `incrementProductVo.incrementAccounts[].expireDateRule.exclude` (bool); `incrementProductVo.incrementAccounts[].expireDateRule.followActionAccountType` (str); `incrementProductVo.incrementAccounts[].expireDateRule.interval` (int); `incrementProductVo.incrementAccounts[].expireDateRule.timePoint` (str); `incrementProductVo.incrementAccounts[].expireDateRule.type` (str); `incrementProductVo.incrementAccounts[].incrementInvestmentRule` (dict); `incrementProductVo.incrementAccounts[].incrementInvestmentRule.investmentFrequency` (null); `incrementProductVo.incrementAccounts[].incrementInvestmentRule.investmentSubType` (str); `incrementProductVo.incrementAccounts[].incrementInvestmentRule.investmentTimeZone` (str); `incrementProductVo.incrementAccounts[].incrementInvestmentRule.investmentType` (str); `incrementProductVo.incrementAccounts[].incrementInvestmentRule.purchaseAccountTargetBalance` (str); `incrementProductVo.incrementAccounts[].instId` (str); `incrementProductVo.incrementAccounts[].redeemAliasName` (str); `incrementProductVo.incrementAccounts[].settlementAccount` (str); `incrementProductVo.incrementAccounts[].timeCondition` (null); `incrementProductVo.incrementAccounts[].timeZone` (str); `incrementProductVo.incrementAccounts[].virtualAccount` (str); `incrementProductVo.incrementAccounts[].virtualMode` (bool); `incrementProductVo.incrementDebitRateRules` (list); `incrementProductVo.incrementInterestRule` (dict); `incrementProductVo.incrementInterestRule.interestCalculationBasic` (str); `incrementProductVo.incrementInterestRule.interestCalculationDateRule` (str); `incrementProductVo.incrementInterestRule.interestCalculationFrequency` (str); `incrementProductVo.incrementInterestRule.interestCalculationMethod` (str); `incrementProductVo.incrementInterestRule.interestCalculationNum` (str); `incrementProductVo.incrementInterestRule.interestDaysCalculationType` (str); `incrementProductVo.incrementInterestRule.interestEntryDate` (str); `incrementProductVo.incrementInterestRule.interestIntervalType` (str); `incrementProductVo.incrementInterestRule.settlementDate` (str); `incrementProductVo.incrementProductClass` (str); `incrementProductVo.incrementProductCode` (str); `incrementProductVo.incrementProductId` (str); `incrementProductVo.incrementProductName` (str); `incrementProductVo.incrementProductType` (str); `incrementProductVo.incrementProductTypeCode` (str); `incrementProductVo.incrementRateRules` (list); `incrementProductVo.incrementRateRules[]` (dict); `incrementProductVo.incrementRateRules[].aliasNameList` (list); `incrementProductVo.incrementRateRules[].currency` (str); `incrementProductVo.incrementRateRules[].endDate` (str); `incrementProductVo.incrementRateRules[].gmtCreate` (int); `incrementProductVo.incrementRateRules[].gmtModified` (int); `incrementProductVo.incrementRateRules[].incrementProductId` (str); `incrementProductVo.incrementRateRules[].interestCalculationTierRule` (str); `incrementProductVo.incrementRateRules[].interestCalculationType` (str); `incrementProductVo.incrementRateRules[].ladderRateRules` (list); `incrementProductVo.incrementRateRules[].lastOperator` (str); `incrementProductVo.incrementRateRules[].operator` (str); `incrementProductVo.incrementRateRules[].rateRuleId` (str); `incrementProductVo.incrementRateRules[].rateRuleType` (str); `incrementProductVo.incrementRateRules[].startDate` (str); `incrementProductVo.incrementRateRules[].status` (str); `incrementProductVo.incrementRateRules[].tntInstId` (str); `incrementProductVo.incrementRebateRule` (null); `incrementProductVo.incrementRiskType` (str); `incrementProductVo.interestRolloverType` (str); `incrementProductVo.isin` (str); `incrementProductVo.lastOperator` (str); `incrementProductVo.maxTenor` (str); `incrementProductVo.memo` (str); `incrementProductVo.navType` (str); `incrementProductVo.nextRolloverDate` (str); `incrementProductVo.oldIncrementProduct` (null); `incrementProductVo.operator` (str); `incrementProductVo.principalInterestSettlementType` (str); `incrementProductVo.processFlag` (str); `incrementProductVo.processId` (str); `incrementProductVo.productAttribute` (str); `incrementProductVo.productTerm` (str); `incrementProductVo.rateGetMethod` (str); `incrementProductVo.repricingOffset` (str); `incrementProductVo.repricingPeriod` (str); `incrementProductVo.rolloverDateType` (str); `incrementProductVo.settlementTime` (str); `incrementProductVo.stableCoin` (str); `incrementProductVo.status` (str); `incrementProductVo.tntInstId` (str); `incrementProductVo.totalExpenseRatio` (str); `incrementProductVo.version` (int); `incrementRiskType` (str); `instId` (str); `interestToReceive` (str); `lastOperator` (str); `maxTenor` (str); `memo` (str); `nav` (str); `operator` (str); `orderId` (str); `orderStatus` (str); `overnightDepositBuyAliasName` (str); `overnightDepositRedeemAliasName` (str); `overnightTermDepositPositionOrderId` (str); `principalToReceive` (str); `processId` (str); `productAttribute` (str); `productCode` (str); `productId` (str); `productTerm` (str); `productType` (str); `rateValue` (str); `redeemAliasName` (str); `redeemReason` (str); `redeemedAmount` (str); `redemptionFee` (str); `remainingRedeemedShares` (str); `settlementAccount` (str); `shares` (str); `source` (str); `transactionDate` (str); `transactionType` (str); `valueDate` (str); `virtualAccount` (str).

### investment transactions list / None

Source: `POST /queryIncrementOrderList.json`. Probe IDs: `business-02-r1`, `business-02-r2`, `business-02-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1515170, 9535500, 9536669.

Sample fields: `aliasName` (str); `amount` (str); `bankDetailVos` (list); `bankId` (str); `buyOrderNo` (str); `canRedeemAmount` (str); `compoundId` (str); `currency` (str); `cusipNo` (str); `enquireRateGetMethodVO` (null); `expireDate` (str); `fileUrlList` (list); `fundsAccount` (str); `gainLoss` (str); `incrementCollateralInfoVO` (dict/null); `incrementCollateralInfoVO.collateralProductType` (str); `incrementCollateralInfoVO.collateralType` (str); `incrementCollateralInfoVO.remainingCollateralFaceValueAmount` (str); `incrementCollateralInfoVO.remainingCollateralShares` (str); `incrementCollateralInfoVO.totalCollateralFaceValueAmount` (str); `incrementCollateralInfoVO.totalCollateralShares` (str); `incrementProductVo` (null); `incrementRiskType` (str); `instId` (str); `interestToReceive` (str); `lastOperator` (str); `maxTenor` (str); `memo` (str); `nav` (str); `operator` (str); `orderId` (str); `orderStatus` (str); `overnightDepositBuyAliasName` (str); `overnightDepositRedeemAliasName` (str); `overnightTermDepositPositionOrderId` (str); `principalToReceive` (str); `processId` (str); `productAttribute` (str); `productCode` (str); `productId` (str); `productTerm` (str); `productType` (str); `rateValue` (str); `redeemAliasName` (str); `redeemReason` (str); `redeemedAmount` (str); `redemptionFee` (str); `remainingRedeemedShares` (str); `settlementAccount` (str); `shares` (str); `source` (str); `transactionDate` (str); `transactionType` (str); `valueDate` (str); `virtualAccount` (str).

### investment transactions list / offset10

Source: `POST /queryIncrementOrderList.json`. Probe IDs: `page-two-02-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1515170, 9535500, 9536669.

Sample fields: `aliasName` (str); `amount` (str); `bankDetailVos` (list); `bankId` (str); `buyOrderNo` (str); `canRedeemAmount` (str); `compoundId` (str); `currency` (str); `cusipNo` (str); `enquireRateGetMethodVO` (null/dict); `expireDate` (str); `fileUrlList` (list); `fundsAccount` (str); `gainLoss` (str); `incrementCollateralInfoVO` (null/dict); `incrementProductVo` (null); `incrementRiskType` (str); `instId` (str); `interestToReceive` (str); `lastOperator` (str); `maxTenor` (str); `memo` (str); `nav` (str); `operator` (str); `orderId` (str); `orderStatus` (str); `overnightDepositBuyAliasName` (str); `overnightDepositRedeemAliasName` (str); `overnightTermDepositPositionOrderId` (str); `principalToReceive` (str); `processId` (str); `productAttribute` (str); `productCode` (str); `productId` (str); `productTerm` (str); `productType` (str); `rateValue` (str); `redeemAliasName` (str); `redeemReason` (str); `redeemedAmount` (str); `redemptionFee` (str); `remainingRedeemedShares` (str); `settlementAccount` (str); `shares` (str); `source` (str); `transactionDate` (str); `transactionType` (str); `valueDate` (str); `virtualAccount` (str); `enquireRateGetMethodVO.currency` (str); `enquireRateGetMethodVO.floatDirection` (str); `enquireRateGetMethodVO.floatValue` (str); `enquireRateGetMethodVO.rateCalculateType` (str); `enquireRateGetMethodVO.rateName` (str); `enquireRateGetMethodVO.ratePeriod` (str); `enquireRateGetMethodVO.rateProvide` (str); `enquireRateGetMethodVO.rateValue` (str); `incrementCollateralInfoVO.collateralProductType` (str); `incrementCollateralInfoVO.collateralType` (str); `incrementCollateralInfoVO.remainingCollateralFaceValueAmount` (str); `incrementCollateralInfoVO.remainingCollateralShares` (str); `incrementCollateralInfoVO.totalCollateralFaceValueAmount` (str); `incrementCollateralInfoVO.totalCollateralShares` (str).

### ledger accounts list / INNER

Source: `POST /bookCustomerAccount/queryList.json`. Probe IDs: `business-10-r1`, `business-10-r2`, `business-10-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `bookType`, `parentCustomerNo`.

Published UI bundle character offsets: 1519855, 5240757, 5241454.

Sample fields: `accountNo` (str); `bookScene` (str); `bookType` (str); `creator` (str); `currency` (str); `customerLevel` (str); `customerName` (str); `gmtModified` (str); `legalEntityCode` (str); `memo` (str); `processNo` (str); `status` (str).

### ledger accounts list / OUTER

Source: `POST /bookCustomerAccount/queryList.json`. Probe IDs: `business-08-r1`, `business-08-r2`, `business-08-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `bookType`, `parentCustomerNo`.

Published UI bundle character offsets: 1519855, 5240757, 5241454.

Sample fields: `accountNo` (str); `bookScene` (str); `bookType` (str); `creator` (str); `currency` (str); `customerLevel` (str); `customerName` (str); `gmtModified` (str); `legalEntityCode` (str); `memo` (str); `processNo` (str); `status` (str).

### ledger accounts list / offset10

Source: `POST /bookCustomerAccount/queryList.json`. Probe IDs: `page-two-08-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `bookType`, `parentCustomerNo`.

Published UI bundle character offsets: 1519855, 5240757, 5241454.

Sample fields: `accountNo` (str); `bookScene` (str); `bookType` (str); `creator` (str); `currency` (str); `customerLevel` (str); `customerName` (str); `gmtModified` (str); `legalEntityCode` (str); `memo` (str); `processNo` (str); `status` (str).

### ledger balances list / INNER

Source: `POST /balanceBookquery.json`. Probe IDs: `business-11-r1`, `business-11-r2`, `business-11-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `accountingStartDate`, `accountingEndDate`, `valueDateStart`, `valueDateEnd`, `bookType`, `parentCustomerNo`.

Published UI bundle character offsets: 1512283, 5093500, 5095221.

Sample fields: `accountNo` (str); `accountingDate` (str); `businessEntity` (str); `closeBalance` (str); `closeBusinessBalance` (str); `closeOperatorBalance` (str); `closeSaBalance` (str); `currency` (str); `customerBookScene` (str); `customerLevel` (str); `customerName` (str); `valueDate` (str).

### ledger balances list / OUTER

Source: `POST /balanceBookquery.json`. Probe IDs: `business-09-r1`, `business-09-r2`, `business-09-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `accountingStartDate`, `accountingEndDate`, `valueDateStart`, `valueDateEnd`, `bookType`, `parentCustomerNo`.

Published UI bundle character offsets: 1512283, 5093500, 5095221.

Sample fields: `accountNo` (str); `accountingDate` (str); `businessEntity` (str); `closeBalance` (str); `closeBusinessBalance` (str); `closeOperatorBalance` (str); `closeSaBalance` (str); `currency` (str); `customerBookScene` (str); `customerLevel` (str); `customerName` (str); `valueDate` (str).

### ledger balances list / offset10

Source: `POST /balanceBookquery.json`. Probe IDs: `page-two-09-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `accountingStartDate`, `accountingEndDate`, `valueDateStart`, `valueDateEnd`, `bookType`, `parentCustomerNo`.

Published UI bundle character offsets: 1512283, 5093500, 5095221.

Sample fields: `accountNo` (str); `accountingDate` (str); `businessEntity` (str); `closeBalance` (str); `closeBusinessBalance` (str); `closeOperatorBalance` (str); `closeSaBalance` (str); `currency` (str); `customerBookScene` (str); `customerLevel` (str); `customerName` (str); `valueDate` (str).

### ledger customers get / None

Source: `GET /bookCustomer/detail.json`. Probe IDs: `business-70-r1`, `business-70-r2`, `business-70-r3`. Record container: `$.data`; total path: `None`.

Encoding: `query`. Top-level request fields: `tntInstId`, `customerNo`, `version`.

Native identity binding (field names only): `{"leaf": "ledger customers list", "row_fields": ["customerNo", "version"], "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 5226682, 5195718.

Sample fields: `bookCustomerRecognizeRules` (list); `bookCustomerRecognizeRules[]` (dict); `bookCustomerRecognizeRules[].priority` (int); `bookCustomerRecognizeRules[].ruleType` (str); `bookCustomerRecognizeRules[].targetValues` (list); `bookCustomerRecognizeRules[].targetValues[]` (str); `customerLevel` (str); `customerName` (str); `customerNo` (str); `customerSceneList` (list); `customerSceneList[]` (str); `innerCustomerScene` (dict); `innerCustomerScene.balanceCalculationModes` (list); `innerCustomerScene.balanceCalculationModes[]` (dict); `innerCustomerScene.balanceCalculationModes[].balanceCalculationType` (str); `innerCustomerScene.balanceCalculationModes[].commercializationStrategyType` (str); `innerCustomerScene.balanceCalculationModes[].context` (str); `innerCustomerScene.balanceCalculationModes[].customerBookScene` (str); `innerCustomerScene.balanceCalculationModes[].holidayType` (str); `innerCustomerScene.balanceCalculationModes[].parentCustomerNo` (str); `innerCustomerScene.interestCalculationModels` (list); `innerCustomerScene.interestCalculationModels[]` (dict); `innerCustomerScene.interestCalculationModels[].interestBalanceRange` (list); `innerCustomerScene.interestCalculationModels[].interestBalanceRange[]` (str); `innerCustomerScene.interestCalculationModels[].interestBalanceType` (str); `innerCustomerScene.interestCalculationModels[].interestRange` (list); `innerCustomerScene.interestCalculationModels[].interestRange[]` (str); `innerCustomerScene.interestCalculationModels[].interestType` (str); `innerCustomerScene.interestCalculationModels[].parentCustomerNo` (list); `innerCustomerScene.interestCalculationModels[].parentCustomerNo[]` (str); `memo` (str); `operatorList` (list); `operatorList[]` (dict); `operatorList[].gmtModified` (str); `operatorList[].operator` (str); `operatorList[].version` (int); `outerCustomerScene` (dict); `outerCustomerScene.balanceCalculationModes` (list); `outerCustomerScene.balanceCalculationModes[]` (dict); `outerCustomerScene.balanceCalculationModes[].balanceCalculationType` (str); `outerCustomerScene.balanceCalculationModes[].commercializationStrategyType` (str); `outerCustomerScene.balanceCalculationModes[].context` (str); `outerCustomerScene.balanceCalculationModes[].customerBookScene` (str); `outerCustomerScene.balanceCalculationModes[].holidayType` (str); `outerCustomerScene.balanceCalculationModes[].parentCustomerNo` (str); `outerCustomerScene.interestCalculationModels` (list); `outerCustomerScene.interestCalculationModels[]` (dict); `outerCustomerScene.interestCalculationModels[].interestBalanceRange` (list); `outerCustomerScene.interestCalculationModels[].interestBalanceRange[]` (str); `outerCustomerScene.interestCalculationModels[].interestBalanceType` (str); `outerCustomerScene.interestCalculationModels[].interestRange` (list); `outerCustomerScene.interestCalculationModels[].interestRange[]` (str); `outerCustomerScene.interestCalculationModels[].interestType` (str); `outerCustomerScene.interestCalculationModels[].parentCustomerNo` (list); `outerCustomerScene.interestCalculationModels[].parentCustomerNo[]` (str).

### ledger customers list / None

Source: `POST /bookCustomer/queryList.json`. Probe IDs: `business-07-r1`, `business-07-r2`, `business-07-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `parentCustomerNo`.

Published UI bundle character offsets: 1520430, 5223966.

Sample fields: `approveStatus` (str); `customerLevel` (str); `customerName` (str); `customerNo` (str); `customerScenes` (list); `customerScenes[]` (str); `gmtModified` (str); `lastOperator` (str); `memo` (str); `processNo` (str); `status` (str); `version` (str).

### ledger customers list / offset10

Source: `POST /bookCustomer/queryList.json`. Probe IDs: `page-two-07-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `parentCustomerNo`.

Published UI bundle character offsets: 1520430, 5223966.

No populated record schema verified in this case.

### network account-capabilities get / None

Source: `POST /serviceInfoDetail.json`. Probe IDs: `core-43-r1`, `core-43-r2`, `core-43-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json-body`. Top-level request fields: `id`.

Native identity binding (field names only): `{"parameter": "id", "rowfield": "id", "source_leaf": "network account-capabilities list", "source_path": "$.data.data"}`.

Published UI bundle character offsets: 1509093, 5041713.

Sample fields: `aliasName` (str); `bankHoliday` (str); `bankId` (str); `businessCategory` (str); `businessName` (str); `checkSufficient` (str); `currency` (str); `currencyHoliday` (str); `customizedScene` (str); `dailyCumulativeLimit` (str); `effectiveness` (str); `executeTime` (str); `expectTransferTime` (str); `gmtCreate` (str); `gmtModified` (str); `id` (int); `instId` (str); `memo` (str); `operator` (str); `processId` (str); `processStatus` (str); `processType` (null); `ruleId` (int); `ruleType` (str); `runStatus` (str); `status` (str); `timeZone` (str); `tntInstId` (str).

### network account-capabilities list / None

Source: `POST /serviceInfoQuery.json`. Probe IDs: `core-21-r1`, `core-21-r2`, `core-21-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1508908, 5080877, 5081206.

Sample fields: `aliasName` (str); `bankHoliday` (str); `bankId` (str); `businessCategory` (str); `businessName` (str); `checkSufficient` (str); `currency` (str); `currencyHoliday` (str); `customizedScene` (str); `dailyCumulativeLimit` (str); `effectiveness` (str); `executeTime` (str); `expectTransferTime` (str); `gmtCreate` (str); `gmtModified` (str); `id` (int); `instId` (str); `memo` (str); `operator` (str); `processId` (str); `processStatus` (str); `processType` (null); `ruleId` (int); `ruleType` (str); `runStatus` (str); `status` (str); `timeZone` (str); `tntInstId` (str).

### network account-capabilities list / offset10

Source: `POST /serviceInfoQuery.json`. Probe IDs: `page-two-81-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1508908, 5080877, 5081206.

Sample fields: `aliasName` (str); `bankHoliday` (str); `bankId` (str); `businessCategory` (str); `businessName` (str); `checkSufficient` (str); `currency` (str); `currencyHoliday` (str); `customizedScene` (str); `dailyCumulativeLimit` (str); `effectiveness` (str); `executeTime` (str); `expectTransferTime` (str); `gmtCreate` (str); `gmtModified` (str); `id` (int); `instId` (str); `memo` (str); `operator` (str); `processId` (str); `processStatus` (str); `processType` (null); `ruleId` (int); `ruleType` (str); `runStatus` (str); `status` (str); `timeZone` (str); `tntInstId` (str).

### network bank-baselines get / None

Source: `GET /bankAccountBaseLineDetail.json`. Probe IDs: `core-42-r1`, `core-42-r2`, `core-42-r3`. Record container: `$.result.data`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `aliasName`.

Native identity binding (field names only): `{"parameter": "aliasName", "rowfield": "aliasName", "source_leaf": "network bank-baselines list", "source_path": "$.result.data"}`.

Published UI bundle character offsets: 1499543, 4395873.

Sample fields: `accountType` (str); `accountingClassification` (str); `aliasName` (str); `apnAbility` (dict); `apnAbility.manualApnTag` (str); `apnAbility.rtpCredit` (str); `apnAbility.rtpDebit` (str); `apnAbility.systemApnTag` (str); `apnAbility.whaleCredit` (str); `apnAbility.whaleDebit` (str); `approvalStatus` (str); `area` (str); `bankId` (str); `blockChainAccountType` (str); `businessLines` (list); `cashPoolInfoVO` (null); `cashPoolTargetBalance` (str); `cashPoolVOList` (list); `colorType` (str); `creditLimitVOList` (list); `currency` (str); `dayBalanceStatement` (str); `dayDetailStatement` (str); `fundAttributeList` (list); `gmtModified` (str); `h2hNetWorkVOList` (list); `h2hNetWorkVOList[]` (dict); `h2hNetWorkVOList[].beneficiaryLimitList` (list); `h2hNetWorkVOList[].beneficiaryLimitList[]` (dict); `h2hNetWorkVOList[].beneficiaryLimitList[].area` (list); `h2hNetWorkVOList[].beneficiaryLimitList[].currency` (str); `h2hNetWorkVOList[].beneficiaryLimitList[].maxLimit` (str); `h2hNetWorkVOList[].beneficiaryLimitList[].minLimit` (str); `h2hNetWorkVOList[].businessServiceTimeFrameList` (list); `h2hNetWorkVOList[].businessServiceTimeFrameList[]` (dict); `h2hNetWorkVOList[].businessServiceTimeFrameList[].endTime` (str); `h2hNetWorkVOList[].businessServiceTimeFrameList[].startTime` (str); `h2hNetWorkVOList[].businessServiceTimeZone` (str); `h2hNetWorkVOList[].calendar` (str); `h2hNetWorkVOList[].clearingSystemName` (str); `h2hNetWorkVOList[].clearingSystemType` (str); `h2hNetWorkVOList[].paymentLimit` (dict); `h2hNetWorkVOList[].paymentLimit.area` (list); `h2hNetWorkVOList[].paymentLimit.currency` (str); `h2hNetWorkVOList[].paymentLimit.maxLimit` (str); `h2hNetWorkVOList[].paymentLimit.minLimit` (str); `h2hNetWorkVOList[].supportCrossCurrency` (str); `h2hNetWorkVOList[].supportFVT` (str); `h2hNetWorkVOList[].supportOBO` (str); `h2hNetWorkVOList[].supportRefund` (str); `h2hNetWorkVOList[].systemServiceTimeFrameList` (list); `h2hNetWorkVOList[].systemServiceTimeFrameList[]` (dict); `h2hNetWorkVOList[].systemServiceTimeFrameList[].endTime` (str); `h2hNetWorkVOList[].systemServiceTimeFrameList[].startTime` (str); `h2hNetWorkVOList[].systemServiceTimeZone` (str); `headQuarter` (str); `highlightedAccountType` (str); `instId` (str); `intraDayBalanceStatement` (str); `intraDayDetailStatement` (str); `intraDayStatementFrequency` (str); `isHighlighted` (str); `isLp` (str); `linkedAccountList` (list); `manualInfoStatus` (str); `operationMode` (str); `operationTagVO` (dict); `operationTagVO.aliasName` (str); `operationTagVO.balance` (str); `operationTagVO.operation` (str); `operationTagVO.risk` (str); `operationTagVO.yield` (str); `operationTagVO.operationDecision` (str); `operationTagVO.remark` (str); `operator` (str); `paymentTypeCode` (str); `ruleTargetBalance` (str); `status` (str); `supportAccountList` (list); `supportBlockchain` (str); `swapAbility` (null); `targetBalance` (str); `timeZone` (str); `whaleNetWorkVOList` (list).

### network bank-baselines list / None

Source: `GET /bankAccountBaseLineQuery.json`. Probe IDs: `core-08-r1`, `core-08-r2`, `core-08-r3`. Record container: `$.result.data`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankAccountBaseLineQuery`.

Published UI bundle character offsets: 1499475, 4478561, 4479439.

Sample fields: `accountType` (str); `accountingClassification` (str); `aliasName` (str); `area` (str); `bankId` (str); `blockChainAccountType` (str); `clearingNetWorkList` (list); `clearingNetWorkList[]` (str); `colorType` (str); `currency` (str); `headQuarter` (str); `highlightedAccountType` (str); `instId` (str); `isHighlighted` (str); `isLp` (str); `operationMode` (str); `processId` (str); `stableCoin` (str); `stableCoinType` (str); `status` (str); `supportBlockchain` (str); `supportCrossCurrency` (str); `timeZone` (str).

### network bank-baselines list / offset10

Source: `GET /bankAccountBaseLineQuery.json`. Probe IDs: `page-two-69-r1`. Record container: `$.result.data`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankAccountBaseLineQuery`.

Published UI bundle character offsets: 1499475, 4478561, 4479439.

Sample fields: `accountType` (str); `accountingClassification` (str); `aliasName` (str); `area` (str); `bankId` (str); `blockChainAccountType` (str); `clearingNetWorkList` (list); `clearingNetWorkList[]` (str); `colorType` (str); `currency` (str); `headQuarter` (str); `highlightedAccountType` (str); `instId` (str); `isHighlighted` (str); `isLp` (str); `operationMode` (str); `processId` (str); `stableCoin` (str); `stableCoinType` (str); `status` (str); `supportBlockchain` (str); `supportCrossCurrency` (str); `timeZone` (str).

### network product-baselines list / None

Source: `POST /api/product/timeliness/payment/getAll.json`. Probe IDs: `core-22-r1`, `core-22-r2`, `core-22-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `productStatus`.

Published UI bundle character offsets: 1507087, 6390428, 6391134.

No populated record schema verified in this case.

### network realtime get / None

Source: `POST /api/ai/decision/network/detail.json`. Probe IDs: `core-34-r1`, `core-34-r2`, `core-34-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json-body`. Top-level request fields: `id`.

Native identity binding (field names only): `{"parameter": "id", "rowfield": "id", "source_leaf": "network realtime list", "source_path": "$.data.data"}`.

Published UI bundle character offsets: 7189651, 7211626.

Sample fields: `avgEffectiveness` (str); `clearingNetworkName` (str); `clearingNetworkType` (str); `creator` (str); `creditAliasName` (str); `creditBankId` (str); `creditCurrency` (str); `creditLegalEntityCode` (str); `debitAliasName` (str); `debitBankId` (str); `debitCurrency` (str); `debitLegalEntityCode` (str); `effectiveness` (str); `effectivenessLevel` (int); `fundAction` (str); `gmtCreate` (int); `gmtModified` (int); `id` (str); `lastOperationTime` (null); `memo` (str); `networkStatus` (str); `operationCalendar` (str); `operationDateType` (str); `operationEffectiveness` (str); `operationTime` (null); `operationTool` (str); `processId` (str); `processStatus` (str); `routeId` (str); `runStatus` (str); `scene` (str); `singlePaymentLimit` (null); `successRate` (str); `timeZone` (str); `updater` (str); `version` (int).

### network realtime list / None

Source: `POST /api/ai/decision/network/queryDecisionNetwork.json`. Probe IDs: `core-24-r1`, `core-24-r2`, `core-24-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`.

Published UI bundle character offsets: 7189467, 7356541, 7356541.

Sample fields: `avgEffectiveness` (str); `clearingNetworkName` (str); `clearingNetworkType` (str); `creator` (str); `creditAliasName` (str); `creditBankId` (str); `creditCurrency` (str); `creditLegalEntityCode` (str); `debitAliasName` (str); `debitBankId` (str); `debitCurrency` (str); `debitLegalEntityCode` (str); `effectiveness` (str); `effectivenessLevel` (int); `fundAction` (str); `gmtCreate` (int); `gmtModified` (int); `id` (str); `lastOperationTime` (null); `memo` (str); `networkStatus` (str); `operationCalendar` (str); `operationDateType` (str); `operationEffectiveness` (str); `operationTime` (null); `operationTool` (str); `processId` (str); `processStatus` (str); `routeId` (str); `runStatus` (str); `scene` (str); `singlePaymentLimit` (null); `successRate` (str); `timeZone` (str); `updater` (str); `version` (int).

### network realtime list / offset10

Source: `POST /api/ai/decision/network/queryDecisionNetwork.json`. Probe IDs: `page-two-84-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`.

Published UI bundle character offsets: 7189467, 7356541, 7356541.

Sample fields: `avgEffectiveness` (str); `clearingNetworkName` (str); `clearingNetworkType` (str); `creator` (str); `creditAliasName` (str); `creditBankId` (str); `creditCurrency` (str); `creditLegalEntityCode` (str); `debitAliasName` (str); `debitBankId` (str); `debitCurrency` (str); `debitLegalEntityCode` (str); `effectiveness` (str); `effectivenessLevel` (int); `fundAction` (str); `gmtCreate` (int); `gmtModified` (int); `id` (str); `lastOperationTime` (null); `memo` (str); `networkStatus` (str); `operationCalendar` (str); `operationDateType` (str); `operationEffectiveness` (str); `operationTime` (null); `operationTool` (str); `processId` (str); `processStatus` (str); `routeId` (str); `runStatus` (str); `scene` (str); `singlePaymentLimit` (null); `successRate` (str); `timeZone` (str); `updater` (str); `version` (int).

### operations asset-trades list / None

Source: `POST /assetTransferOrderListQuery.json`. Probe IDs: `business-52-r1`, `business-52-r2`, `business-52-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `tradingDateBegin`, `tradingDateEnd`.

Published UI bundle character offsets: 1475351, 9585753, 9586983.

No populated record schema verified in this case.

### operations asset-trades list / previous-day:None

Source: `POST /assetTransferOrderListQuery.json`. Probe IDs: `previous-day-46-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `tradingDateBegin`, `tradingDateEnd`.

Published UI bundle character offsets: 1475351, 9585753, 9586983.

Sample fields: `accountingEntityCode` (str); `actualValueDate` (str); `aliasName` (str); `assetProductVo` (dict); `assetProductVo.assertProductCategory` (str); `assetProductVo.assertProductCode` (str); `assetProductVo.assertProductName` (str); `assetProductVo.assertProductTenor` (str); `assetProductVo.assertProductType` (str); `assetTransferAmount` (str); `assetTransferCurrency` (str); `bankId` (str); `counterpartTransferAmount` (str); `counterpartyAccountCurrency` (str); `counterpartyAccountingEntityCode` (str); `counterpartyAliasName` (str); `counterpartyBankId` (str); `counterpartyLegalEntityCode` (str); `counterpartyTransferCurrency` (str); `creator` (str); `currency` (str); `digitalCurrencyCategory` (str); `endToEndId` (str); `errorMsg` (str); `finNetId` (str); `globalOrderId` (str); `gmtCreate` (str); `gmtCreditReturn` (str); `gmtDebitReturn` (str); `gmtModified` (str); `gmtSend` (str); `lastOperator` (str); `legalEntityCode` (str); `memo` (str); `orderNo` (str); `orderStatus` (str); `peggedCurrency` (str); `processId` (str); `purposeCode` (str); `referDigitalCurrency` (str); `reportId` (str); `retryTimes` (int); `source` (str); `timezone` (str); `tradingDate` (str); `transFerOrderLogVoList` (list); `transFerOrderLogVoList[]` (dict); `transFerOrderLogVoList[].content` (str); `transFerOrderLogVoList[].gmtCreate` (int); `transFerOrderLogVoList[].gmtCreateStr` (str); `transFerOrderLogVoList[].gmtModified` (int); `transFerOrderLogVoList[].gmtModifiedStr` (str); `transFerOrderLogVoList[].id` (int); `transFerOrderLogVoList[].lastOperator` (str); `transFerOrderLogVoList[].logType` (str); `transFerOrderLogVoList[].operator` (str); `transFerOrderLogVoList[].orderNo` (str); `transactionType` (str); `userName` (str).

### operations decisions get / None

Source: `POST /api/ai/decision/report/getDetail.json`. Probe IDs: `business-65-r1`, `business-65-r2`, `business-65-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json`. Top-level request fields: `id`.

Native identity binding (field names only): `{"leaf": "operations decisions list", "row_field": "id", "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 5777109.

Sample fields: `actionReportVO` (dict); `actionReportVO.alBankTransferFile` (str); `actionReportVO.bIC` (str); `actionReportVO.bankTransNo` (str); `actionReportVO.bizNo` (str); `actionReportVO.businessType` (str); `actionReportVO.chargeBearer` (str); `actionReportVO.clearingNetworkName` (str); `actionReportVO.clearingNetworkType` (str); `actionReportVO.compensationFlag` (str); `actionReportVO.creatorId` (str); `actionReportVO.creditAccountName` (str); `actionReportVO.creditAccountNo` (str); `actionReportVO.creditAccountType` (str); `actionReportVO.creditAliasName` (str); `actionReportVO.creditAmount` (str); `actionReportVO.creditBankId` (str); `actionReportVO.creditCurrency` (str); `actionReportVO.creditEntity` (str); `actionReportVO.creditFundAttribute` (str); `actionReportVO.creditLpTaAliasName` (str); `actionReportVO.creditTaAliasName` (str); `actionReportVO.creditValueDate` (str); `actionReportVO.debitAccountName` (str); `actionReportVO.debitAccountNo` (str); `actionReportVO.debitAccountType` (str); `actionReportVO.debitAliasName` (str); `actionReportVO.debitAmount` (str); `actionReportVO.debitBankId` (str); `actionReportVO.debitCurrency` (str); `actionReportVO.debitEntity` (str); `actionReportVO.debitFundAttribute` (str); `actionReportVO.debitInstCode` (str); `actionReportVO.debitLpTaAliasName` (str); `actionReportVO.debitTaAliasName` (str); `actionReportVO.debitValueDate` (str); `actionReportVO.decisionMode` (str); `actionReportVO.drAlisName` (str); `actionReportVO.effectivenessReq` (str); `actionReportVO.endToEndId` (str); `actionReportVO.env` (str); `actionReportVO.eventCode` (str); `actionReportVO.executeResult` (str); `actionReportVO.expectCreditValueDate` (str); `actionReportVO.expectCreditValueTime` (int); `actionReportVO.expectDebitValueDate` (str); `actionReportVO.expectDebitValueTime` (int); `actionReportVO.expectValueDate` (str); `actionReportVO.extParams` (str); `actionReportVO.fileBatchNo` (str); `actionReportVO.finNetId` (str); `actionReportVO.firstApproval` (str); `actionReportVO.fourthApproval` (str); `actionReportVO.gapId` (str); `actionReportVO.globalLinkIndex` (str); `actionReportVO.gmtCheck` (str); `actionReportVO.gmtCreate` (str); `actionReportVO.gmtModified` (str); `actionReportVO.gmtReturn` (str); `actionReportVO.gmtReturnFinnet` (null); `actionReportVO.gmtSend` (str); `actionReportVO.instRegistrationNumber` (str); `actionReportVO.lastOperator` (str); `actionReportVO.memo` (str); `actionReportVO.needReview` (bool); `actionReportVO.needTally` (str); `actionReportVO.network` (str); `actionReportVO.nodeNum` (int); `actionReportVO.operator` (str); `actionReportVO.orderHolder` (str); `actionReportVO.orderId` (str); `actionReportVO.orderNo` (str); `actionReportVO.orderSource` (str); `actionReportVO.orderStatus` (str); `actionReportVO.orderType` (str); `actionReportVO.paymentDetail` (str); `actionReportVO.processCode` (str); `actionReportVO.processId` (str); `actionReportVO.productedCode` (str); `actionReportVO.purposeCode` (str); `actionReportVO.receiptStatus` (str); `actionReportVO.regulatoryInfo` (str); `actionReportVO.reportId` (str); `actionReportVO.requireBizNo` (str); `actionReportVO.retryTime` (int); `actionReportVO.routeCategory` (str); `actionReportVO.routeId` (str); `actionReportVO.routeType` (str); `actionReportVO.scene` (str); `actionReportVO.scheduleTaskId` (str); `actionReportVO.secondApproval` (str); `actionReportVO.source` (str); `actionReportVO.target` (str); `actionReportVO.thirdApproval` (str); `actionReportVO.tntInstId` (str); `actionReportVO.transFerOrderLogVoList` (list); `assetTransactionType` (str); `attributionDetailReason` (str); `attributionType` (list); `baseBalance` (null); `baseBalanceAdj` (null); `cashPoolName` (str); `clearingNetworkName` (str); `costAmount` (null); `creditAliasName` (str); `creditAmount` (str); `creditBankId` (str); `creditCurrency` (str); `creditEntity` (str); `creditValueDate` (str); `debitAliasName` (str); `debitAmount` (str); `debitBankId` (str); `debitCurrency` (str); `debitEntity` (str); `debitValueDate` (str); `decisionAmount` (str); `decisionCurrency` (str); `decisionMode` (str); `decisionTime` (null); `executionTimeEnd` (str); `executionTimeStart` (str); `extParams` (str); `finishStatus` (str); `fundActionType` (str); `genOrder` (int); `globalLinkIndex` (str); `gmtCreate` (str); `gmtModified` (str); `groupId` (str); `id` (int); `invalidDecisionReportList` (list); `lastOperator` (str); `linkType` (str); `neeDecisionOperation` (str); `needReview` (str); `operationOrderEditContent` (str); `operationStatus` (str); `operationType` (str); `operator` (str); `orderNo` (str); `processId` (str); `productCode` (str); `relationReportId` (str); `remainAmount` (null); `reportId` (str); `reportStatus` (str); `riskActionType` (str); `riskEventVOS` (list); `ruleId` (str); `ruleRelationId` (str); `status` (str); `strategyName` (str); `strategyType` (str); `subDecisionTaskId` (str); `subInstructionStatus` (str); `taskId` (str); `timeliness` (int); `tntInstId` (str); `version` (int).

### operations decisions history / None

Source: `POST /api/ai/decision/report/getHistory.json`. Probe IDs: `business-66-r1`, `business-66-r2`, `business-66-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json`. Top-level request fields: `id`.

Native identity binding (field names only): `{"leaf": "operations decisions list", "row_field": "id", "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 7148300.

Sample fields: `actionReportVO` (null); `assetTransactionType` (str); `attributionDetailReason` (str); `attributionType` (list); `baseBalance` (null); `baseBalanceAdj` (null); `cashPoolName` (str); `clearingNetworkName` (str); `costAmount` (null); `creditAliasName` (str); `creditAmount` (str); `creditBankId` (str); `creditCurrency` (str); `creditEntity` (str); `creditValueDate` (str); `debitAliasName` (str); `debitAmount` (str); `debitBankId` (str); `debitCurrency` (str); `debitEntity` (str); `debitValueDate` (str); `decisionAmount` (str); `decisionCurrency` (str); `decisionMode` (str); `decisionTime` (null); `executionTimeEnd` (str); `executionTimeStart` (str); `extParams` (str); `finishStatus` (str); `fundActionType` (str); `genOrder` (int); `globalLinkIndex` (str); `gmtCreate` (str); `gmtModified` (str); `groupId` (str); `id` (int); `invalidDecisionReportList` (list); `lastOperator` (str); `linkType` (str); `neeDecisionOperation` (str); `needReview` (str); `operationOrderEditContent` (str); `operationStatus` (str); `operationType` (str); `operator` (str); `orderNo` (str); `processId` (str); `productCode` (str); `relationReportId` (str); `remainAmount` (null); `reportId` (str); `reportStatus` (str); `riskActionType` (str); `riskEventVOS` (list); `ruleId` (str); `ruleRelationId` (str); `status` (str); `strategyName` (str); `strategyType` (str); `subDecisionTaskId` (str); `subInstructionStatus` (str); `taskId` (str); `timeliness` (int); `tntInstId` (str); `version` (int).

### operations decisions list / None

Source: `POST /api/ai/decision/report/getAllNew.json`. Probe IDs: `business-48-r1`, `business-48-r2`, `business-48-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `startTime`, `endTime`, `createStartTime`, `createEndTime`.

Published UI bundle character offsets: 7151705.

No populated record schema verified in this case.

### operations decisions list / previous-day:None

Source: `POST /api/ai/decision/report/getAllNew.json`. Probe IDs: `previous-day-42-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `startTime`, `endTime`, `createStartTime`, `createEndTime`.

Published UI bundle character offsets: 7151705.

Sample fields: `actionReportVO` (null); `assetTransactionType` (str); `attributionDetailReason` (str); `attributionType` (list); `baseBalance` (null); `baseBalanceAdj` (null); `cashPoolName` (str); `clearingNetworkName` (str); `costAmount` (null); `creditAliasName` (str); `creditAmount` (str); `creditBankId` (str); `creditCurrency` (str); `creditEntity` (str); `creditValueDate` (str); `debitAliasName` (str); `debitAmount` (str); `debitBankId` (str); `debitCurrency` (str); `debitEntity` (str); `debitValueDate` (str); `decisionAmount` (str); `decisionCurrency` (str); `decisionMode` (str); `decisionTime` (null); `executionTimeEnd` (str); `executionTimeStart` (str); `extParams` (str); `finishStatus` (str); `fundActionType` (str); `genOrder` (int); `globalLinkIndex` (str); `gmtCreate` (str); `gmtModified` (str); `groupId` (str); `id` (int); `invalidDecisionReportList` (list); `lastOperator` (str); `linkType` (str); `neeDecisionOperation` (str); `needReview` (str); `operationOrderEditContent` (str); `operationStatus` (str); `operationType` (str); `operator` (str); `orderNo` (str); `processId` (str); `productCode` (str); `relationReportId` (str); `remainAmount` (null); `reportId` (str); `reportStatus` (str); `riskActionType` (str); `riskEventVOS` (list); `ruleId` (str); `ruleRelationId` (str); `status` (str); `strategyName` (str); `strategyType` (str); `subDecisionTaskId` (str); `subInstructionStatus` (str); `taskId` (str); `timeliness` (int); `tntInstId` (str); `version` (int).

### operations demands list / FUND_REQUIRE

Source: `GET /riskActionTaskQuery.json`. Probe IDs: `business-45-r1`, `business-45-r2`, `business-45-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `riskActionTaskQueryVO`.

Published UI bundle character offsets: 7148300, 7151646, 7154000.

No populated record schema verified in this case.

### operations demands list / previous-day:FUND_REQUIRE

Source: `GET /riskActionTaskQuery.json`. Probe IDs: `previous-day-39-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `riskActionTaskQueryVO`.

Published UI bundle character offsets: 7148300, 7151646, 7154000.

No populated record schema verified in this case.

### operations executions list / INSTRUCTION_ACCOUNT_FLOW,INSTRUCTION_ACCOUNT_FLOW_MANUAL

Source: `GET /riskActionTaskQuery.json`. Probe IDs: `business-46-r1`, `business-46-r2`, `business-46-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `riskActionTaskQueryVO`.

Published UI bundle character offsets: 7148300, 7151646, 7154000.

No populated record schema verified in this case.

### operations executions list / REAL_TIME_INITIATIVE_SUPPLEMENT,REAL_TIME_PASSIVE_SUPPLEMENT,REAL_TIME_INITIATIVE_COLLECTION

Source: `GET /riskActionTaskQuery.json`. Probe IDs: `business-47-r1`, `business-47-r2`, `business-47-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `riskActionTaskQueryVO`.

Published UI bundle character offsets: 7148300, 7151646, 7154000.

No populated record schema verified in this case.

### operations executions list / previous-day:INSTRUCTION_ACCOUNT_FLOW,INSTRUCTION_ACCOUNT_FLOW_MANUAL

Source: `GET /riskActionTaskQuery.json`. Probe IDs: `previous-day-40-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `riskActionTaskQueryVO`.

Published UI bundle character offsets: 7148300, 7151646, 7154000.

No populated record schema verified in this case.

### operations executions list / previous-day:REAL_TIME_INITIATIVE_SUPPLEMENT,REAL_TIME_PASSIVE_SUPPLEMENT,REAL_TIME_INITIATIVE_COLLECTION

Source: `GET /riskActionTaskQuery.json`. Probe IDs: `previous-day-41-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `riskActionTaskQueryVO`.

Published UI bundle character offsets: 7148300, 7151646, 7154000.

No populated record schema verified in this case.

### operations forwards get / None

Source: `POST /forwardOrderDetail.json`. Probe IDs: `business-63-r1`, `business-63-r2`, `business-63-r3`. Record container: `$.data`; total path: `None`.

Encoding: `form`. Top-level request fields: `forwardId`.

Native identity binding (field names only): `{"leaf": "operations forwards list", "row_field": "orderNo", "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 7603426, 7589659.

Sample fields: `actualRate` (str); `bookId` (str); `buyAliasName` (str); `buyAmount` (str); `buyCurrency` (str); `buyInst` (str); `currencyPair` (str); `expectRate` (str); `hedgeOrderId` (str); `lastOperator` (str); `memo` (str); `operator` (str); `orderNo` (str); `orderStatus` (str); `sellAliasName` (str); `sellAmount` (str); `sellCurrency` (str); `sellInst` (str); `tradeDate` (str); `valueDate` (str).

### operations forwards list / None

Source: `POST /forwardOrderList.json`. Probe IDs: `business-04-r1`, `business-04-r2`, `business-04-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1521537, 7599654.

Sample fields: `actualRate` (str); `bookId` (str); `buyAliasName` (str); `buyAmount` (str); `buyCurrency` (str); `buyInst` (str); `currencyPair` (str); `expectRate` (str); `hedgeOrderId` (str); `lastOperator` (str); `memo` (str); `operator` (str); `orderNo` (str); `orderStatus` (str); `sellAliasName` (str); `sellAmount` (str); `sellCurrency` (str); `sellInst` (str); `tradeDate` (str); `valueDate` (str).

### operations forwards list / offset10

Source: `POST /forwardOrderList.json`. Probe IDs: `page-two-04-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1521537, 7599654.

Sample fields: `actualRate` (str); `bookId` (str); `buyAliasName` (str); `buyAmount` (str); `buyCurrency` (str); `buyInst` (str); `currencyPair` (str); `expectRate` (str); `hedgeOrderId` (str); `lastOperator` (str); `memo` (str); `operator` (str); `orderNo` (str); `orderStatus` (str); `sellAliasName` (str); `sellAmount` (str); `sellCurrency` (str); `sellInst` (str); `tradeDate` (str); `valueDate` (str).

### operations prefunds get / None

Source: `GET /queryPreFundingOrderDetail.json`. Probe IDs: `business-64-r1`, `business-64-r2`, `business-64-r3`. Record container: `$.result.data`; total path: `None`.

Encoding: `query`. Top-level request fields: `tntInstId`, `preFundingId`.

Native identity binding (field names only): `{"leaf": "operations prefunds list", "row_field": "id", "source_path": "result.dataValue[0]"}`.

Published UI bundle character offsets: 6326383, 6304743.

Sample fields: `allowUseAmount` (str); `amount` (str); `amountUSD` (str); `applyType` (str); `approverList` (list); `approverList[]` (str); `bizLine` (str); `bizProject` (str); `businessCountEvaluate` (str); `currency` (str); `department` (str); `detailReason` (str); `endDate` (str); `fileUrlList` (list); `fileUrlList[]` (str); `fundingActionType` (str); `fundingSource` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `instId` (str); `lastOperator` (str); `memo` (str); `operator` (str); `preFundingManage` (str); `prefundingAliasName` (str); `prefundingBizNo` (str); `prefundingPrice` (str); `prefundingType` (str); `processId` (str); `quotaExplain` (str); `reason` (str); `returnPlain` (str); `reviewDate` (str); `startDate` (str); `status` (str); `usedAmount` (str); `version` (int).

### operations prefunds list / APPROVED,CLOSED

Source: `GET /queryPreFundingOrderList.json`. Probe IDs: `business-49-r1`, `business-49-r2`, `business-49-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `preFundingOrderQueryVO`, `timeZone`.

Published UI bundle character offsets: 6321547, 6342858.

Sample fields: `allowUseAmount` (str); `amount` (str); `amountUSD` (str); `applyType` (str); `approverList` (list); `approverList[]` (str); `bizLine` (str); `bizProject` (str); `businessCountEvaluate` (str); `currency` (str); `department` (str); `detailReason` (str); `endDate` (str); `fileUrlList` (list); `fundingActionType` (str); `fundingSource` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `instId` (str); `lastOperator` (str); `memo` (str); `operator` (str); `preFundingManage` (str); `prefundingAliasName` (str); `prefundingBizNo` (str); `prefundingPrice` (str); `prefundingType` (str); `processId` (str); `quotaExplain` (str); `reason` (str); `returnPlain` (str); `reviewDate` (str); `startDate` (str); `status` (str); `usedAmount` (str); `version` (int).

### operations prefunds list / SUBMITTED,REJECTED,CLOSED_SUBMITTED

Source: `GET /queryPreFundingOrderList.json`. Probe IDs: `business-50-r1`, `business-50-r2`, `business-50-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `preFundingOrderQueryVO`, `timeZone`.

Published UI bundle character offsets: 6321547, 6342858.

Sample fields: `allowUseAmount` (str); `amount` (str); `amountUSD` (str); `applyType` (str); `approverList` (list); `approverList[]` (str); `bizLine` (str); `bizProject` (str); `businessCountEvaluate` (str); `currency` (str); `department` (str); `detailReason` (str); `endDate` (str); `fileUrlList` (list); `fundingActionType` (str); `fundingSource` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `instId` (str); `lastOperator` (str); `memo` (str); `operator` (str); `preFundingManage` (str); `prefundingAliasName` (str); `prefundingBizNo` (str); `prefundingPrice` (str); `prefundingType` (str); `processId` (str); `quotaExplain` (str); `reason` (str); `returnPlain` (str); `reviewDate` (str); `startDate` (str); `status` (str); `usedAmount` (str); `version` (int).

### operations prefunds list / offset10

Source: `GET /queryPreFundingOrderList.json`. Probe IDs: `page-two-43-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `preFundingOrderQueryVO`, `timeZone`.

Published UI bundle character offsets: 6321547, 6342858.

Sample fields: `allowUseAmount` (str); `amount` (str); `amountUSD` (str); `applyType` (str); `approverList` (list); `approverList[]` (str); `bizLine` (str); `bizProject` (str); `businessCountEvaluate` (str); `currency` (str); `department` (str); `detailReason` (str); `endDate` (str); `fileUrlList` (list); `fundingActionType` (str); `fundingSource` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `instId` (str); `lastOperator` (str); `memo` (str); `operator` (str); `preFundingManage` (str); `prefundingAliasName` (str); `prefundingBizNo` (str); `prefundingPrice` (str); `prefundingType` (str); `processId` (str); `quotaExplain` (str); `reason` (str); `returnPlain` (str); `reviewDate` (str); `startDate` (str); `status` (str); `usedAmount` (str); `version` (int).

### operations swaps list / None

Source: `POST /swapOrderQuery.json`. Probe IDs: `business-44-r1`, `business-44-r2`, `business-44-r3`. Record container: `$.result.swapOrderVOList`; total path: `$.result.count`.

Encoding: `form`. Top-level request fields: `tntInstId`, `swapOrderQueryVO`.

Published UI bundle character offsets: 3144800, 3145685.

No populated record schema verified in this case.

### operations swaps list / previous-day:None

Source: `POST /swapOrderQuery.json`. Probe IDs: `previous-day-38-r1`. Record container: `$.result.swapOrderVOList`; total path: `$.result.count`.

Encoding: `form`. Top-level request fields: `tntInstId`, `swapOrderQueryVO`.

Published UI bundle character offsets: 3144800, 3145685.

No populated record schema verified in this case.

### operations transfers get / None

Source: `POST /transferOrderQueryDetail.json`. Probe IDs: `business-71-r1`, `business-71-r2`, `business-71-r3`. Record container: `$.baseResult.data`; total path: `None`.

Encoding: `form`. Top-level request fields: `orderNo`.

Native identity binding (field names only): `{"leaf": "operations transfers list", "row_field": "orderNo", "source_path": "result.data[0]"}`.

Published UI bundle character offsets: 7119596.

Sample fields: `alBankTransferFile` (str); `bIC` (str); `bankTransNo` (str); `bizNo` (str); `businessType` (str); `chargeBearer` (str); `clearingNetworkName` (str); `clearingNetworkType` (str); `compensationFlag` (str); `creatorId` (str); `creditAccountName` (str); `creditAccountNo` (str); `creditAccountType` (str); `creditAliasName` (str); `creditAmount` (str); `creditBankId` (str); `creditCurrency` (str); `creditEntity` (str); `creditFundAttribute` (str); `creditLpTaAliasName` (str); `creditTaAliasName` (str); `creditValueDate` (str); `debitAccountName` (str); `debitAccountNo` (str); `debitAccountType` (str); `debitAliasName` (str); `debitAmount` (str); `debitBankId` (str); `debitCurrency` (str); `debitEntity` (str); `debitFundAttribute` (str); `debitInstCode` (str); `debitLpTaAliasName` (str); `debitTaAliasName` (str); `debitValueDate` (str); `decisionMode` (str); `drAlisName` (str); `effectivenessReq` (str); `endToEndId` (str); `env` (str); `eventCode` (str); `executeResult` (str); `expectCreditValueDate` (str); `expectCreditValueTime` (int); `expectDebitValueDate` (str); `expectDebitValueTime` (int); `expectValueDate` (str); `extParams` (str); `fileBatchNo` (str); `finNetId` (str); `firstApproval` (str); `fourthApproval` (str); `gapId` (str); `globalLinkIndex` (str); `gmtCheck` (str); `gmtCreate` (str); `gmtModified` (str); `gmtReturn` (str); `gmtReturnFinnet` (int); `gmtSend` (str); `instRegistrationNumber` (str); `lastOperator` (str); `memo` (str); `needReview` (bool); `needTally` (str); `network` (str); `nodeNum` (int); `operator` (str); `orderHolder` (str); `orderId` (str); `orderNo` (str); `orderSource` (str); `orderStatus` (str); `orderType` (str); `paymentDetail` (str); `processCode` (str); `processId` (str); `productedCode` (str); `purposeCode` (str); `receiptStatus` (str); `regulatoryInfo` (str); `reportId` (str); `requireBizNo` (str); `retryTime` (int); `routeCategory` (str); `routeId` (str); `routeType` (str); `scene` (str); `scheduleTaskId` (str); `secondApproval` (str); `source` (str); `target` (str); `thirdApproval` (str); `tntInstId` (str); `transFerOrderLogVoList` (list).

### operations transfers list / None

Source: `POST /transferOrderQuery.json`. Probe IDs: `business-51-r1`, `business-51-r2`, `business-51-r3`. Record container: `$.result.data`; total path: `$.result.count`.

Encoding: `form`. Top-level request fields: `tntInstId`, `transferOrderQueryRequestVO`.

Published UI bundle character offsets: 1475230, 2570578, 2571994.

No populated record schema verified in this case.

### operations transfers list / previous-day:None

Source: `POST /transferOrderQuery.json`. Probe IDs: `previous-day-45-r1`. Record container: `$.result.data`; total path: `$.result.count`.

Encoding: `form`. Top-level request fields: `tntInstId`, `transferOrderQueryRequestVO`.

Published UI bundle character offsets: 1475230, 2570578, 2571994.

Sample fields: `alBankTransferFile` (str); `bIC` (str); `bankTransNo` (str); `bizNo` (str); `businessType` (str); `chargeBearer` (str); `clearingNetworkName` (str); `clearingNetworkType` (str); `compensationFlag` (str); `creatorId` (str); `creditAccountName` (str); `creditAccountNo` (str); `creditAccountType` (str); `creditAliasName` (str); `creditAmount` (str); `creditBankId` (str); `creditCurrency` (str); `creditEntity` (str); `creditFundAttribute` (str); `creditLpTaAliasName` (str); `creditTaAliasName` (str); `creditValueDate` (str); `debitAccountName` (str); `debitAccountNo` (str); `debitAccountType` (str); `debitAliasName` (str); `debitAmount` (str); `debitBankId` (str); `debitCurrency` (str); `debitEntity` (str); `debitFundAttribute` (str); `debitInstCode` (str); `debitLpTaAliasName` (str); `debitTaAliasName` (str); `debitValueDate` (str); `decisionMode` (str); `drAlisName` (str); `effectivenessReq` (str); `endToEndId` (str); `env` (str); `eventCode` (str); `executeResult` (str); `expectCreditValueDate` (str); `expectCreditValueTime` (int); `expectDebitValueDate` (str); `expectDebitValueTime` (int); `expectValueDate` (str); `extParams` (str); `fileBatchNo` (str); `finNetId` (str); `firstApproval` (str); `fourthApproval` (str); `gapId` (str); `globalLinkIndex` (str); `gmtCheck` (str); `gmtCreate` (str); `gmtModified` (str); `gmtReturn` (str); `gmtReturnFinnet` (int/null); `gmtSend` (str); `instRegistrationNumber` (str); `lastOperator` (str); `memo` (str); `needReview` (bool); `needTally` (str); `network` (str); `nodeNum` (int); `operator` (str); `orderHolder` (str); `orderId` (str); `orderNo` (str); `orderSource` (str); `orderStatus` (str); `orderType` (str); `paymentDetail` (str); `processCode` (str); `processId` (str); `productedCode` (str); `purposeCode` (str); `receiptStatus` (str); `regulatoryInfo` (str); `reportId` (str); `requireBizNo` (str); `retryTime` (int); `routeCategory` (str); `routeId` (str); `routeType` (str); `scene` (str); `scheduleTaskId` (str); `secondApproval` (str); `source` (str); `target` (str); `thirdApproval` (str); `tntInstId` (str); `transFerOrderLogVoList` (list); `transFerOrderLogVoList[]` (dict); `transFerOrderLogVoList[].content` (str); `transFerOrderLogVoList[].gmtCreate` (int); `transFerOrderLogVoList[].gmtCreateStr` (str); `transFerOrderLogVoList[].gmtModified` (int); `transFerOrderLogVoList[].gmtModifiedStr` (str); `transFerOrderLogVoList[].id` (int); `transFerOrderLogVoList[].lastOperator` (str); `transFerOrderLogVoList[].logType` (str); `transFerOrderLogVoList[].operator` (str); `transFerOrderLogVoList[].orderNo` (str).

### pricing bills list / DEPOSIT

Source: `POST /accountBookQuery.json`. Probe IDs: `business-17-r2`, `business-17-r3`, `business-17-r1`. Record container: `$.result.data`; total path: `$.result.count`.

Encoding: `form`. Top-level request fields: `tntInstId`, `clientBillQueryVO`.

Published UI bundle character offsets: 1500576, 5388100, 5389586.

No populated record schema verified in this case.

### pricing bills list / previous-day:DEPOSIT

Source: `POST /accountBookQuery.json`. Probe IDs: `previous-day-17-r1`. Record container: `$.result.data`; total path: `$.result.count`.

Encoding: `form`. Top-level request fields: `tntInstId`, `clientBillQueryVO`.

Published UI bundle character offsets: 1500576, 5388100, 5389586.

No populated record schema verified in this case.

### pricing client-prices list / ACTIVATED

Source: `GET /getClientPriceList.json`. Probe IDs: `business-12-r1`, `business-12-r2`, `business-12-r3`. Record container: `$.result.data`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `clientPriceQueryVO`.

Published UI bundle character offsets: 1500160, 5335840.

No populated record schema verified in this case.

### pricing client-prices list / DEPRECATED,WAIT_FOR_AUDIT,DRAFT

Source: `GET /getClientPriceList.json`. Probe IDs: `business-13-r1`, `business-13-r2`, `business-13-r3`. Record container: `$.result.data`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `clientPriceQueryVO`.

Published UI bundle character offsets: 1500160, 5335840.

No populated record schema verified in this case.

### pricing client-prices list / previous-day:ACTIVATED

Source: `GET /getClientPriceList.json`. Probe IDs: `previous-day-12-r1`. Record container: `$.result.data`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `clientPriceQueryVO`.

Published UI bundle character offsets: 1500160, 5335840.

No populated record schema verified in this case.

### pricing client-prices list / previous-day:DEPRECATED,WAIT_FOR_AUDIT,DRAFT

Source: `GET /getClientPriceList.json`. Probe IDs: `previous-day-13-r1`. Record container: `$.result.data`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `clientPriceQueryVO`.

Published UI bundle character offsets: 1500160, 5335840.

Sample fields: `area` (str); `colorType` (str); `costDate` (str); `costPriceId` (str); `customerLevel` (str); `customerName` (str); `customerNo` (str); `customerScene` (str); `customerSceneDesc` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `lastOperator` (str); `operator` (str); `period` (str); `pricingCurrency` (str); `pricingPattern` (dict); `pricingPattern.pricingCurrency` (str); `pricingPattern.pricingModeItemList` (list); `pricingPattern.pricingModeItemList[]` (dict); `pricingPattern.pricingModeItemList[].endTransAmount` (str); `pricingPattern.pricingModeItemList[].lowerPrice` (str); `pricingPattern.pricingModeItemList[].rate` (str); `pricingPattern.pricingModeItemList[].startTransAmount` (str); `pricingPattern.pricingModeItemList[].upperPrice` (str); `pricingPattern.tierPricingType` (str); `pricingPattern.transCurrency` (str); `pricingPatternType` (str); `processId` (str); `rate` (str); `serviceType` (str); `status` (str); `tntInstId` (str); `transCurrency` (str); `version` (int).

### pricing cost-prices list / None

Source: `GET /costPriceList.json`. Probe IDs: `business-14-r1`, `business-14-r2`, `business-14-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `costPriceQueryVO`.

Published UI bundle character offsets: 1500398, 5372419.

No populated record schema verified in this case.

### pricing cost-prices list / previous-day:None

Source: `GET /costPriceList.json`. Probe IDs: `previous-day-14-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `costPriceQueryVO`.

Published UI bundle character offsets: 1500398, 5372419.

Sample fields: `bizLine` (str); `colorType` (str); `costDate` (str); `currency` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `memo` (str); `operator` (str); `pageNo` (int); `pageSize` (int); `period` (str); `relationFactorId` (str); `rowStart` (int); `serviceType` (str); `startindex` (int); `tntInstId` (str); `totalSize` (int); `value` (str); `version` (int).

### pricing factor-values list / None

Source: `GET /costFactorList.json`. Probe IDs: `business-15-r1`, `business-15-r2`, `business-15-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `costFactorQueryVO`.

Published UI bundle character offsets: 1500518, 5362664.

No populated record schema verified in this case.

### pricing factor-values list / previous-day:None

Source: `GET /costFactorList.json`. Probe IDs: `previous-day-15-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `costFactorQueryVO`.

Published UI bundle character offsets: 1500518, 5362664.

Sample fields: `bizLine` (str); `colorType` (str); `costDate` (str); `currency` (str); `factorType` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `indicator` (str); `memo` (str); `operator` (str); `pageNo` (int); `pageSize` (int); `period` (str); `rowStart` (int); `serviceType` (str); `startindex` (int); `tntInstId` (str); `totalSize` (int); `value` (str); `version` (int).

### pricing strategies list / None

Source: `POST /pricingStrategyQuery.json`. Probe IDs: `business-16-r1`, `business-16-r2`, `business-16-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `status`.

Published UI bundle character offsets: 1510213, 5416152.

Sample fields: `area` (str); `colorType` (str); `customerLevel` (str); `customerName` (str); `customerNo` (str); `customerScene` (str); `customerSceneDesc` (str); `formula` (null/dict); `gmtCreate` (str); `gmtModified` (str); `id` (str); `lastOperator` (str); `operator` (str); `period` (str); `pricingCurrency` (str); `pricingPatternType` (str); `processId` (str); `processStatus` (str); `quotationMethod` (str); `serviceType` (str); `status` (str); `stepwisePricingStrategyPatternVO` (dict/null); `stepwisePricingStrategyPatternVO.pricingCurrency` (str); `stepwisePricingStrategyPatternVO.pricingModeItemList` (list); `stepwisePricingStrategyPatternVO.pricingModeItemList[]` (dict); `stepwisePricingStrategyPatternVO.pricingModeItemList[].endTransAmount` (str); `stepwisePricingStrategyPatternVO.pricingModeItemList[].formulaVO` (dict); `stepwisePricingStrategyPatternVO.pricingModeItemList[].lowerPrice` (str); `stepwisePricingStrategyPatternVO.pricingModeItemList[].startTransAmount` (str); `stepwisePricingStrategyPatternVO.pricingModeItemList[].upperPrice` (str); `stepwisePricingStrategyPatternVO.tierPricingType` (str); `tntInstId` (str); `transCurrency` (str); `formula.benchmarkName` (str); `formula.benchmarkSource` (str); `formula.benchmarkType` (str); `formula.coefficient` (str); `formula.formulaName` (str); `formula.priceType` (str); `formula.rate` (str); `formula.surcharge` (str).

### pricing strategies list / offset10

Source: `POST /pricingStrategyQuery.json`. Probe IDs: `page-two-16-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `status`.

Published UI bundle character offsets: 1510213, 5416152.

Sample fields: `area` (str); `colorType` (str); `customerLevel` (str); `customerName` (str); `customerNo` (str); `customerScene` (str); `customerSceneDesc` (str); `formula` (null); `gmtCreate` (str); `gmtModified` (str); `id` (str); `lastOperator` (str); `operator` (str); `period` (str); `pricingCurrency` (str); `pricingPatternType` (str); `processId` (str); `processStatus` (str); `quotationMethod` (str); `serviceType` (str); `status` (str); `stepwisePricingStrategyPatternVO` (dict); `stepwisePricingStrategyPatternVO.pricingCurrency` (str); `stepwisePricingStrategyPatternVO.pricingModeItemList` (list); `stepwisePricingStrategyPatternVO.pricingModeItemList[]` (dict); `stepwisePricingStrategyPatternVO.pricingModeItemList[].endTransAmount` (str); `stepwisePricingStrategyPatternVO.pricingModeItemList[].formulaVO` (dict); `stepwisePricingStrategyPatternVO.pricingModeItemList[].lowerPrice` (str); `stepwisePricingStrategyPatternVO.pricingModeItemList[].startTransAmount` (str); `stepwisePricingStrategyPatternVO.pricingModeItemList[].upperPrice` (str); `stepwisePricingStrategyPatternVO.tierPricingType` (str); `tntInstId` (str); `transCurrency` (str).

### pricing valuations list / None

Source: `GET /getFeeOrderList.json`. Probe IDs: `business-68-r1`, `business-68-r2`, `business-68-r3`. Record container: `$.result.data`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `feeOrderListQueryVO`.

Published UI bundle character offsets: 5534000, 5536517.

No populated record schema verified in this case.

### pricing valuations list / previous-day:None

Source: `GET /getFeeOrderList.json`. Probe IDs: `previous-day-59-r1`. Record container: `$.result.data`; total path: `$.result.count`.

Encoding: `query`. Top-level request fields: `tntInstId`, `feeOrderListQueryVO`.

Published UI bundle character offsets: 5534000, 5536517.

No populated record schema verified in this case.

### reference areas cities list / None

Source: `GET /queryParaCity.json`. Probe IDs: `core-02-r1`, `core-02-r2`, `core-02-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `paraCityQueryVO`.

Published UI bundle character offsets: 1487958, 4193665, 4194002.

Sample fields: `aliasName` (str); `code` (str); `countryCode` (str); `gmtCreate` (int); `gmtModified` (int); `id` (int); `memo` (str); `name` (str); `provinceCode` (str); `timeZone` (str).

### reference areas cities list / offset10

Source: `GET /queryParaCity.json`. Probe IDs: `page-two-64-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `paraCityQueryVO`.

Published UI bundle character offsets: 1487958, 4193665, 4194002.

Sample fields: `aliasName` (str); `code` (str); `countryCode` (str); `gmtCreate` (int); `gmtModified` (int); `id` (int); `memo` (str); `name` (str); `provinceCode` (str); `timeZone` (str).

### reference areas countries list / None

Source: `GET /queryParaCountry.json`. Probe IDs: `core-04-r1`, `core-04-r2`, `core-04-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `paraCountryQueryVO`.

Published UI bundle character offsets: 1488015, 4193665, 4194002.

Sample fields: `aliasName` (str); `areaName` (str); `clearingCurrency` (str); `clearingCurrencyList` (list); `clearingCurrencyList[]` (str); `code` (str); `fundCenter` (str); `gmtCreate` (int); `gmtModified` (int); `id` (int); `localCurrency` (str); `memo` (str); `name` (str).

### reference areas countries list / offset10

Source: `GET /queryParaCountry.json`. Probe IDs: `page-two-65-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `paraCountryQueryVO`.

Published UI bundle character offsets: 1488015, 4193665, 4194002.

Sample fields: `aliasName` (str); `areaName` (str); `clearingCurrency` (str); `clearingCurrencyList` (list); `clearingCurrencyList[]` (str); `code` (str); `fundCenter` (str); `gmtCreate` (int); `gmtModified` (int); `id` (int); `localCurrency` (str); `memo` (str); `name` (str).

### reference areas provinces list / None

Source: `GET /queryParaProvince.json`. Probe IDs: `core-03-r1`. Record container: `None`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `paraProvinceQueryVO`.

Published UI bundle character offsets: 1488075, 4193665, 4194002.

No populated record schema verified in this case.

### reference banks list / None

Source: `GET /queryParaBank.json`. Probe IDs: `core-01-r1`, `core-01-r2`, `core-01-r3`. Record container: `$.result.bankVoList`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `paraBankVO`.

Published UI bundle character offsets: 1489390, 4344619, 4341165.

Sample fields: `bankId` (str); `bankName` (str); `bankSwiftCode` (str); `branchFlag` (str); `cityCode` (str); `gmtCreate` (int); `gmtModified` (int); `hqBankId` (str); `id` (int); `localClearingSystemCode` (str); `masterBankId` (str); `masterBankName` (str); `memo` (str); `pageNo` (int); `pageSize` (int); `rowStart` (int); `startindex` (int); `state` (str); `tntInstId` (str); `totalSize` (int).

### reference business-lines list / None

Source: `GET /bankAccountBusinessLineQuery.json`. Probe IDs: `core-06-r1`, `core-06-r2`, `core-06-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankAccountBusinessLineQueryVO`.

Published UI bundle character offsets: 1493952, 4567870, 4568194.

Sample fields: `accountNo` (str); `aliasName` (str); `bankId` (str); `businessLine` (str); `currency` (str); `entity` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `operator` (str); `pageNo` (int); `pageSize` (int); `rowStart` (int); `startindex` (int); `tntInstId` (str); `totalSize` (int).

### reference business-lines list / offset10

Source: `GET /bankAccountBusinessLineQuery.json`. Probe IDs: `page-two-67-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankAccountBusinessLineQueryVO`.

Published UI bundle character offsets: 1493952, 4567870, 4568194.

Sample fields: `accountNo` (str); `aliasName` (str); `bankId` (str); `businessLine` (str); `currency` (str); `entity` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `operator` (str); `pageNo` (int); `pageSize` (int); `rowStart` (int); `startindex` (int); `tntInstId` (str); `totalSize` (int).

### reference calendars list / None

Source: `GET /queryCalendars.json`. Probe IDs: `core-05-r1`, `core-05-r2`, `core-05-r3`. Record container: `$.result.data`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `calendarQuery`.

Published UI bundle character offsets: 1487840, 3111080, 3111380.

Sample fields: `calendarBaseId` (str); `calendarName` (str); `calendarType` (str); `cityCode` (str); `countryCode` (str); `currencyCode` (str); `dayInfoList` (list); `dayInfoList[]` (dict); `dayInfoList[].calendarBaseId` (int); `dayInfoList[].dayOfMonth` (int); `dayInfoList[].dayOfWeek` (int); `dayInfoList[].eventName` (str); `dayInfoList[].id` (str); `dayInfoList[].monthOfYear` (int); `dayInfoList[].year` (int); `memo` (str); `modifiedTime` (str); `operator` (str); `year` (int).

### reference calendars list / offset10

Source: `GET /queryCalendars.json`. Probe IDs: `page-two-66-r1`. Record container: `$.result.data`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `calendarQuery`.

Published UI bundle character offsets: 1487840, 3111080, 3111380.

Sample fields: `calendarBaseId` (str); `calendarName` (str); `calendarType` (str); `cityCode` (str); `countryCode` (str); `currencyCode` (str); `dayInfoList` (list); `dayInfoList[]` (dict); `dayInfoList[].calendarBaseId` (int); `dayInfoList[].dayOfMonth` (int); `dayInfoList[].dayOfWeek` (int); `dayInfoList[].eventName` (str); `dayInfoList[].id` (str); `dayInfoList[].monthOfYear` (int); `dayInfoList[].year` (int); `memo` (str); `modifiedTime` (str); `operator` (str); `year` (int).

### reference entities list / None

Source: `GET /entityMaintQuery.json`. Probe IDs: `core-00-r1`, `core-00-r2`, `core-00-r3`. Record container: `$.result.entityMaintVOList`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `entityMaintQueryVO`.

Published UI bundle character offsets: 1487898, 5579190, 5576045.

Sample fields: `cityCode` (str); `countryCode` (str); `entityCode` (list); `entityCode[]` (str); `gmtCreate` (int); `gmtModified` (int); `id` (int); `innerReconInst` (str); `instCode` (str); `instId` (str); `instName` (str); `memo` (str); `state` (str).

### risk account-capacity list / None

Source: `GET /api/fund/capacity/queryFundCapacityByAliasName.json`. Probe IDs: `business-73-r1`. Record container: `None`; total path: `None`.

Encoding: `query`. Top-level request fields: `aliasName`.

Native identity binding (field names only): `{"leaf": "cash accounts list", "row_field": "aliasName", "source_path": "result.dataValue[0]"}`.

Published UI bundle character offsets: 1521987, 2587113.

No populated record schema verified in this case.

### risk anomalies list / None

Source: `POST /api/risk/event/getAll.json`. Probe IDs: `business-06-r1`, `business-06-r2`, `business-06-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `startTime`, `endTime`, `riskMode`.

Published UI bundle character offsets: 1516395, 7037486.

No populated record schema verified in this case.

### risk anomalies list / previous-day:None

Source: `POST /api/risk/event/getAll.json`. Probe IDs: `previous-day-06-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `startTime`, `endTime`, `riskMode`.

Published UI bundle character offsets: 1516395, 7037486.

No populated record schema verified in this case.

### risk events list / None

Source: `POST /api/risk/event/getAll.json`. Probe IDs: `business-05-r1`, `business-05-r2`, `business-05-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `startTime`, `endTime`, `riskMode`.

Published UI bundle character offsets: 1516395, 7066200, 7067707.

No populated record schema verified in this case.

### risk events list / previous-day:None

Source: `POST /api/risk/event/getAll.json`. Probe IDs: `previous-day-05-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`, `timeZone`, `startTime`, `endTime`, `riskMode`.

Published UI bundle character offsets: 1516395, 7066200, 7067707.

No populated record schema verified in this case.

### risk metrics list / BREAK_EVEN_RATE

Source: `POST /api/metric/singleMetricQuery.json`. Probe IDs: `business-56-r1`, `business-56-r2`, `business-56-r3`. Record container: `None`; total path: `None`.

Encoding: `json`. Top-level request fields: `tntInstId`, `metricName`, `metricLabel`.

Published UI bundle character offsets: 1502243, 6454847, 6455894, 6456354, 6456818.

No populated record schema verified in this case.

### risk metrics list / CONCENTRATION_RATE

Source: `POST /api/metric/manyMetricQuery.json`. Probe IDs: `business-57-r1`, `business-57-r2`, `business-57-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json`. Top-level request fields: `tntInstId`, `metricName`.

Published UI bundle character offsets: 1502430, 6457240, 6457814, 6458376.

Sample fields: `balanceByUsd` (str); `gmtCreate` (str); `gmtModified` (str); `id` (int); `metricLabel` (str); `metricName` (str); `metricNameDescription` (str); `reportDate` (str); `reportTime` (str); `reportTimeOnlyHourAndMinuter` (str); `value` (str).

### risk metrics list / CREDIT_USAGE_RATE

Source: `POST /api/metric/manyMetricQuery.json`. Probe IDs: `business-58-r1`, `business-58-r2`, `business-58-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json`. Top-level request fields: `tntInstId`, `metricName`.

Published UI bundle character offsets: 1502430, 6457240, 6457814, 6458376.

Sample fields: `balanceByUsd` (str); `bankAmountList` (list); `bankAmountList[]` (dict); `bankAmountList[].amount` (str); `bankAmountList[].bankId` (str); `gmtCreate` (str); `gmtModified` (str); `id` (int); `metricLabel` (str); `metricName` (str); `metricNameDescription` (str); `reportDate` (str); `reportTime` (str); `reportTimeOnlyHourAndMinuter` (str); `totalAmount` (str); `value` (str).

### risk metrics list / CURRENCY_T3_LCR

Source: `POST /api/metric/manyMetricQuery.json`. Probe IDs: `business-59-r1`, `business-59-r2`, `business-59-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json`. Top-level request fields: `tntInstId`, `metricName`.

Published UI bundle character offsets: 1502430, 6457240, 6457814, 6458376.

No populated record schema verified in this case.

### risk metrics list / GEO_BALANCE_RATE

Source: `POST /api/metric/singleMetricQuery.json`. Probe IDs: `business-55-r1`, `business-55-r2`, `business-55-r3`. Record container: `None`; total path: `None`.

Encoding: `json`. Top-level request fields: `tntInstId`, `metricName`, `metricLabel`.

Published UI bundle character offsets: 1502243, 6454847, 6455894, 6456354, 6456818.

No populated record schema verified in this case.

### risk metrics list / SINO_FOREIGN_BALANCE_RATE

Source: `POST /api/metric/singleMetricQuery.json`. Probe IDs: `business-54-r1`, `business-54-r2`, `business-54-r3`. Record container: `None`; total path: `None`.

Encoding: `json`. Top-level request fields: `tntInstId`, `metricName`, `metricLabel`.

Published UI bundle character offsets: 1502243, 6454847, 6455894, 6456354, 6456818.

No populated record schema verified in this case.

### risk metrics list / TOTAL_T3_LCR

Source: `POST /api/metric/singleMetricQuery.json`. Probe IDs: `business-53-r1`, `business-53-r2`, `business-53-r3`. Record container: `None`; total path: `None`.

Encoding: `json`. Top-level request fields: `tntInstId`, `metricName`, `metricLabel`.

Published UI bundle character offsets: 1502243, 6454847, 6455894, 6456354, 6456818.

No populated record schema verified in this case.

### risk metrics list / open-balance

Source: `POST /api/metric/openBalanceQuery.json`. Probe IDs: `business-60-r1`, `business-60-r2`, `business-60-r3`. Record container: `None`; total path: `None`.

Encoding: `form`. Top-level request fields: `tntInstId`.

Published UI bundle character offsets: 1502157, 6455281.

No populated record schema verified in this case.

### risk sla get / None

Source: `POST /api/risk/sla/slaConfigDetailQuery.json`. Probe IDs: `business-37-r1`, `business-37-r2`, `business-37-r3`. Record container: `$.data`; total path: `None`.

Encoding: `form`. Top-level request fields: `slaConfigId`.

Native identity binding (field names only): `{"leaf": "risk sla list", "row_field": "slaConfigId", "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 9867502.

Sample fields: `compareUrl` (str); `creator` (str); `detailReason` (str); `detailUrl` (str); `effectiveStatus` (str); `gmtCreate` (str); `gmtModified` (str); `lastOperator` (str); `operator` (str); `processId` (str); `processStatus` (str); `riskEventType` (str); `slaConfigId` (str); `slaRuleVOList` (list); `slaRuleVOList[]` (dict); `slaRuleVOList[].highlightedAccountType` (str); `slaRuleVOList[].isHighlighted` (str); `slaRuleVOList[].slaLevelVOList` (list); `slaRuleVOList[].slaLevelVOList[]` (dict); `slaRuleVOList[].slaLevelVOList[].alarmLevel` (int); `slaRuleVOList[].slaLevelVOList[].alertChannel` (str); `slaRuleVOList[].slaLevelVOList[].alertTimeLine` (str); `slaRuleVOList[].slaLevelVOList[].businessPersonnel` (list); `slaRuleVOList[].slaLevelVOList[].dutyAndEntityOwner` (list); `slaRuleVOList[].slaLevelVOList[].dutyAndEntityOwner[]` (str); `slaRuleVOList[].slaLevelVOList[].isUnlimited` (str); `slaRuleVOList[].slaLevelVOList[].repeatFrequency` (str); `slaRuleVOList[].slaLevelVOList[].repeatTime` (str); `tntInstId` (str); `version` (str).

### risk sla list / None

Source: `POST /api/risk/sla/slaConfigPageQuery.json`. Probe IDs: `business-36-r1`, `business-36-r2`, `business-36-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `pageSize`, `rowStart`.

Published UI bundle character offsets: 9853998, 9854909.

Sample fields: `compareUrl` (str); `creator` (str); `detailReason` (str); `detailUrl` (str); `effectiveStatus` (str); `gmtCreate` (str); `gmtModified` (str); `lastOperator` (str); `operator` (str); `processId` (str); `processStatus` (str); `riskEventType` (str); `slaConfigId` (str); `slaRuleVOList` (list); `tntInstId` (str); `version` (str).

### risk sla list / offset10

Source: `POST /api/risk/sla/slaConfigPageQuery.json`. Probe IDs: `page-two-31-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `pageSize`, `rowStart`.

Published UI bundle character offsets: 9853998, 9854909.

Sample fields: `compareUrl` (str); `creator` (str); `detailReason` (str); `detailUrl` (str); `effectiveStatus` (str); `gmtCreate` (str); `gmtModified` (str); `lastOperator` (str); `operator` (str); `processId` (str); `processStatus` (str); `riskEventType` (str); `slaConfigId` (str); `slaRuleVOList` (list); `tntInstId` (str); `version` (str).

### risk thresholds get / None

Source: `POST /api/risk/benchmark/riskEventBenchmarkDetailDetail.json`. Probe IDs: `business-35-r1`, `business-35-r2`, `business-35-r3`. Record container: `$.data`; total path: `None`.

Encoding: `form`. Top-level request fields: `benchmarkId`.

Native identity binding (field names only): `{"leaf": "risk thresholds list", "row_field": "benchmarkId", "source_path": "data.data[0]"}`.

Published UI bundle character offsets: 9642478.

Sample fields: `benchmarkId` (str); `creator` (str); `detailReason` (str); `gmtCreate` (int); `gmtModified` (int); `lastOperator` (str); `operator` (str); `processId` (str); `riskEventType` (str); `status` (str); `subBenchmarkList` (list); `subBenchmarkList[]` (dict); `subBenchmarkList[].benchmarkType` (str); `subBenchmarkList[].benchmarkValue` (str); `subBenchmarkList[].extraField` (str); `subBenchmarkList[].riskEventType` (str); `subBenchmarkList[].riskIndicator` (str); `subBenchmarkList[].riskObjectType` (str); `subBenchmarkList[].riskObjectValue` (str); `tntInstId` (str); `version` (str).

### risk thresholds list / None

Source: `POST /api/risk/benchmark/riskEventBenchmarkQuery.json`. Probe IDs: `business-34-r1`, `business-34-r2`, `business-34-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1477289, 9622510, 9622750.

Sample fields: `benchmarkId` (str); `creator` (str); `detailReason` (str); `gmtCreate` (int); `gmtModified` (int); `lastOperator` (str); `operator` (str); `processId` (str); `riskEventType` (str); `status` (str); `subBenchmarkList` (list); `subBenchmarkList[]` (dict); `subBenchmarkList[].benchmarkType` (str); `subBenchmarkList[].benchmarkValue` (str); `subBenchmarkList[].extraField` (str); `subBenchmarkList[].riskEventType` (str); `subBenchmarkList[].riskIndicator` (str); `subBenchmarkList[].riskObjectType` (str); `subBenchmarkList[].riskObjectValue` (str); `tntInstId` (str); `version` (str).

### risk thresholds list / offset10

Source: `POST /api/risk/benchmark/riskEventBenchmarkQuery.json`. Probe IDs: `page-two-29-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json`. Top-level request fields: `rowStart`, `pageSize`, `tntInstId`.

Published UI bundle character offsets: 1477289, 9622510, 9622750.

Sample fields: `benchmarkId` (str); `creator` (str); `detailReason` (str); `gmtCreate` (int); `gmtModified` (int); `lastOperator` (str); `operator` (str); `processId` (str); `riskEventType` (str); `status` (str); `subBenchmarkList` (list); `subBenchmarkList[]` (dict); `subBenchmarkList[].benchmarkType` (str); `subBenchmarkList[].benchmarkValue` (str); `subBenchmarkList[].extraField` (str); `subBenchmarkList[].riskEventType` (str); `subBenchmarkList[].riskIndicator` (str); `subBenchmarkList[].riskObjectType` (str); `subBenchmarkList[].riskObjectValue` (str); `tntInstId` (str); `version` (str).

### rules action-mapping list / None

Source: `GET /clientAgreementConfigQuery.json`. Probe IDs: `core-09-r1`, `core-09-r2`, `core-09-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `clientAgreementConfigQueryVO`.

Published UI bundle character offsets: 1496278, 5010175, 5010518.

Sample fields: `bizDirection` (str); `bizEntityCode` (str); `bizType` (str); `currency` (str); `fundActionName` (str); `fundEntityCode` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `lastOperator` (str); `memo` (str); `operator` (str); `processId` (str); `processStatus` (str); `riskActionType` (str); `status` (str); `tntInstId` (str).

### rules action-mapping list / offset10

Source: `GET /clientAgreementConfigQuery.json`. Probe IDs: `page-two-70-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `clientAgreementConfigQueryVO`.

Published UI bundle character offsets: 1496278, 5010175, 5010518.

Sample fields: `bizDirection` (str); `bizEntityCode` (str); `bizType` (str); `currency` (str); `fundActionName` (str); `fundEntityCode` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `lastOperator` (str); `memo` (str); `operator` (str); `processId` (str); `processStatus` (str); `riskActionType` (str); `status` (str); `tntInstId` (str).

### rules forecast list / None

Source: `GET /bankCashForecastRuleQuery.json`. Probe IDs: `core-40-r1`, `core-40-r2`, `core-40-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankCashForecastRuleQueryVO`.

Published UI bundle character offsets: 1488667, 4307039, 4296289.

Sample fields: `accountNo` (str); `bankAccountAliasName` (str); `bankId` (str); `currency` (str); `effectiveTime` (int); `env` (str); `expireTime` (int); `extParamsMap` (str); `forecastOffset` (int); `gmtCreate` (int); `gmtModified` (int); `instId` (str); `lastOperator` (str); `memo` (str); `nextBatchNo` (int); `nextIsCoverIod` (str); `nextIsNeedReview` (str); `nextIsTriggerOperation` (str); `nextTriggerTime` (int); `operator` (str); `paymentDetails` (str); `processId` (str); `processStatus` (str); `purposeCode` (str); `regulatoryInfo` (str); `ruleBizNo` (str); `ruleId` (str); `ruleName` (str); `ruleStatus` (str); `ruleType` (str); `timeZone` (str); `tntInstId` (str); `triggerTimes` (str).

### rules forecast list / offset10

Source: `GET /bankCashForecastRuleQuery.json`. Probe IDs: `page-two-96-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankCashForecastRuleQueryVO`.

Published UI bundle character offsets: 1488667, 4307039, 4296289.

No populated record schema verified in this case.

### rules forecast-filter list / None

Source: `GET /queryAllBankCashForecastFilter.json`. Probe IDs: `core-15-r1`, `core-15-r2`, `core-15-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankCashForecastFilterQueryVO`.

Published UI bundle character offsets: 1495699, 4217162, 4217495.

Sample fields: `bankAccountNo` (str); `bankAliasName` (str); `bankId` (str); `currency` (str); `exType` (str); `gmtCreate` (str); `gmtModified` (str); `id` (int); `instId` (str); `keyWord` (str); `pageNo` (int); `pageSize` (int); `rowStart` (int); `startindex` (int); `tntInstId` (str); `totalSize` (int).

### rules forecast-filter list / offset10

Source: `GET /queryAllBankCashForecastFilter.json`. Probe IDs: `page-two-76-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankCashForecastFilterQueryVO`.

Published UI bundle character offsets: 1495699, 4217162, 4217495.

Sample fields: `bankAccountNo` (str); `bankAliasName` (str); `bankId` (str); `currency` (str); `exType` (str); `gmtCreate` (str); `gmtModified` (str); `id` (int); `instId` (str); `keyWord` (str); `pageNo` (int); `pageSize` (int); `rowStart` (int); `startindex` (int); `tntInstId` (str); `totalSize` (int).

### rules funding list / None

Source: `GET /fundRiskActionRelationQuery.json`. Probe IDs: `core-12-r1`, `core-12-r2`, `core-12-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `fundRiskActionRelationQueryVO`.

Published UI bundle character offsets: 1497077, 5643485, 5643850.

Sample fields: `aliasName` (str); `bizLine` (str); `checkLiquidity` (str); `creator` (str); `editId` (str); `effectiveness` (str); `expectTransferTime` (str); `fundInstId` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `iterationId` (str); `lastOperator` (str); `memo` (str); `messageConfigName` (str); `messageNoticeId` (str); `moduleCode` (str); `moduleId` (str); `nextTriggerTime` (str); `operateType` (str); `operationAliasName` (str); `operationEnable` (bool); `operator` (str); `processId` (str); `processStatus` (str); `relationName` (str); `riskActionRuleId` (str); `riskActionRuleName` (str); `status` (str); `subBizLine` (str); `tntInstId` (str); `version` (int).

### rules funding list / offset10

Source: `GET /fundRiskActionRelationQuery.json`. Probe IDs: `page-two-73-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `fundRiskActionRelationQueryVO`.

Published UI bundle character offsets: 1497077, 5643485, 5643850.

Sample fields: `aliasName` (str); `bizLine` (str); `checkLiquidity` (str); `creator` (str); `editId` (str); `effectiveness` (str); `expectTransferTime` (str); `fundInstId` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `iterationId` (str); `lastOperator` (str); `memo` (str); `messageConfigName` (str); `messageNoticeId` (str); `moduleCode` (str); `moduleId` (str); `nextTriggerTime` (str); `operateType` (str); `operationAliasName` (str); `operationEnable` (bool); `operator` (str); `processId` (str); `processStatus` (str); `relationName` (str); `riskActionRuleId` (str); `riskActionRuleName` (str); `status` (str); `subBizLine` (str); `tntInstId` (str); `version` (int).

### rules fx-settlement list / None

Source: `GET /fxBankAccountConfigQuery.json`. Probe IDs: `core-14-r1`, `core-14-r2`, `core-14-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `fxBankAccountPropertyConfigQueryVO`.

Published UI bundle character offsets: 1497744, 5667413, 5667737.

Sample fields: `accountNo` (str); `bankAliasName` (str); `bankId` (str); `currency` (str); `direction` (str); `gmtCreate` (str); `gmtModified` (str); `id` (int); `instCode` (str); `instId` (str); `operator` (str); `processId` (str); `processStatus` (str); `reconInst` (str); `reconInstCode` (str); `runStatus` (str); `status` (str); `tntInstId` (str); `tradeProfileId` (str).

### rules fx-settlement list / offset10

Source: `GET /fxBankAccountConfigQuery.json`. Probe IDs: `page-two-75-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `fxBankAccountPropertyConfigQueryVO`.

Published UI bundle character offsets: 1497744, 5667413, 5667737.

Sample fields: `accountNo` (str); `bankAliasName` (str); `bankId` (str); `currency` (str); `direction` (str); `gmtCreate` (str); `gmtModified` (str); `id` (int); `instCode` (str); `instId` (str); `operator` (str); `processId` (str); `processStatus` (str); `reconInst` (str); `reconInstCode` (str); `runStatus` (str); `status` (str); `tntInstId` (str); `tradeProfileId` (str).

### rules monitoring list / None

Source: `GET /queryRules.json`. Probe IDs: `core-39-r1`, `core-39-r2`, `core-39-r3`. Record container: `$.result.ruleVOList`; total path: `$.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `ruleQueryVO`.

Published UI bundle character offsets: 1490903, 3082374, 3080017.

No populated record schema verified in this case.

### rules notification get / None

Source: `GET /messageNoticeConfigDetail.json`. Probe IDs: `core-31-r1`, `core-31-r2`, `core-31-r3`. Record container: `$.result.data`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `id`.

Native identity binding (field names only): `{"parameter": "id", "rowfield": "id", "source_leaf": "rules notification list", "source_path": "$.result.dataValue"}`.

Published UI bundle character offsets: 1498744, 6496081, 6504197.

Sample fields: `configName` (str); `creator` (str); `editId` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `iterationId` (str); `lastOperator` (str); `maxRetryTime` (int); `memo` (str); `moduleCode` (str); `moduleId` (str); `operateType` (str); `operator` (str); `paras` (dict); `paras.gotoneServiceCodeEnum` (str); `paras.memo` (str); `paras.message` (str); `paras.notificationTypes` (list); `paras.notificationTypes[]` (str); `paras.subscribers` (list); `paras.webhookUrl` (str); `tntInstId` (str); `used` (bool).

### rules notification list / None

Source: `GET /messageNoticeConfigQuery.json`. Probe IDs: `core-10-r1`, `core-10-r2`, `core-10-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `messageNoticeConfigQueryVO`.

Published UI bundle character offsets: 1498540, 6520093, 6520393.

Sample fields: `configName` (str); `creator` (str); `editId` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `iterationId` (str); `lastOperator` (str); `maxRetryTime` (int); `memo` (str); `moduleCode` (str); `moduleId` (str); `operateType` (str); `operator` (str); `paras` (dict); `paras.gotoneServiceCodeEnum` (str); `paras.memo` (str); `paras.message` (str); `paras.notificationTypes` (list); `paras.notificationTypes[]` (str); `paras.subscribers` (list); `paras.webhookUrl` (str); `tntInstId` (str); `used` (bool).

### rules notification list / offset10

Source: `GET /messageNoticeConfigQuery.json`. Probe IDs: `page-two-71-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `messageNoticeConfigQueryVO`.

Published UI bundle character offsets: 1498540, 6520093, 6520393.

Sample fields: `configName` (str); `creator` (str); `editId` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `iterationId` (str); `lastOperator` (str); `maxRetryTime` (int); `memo` (str); `moduleCode` (str); `moduleId` (str); `operateType` (str); `operator` (str); `paras` (dict); `paras.gotoneServiceCodeEnum` (str); `paras.memo` (str); `paras.message` (str); `paras.notificationTypes` (list); `paras.notificationTypes[]` (str); `paras.subscribers` (list); `paras.webhookUrl` (str); `tntInstId` (str); `used` (bool).

### rules operation get / None

Source: `GET /riskActionRuleDetail.json`. Probe IDs: `core-29-r1`, `core-29-r2`, `core-29-r3`. Record container: `$.result.data`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `ruleId`.

Native identity binding (field names only): `{"parameter": "ruleId", "rowfield": "ruleId", "source_leaf": "rules operation list", "source_path": "$.result.dataValue"}`.

Published UI bundle character offsets: 1496861, 6573462, 6575634.

Sample fields: `accountRule` (str); `amountStrategyId` (str); `creator` (str); `dealMode` (str); `editId` (str); `gmtCreate` (str); `gmtModified` (str); `iterationId` (str); `lastOperator` (str); `maxAmount` (str); `memo` (str); `minAmount` (str); `moduleCode` (str); `moduleId` (str); `operateType` (str); `operationEnable` (bool); `operator` (str); `paymentDetails` (str); `processId` (str); `processStatus` (str); `purposeCode` (str); `regulatoryInfo` (str); `riskActionType` (str); `riskActionTypes` (list); `riskActionTypes[]` (dict); `riskActionTypes[].actionRuleId` (str); `riskActionTypes[].relationId` (str); `riskActionTypes[].riskActionType` (str); `ruleId` (str); `ruleName` (str); `ruleStatus` (str); `timeConditions` (list); `timeZone` (str); `tntInstId` (str); `triggerStrategyId` (str); `valueDateEnabled` (str); `valueDateOffset` (str); `version` (int).

### rules operation list / None

Source: `GET /riskActionRuleListQuery.json`. Probe IDs: `core-13-r1`, `core-13-r2`, `core-13-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `riskActionRuleListQueryVO`.

Published UI bundle character offsets: 1496794, 6582442, 6582785.

Sample fields: `accountRule` (str); `amountStrategyId` (str); `creator` (str); `dealMode` (str); `editId` (str); `gmtCreate` (str); `gmtModified` (str); `iterationId` (str); `lastOperator` (str); `maxAmount` (str); `memo` (str); `minAmount` (str); `moduleCode` (str); `moduleId` (str); `operateType` (str); `operationEnable` (bool); `operator` (str); `paymentDetails` (str); `processId` (str); `processStatus` (str); `purposeCode` (str); `regulatoryInfo` (str); `riskActionType` (str); `riskActionTypes` (list); `riskActionTypes[]` (dict); `riskActionTypes[].actionRuleId` (str); `riskActionTypes[].relationId` (str); `riskActionTypes[].riskActionType` (str); `ruleId` (str); `ruleName` (str); `ruleStatus` (str); `timeConditions` (list); `timeZone` (str); `tntInstId` (str); `triggerStrategyId` (str); `valueDateEnabled` (str); `valueDateOffset` (str); `version` (int).

### rules operation list / offset10

Source: `GET /riskActionRuleListQuery.json`. Probe IDs: `page-two-74-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `riskActionRuleListQueryVO`.

Published UI bundle character offsets: 1496794, 6582442, 6582785.

Sample fields: `accountRule` (str); `amountStrategyId` (str); `creator` (str); `dealMode` (str); `editId` (str); `gmtCreate` (str); `gmtModified` (str); `iterationId` (str); `lastOperator` (str); `maxAmount` (str); `memo` (str); `minAmount` (str); `moduleCode` (str); `moduleId` (str); `operateType` (str); `operationEnable` (bool); `operator` (str); `paymentDetails` (str); `processId` (str); `processStatus` (str); `purposeCode` (str); `regulatoryInfo` (str); `riskActionType` (str); `riskActionTypes` (list); `riskActionTypes[]` (dict); `riskActionTypes[].actionRuleId` (str); `riskActionTypes[].relationId` (str); `riskActionTypes[].riskActionType` (str); `ruleId` (str); `ruleName` (str); `ruleStatus` (str); `timeConditions` (list); `timeZone` (str); `tntInstId` (str); `triggerStrategyId` (str); `valueDateEnabled` (str); `valueDateOffset` (str); `version` (int).

### rules realtime get / None

Source: `POST /api/realtime/rule/getDetail.json`. Probe IDs: `core-33-r1`, `core-33-r2`, `core-33-r3`. Record container: `$.data`; total path: `None`.

Encoding: `json-body`. Top-level request fields: `Id`.

Native identity binding (field names only): `{"parameter": "Id", "rowfield": "id", "source_leaf": "rules realtime list", "source_path": "$.data.data"}`.

Published UI bundle character offsets: 7188563, 7468289.

Sample fields: `aliasName` (str); `bankId` (str); `bizAdjustmentAmount` (str); `creator` (str); `currency` (str); `forecastCycle` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `legalEntityCode` (str); `memo` (str); `networkPreference` (str); `operationActionList` (list); `operationActionList[]` (dict); `operationActionList[].actionType` (str); `operationActionList[].id` (int); `operationActionList[].needReview` (str); `operationActionList[].ruleId` (str); `operationActionList[].timeZone` (str); `operationActionList[].triggerTimesRule` (list); `operationActionList[].useIod` (str); `operationActionList[].useIodTimesRule` (list); `operationPreference` (str); `operationStrategy` (str); `operationTime` (list); `paymentDetail` (str); `processId` (str); `processStatus` (str); `purposeCode` (str); `regulatoryInfo` (str); `ruleName` (str); `runStatus` (str); `updater` (str); `useAlgorithm` (str); `version` (int).

### rules realtime list / None

Source: `POST /api/realtime/rule/getAll.json`. Probe IDs: `core-23-r1`, `core-23-r2`, `core-23-r3`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`.

Published UI bundle character offsets: 7188382, 7371670, 7371670.

Sample fields: `aliasName` (str); `bankId` (str); `bizAdjustmentAmount` (str); `creator` (str); `currency` (str); `forecastCycle` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `legalEntityCode` (str); `memo` (str); `networkPreference` (str); `operationActionList` (list); `operationPreference` (str); `operationStrategy` (str); `operationTime` (list); `paymentDetail` (str); `processId` (str); `processStatus` (str); `purposeCode` (str); `regulatoryInfo` (str); `ruleName` (str); `runStatus` (str); `updater` (str); `useAlgorithm` (str); `version` (int); `operationTime[]` (dict); `operationTime[].beginTime` (str); `operationTime[].calendarCode` (str); `operationTime[].calendarConditionVos` (list); `operationTime[].calendarConditionVos[]` (dict); `operationTime[].calendarType` (str); `operationTime[].conditionLogical` (int); `operationTime[].customCalendarId` (str); `operationTime[].customeType` (str); `operationTime[].days` (list); `operationTime[].endTime` (str); `operationTime[].exclude` (bool); `operationTime[].followActionAccountType` (str); `operationTime[].interval` (int); `operationTime[].timePoint` (str); `operationTime[].type` (str).

### rules realtime list / offset10

Source: `POST /api/realtime/rule/getAll.json`. Probe IDs: `page-two-83-r1`. Record container: `$.data.data`; total path: `$.data.totalCount`.

Encoding: `json-body`. Top-level request fields: `rowStart`, `pageSize`.

Published UI bundle character offsets: 7188382, 7371670, 7371670.

Sample fields: `aliasName` (str); `bankId` (str); `bizAdjustmentAmount` (str); `creator` (str); `currency` (str); `forecastCycle` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `legalEntityCode` (str); `memo` (str); `networkPreference` (str); `operationActionList` (list); `operationPreference` (str); `operationStrategy` (str); `operationTime` (list); `paymentDetail` (str); `processId` (str); `processStatus` (str); `purposeCode` (str); `regulatoryInfo` (str); `ruleName` (str); `runStatus` (str); `updater` (str); `useAlgorithm` (str); `version` (int).

### rules transfer get / None

Source: `GET /queryTransferRuleDetail.json`. Probe IDs: `core-48-r1`, `core-48-r2`, `core-48-r3`. Record container: `$.result.transferRuleVO`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `ruleId`.

Native identity binding (field names only): `{"parameter": "ruleId", "rowfield": "ruleId", "source_leaf": "rules transfer list", "source_path": "$.result.transferRuleVOS"}`.

Published UI bundle character offsets: 1475625, 3024314.

Sample fields: `antProcessURL` (str); `bizConditions` (list); `bizConditions[]` (dict); `bizConditions[].condition` (str); `bizConditions[].conditionLogical` (int); `bizConditions[].gradeVOList` (list); `bizConditions[].gradeVOList[]` (dict); `bizConditions[].gradeVOList[].gradeNo` (int); `bizConditions[].gradeVOList[].gradeSymbol` (int); `bizConditions[].gradeVOList[].maxValue` (int); `bizConditions[].gradeVOList[].minValue` (int); `bizConditions[].id` (int); `bizConditions[].name` (str); `bizConditions[].order` (int); `bizConditions[].paraMap` (null); `bizConditions[].tntInstId` (str); `block` (str); `businessScene` (str); `businessType` (str); `creator` (str); `creditAccountName` (str); `creditAccountNo` (str); `creditAliasName` (str); `creditBankId` (str); `creditCurrency` (str); `creditEntity` (str); `debitAccountName` (str); `debitAccountNo` (str); `debitAliasName` (str); `debitBankId` (str); `debitCurrency` (str); `debitEntity` (str); `editId` (str); `editPermission` (str); `effectiveTime` (int); `effectivenessReq` (str); `env` (str); `expiryTime` (int); `extTitle` (str); `gmtCheck` (int); `gmtCreate` (int); `gmtModified` (int); `instId` (str); `iterationId` (str); `memo` (str); `moduleCode` (str); `moduleId` (str); `needTally` (str); `network` (str); `nextTriggerTime` (int); `operateType` (str); `operationEnable` (bool); `operator` (str); `outBizNo` (str); `outRequestNo` (str); `ownerId` (str); `ownerType` (str); `paymentAmount` (str); `paymentDetails` (str); `preCheckCondtions` (list); `processId` (str); `purposeCode` (str); `regulatoryInfo` (str); `ruleActionVOS` (list); `ruleActionVOS[]` (list); `ruleActionVOS[][]` (dict); `ruleActionVOS[][].actionPara` (dict); `ruleActionVOS[][].actionPara.gotoneServiceCodeEnum` (str); `ruleActionVOS[][].actionPara.memo` (str); `ruleActionVOS[][].actionPara.message` (str); `ruleActionVOS[][].actionPara.notificationTypes` (list); `ruleActionVOS[][].actionPara.subscribers` (list); `ruleActionVOS[][].actionPara.webhookUrl` (str); `ruleActionVOS[][].block` (str); `ruleActionVOS[][].code` (str); `ruleActionVOS[][].conditions` (list); `ruleActionVOS[][].executeTimes` (int); `ruleActionVOS[][].gmtCreate` (int); `ruleActionVOS[][].gmtModified` (int); `ruleActionVOS[][].id` (int); `ruleActionVOS[][].maxRetryTime` (int); `ruleActionVOS[][].memo` (str); `ruleActionVOS[][].order` (int); `ruleActionVOS[][].paraMap` (null); `ruleActionVOS[][].ruleId` (str); `ruleActionVOS[][].subRuleId` (int); `ruleActionVOS[][].tntInstId` (str); `ruleActionVOS[][].transferActionParaVO` (null); `ruleCheckCondtions` (list); `ruleHolder` (str); `ruleId` (str); `ruleModel` (str); `ruleName` (str); `ruleNo` (str); `sceneCode` (str); `securityLevel` (str); `sourceApp` (str); `status` (str); `subBusinessType` (str); `subTitle` (str); `timeConditions` (list); `timeConditions[]` (dict); `timeConditions[].beginTime` (str); `timeConditions[].calendarCode` (str); `timeConditions[].calendarConditionVos` (list); `timeConditions[].calendarConditionVos[]` (dict); `timeConditions[].calendarConditionVos[].calendarCode` (str); `timeConditions[].calendarConditionVos[].calendarType` (str); `timeConditions[].calendarConditionVos[].customCalendarId` (str); `timeConditions[].calendarConditionVos[].customeType` (str); `timeConditions[].calendarConditionVos[].days` (list); `timeConditions[].calendarConditionVos[].exclude` (bool); `timeConditions[].calendarConditionVos[].followActionAccountType` (str); `timeConditions[].calendarConditionVos[].order` (int); `timeConditions[].calendarType` (str); `timeConditions[].conditionLogical` (int); `timeConditions[].customCalendarId` (str); `timeConditions[].customeType` (str); `timeConditions[].days` (list); `timeConditions[].endTime` (str); `timeConditions[].exclude` (bool); `timeConditions[].followActionAccountType` (str); `timeConditions[].interval` (int); `timeConditions[].timePoint` (str); `timeConditions[].type` (str); `timeZone` (str); `title` (str); `tntInstId` (str); `transferRuleType` (str); `transferType` (str); `triggerTimes` (str); `triggerType` (int); `userGroupCode` (str); `version` (int).

### rules transfer list / None

Source: `GET /transferRuleQuery.json`. Probe IDs: `core-38-r1`, `core-38-r2`, `core-38-r3`. Record container: `$.result.transferRuleVOS`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `transferRuleQueryRequest`.

Published UI bundle character offsets: 1475485, 2629130, 2623732.

Sample fields: `antProcessURL` (str); `bizConditions` (list); `block` (str); `businessScene` (str); `businessType` (str); `creator` (str); `creditAccountName` (str); `creditAccountNo` (str); `creditAliasName` (str); `creditBankId` (str); `creditCurrency` (str); `creditEntity` (str); `debitAccountName` (str); `debitAccountNo` (str); `debitAliasName` (str); `debitBankId` (str); `debitCurrency` (str); `debitEntity` (str); `editId` (str); `editPermission` (str); `effectiveTime` (int); `effectivenessReq` (str); `env` (str); `expiryTime` (int); `extTitle` (str); `gmtCheck` (int); `gmtCreate` (int); `gmtModified` (int); `instId` (str); `iterationId` (str); `memo` (str); `moduleCode` (str); `moduleId` (str); `needTally` (str); `network` (str); `nextTriggerTime` (int); `operateType` (str); `operationEnable` (bool); `operator` (str); `outBizNo` (str); `outRequestNo` (str); `ownerId` (str); `ownerType` (str); `paymentAmount` (str); `paymentDetails` (str); `preCheckCondtions` (list); `processId` (str); `purposeCode` (str); `regulatoryInfo` (str); `ruleActionVOS` (list); `ruleCheckCondtions` (list); `ruleHolder` (str); `ruleId` (str); `ruleModel` (str); `ruleName` (str); `ruleNo` (str); `sceneCode` (str); `securityLevel` (str); `sourceApp` (str); `status` (str); `subBusinessType` (str); `subTitle` (str); `timeConditions` (list); `timeZone` (str); `title` (str); `tntInstId` (str); `transferRuleType` (str); `transferType` (str); `triggerTimes` (str); `triggerType` (int); `userGroupCode` (str); `version` (int).

### rules transfer list / offset10

Source: `GET /transferRuleQuery.json`. Probe IDs: `page-two-94-r1`. Record container: `$.result.transferRuleVOS`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `transferRuleQueryRequest`.

Published UI bundle character offsets: 1475485, 2629130, 2623732.

Sample fields: `antProcessURL` (str); `bizConditions` (list); `block` (str); `businessScene` (str); `businessType` (str); `creator` (str); `creditAccountName` (str); `creditAccountNo` (str); `creditAliasName` (str); `creditBankId` (str); `creditCurrency` (str); `creditEntity` (str); `debitAccountName` (str); `debitAccountNo` (str); `debitAliasName` (str); `debitBankId` (str); `debitCurrency` (str); `debitEntity` (str); `editId` (str); `editPermission` (str); `effectiveTime` (int); `effectivenessReq` (str); `env` (str); `expiryTime` (int); `extTitle` (str); `gmtCheck` (int); `gmtCreate` (int); `gmtModified` (int); `instId` (str); `iterationId` (str); `memo` (str); `moduleCode` (str); `moduleId` (str); `needTally` (str); `network` (str); `nextTriggerTime` (int); `operateType` (str); `operationEnable` (bool); `operator` (str); `outBizNo` (str); `outRequestNo` (str); `ownerId` (str); `ownerType` (str); `paymentAmount` (str); `paymentDetails` (str); `preCheckCondtions` (list); `processId` (str); `purposeCode` (str); `regulatoryInfo` (str); `ruleActionVOS` (list); `ruleCheckCondtions` (list); `ruleHolder` (str); `ruleId` (str); `ruleModel` (str); `ruleName` (str); `ruleNo` (str); `sceneCode` (str); `securityLevel` (str); `sourceApp` (str); `status` (str); `subBusinessType` (str); `subTitle` (str); `timeConditions` (list); `timeZone` (str); `title` (str); `tntInstId` (str); `transferRuleType` (str); `transferType` (str); `triggerTimes` (str); `triggerType` (int); `userGroupCode` (str); `version` (int).

### rules transfer-config list / None

Source: `GET /transferConfigQuery.json`. Probe IDs: `core-11-r1`, `core-11-r2`, `core-11-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankTransferFundConfigQueryVo`.

Published UI bundle character offsets: 1489447, 7536942, 7537266.

Sample fields: `agentLegalEntityCode` (str); `approver` (str); `bankId` (str); `bizType` (str); `calculateAmountWay` (str); `creditAliasName` (str); `currency` (str); `debitAliasName` (str); `debitType` (str); `direction` (str); `effectiveStatus` (str); `entity` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `lastOperator` (str); `operator` (str); `originCurrency` (str); `pageNo` (int); `pageSize` (int); `processId` (str); `processStatus` (str); `reconInst` (str); `rowStart` (int); `startindex` (int); `subBizType` (str); `tntInstId` (str); `totalSize` (int); `transactionAliasName` (str); `transferWay` (str).

### rules transfer-config list / offset10

Source: `GET /transferConfigQuery.json`. Probe IDs: `page-two-72-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankTransferFundConfigQueryVo`.

Published UI bundle character offsets: 1489447, 7536942, 7537266.

Sample fields: `agentLegalEntityCode` (str); `approver` (str); `bankId` (str); `bizType` (str); `calculateAmountWay` (str); `creditAliasName` (str); `currency` (str); `debitAliasName` (str); `debitType` (str); `direction` (str); `effectiveStatus` (str); `entity` (str); `gmtCreate` (str); `gmtModified` (str); `id` (str); `lastOperator` (str); `operator` (str); `originCurrency` (str); `pageNo` (int); `pageSize` (int); `processId` (str); `processStatus` (str); `reconInst` (str); `rowStart` (int); `startindex` (int); `subBizType` (str); `tntInstId` (str); `totalSize` (int); `transactionAliasName` (str); `transferWay` (str).

### rules treasury-transfer list / None

Source: `GET /queryTreasuryTransferRuleList.json`. Probe IDs: `core-16-r1`. Record container: `None`; total path: `None`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `transferRuleQueryRequest`.

Published UI bundle character offsets: 1475549, 3193153, 3193453.

No populated record schema verified in this case.

### rules waterlevel get / None

Source: `GET /bankAccountBufferListByAliasName.json`. Probe IDs: `core-46-r1`, `core-46-r2`, `core-46-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `aliasName`.

Native identity binding (field names only): `{"parameter": "aliasName", "rowfield": "aliasName", "source_leaf": "rules waterlevel list", "source_path": "$.result.dataValue"}`.

Published UI bundle character offsets: 1493422, 4522540.

Sample fields: `accountNo` (str); `accountingEntityCode` (str); `aliasName` (str); `bankId` (str); `bufferId` (str); `bufferSource` (str); `containSafetyBuffer` (str); `containStructureBuffer` (str); `currency` (str); `daytimeBufferVos` (list); `entity` (str); `gmtCreate` (str); `gmtModified` (str); `legalEntityCode` (str); `manualBuffer` (str); `memo` (str); `operator` (str); `pageNo` (int); `pageSize` (int); `processId` (str); `processStatus` (str); `rowStart` (int); `safetyBuffer` (str); `startindex` (int); `status` (str); `structureBuffer` (str); `sumBuffer` (str); `timeZone` (str); `tntInstId` (str); `totalSize` (int); `version` (str).

### rules waterlevel list / None

Source: `GET /bankAccountBufferQuery.json`. Probe IDs: `core-45-r1`, `core-45-r2`, `core-45-r3`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankAccountBufferQueryVO`.

Published UI bundle character offsets: 1493293, 4524766.

Sample fields: `accountNo` (str); `accountingEntityCode` (str); `aliasName` (str); `bankId` (str); `bufferId` (str); `bufferSource` (str); `containSafetyBuffer` (str); `containStructureBuffer` (str); `currency` (str); `daytimeBufferVos` (list); `entity` (str); `gmtCreate` (str); `gmtModified` (str); `legalEntityCode` (str); `manualBuffer` (str); `memo` (str); `operator` (str); `pageNo` (int); `pageSize` (int); `processId` (str); `processStatus` (str); `rowStart` (int); `safetyBuffer` (str); `startindex` (int); `status` (str); `structureBuffer` (str); `sumBuffer` (str); `timeZone` (str); `tntInstId` (str); `totalSize` (int); `version` (str).

### rules waterlevel list / offset10

Source: `GET /bankAccountBufferQuery.json`. Probe IDs: `page-two-101-r1`. Record container: `$.result.dataValue`; total path: `$.result.count`.

Encoding: `url-query`. Top-level request fields: `tntInstId`, `bankAccountBufferQueryVO`.

Published UI bundle character offsets: 1493293, 4524766.

Sample fields: `accountNo` (str); `accountingEntityCode` (str); `aliasName` (str); `bankId` (str); `bufferId` (str); `bufferSource` (str); `containSafetyBuffer` (str); `containStructureBuffer` (str); `currency` (str); `daytimeBufferVos` (list); `entity` (str); `gmtCreate` (str); `gmtModified` (str); `legalEntityCode` (str); `manualBuffer` (str); `memo` (str); `operator` (str); `pageNo` (int); `pageSize` (int); `processId` (str); `processStatus` (str); `rowStart` (int); `safetyBuffer` (str); `startindex` (int); `status` (str); `structureBuffer` (str); `sumBuffer` (str); `timeZone` (str); `tntInstId` (str); `totalSize` (int); `version` (str).

## Source boundaries

Production menu and native UI source are current runtime evidence. Historical product wiki/PRD documents supplied terminology in the first draft; they do not establish these API contracts. Existing cache implementation and the isolated benchmark supply local implementation evidence. Proposed behavior is specified in [GitHub issue #71](https://github.com/proletariat64/dogopencli/issues/71); no liquidity CLI implementation or release has been delivered by this investigation.
