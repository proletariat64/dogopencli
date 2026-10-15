# R06 native inquiry qualification

Observed: 2026-10-16
Scope: general
Status: snapshot

Date: 2026-10-16. Scope: issue #191's eight inquiry leaves.

This report records native frontend source inspection and authenticated,
inquiry-only requests through an isolated headless browser. It does not establish
public CLI UAT, cache behavior, or release acceptance. No authentication material
or production rows are included. The research target was closed after inspection;
the dedicated Chrome process and existing payment target were preserved.

## Native callers

The inspected page was
`https://iliquidity.alipay.com/GUAPW3SG/menu/DemandsDetails`. Its deployment was
[`S090011940898/umi.js`](https://gw.alipayobjects.com/render/p/yuyan/180020010000002482/S090011940898/umi.js).
Module numbers and minified symbol names identify that deployment only.

Module `25572` implements F01–F04, D01, D02, and D03 as direct, flat JSON POSTs
with `Content-Type: application/json;charset=utf-8` and `JSON.stringify(z)`.
There is no nested VO wrapper or stringified VO field. These callers do not add
`tntInstId`; the inspected inquiries succeeded without that payload field.

- Forecast component `Sgt` maps scalar `aliasName`, optional scalar `entity` and
  `bankId`, and `startDate`/`endDate` formatted as `YYYYMMDD`. The UI labels this
  range **Forecast Date**. Initial `rowStart` is zero; native page widths are
  T0/T3/Daily 10 and Hours 24.
- D01 and D02 use helper `Ko.hG`, which preserves scalar `entity`, `bankId`, and
  `aliasName`, formats `valueDate[0:2]` into `startDate`/`endDate`, converts provided
  amount bounds to strings, and adds `rowStart=0,pageSize=10`. Their range label
  is **Expect Value Date**. The D02 form requires entity and alias.
- D03's Fund Demands chart caller sends scalar `aliasName`, a single date as
  equal `startDate`/`endDate`, and optional `fundActionTypes=[code]`. This caller
  does not add entity/bank fields. A direct request including the resolved
  `entity` and `bankId` also succeeded. The separate Initiative Cashflow chart
  resolves entity from its account directory; it is not the D03 source.

All seven list/statistics requests returned HTTP 200 with `success=true` for the
same known account and resolved entity/bank context on `20261015`. F01–F04,
D01, and D02 return rows in `data.data` with `data.totalCount`; D03 returns an
array directly in `data`.

## F02: T3 Forecast

The week `20261009`–`20261015` returned a stable total of 42. Native page width
10 produced `10+10+10+10+2+0` rows at requested offsets
`0,10,20,30,40,42`; the response echoed these offsets. The final request was an
independent empty termination probe. A repeated first page matched every field
and its order.

All 42 tuples `(aliasName,forecastDate,expectValueDate,fundActionType,dateFlag)`
were distinct, with no null or blank dimensions. This is an observed business
identity within the qualified account/date scope, not a native ID guarantee.
Keeping entity, bank, and currency in the normalized identity further scopes
records across account contexts; source creation time need not manufacture an ID.

Observed fields were strings: `accountType`, `aliasName`, `amount`, `bankId`,
`currency`, `dateFlag`, `entity`, `expectValueDate`, `forecastDate`,
`fundActionType`, `gmtCreate`, `inflowAmount`, `outflowAmount`, and `timeZone`.
Both range endpoints and all seven intervening forecast dates were represented.
A single-day forecast-date request for `20261015` returned expected value dates
`20261016`, `20261019`, and `20261020`. These are different business dates.
`gmtCreate` used `YYYY-MM-DD HH:mm:ss`; the sample's `timeZone` was
`Europe/London`. The evidence does not assign a timezone to a naive timestamp or
establish the backend's timezone conversion rule for range predicates.

## D01: Fund Demands

The single expected value date `20261015` returned 33,977 rows. Native page width
5,000 produced six full pages, a 3,977-row tail, and an empty terminal request at
offset 33,977. The total remained 33,977. All native `id` values were nonblank
strings and distinct across the complete result. `originalBizNo` was also
distinct in this sample; it is preserved separately and is not assumed to be a
permanently unique global identifier.

**The response's `rowStart` was zero on every D01 page**, including later pages
and the empty terminal response. Response `pageSize` remained 5,000. D01 coverage
therefore uses requested offsets, progressing native identities, stable totals,
and terminal evidence; it cannot require a trustworthy echoed offset. This
exception is specific to the observed D01 contract.

Observed fields were strings: `accountType`, `aliasName`, `amount`, `bankID`,
`bookId`, `businessCategory`, `businessEntity`, `completionTime`, `currency`,
`demandsStatus`, `effectiveness`, `entity`, `expectValueDate`, `expectValueTime`,
`fundActionType`, `fundDirection`, `id`, `localCrossBorder`, `originalBizNo`,
`receivedTime`, and `timezone`. Native `bankID` has uppercase `ID`.
`expectValueDate` was `YYYYMMDD`; `expectValueTime`, `receivedTime`, and
`completionTime` were full `YYYY-MM-DD HH:mm:ss` strings. Every row's expected
value date matched the single requested day. The sample used `Europe/London`,
directions `inflow`/`outflow`, and demand statuses `SUCCESS`/`NO_NEED_PROCESS`.
These demand statuses do not establish bank execution success.

## D02: Initiative Cashflow

The range `20261014`–`20261015` returned a stable total of 6,127. Native page
width 5,000 produced `5000+1127+0` rows at requested and echoed offsets
`0,5000,6127`. A repeated first page matched every field and its order. Both
inclusive expected value dates were represented.

All 6,127 tuples `(bankAccountAliasName,bankAccountFlowDateSourceTypeStr,
originalBizNo,expectValueDate,expectValueTime,currency)` were distinct and their
dimensions nonblank. The sample spans two dates and three source codes:
`SETTLE_INSTRUCTION`, `ILIQUIDITY_TRANSFER_ORDER`, and `EXCHANGE_INSTRUCTION`.
This supports a scoped composite identity with duplicate/conflict detection. It
does not prove perpetual uniqueness across every account, source, or date.

All 6,127 rows had null `bankAccountFlowDateSourceType`, blank
`expectValueDateTime`, and no `receivedTime` key. The source code was populated
in `bankAccountFlowDateSourceTypeStr`. The frontend expanded-row label
**Received Time** renders `receivedTime || gmtCreateStr`; the CLI must retain
the actual returned source fields rather than synthesize `receivedTime`.

Observed string fields were `accountType`, `amountStr`,
`bankAccountAliasName`, `bankAccountFlowDateSourceTypeStr`, `bankAccountNo`,
`bankId`, `currency`, `entity`, `expectValueDate`, `expectValueDateTime`,
`expectValueTime`, `extBizType`, `fundDirection`, `gmtCreateStr`,
`gmtModifiedStr`, `originalBizNo`, `status`, `subBizType`, and `timeZone`.
`gmtCreate`/`gmtModified` were null. `expectValueTime`, `gmtCreateStr`, and
`gmtModifiedStr` used `YYYY-MM-DD HH:mm:ss`; `expectValueDate` used `YYYYMMDD`.
The sample's `timeZone` was `Europe/London`.

`amount` is an object: `amount`, `cent`, and `centFactor` are native JSON
numbers; `currency`, `currencyCode`, and `currencyValue` are strings. Preserve
the shared parser's decimal handling and the exact `amountStr`. Research used
JavaScript only to inspect metadata, not to export numeric business values.

## S01: account strategies

The default request `{pageSize:5000,rowStart:0}` returned 1,897 rows and total
1,897. An independent request at `rowStart=1897` returned an empty array with
the same total and echoed offset/page width. All observed
`(aliasName,currency,version)` tuples were distinct in this default scope.
`version` was a native number. This is a version-scoped identity observation,
not proof that the default view contains all historical or approval versions.
No status or extra version query was made in this research.

Observed string fields were `accountType`, `aliasName`, `bankId`,
`coverAlgorithm`, `currency`, `entity`, `lastModifiedTime`, `lastOperator`,
`needProcessId`, `operationStrategy`, `operationType`, `processId`,
`processMemo`, `processStatus`, and `status`. Preserve configuration status,
approval status, version, and strategy display text as separate source facts.

## Leaves that remain gated

- **F01, F03, F04:** the known-account single-day inquiries returned successful
  zero totals. A bounded search using three additional accounts with T0 strategy
  configuration over `20260916`–`20261016` also returned zero on all three
  endpoints. This proves scoped successful emptiness only. Independent nonempty
  structures, field types, business identities, date/timezone semantics, and
  progressing pagination/termination contracts remain unqualified. Do not copy
  T3's schema or identity to enable these leaves.
- **D03:** the single-day response contained 96 distinct `statisticalDate`
  labels from `00:00` through `23:45`; all four fields (`statisticalDate`,
  `inflowAmount`, `outflowAmount`, `totalAmount`) were strings. The frontend plots
  returned values without accumulation or resampling. Native interval edges,
  cumulative-versus-interval meaning, timezone, included demand statuses, and
  zero/missing-slot rules remain unproved. The array does not establish
  pagination or equality with a sum of D01 rows. Keep execution gated until
  these semantics are verified.

### Final bounded discovery attempt

A separate native research probe omitted both alias and entity for
`20261010`–`20261016`, with only `startDate`, `endDate`, `rowStart=0`, and the
native first-page width. Exactly one request was sent to each endpoint:

| Leaf | Page width | HTTP | Business result | Observed rows |
| --- | --- | --- | --- | --- |
| F01 `/dailyForecastList.json` | 10 | 200 | `success=true,totalCount=0` | 0 |
| F03 `/hourlyMaxForecastList.json` | 24 | 200 | `success=false,errorCode="001"` | No successful list |
| F04 `/dailyMaxForecastList.json` | 10 | 200 | `success=true,totalCount=0` | 0 |

No rows or candidate account identities were returned, and no broader discovery
was attempted. The F03 business failure is not a successful empty response.
These probes do not change the product CLI's required single-account contract.

D03's deployed source was inspected again: the **Intraday Trend- Demands Amount**
chart uses a single **Expect Value Date**, optional fund-action selection, and
the direct statistics service in module `25572`. It supplies no authoritative
interval, timezone, inclusion-status, or missing-slot definition. A graph-first
knowledge-base lookup followed by a literal check of the Liquidity documents
found no matching endpoint, `statisticalDate`, intraday chart label, or
fifteen-minute contract. This bounded search did not resolve D03's semantic gates.

These native observations must be followed by separate public CLI UAT for each
enabled leaf, including live/refresh/offline behavior, quality metadata, and
cache publication boundaries. Samples are not universal nullability guarantees
or backend performance SLAs.
