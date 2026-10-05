# Four bounded Liquidity lists: Batch F v0.1.0

Authoritative specifications: [#109](https://github.com/proletariat64/dogopencli/issues/109),
[#110](https://github.com/proletariat64/dogopencli/issues/110),
[#111](https://github.com/proletariat64/dogopencli/issues/111), and
[#112](https://github.com/proletariat64/dogopencli/issues/112).
Parent scope: [#72](https://github.com/proletariat64/dogopencli/issues/72).
The user requested one shared PR for these four otherwise independent tickets.
Implementation and UAT status are recorded in the
[acceptance report](../research/general/2026-10-05-liquidity-batch-f-acceptance.md).

## Shared behavior

All requests run through the verified inquiry transport on
`https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt`.
Only the methods, endpoints, fields and fixed values below are accepted.
Missing success flags, malformed containers, invalid identities, scope/echo
conflicts, authentication, permission and transport errors are hard failures.
They preserve prior captures and never become successful empty results.

Default list reads are offline. Explicit root refresh atomically publishes
the exact scope. Explicit `--live` never writes or falls back to saved data.
New schemas isolate these lists from prior placeholders and other captures.
Independent native details are acquired only through their existing explicit
commands, never by list refresh. Retention reuses
[ADR 0018](../adr/0018-liquidity-capture-store-and-retention.md), and quality
handling follows [ADR 0019](../adr/0019-usable-incomplete-acquisitions.md).

Native strings, numbers, nulls, empty strings and unknown business states
remain unchanged. No amount, ratio, currency, date arithmetic or business-rule
audit is added. Capture time never substitutes for a source timestamp;
unproven source timezone and boundary semantics remain unknown.
Synthetic fixtures and aggregate UAT evidence are public; real records,
account identifiers, tokens, cookies and profiles remain private.

## Risk SLA configuration summaries (#109)

`liquidity risk sla list` is settings with a snapshot profile. One JSON POST
`/api/risk/sla/slaConfigPageQuery.json` sends exactly `rowStart=0` and
`pageSize=5000`. Actual transport validation fixes both values. No new source
filter, offset paging or detail crawl is allowed.

The response requires top-level `success=true`, an object array `data.data`
and nonnegative integer `data.totalCount`. Completeness requires raw arrivals,
unique nonempty string `slaConfigId` values, and native total to agree.
Duplicates retain quality facts; conflicting projections fail. The native
`tntInstId` must match the application tenant. `version` is a native string
configuration version, separate from identity.

Only `slaConfigId`, `riskEventType`, `effectiveStatus`, `processStatus`,
`version`, `tntInstId`, `gmtCreate` and `gmtModified` are projected when
present. The empty-only observed `slaRuleVOList` is excluded. Rule levels and
notification recipients remain the independent detail contract.
Native count 0 with an empty array is a complete empty result; missing count
is a protocol failure. Safe incomplete coverage follows the default/strict
policy without changing historical small-page behavior.

## One-account/day forecast accuracy (#110)

`liquidity forecast accuracy list --account ACCOUNT --record-date YYYY-MM-DD`
is runtimes with a history profile. Account and record creation query date
are required. The native GMT Create Date/Time control does not establish a
source timezone, and `valueDate` may differ from the query date.

The base GET `/bankCashForecastRecordAccuracyQuery.json` sends only outer
`tntInstId` and JSON-string `bankCashForecastRecordQueryVo`. Its VO has fixed
tenant, `rowStart=0`, `pageSize=5000`, single-element `aliasName`, query date
mapped to both `valueStartDay`/`valueEndDay` as YYYYMMDD, and fixed
`recordStartTime=000000`/`recordEndTime=235959`.
It requires `resultFlag=true`, `result.success=true`, object array
`result.dataValue` and nonnegative integer `result.count`. Identity is native
nonempty string `id`; account alias echo must match.

Every base row binds one GET `/cashFlowDetailDay.json` through outer tenant
and JSON-string `bankAccountDetailCashFlowQueryVO`. The VO binds source
`valueDate`, `accountNo`, `instId`, `currency`, `bankId`, `forecastRecordId=id`,
`aliasName=bankAccountAliasName` and `forecastBalance`. Only native string
`0.0`/`0.00` becomes request string `0`; public values remain unchanged.
Metric success requires `resultFlag=true`, `result.success=true`, and object
`result.bankAccountDetailDayVO`. Association is native request binding;
the CLI does not fabricate a backend record echo.

The base projection is `id`, `bankAccountAliasName`, `currency`, `valueDate`,
`baseValueDate`, `recordCreateTime`, `forecastBalance`, `cashFlowTransIn`,
`cashFlowTransOut`, `forecastTaskId`, `forecastBatchNo`, and `forecastRuleId`.
Nested `accuracy` preserves `cashFlowAccuracy`, `cashFlowInflow`,
`cashFlowOutflow`, `flowAccuracy`, `inflowAccuracy`, `outflowAccuracy`,
`realTrafficAmount`, `realizedBalance`, `realizedInflow`, `realizedOutflow`,
and `trafficForecastAmount`. Request-only account numbers and binding fields
are excluded from public records and the capture.

The client permits at most 100 base rows per scope and shares one query
deadline across the base and all metric requests. Incomplete base coverage
or an over-budget base fails with INCOMPLETE_RESULT before metric fan-out,
with no candidate data or publication. Any required binding or metric failure
is hard failure. Base-only rows are never accuracy records. A complete empty
base performs no metric requests. Exact tenant/account/query-date scopes do
not merge or fall back across accounts or dates; query date does not establish
dated business coverage.

## Explicit-account capacity (#111)

`liquidity risk account-capacity list --account ACCOUNT [--account ACCOUNT]`
is runtimes with a history profile. The client requires 1–10 distinct nonempty
aliases, canonicalizes their sorted set, and queries each in deterministic
order. The display `--all` flag never discovers additional accounts.

Each GET `/api/fund/capacity/queryFundCapacityByAliasName.json` sends only
`aliasName`. Top-level `success=true`, object `data`, and exact nonempty alias
echo are required. One source object is one account row; no synthetic ID is
added. Complete means one validated object per requested alias.
`requested_count` and `resolved_count` describe the client scope;
`reported_total=null` reflects absence of a native global total.
Any failed account rejects the whole candidate and preserves prior capture.

The ten projected native fields are `aliasName`, `currency`,
`accountAvailableBalance`, `availableIod`, `availableResource`,
`cashPoolSupportAvailableResource`, `outFlowCapacity`, `totalIod`, `usedIod`,
and `valueTime`. Native UI labels `availableResource` as Outflow Capacity;
the meaning of `outFlowCapacity` and `cashPoolSupportAvailableResource`
remains unknown. These fields are separate and never substitute for one
another. `valueTime` remains a raw source string with unknown timezone.

## TARGET_RFQ subtasks (#112)

`liquidity investment rfqs list --from-date YYYY-MM-DD --to-date YYYY-MM-DD`
is runtimes with a history profile. Paired dates are mandatory and ordered.
One JSON POST `/rfq/subInquiryTask/querySubInquiryTask.json` sends exactly
`rowStart=0`, `pageSize=5000`, `inquiryType=TARGET_RFQ`,
`inquiryStartDate` and `inquiryEndDate` as YYYYMMDD. Fixed values are enforced
in the shared transport. No alternative inquiry type or additional filter
is exposed.

The response requires top-level `success=true`, object array `data.data`
and nonnegative integer `data.totalCount`. Completeness requires raw arrivals
= unique nonempty string `inquirySubTaskId` = reported total. Every row must
echo TARGET_RFQ. `inquiryTaskId` is a parent reference, so distinct subtasks
sharing a parent remain separate. Conflicting subtask projections fail;
duplicates and undercoverage remain explicit quality facts.

Projection preserves `inquirySubTaskId`, `inquiryTaskId`, `inquiryType`,
`productType`, `currency`, `tenor`, `redemptionFeature`, `inquiryStatus`,
`quotationStatus`, `winStatus`, `quotedNum`, `inquiryNum`, `winNum`,
`inquiryStartTime`, `inquiryEndTime`, `modifyTime`, and `processStatus`.
Counts are not recalculated. Source times do not inherit the separate
investment-quotes timezone. Exact type/date scopes are isolated without
offset paging, cross-type recovery or parent/session derivation.
Explicit successful empty array with count 0 is complete; backend 099 is
a failure. FULL_RANGE_RFQ remains excluded.
