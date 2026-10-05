# Batch F3 investment offers, quote sessions and investable funds

Observed: 2026-10-06
Scope: general
Status: snapshot

Evidence-gated discovery for the three Batch F investment leaves in
[#118](https://github.com/proletariat64/dogopencli/issues/118), under the
parent tracker [#72](https://github.com/proletariat64/dogopencli/issues/72).
This is native inquiry evidence only: no list was enabled, no production CLI
UAT was run, and all three leaves remain deferred with named blockers.

## Method and environment

Liquidity authentication was independently verified on the dedicated headless
CDP 9223 session (isolated profile, liquidity probe settled on the first-party
origin). Probes were serial, read-only business inquiries through the
restricted inquiry transport; no mutation, login repair, unknown request or
shared-session takeover occurred. Read-only graphify queries located the
owning knowledge-base sources (P1–P5 in the issue), followed by direct source
inspection; graph node summaries were not relied on.

## Offers and quote sessions: no proven native runtime objects

The current ProductPoolView page shows product definition fields (Product
Code, Bank ID, Product Nature/Type/Tenor, CCY, Status). RFQMgmt shows Inquiry
Type/Status, Quotation Status and Inquiry Task ID. QuotationGroupMgmt shows
group ID, name and status.

None of these pages proves an independent native runtime offers object or an
independent quote-session object with its own granularity and identity. The
PRD sources distinguish product definitions, institution inquiries (RFQs),
quote groups, quotes and investment execution; offers and sessions must map to
native objects, not be substituted by already-supported or separately tracked
RFQ/group/quote lists. Renaming RFQ or quote-group lists as offers or
sessions is explicitly rejected.

Decision: `liquidity investment offers list` and
`liquidity investment quote-sessions list` stay deferred with the
`runtimes/unverified` blocker. Next evidence work: establish whether offers
are dated institution-acceptable offers and their relation to supported
quotes; establish independent session granularity and a native session
identity.

## Investable funds: known contract, empty observed scope

The native list inquiry is a JSON POST to `/queryInvestableFundList.json`
with Content-Type `application/json;charset=utf-8`. The frozen request shape
carries native keys `tenant`, `timeZone`, `reportDate`, `startForecastDate`,
`endForecastDate`, `rowStart`, `pageSize` and optional native `currency`.
Source fallback timezone is GMT+08; the current user's timezone preference was
not independently confirmed this round. The response envelope reads
`data.data` rows plus `data.totalCount`.

Bounded probes covered seven report dates (2026-10-06, 2026-10-05, 2026-09-30,
2026-09-01, 2026-07-01, 2026-04-01, 2026-01-01), each at page widths 1000 and
5000, each with the forecast range 2026-01-01 through 2026-10-06 and with the
native empty forecast range: 28 inquiries total. All 28 returned HTTP 200 with
`success=true`, an empty `data.data` and `totalCount=0`, echoing the requested
`rowStart`/`pageSize`. The seven report dates are samples, not an enumeration
of the year. Native future report dates are forbidden and were not queried.

The native UI table columns `forecastDate`, `currency`,
`originalInvestableAmount`, `reserveAmount`, `investedAmount` and
`adjustedInvestableAmount` remain an unpopulated schema: `(forecastDate,
currency)` uniqueness is unproven, amount units/precision are unverified, and
`reportDate` (report dimension) and `forecastDate` (forecast dimension) must
not be read as fetch timestamps.

Decision: `liquidity investment investable-funds list` stays deferred with
the `empty-scope` blocker. Enablement gates on a populated positive sample —
a report scope with real rows or a business-side example — proving nonempty
rows, unique identity, and amount/date semantics, followed by standalone
serial production CLI UAT. The 28 already-empty ranges must not be repeated;
without a positive sample the gate holds.

## Outcome

Leaves evaluated: 3/3. Newly enabled: 0. All three remain unsupported with
specific named blockers; help/describe/snapshot discoverability and
cached/live/strict/refresh rejection are preserved and covered by
`tests/integration/test_liquidity_batch_f3_gate.py`. Investigation completion
and list delivery remain separate; these leaves must not be closed by parent
ticket bookkeeping. The unsupported-leaf count is unchanged (42).

Prior evidence: [October 1 live probes](2026-10-01-liquidity-live-probes.md)
and the [#82](https://github.com/proletariat64/dogopencli/issues/82) spec
history. The 2026-10-06 evidence supersedes the earlier five-probe empty-scope
note for investable funds; dated observations remain historical evidence.
