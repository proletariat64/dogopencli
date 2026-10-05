# Investment quote source-state snapshots v0.1.0

Authoritative specification: [issue #98](https://github.com/proletariat64/dogopencli/issues/98),
2026-10-05 quote clarification. The operator confirmed O/N as Overnight, quote as a
percent value, ticketSize as minimum deposit, UTC+08:00 as source time interpretation,
and omission of totalCount as the native page design. WIN selection is unimplemented
upstream and explicitly excluded. This contract enables only the QUOTED list;
quotes get remains unsupported. Independent [production CLI UAT](../research/general/2026-10-05-quotes-uat.md)
passed 9/9 steps on 2026-10-05, covering 338 unique rows and all 24 projected fields
against the same native response. Local checks and review remain separate gates.

## Bounded request

```text
dogopencli liquidity investment quotes list --from-date 2026-01-01 --to-date 2026-10-05
dogopencli refresh liquidity investment quotes --from-date 2026-01-01 --to-date 2026-10-05
```

Both inclusive value-date bounds are mandatory valid YYYY-MM-DD dates with
start <= end. The fixed Liquidity origin/route sends JSON POST
`/quotationAnalysis.json`, `dataType=QUOTED`, `timeZone=null`, `rowStart=0`,
`pageSize=5000`; public date bounds map to `startValueDate`/`endValueDate` in
YYYYMMDD. The verified caller has no explicit tenant request field. No WIN option,
unbounded request, guessed filter, alternate origin, or fallback query exists.

## Single-response protocol

`success=true` and an array at `data` are required. The existing `PAGE_SINGLE`
collector issues exactly one request with `total=None`. Missing totalCount is
normal and remains `reported_total=null`; the collected record count is not
relabeled as a backend-reported total. Explicit success with `data=[]` is a complete
empty response under this confirmed contract.

The operator-authorized year-to-date range returned 338 unique quotations for
page sizes 10/20/1000/5000 and offset 10, with equal decoded rows. A one-day query
returned the exact 270-record subset. Production CLI UAT also accepted the empty
2026-09-28 through 2026-10-05 scope without replacing the populated year-to-date
capture. This supports a bounded single-response contract,
not a guarantee that arbitrarily larger source datasets have no server capacity
limit. Do not loop through ignored pagination or invent a total to satisfy a gate.

The only native record identity is nonempty string `quotationOrderId`. `inquiryId`
has a different granularity, and no native revision field was observed. Keep
existing ADR 0019 behavior: conflicting same-identity records fail closed; identical
duplicate arrivals provide incomplete evidence, with safe partial/default and
strict refusal. Protocol/shape/authentication/identity failures preserve old cache.

## Source fields and meaning

The projection preserves the 24 observed fields: quotation/inquiry IDs and times,
quotation group, bank, account/product type, department, currency, tenor, quote,
ticketSize, curMaxLimitAvailable, native maximum flags, value/maturity/effectivity
dates, redemption feature, winAmount, negotiation status and source remark. It does
not generate frontend quoteNum, a business revision or another identity.

`quote` is a native percent value without scaling. `ticketSize` is the minimum
deposit amount in source currency. O/N means overnight. `curMaxLimitAvailable`
remains an unconfirmed business term; do not relabel it as an established credit
or trading cap. Source flags are retained, never recomputed.

Native time strings are interpreted in operator-confirmed UTC+08:00; their values
are not converted, and the wire timeZone stays null. Query bounds and capture time
are not source observation times. Native money/rate/currency/date/status values,
including precision, negative/zero, blank/null/missing and unknown values, remain
raw. Do not parse business dates, validate tenor/maturity arithmetic, enforce rate
or amount bounds, fill currency, or calculate rates, limits or deposits. Only
request bounds are parsed to construct a correct bounded inquiry.

## Exact-scope cache

The independent `quotes-v1` namespace reuses `PROFILE_HISTORY`, retaining captures
by fetch time for each exact requested date-filter scope. Default list is offline;
explicit refresh publishes, and live never publishes or falls back. Adjacent,
overlapping and wider/narrower requested ranges are separate scopes. No cross-range
merge or local business-date filtering manufactures source coverage. A successful
empty refresh for one range cannot replace a populated capture for another range.

This preserves raw source dates without introducing dated-retention validation or
a parallel cache framework. Scope metadata records the request bounds; source
observation metadata remains distinct and unknown where no aggregate observation
axis is established. There is no history command or source revision promise.
