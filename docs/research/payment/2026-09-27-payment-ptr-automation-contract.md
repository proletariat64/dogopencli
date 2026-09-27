# Payment PTR automation-batch contract investigation

Observed: 2026-09-27
Scope: payment
Status: snapshot

## Outcome

The automation-batch list contract for
[#68](https://github.com/proletariat64/dogopencli/issues/68) now has independent
nonempty native evidence and complete, repeated acquisition of an explicit date
window. This report records the verified list subset and the remaining limits.
`get` remains deferred: the native Details view queries child cases and receives
parent summary values from its navigation URL, rather than querying an
independent parent detail representation.

## Established evidence and provenance

The [shared native discovery](2026-09-27-payment-ptr-contract-discovery.md)
records the following direct observation:

- Wrapper: `https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/productPTRManagement/autoFlowManagement`.
- Native inquiry: `POST https://iglobalfundcontrol.alipay.com/api/ptr/auto-batch/query`.
- JSON request contains integer `pageNo` and `pageSize`.
- Response contains `success`, `pageNo`, `pageSize`, `totalCount`,
  `resultDataList`, `errorContext`, `permissions`, `showButton` and
  `sofaTracerId`. Ten rows were observed; this does not prove total coverage.
- Sample row: string `batchId`, `batchStatus`, `approvalStatus`; integer
  `batchDate`, `caseCount`, `approvedCaseCount`, `orderCount`.
- Native labels: Batch Date, Batch number, Batch Status, Test Case Name,
  Outflow channel, Debit account, Clearing network, Payment Currency,
  Receipt Currency, Approval Status and Batch Approver.
- Details and Approval are separate controls. Approval was not invoked.

These observations initially came from the shared investigation. A resumed
independent session reproduced them and added the evidence below.

## Bounded follow-up

Follow-up used the repository's existing CDP helper on port 9222 under
`inquiry_session(config_file=config_path())`, retaining the profile coordination
lease and authentication probe. It created and closed only its own temporary
target. It did not launch or switch Chrome, touch authentication, invoke
approval, run PTR, create a batch, or modify configuration.

The first attempt passed the shared authentication probe and reached the expected
wrapper origin, but the observed page had no form labels, buttons, inputs or
table headers. No automation query was captured. A second attempt failed before
the research target was created: the shared readiness probe remained
`readyState=loading`. A bounded retry failed in the probe's `Page.navigate` with
a CDP websocket timeout. These are runtime access failures; neither establishes
expired authentication, absent automation data or denied inquiry permission.

No response rows, cookies, headers, tokens or request identities were persisted.
Only sanitized structural observations are recorded here.

## Decisions pending contract freeze

The table below preserves the initial gaps. The later verification section
supersedes entries explicitly resolved there; unresolved claims remain deferred.

| Area | Decision and remaining evidence |
| --- | --- |
| Object identity | `batchId` is a candidate string identity. Unique/nonempty identity across all pages and repeated reads remains unverified. Do not equate this resource with patrol batches or execution tasks. |
| Date scope | `batchDate` is an integer in a sample, not proof of milliseconds, timezone or filter semantics. Native default range, backend start/end keys, inclusive/exclusive bounds and hidden window remain unverified. No `all` cache scope may imply complete history. |
| Pagination | Page origin, accepted size, stable ordering, total semantics, final/overrun page, repeated-page identity and cross-page overlap remain unverified. Ten observed rows cannot establish a complete snapshot. |
| Status | Preserve distinct `batchStatus` and `approvalStatus`. No enum inventory, transition model or derived success verdict is frozen. |
| Counts | `caseCount`, `approvedCaseCount`, `orderCount` are separate observed aggregates. Their denominators and relationships require evidence; do not infer equality or child completeness. |
| Filters | Batch ID/status, approval status, date and native association labels remain candidates. Backend mapping, returned fields and exact matching rules are unverified. Defer every public filter until independently evidenced. |
| Details | **Defer `get`**. A Details control alone does not establish an independent inquiry endpoint, parent identity or complete child pagination. Do not expose a list summary as detail. |
| Direction | Placement under payment and labels referring to outflow are insufficient to prove API direction isolation. Verify native fixed direction or returned-object semantics before implementation. |
| Failures | Successful envelope structure does not prove business rejection, permission, authentication or empty-scope envelopes. Do not interpret mere `errorContext` presence as failure. |
| Cache | Source `sources.payment_ptr_automation_batches` and capability `payment.ptr.automation_batches.list` remain naming candidates. No namespace/scope or freshness policy is frozen without a verified bounded history contract. |

## Next verification

After a healthy serial authentication probe, retain one coordinated inquiry
session and capture a native Batch Date query. Observe the exact date fields and
native page changes before replaying the already observed query. Verify a
bounded nonempty range end-to-end, repeat the acquisition, and compare counts,
identities and versions without logging row values. Inspect only the distinct
read-only Details control, if available, to decide whether detail can be included.
Do not invoke Approval or create a sample batch to fill evidence gaps.

The acceptance gate remains a current native contract, not historical Graphify
or LLM wiki descriptions. Those sources establish neither automation-batch API
semantics nor equivalence to patrol objects.

## Resumed native and deployed-source verification

After access recovered, one coordinated inquiry session retained its own native
target for list, date-window, pagination and Details investigation. Native list
load and Query produced `POST /api/ptr/auto-batch/query` with JSON
`{"pageNo":0,"pageSize":10}`. Date inputs were empty. The page rendered directly
in the wrapper, with browser timezone `Asia/Shanghai`.

The page's already-loaded deployed source was inspected to identify parameters;
no parameters were derived from historical database names. The relevant asset
base was
`https://renderoffice-intl.alipayobjects.com/p/yuyan/180020010001251366/`:

- `10f3c34a-async.16d6f7d5.js`: batch list, `rowKey:"batchId"`, native request
  `pageNo=(current||1)-1`, default `pageSize=10`, `dateFormatter:"string"`.
- The Batch Date column uses `valueType:"dateRange"` and transforms its value
  into `batchDateStart:t[0], batchDateEnd:t[1]`. It does not add a direction
  parameter or a default date window.
- `6d3c298e-async.8df13353.js`: Details query adds the parent `batchId` to child
  filters and uses the same zero-based page conversion.

Date-range controls were inspected, but synthetic DOM clicks did not complete
both native range fields. The date keys therefore have **deployed-source plus
successful endpoint replay evidence**, not a captured native date-filled
request. This distinction is intentional.

## Verified bounded list acquisition

The exact source-derived request was replayed with
`batchDateStart:"2026-09-01"`, `batchDateEnd:"2026-09-27"`, `pageSize:10`.

| Page | Returned page | Returned size | Envelope total | Rows |
| --- | --- | --- | --- | --- |
| 0 | 0 | 10 | 11 | 10 |
| 1 | 1 | 10 | 11 | 1 |
| 2, overrun | 2 | 10 | 11 | 0 |

The two data pages contained 11 distinct, nonempty string `batchId` values and
no cross-page overlap. A complete second acquisition of both pages reproduced
all row values in the same order and the same total. The sampled order was
descending by `batchDate`; this is an observation, not a guaranteed secondary
sort for equal dates.

All returned timestamps fell within the requested Shanghai calendar window.
A query with start=end equal to the latest observed batch's calendar date
returned that real, non-midnight batch. Partitioning the original scope into
dates before that day and dates from that day returned 10 and 1 rows, with
timestamp checks respecting the partition and totals summing to 11.

This supports inclusive date-only calendar bounds for the sampled records.
There were no exact-midnight boundary samples establishing the server's timezone
independently of the browser. Do not claim that timezone ambiguity has been
tested away. Timestamps are interpreted by the deployed UI through its ordinary
date formatter; the browser used Asia/Shanghai.

Use explicit bounded dates in the acquisition scope and cache identity. The
timezone component of the namespace must remain unfrozen until proven.
No unbounded `all` scope is justified by this research. Retain page size 10 until
other native-supported sizes are verified. Collect all pages, reject changed
totals, duplicate IDs, missing IDs and premature termination, and compare a
second complete pass before publication. This cannot promise a transactionally
atomic server snapshot; active batches can change during acquisition.

## Verified rows, filters and empty envelope

The union of list fields in this window was:

| Field | Observed type and meaning boundary |
| --- | --- |
| `batchId` | String; unique within both complete acquisitions |
| `batchDate` | Integer timestamp, rendered as a date/time by native UI |
| `batchStatus` | String; independent of approval status |
| `approvalStatus` | String; independent of execution status |
| `caseCount` | Integer; requested-case aggregate |
| `approvedCaseCount` | Integer; approved-case aggregate |
| `orderCount` | Integer; document aggregate |
| `approvalTime` | Optional integer timestamp |
| `approver` | Optional string; personal identifier, omit from default output |

Native enum inquiry `/api/ptr/auto-batch/enums` returned batch statuses
`UNPROCESSED`, `EXECUTING`, `COMPLETED` and approval statuses `PENDING`,
`APPROVED`, `REJECTED`. The scoped rows included UNPROCESSED/EXECUTING and
PENDING/APPROVED. Preserve server strings rather than restricting future values
to this observed inventory.

Replays of source-grounded `batchId`, `batchStatus:EXECUTING` and
`approvalStatus:APPROVED` matched the corresponding exact local subsets of the
complete 11-row scope. Include these as whole-value local filters, with repeated
values OR and separate fields AND, so cached and live filtering share semantics.
Date inputs define acquisition scope rather than a post-acquisition business
filter.

Defer case name, channel, account, network and currency filters: the native UI
supports association filtering but those associations are not present in the
batch summaries. Adding server-only filters would break whole-scope cache/live
equivalence without a separately evidenced child model. Defer approver filtering
pending identifier/sensitive-output policy; its native transform uses
`operatorName` when supplied a selected user object.

A bounded empty query for `2099-01-01` returned business success, `totalCount:0`,
`pageNo:0`, `pageSize:10` and **no `resultDataList` property**. This is not null
or an empty array. The response otherwise contained `errorContext`,
`permissions`, `showButton` and `sofaTracerId`. An implementation may normalize
an absent list only in this verified successful zero-total envelope; missing
rows with a positive total must fail. This is a filtered empty range, not proof
the complete production resource is empty.

## Native Details and direction boundary

Only the distinct Details button was clicked. It navigated to
`autoFlowManagement/ptrBatchDetail`; the list source passes parent `batchId`,
`batchDate`, `approvalTime`, `approver` and `batchStatus` in navigation parameters.
The child page natively loaded `POST /api/ptr/auto-batch/case/query` and
`/api/ptr/auto-batch/case/filter-options`. No Approval control was clicked.

A child query for a parent with `caseCount:2` returned `totalCount:2` and two
rows. Children have their own string `id`, case identity/name/type/attribute,
outflow institution, debtor/creditor account aliases and currencies, clearing
network, capability/verification fields, `executeStatus`, `disposalResult`, and
create/modify timestamps. They **do not contain a parent `batchId` echo** in the
sample. The first selected zero-case parent produced a successful zero-total
child result with the list omitted.

All 11 sampled timestamps had UTC hour 01, which is hour 09 in Shanghai.
Neither the same-day query nor the partition distinguishes UTC from Shanghai
midnight semantics. Browser timezone must not become a server timezone claim.

These facts support an outflow automation-case workflow distinct from patrol
batches. There is no native direction argument to fix, and sampled child fields
and page labels consistently describe outflow. Shared-backend exclusion of every
possible inflow record is not independently proven. Sampled children contain no
direction, `inOrOut` or `fundOut` discriminator and no nested outflow baseline
object; debtor/creditor fields alone do not prove direction. Do not invent a direction
parameter. Preserve this dedicated endpoint's resource identity rather than
joining it with collection PTR data.

**Defer `get` and child commands.** No independent parent detail endpoint was
observed, parent summary values come from the URL, child parent identity is not
echoed, and full child pagination across all parents was not established.
Counts must remain separate server aggregates; this single two-case example
does not prove their formulas generally.

## Remaining release decisions

Keep #68 `needs-info`: **server date timezone and structural payment-direction
isolation remain release blockers**. The partial list evidence does not waive
those explicit issue requirements. Prove those boundaries before freezing the
bounded-range CLI/cache policy and recording include/defer choices in the
issue. Business failure/authentication/permission envelopes were not induced;
test those with sanitized synthetic fixtures and the existing shared transport.
No live mutation should be used to create failure or transition examples.
