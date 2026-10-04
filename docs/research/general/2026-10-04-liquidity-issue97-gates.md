# Liquidity issue 97: native details, areas and fee-order gates

Observed: 2026-10-04
Scope: general
Status: snapshot

Specification: [issue #97](https://github.com/proletariat64/dogopencli/issues/97).
Baseline: `c15e35f`, version `0.2.6`, 75 supported / 58 unsupported leaves.
This report separates native investigation from implementation and registered
public CLI production UAT. Issue #97 remains open while an original candidate
is deferred without the operator accepting that deferral.

## Current native investigation

CDP 9223 was reachable and its profile login/control locks were idle. Independent
Liquidity authentication passed. Native investigations held the exclusive control
lock, used their own temporary targets, and closed them afterwards. No province
request, browser restart, authentication repair or mutation was performed.
Production responses remain private in ignored `tmp/issue97/`.

The authenticated PortfolioMgmt page referenced the current `umi.js` with SHA256
`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`.
Native caller inspection preceded each inquiry. Business requests used the
existing restricted transport and explicit inquiry contracts.

| Candidate / variant | Current evidence | Gate status |
| --- | --- | --- |
| strategy-results get / fund | Form POST `/api/increment/decision/task/taskDetail.json`, only `taskId` from list `id`; nonempty detail echoes `taskId` and `FUND_DECISION_TASK` | Native identity passed; implementation and CLI UAT pending |
| strategy-results get / product | Independently queried same true detail caller; echoes `taskId` and `PRODUCT_DECISION_TASK`; native `investableFundResultVo=null` | Native identity passed; implementation and CLI UAT pending |
| risk events get | Form POST `/api/risk/event/detail.json`, only `riskEventId` from event list `id`; detail `id` and `RISK_EVENT` match | Native identity passed; implementation and CLI UAT pending |
| risk anomalies get | Independently queried alert detail; detail `id` and `RISK_ALERT` match | Native identity passed; implementation and CLI UAT pending |
| reference areas list / city | GET `/queryParaCity.json`, width 10, 17 pages: 161 arrivals / 144 distinct IDs / 161 reported; stable total, repeated records, no conflicting duplicate content | Deferred: complete coverage not proven |
| reference areas list / country | GET `/queryParaCountry.json`, width 10, 6 pages: 52 arrivals / 48 distinct IDs / 52 reported; stable total, repeated records, no conflicting duplicate content | Deferred: complete coverage not proven |
| pricing fee-orders list | GET `/getFeeOrderList.json`, August 1–31: 2 arrivals / 2 IDs / 2 reported; independent single-day and empty-day inquiries passed | Native bounded contract passed; implementation and CLI UAT pending |

The current strategy and risk parents remove their historical missing-parent
blocker, but list refresh must still never fetch details. Native detail callers
do not send tenant, task type or risk mode; local expected-type validation must
not invent those wire fields. Risk sub-events are a separate paginated inquiry
and are outside the single-object detail contract.

Areas retain their existing unsupported leaf. Deduplicating the observed pages
would not prove that missing records were acquired. Neither type is enabled,
no default all-types query is introduced, and province permission remains
untouched. Safe-partial policy does not waive the first-release completeness gate.

## Fee-order scope and semantics

The native Efficient Service caller sends top-level `tntInstId=GUAPW3SG` and a
JSON-string `feeOrderListQueryVO`, containing tenant, `beginDate`, `endDate`,
`timeZone=GMT+08`, `rowStart` and `pageSize=10`. Its envelope is
`resultFlag=true`, records `result.data`, total `result.count`.

The UI labels the date filter Service Date and provides Today and This Month
ranges. The accepted query is explicitly bounded to at most 31 calendar days.
Native YYYYMMDD service-date bounds are inclusive: August 4 and August 6 each
return 1/1 for equal start/end; August 4–6 returns 2/2; August 5 returns 0/0.
The full August query also returns 2/2. No broader fallback was attempted.
The fixed GMT+08 query setting is distinct from the naive source timestamps:
`serviceTime`, `gmtCreate` and `gmtModified` retain their native strings without
an inferred UTC offset or conversion. Capture time is not source business time.

The UI labels `feeAmount` as Fee (Pricing CCY), `pricingCurrency` as Pricing CCY,
`transAmount` as Transaction Amount, and `currency` as Currency. Decimal strings
and source values must retain precision. No valuation, aggregation or FX amount
is calculated. `id` identifies the fee order within the tenant; service date
defines the requested range. No status field was present in the sampled rows,
so the implementation must not invent one.

Fee orders are a new runtime leaf. Existing `pricing valuations list/get` remain
unsupported, with no alias, redirect or cache migration.

## Delivery evidence

Implementation, focused checks, independent review and registered CLI production
UAT are pending. Native investigations above are not substitutes for those gates.
No release/version change or issue closure has occurred.

## Sources

- [Historical batch C evidence](2026-10-04-liquidity-batch-c-gates.md).
- [Historical risk list evidence](2026-10-04-liquidity-issue88-release-gates.md).
- [Historical full probe inventory](2026-10-01-liquidity-live-probes.md).
- Current native bundle: strategy service offset 1532400, fund/product detail
  callers 11470680/11486370, risk service 1516510, risk detail caller 6951720,
  area caller 4194391, fee caller 5536517 and fee fields/date control 5538477/5551191
  (zero-based Unicode character offsets, not byte offsets).
