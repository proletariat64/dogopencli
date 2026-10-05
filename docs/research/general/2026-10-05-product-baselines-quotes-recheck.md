# Product baselines and investment quotes: bounded recheck

Observed: 2026-10-05
Scope: general
Status: snapshot

Research for the two remaining candidates in [#98](https://github.com/proletariat64/dogopencli/issues/98), following pool-balances and credit-usage delivery on PR #100. The operator subsequently confirmed that product baselines are unused and requested removal from the catalog. Quotes remain under investigation. This is native inquiry evidence, not quote CLI implementation or production UAT.

## Fresh native evidence

Liquidity authentication was independently verified on the dedicated headless CDP 9223 session. Browser ownership was checked with the exclusive control lock; queries used temporary targets and the restricted inquiry transport. No business mutation, login repair or shared-session takeover occurred.

The current authenticated page references `S090011910164/umi.js` on the first-party alipayobjects host. A fresh fetch matched the previously inspected bundle exactly: SHA256 `cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`, 15,763,128 bytes. Caller offsets below use zero-based Unicode character positions.

| Candidate | Exact bounded scope | Observed result |
| --- | --- | --- |
| network product-baselines list | JSON POST `/api/product/timeliness/payment/getAll.json`; tenant GUAPW3SG; rowStart 0/pageSize 10; RUN, INIT and PAUSE queried separately | All three explicitly successful; `data.data=[]`, `data.totalCount=0` |
| investment quotes list | JSON POST `/quotationAnalysis.json`; rowStart 0/pageSize 10; QUOTED and WIN separately; startValueDate 20260928/endValueDate 20261005; native timeZone null | Both explicitly successful; `data=[]`; top-level `totalCount` absent |

Five initial business queries were issued. Quote dates reproduce the native UI default of seven days before browser today through today, not a newly invented history search. The exact named timezone cookie was absent; the caller forwards null, so no environment timezone was substituted. Query totals, response structure and dates above are fresh observations. Raw responses and browser metadata remain private.

## Product-baseline meaning and remaining gap

The native caller maps its three tabs to RUN/INIT/PAUSE and adds the route tenant (bundle offsets 6391100–6391800). Its table describes payment entity, country, currency, bank/account, RealTime/T0/T1 product type, configured limits, service windows and holidays. Those are configured capabilities, not observed payment speed or SLA attainment.

Read-only graphify queries were used to locate owning knowledge-base sources, followed by direct source inspection:

- Liquidity's *全球实时达产品说明书* (2023-12-15, source 143062443, lines 126–131) describes baseline inquiry as supported timeliness products for payment bank accounts. Internal lifecycle management is struck through in this historical document.
- *流动性平台页面梳理* (2024-03-13, source 323959460, lines 79–80) marks 产品基线管理 as 待确认 / 不用, while 银存基线管理 is 运行中 / 在用. Historical disuse is a plausible explanation for empty results, not proof of current retirement or global absence. Bank-account baselines are not substituted for this candidate.

The three tested scopes are explicitly complete-empty, but no populated schema, typed row identity or revision/status contract has been observed. The operator then explicitly confirmed that this exact module is no longer used and requested removal from the list. This operator decision, rather than empty responses alone, authorizes retiring both unsupported product-baselines list/get paths. Preserve other bank/account/SLA baseline capabilities. Do not infer a nonempty contract from the static editor's id reference or fabricate fixtures to clear the first-release gate.

## Quote meaning and remaining gap

The owning CY26 Liquidity product plan (2026-08-18, source 490870296, line 5) separates quotation-group management, inquiry, quote, negotiation and win. The CY25-S2 plan (2025-11-13, source 460449362, line 54) likewise separates grouping, inquiry capture and negotiation results. Groups and inquiries cannot replace quote records.

Current source calls `/quotationAnalysis.json` (offset 1531981). The actual table labels `quotationOrderId` as Quotation Id and retains distinct inquiry identifiers (10004500–10007000). The caller reads top-level data and totalCount, locally derives quoteNum from quote, and defaults a missing displayed total to zero (11130600–11131700). That display fallback does not prove complete acquisition. Native date defaults and QUOTED/WIN switching are at 11133000–11133700.

Both initial quote responses omit totalCount. They cannot establish a complete-empty protocol. The operator then explicitly authorized widening the value-date range to 2026-01-01 through browser today, 2026-10-05. This remains a finite, requested scope, not an all-history query.

## Operator-authorized wider quote scope

The same native request with startValueDate 20260101/endValueDate 20261005 returned 338 QUOTED rows and zero WIN rows. All 338 quotationOrderId values are nonblank strings and unique; 203 inquiryId values confirm that inquiry identity is a different granularity. There are no identical duplicate rows. No totalCount is present in either variant.

Observed value dates and row counts: 20260413 (40), 20260414 (13), 20260415 (1), 20260416 (1), 20260429 (6), 20260506 (3), 20260508 (2), 20260511 (2), and 20260820 (270). The native schema contains string quotation/inquiry timestamps, valueDate, quote, currency, ticketSize, curMaxLimitAvailable, maturity/effectivity dates, winAmount and negotiationStatus; no explicit revision field was observed. All observed negotiationStatus values are NOT_NEGOTIATED. No source rate, amount, bank or identifier values are published here.

Three bounded follow-ups tested the reading protocol:

| Scope change | Rows | Observation |
| --- | --- | --- |
| Same year-to-date dates, rowStart 10/pageSize 10 | 338 | Byte-equivalent decoded row sequence to the initial rowStart 0/pageSize 10 response |
| Same year-to-date dates, rowStart 0/pageSize 20 | 338 | Same decoded row sequence and identities |
| 20260820 through 20260820, rowStart 0/pageSize 10 | 270 | Exactly the identity subset for that day in the larger response; no other value date |

This is evidence that these pagination parameters do not page the observed quote dataset, while the value-date filter does select the observed day, including an equal start/end boundary. Do not add repeated pages to a collector or invent a totalCount. It is not proof of an unlimited server response or absence of a hidden truncation cap. Static caller pagination controls and backend behavior differ here.

Ten business inquiries were issued in total: three baseline states, two default quote variants, two authorized wider quote variants and three QUOTED protocol controls. No mutations, quote-group/RFQ fallback, guessed timezone, or further scope expansion occurred. Raw results remain private. Quote interest rates and monetary strings should remain source values; no arithmetic or business-rule validation is proposed.

## Outcome

Remaining candidates evaluated: 2/2. Quote newly enabled: 0. Product-baselines is retired at the operator's explicit request, not counted as an implemented capability. Original #98 accounting is two delivered candidates, one retired candidate and one remaining quote candidate. Removing the two unsupported product-baseline paths changes this independent branch catalog from 77 supported/56 unsupported/133 total to 77 supported/54 unsupported/131 total; it does not merge the separate #97 branch or release a version.

The quote investigation now has populated native identity/schema and observed date-filter behavior. It still needs a reliable bounded full-response contract (including whether there is a server truncation cap), a decision on supported variants given WIN remains empty, and honest native timestamp/zone metadata. No quote implementation or production CLI UAT is claimed. Existing pool/credit settings and runtime caches are unchanged.

Prior evidence: [October 4 gates](2026-10-04-liquidity-issue98-gates.md). The new populated scope and operator retirement supersede only the corresponding earlier gates; dated observations remain historical evidence.
