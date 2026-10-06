# Batch H rule-status native contract and first-enable evidence

Observed: 2026-10-06
Scope: general
Status: snapshot

Batch H (spec issue #122) enables `liquidity operations rule-status list` as
one bounded single-response native list over the TransferRunOverview summary
inquiry. This note records the verified contract behind the enablement; only
fixed inquiry contract evidence and aggregates appear here, never raw
production rows or authentication values. Production CLI UAT remains a
separate serial acceptance step on the authorized profile.

## Native inquiry

- GET `/queryTransferRulePreRunRecords.json` on `iliquidity.alipay.com`.
- Outer fields: `tntInstId` and the JSON-stringified
  `transferRuleRecordQueryRequesVO` (the misspelled native key is kept
  exactly).
- Inner VO fields: tenant, `rowStart`, `pageSize`, string
  `queryDetailed="false"`, `triggerStartTime`, `triggerEndTime`
  (`YYYY-MM-DD HH:mm:ss`, the source date-picker serialization), and empty
  `executeStatusList`/`createdOrderList`/`orderStatusList`.
- The summary handler consumes `result.data` with `result.count` as the
  total under outer `resultFlag` and inner `result.success`.
- The expanded-record action (`queryDetailed="true"` plus `ruleId`) is a
  different native projection and stays unsupported, as does any getter.

## Verified scope and time convention

- Expected trigger time is the scope dimension; the native renderer is
  explicitly UTC (`momentFormatTimeUtc`), and point probes with adjacent
  empty seconds agree with inclusive UTC wire timestamps.
- Public bounds `--trigger-from`/`--trigger-to` are both required,
  `YYYY-MM-DD HH:mm:ss` UTC, inclusive; equal endpoints select one exact
  second. Missing, malformed or reversed bounds are rejected before any
  browser access.
- All observed timestamps are integer epoch milliseconds; they are preserved
  losslessly (raw integers) and documented as UTC. `realTriggerTime` was
  null in 101 of 194 populated rows and stays null.

## Bounded single-response acquisition

- One fixed request only: `rowStart=0`, `pageSize=5000`. No offset loop, no
  dedupe across pages, no fallback to the accumulated-page experiment.
- The pageSize-30 experiment produced 194 arrivals but only 193 unique IDs
  at count 194; cross-page ordering is unstable, so the contract is one
  counted bounded response.
- Hard gates before output or publication (strict rejection, not usable
  incomplete): outer `resultFlag` true and inner `success` true; data a
  record array; `count` a nonnegative native integer no greater than 5000;
  returned rows and unique native IDs both equal `count`; count 0 requires
  an empty array; every row passes tenant and expected-trigger bounds;
  every native `id` is a positive integer (booleans excluded) whose public
  identity is the canonical lossless string form.
- Overflow, shortfall, extra rows, missing or invalid counts and duplicate
  identities fail and advise narrowing the trigger range; prior cache bytes
  are preserved. A genuinely empty verified scope publishes a truthful
  zero-row capture.

## Approved projection

Projected fields: `id`, `ruleId`, `executeStatus`, `createdOrder`, `bizNo`,
`orderStatus`, `expectTriggerTime`, nullable `realTriggerTime`, `gmtCreate`
and `gmtModified`. Runtime statuses stay raw native values: observed
`executeStatus` values were `EXECUTED`, `NON-EXECUTION` and
`PRE_CONDITION_BLOCK`; `createdOrder` was `Y`/`N`; `orderStatus` included
empty, `INIT`, `PAID` and `PAYMENT_FAILURE`. Empty payment references are
valid non-payment records and never establish identity.

Excluded: `debitAmount` (units unestablished), account aliases and numbers,
rule-name and business-type free text, `expectTriggerDate`, operators,
environment/workflow metadata, nested task/order references and the
expanded detail projection.

## Fresh native evidence, 2026-10-06

| Native scope | Page size | Outer / inner success | Rows / count | Unique native IDs |
| --- | ---: | --- | --- | --- |
| 2026-10-06 initial UI query | 10 | true / true | 0 / 0 | 0 |
| 2026-01-01 00:00:00 through 2026-10-06 23:59:59 | 5000 | true / true | 194 / 194 | 194 |
| Same year scope | 1000 | true / true | 194 / 194 | 194 |
| Same year scope, one-shot repeat | 5000 | true / true | 194 / 194 | 194 |
| January 2026 | 5000 | true / true | 150 / 150 | 150 |
| Equal UTC start/end at an observed expected trigger | 5000 | true / true | 4 / 4 | 4 |
| Equal points one second before / after | 5000 | true / true | 0 / 0 | 0 |
| 2026-10-06 explicit large-page query | 5000 | true / true | 0 / 0 | 0 |

The expanded single responses were equal ordered arrays; every populated
record had a unique positive integer native `id` and matching tenant.
`ruleId` was unique in this sample but is not the record identity; `bizNo`
had 57 distinct values and may be empty.

## Cache behavior

Independent history-profile captures keyed by the exact
profile/tenant/trigger scope plus the pinned contract (ADR 0016). Refresh
publishes only fully validated responses; live inquiries never write cache
bytes; transport, authentication, business and schema failures preserve
prior bytes; offline list output equals the published capture. ADR 0019
does not lower these first-enable gates.

## Remaining acceptance

Serial production CLI UAT is still pending on the authorized isolated
profile: known nonempty expanded scope, successful empty current-day scope,
equal-endpoint point scope, disconnected offline equality, live no-write
and failure/cache preservation. Research probes are not command acceptance.
