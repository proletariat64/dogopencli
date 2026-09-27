# Payment PTR order bounded-inquiry contract investigation

Observed: 2026-09-27
Scope: payment
Status: snapshot

## Outcome

[#64](https://github.com/proletariat64/dogopencli/issues/64) now has native
two-bound date-query evidence, experimentally verified Shanghai wall-time
interpretation, and three identical complete first-page acquisitions of a
27-day scope. Ordinary page traversal is unreliable. A release contract must
use an independently verified fixed first-page cap and reject overflow rather
than treating page traversal as complete.

Exact equality at a second boundary remains unobserved: all 104 sampled
modification timestamps contain fractional milliseconds. Do not silently claim
inclusive or exclusive equality from the experiments below. `get` was not
investigated and remains deferred.

## Native request and deployed-source evidence

The native iframe was
`https://igfc.alipay.com/receivedPayment/receivedPaymentPtr/productTrialOperationQuery/productTrialOperation`.
Its observed inquiry is
`GET https://iglobalfundcontrol.alipay.com/api/ptr/manage/query.json`.
Browser authentication parameters are deliberately omitted here.

The initial request contained `pageSize=10`; the response echoed `pageNo=0`,
`pageSize=10`, `totalCount=5923` and ten rows. Search added explicit `pageNo=0`.
The form exposes independent `modifiedTimeBegin` and `modifiedTimeEnd` inputs.
Both date-picker calendar and confirmation controls were used; the resulting
native request included:

```text
modifiedTimeBegin=2026-09-01 13:13:57
modifiedTimeEnd=2026-09-27 13:14:20
pageNo=0
pageSize=10
```

The inputs visibly show only dates, but their requests retain the selected
time-of-day. Date-only visual inspection would therefore misstate the scope.

Already-loaded deployed asset
`https://renderoffice-intl.alipayobjects.com/p/yuyan/180020010001284234/1867c91c-async.baf0774b.js`
confirms both `handleSearch` values are formatted with
`YYYY_MM_DD_HH_mm_ss`. Its modification-time column binds to `gmtModified`.
Its page-change handler sends `pageNo=current-1`; native size options are
10, 20, 30, 40 and 50. No date default is added by this component.

Research ran under `inquiry_session(config_file=config_path())` and its shared
profile coordination. Follow-up fetches retained the observed endpoint and
authentication in memory and used 90-second AbortSignal limits. No PTR launch,
verification, manual correction, approval, export or configuration action was
invoked. Raw rows and identifiers stayed in process/browser memory.

## Bounded acquisition and pagination failure

The observed request keys were replayed for the explicit scope
`2026-09-01 00:00:00` through `2026-09-27 23:59:59`.
This is a research interval, not a claim that 23:59:59 includes the final
fractional second of a calendar day.

| Page size | Page number | Envelope total | Actual rows |
| --- | --- | --- | --- |
| 10 | 0 | 104 | 10 |
| 10 | 1 | 104 | 10 |
| 10 | 2, 3, 4, 5 | 104 each | 0 each |
| 50 | 0 | 104 | 50 |
| 50 | 1, 2 | 104 each | 0 each |

The first two size-10 pages contained 20 unique identities, but early empty
pages contradict the reported total. Source-confirmed page numbering therefore
does not prove reliable server pagination. Do not deduplicate, stop on empty,
or merge partial pages and declare the scope complete.

Experimental first-page sizes were then tested against the same bounded scope:

| Request | Echoed size | Total | Rows | Unique `ptrOrderId` |
| --- | --- | --- | --- | --- |
| page 0, size 200 | 200 | 104 | 104 | 104 |
| page 0, size 500 | 500 | 104 | 104 | 104 |
| repeated page 0, size 500 | 500 | 104 | 104 | 104 |

All three complete result arrays were byte-equivalent after parsing to the same
JSON representation, including order and field values. Every row had a nonempty
outflow baseline object `productionTrialRunFundOutAbilityVO`; every
`gmtModified` fell within the scope interpreted as Shanghai wall time.

A prospective implementation may restrict acquisition to two complete
`pageNo=0,pageSize=500` reads, requiring exact pagination echoes,
`len(rows)==totalCount<=500`, unique nonempty IDs, valid projected fields and
identical retained content. Overflow or drift must fail and preserve prior
cache. There is no verified pagination fallback. The bound on days is a product
safety policy, not evidence that every 31-day interval fits 500 rows.

## Timezone and timestamp-boundary experiments

Two distinct real rows were selected from this scope. For each, the same narrow
window around its `gmtModified` epoch was formatted in UTC and then UTC+08:00
using the native timestamp format. Only aggregates and identity membership
booleans were recorded:

| Candidate | Formatting of approximately ±1-second window | Total/rows | Contains exact candidate ID |
| --- | --- | --- | --- |
| A | UTC | 0/0 | No |
| A | UTC+08:00 | 1/1 | Yes |
| B | UTC | 0/0 | No |
| B | UTC+08:00 | 1/1 | Yes |

Returned modification epochs also lay inside the expected candidate window.
Together with the deployed modification-time binding, this establishes that
the observed filter applies to `gmtModified` and interprets these timestamp
strings as UTC+08:00 wall time. This is endpoint-specific evidence; automation
or patrol timestamps must not inherit it.

For a real candidate with fractional milliseconds, let S be its modification
timestamp rounded down to a whole second:

| Native query bounds | Candidate included |
| --- | --- |
| S to S | No |
| S to S+1 second | Yes |
| S-1 second to S | No |
| S+1 second to S+2 seconds | No |

The upper bound is not automatically expanded to the end of its named second.
All 104 rows had nonzero millisecond fractions, so these observations cannot
distinguish `>` from `>=` or `<` from `<=` exactly on the boundary. A precise
public interval needs either additional evidence or a separately verified
bounded-overfetch/local-interval strategy; the following section records that proof.

## Row structure and retention boundary

Every sampled row had string `ptrOrderId` and an object
`productionTrialRunFundOutAbilityVO`. The latter's union of keys was
`clearingSystemName`, `debtorAccountAliasName`, `financialInstCode`,
`regulatoryRequiredObo`, `supportFvt`, `supportObo`, `supportReferenceObo`,
`integrationMode`, `communicationMode`.

The observed top-level union included:

- Typed relationships: `caseId`, `allocateOrderId`, `finNetId`, `bizRequestId`.
- Case and execution: `caseName`, `caseType`, `orderStatus`, `verifyStatus`,
  `ptrFinalResult`, `obo`, `fvt`, `referenceObo`, `purposeCode`.
- Time: integer-valued epoch fields `gmtCreate`, `gmtModified`,
  `bizRequestTime`, optional `lastVerificationDt`, `allocatePayoutTime`.
- Amount/currency/account: `debtorAmount`, optional `returnAmount`,
  `creditorCurrency`, `creditorAccountAliasName`, `virtualDebtorAccount`.
- Individual verification: optional `verifyFvtResult`, `verifyOboResult`,
  `verifyReferenceOboResult`, `spentTime`, `spentTimeInfoSource`.
- Optional FX values: `transactionRate`, `transactionRateRef`.

The response also includes actual receiving account numbers, user IDs,
names/addresses/country, creator/verifier identities, IBAN/BIC, free-form
remarks and failure/purpose details. Do not persist the entire response. Freeze
an explicit allowlist before implementation, using the existing cases privacy
projection as a policy precedent rather than assuming identical fields/types.
The complete comparison above used transient raw rows only.

The structural outflow baseline is stronger evidence than menu placement alone.
Keep order state, verification state and final verdict separate: expected
rejection may pass verification. No local outcome adjudication was performed.

## Frozen padded acquisition

A public half-open interval avoids relying on unknown server equality semantics:

- Required `--updated-from` and `--updated-to`, strict
  `YYYY-MM-DDTHH:MM:SS+08:00`; no date-only input, fractions or other offsets.
- Require `from < to`, requested span at most 31 days, and `to <= current time`.
  These are product scope limits; no future-history completeness is claimed.
- Native query bounds are requested `from` minus one second and requested `to`
  plus one second, formatted `YYYY-MM-DD HH:mm:ss` in UTC+08:00.
- Fixed `pageNo=0,pageSize=500`; acquire and validate the complete padded
  scope twice, compare retained projected rows by `ptrOrderId`, then apply
  local `gmtModified >= from_epoch_ms AND gmtModified < to_epoch_ms`.
- Require both full responses to have exact echoes, total equal to row count,
  total at most 500, distinct nonempty identities and structural outflow
  baselines. Any overflow, truncation, mismatch or retained-content drift fails
  before publication. No paging fallback or partial merge.
- `gmtModified` is required, integer epoch milliseconds. The scope removes
  padding rows only after completeness/stability proof; business filters and
  display windows follow that scope operation.
- Source `sources.payment_ptr_orders`, capability `payment.ptr.orders.list`,
  schema version 1. Scope string:
  `updated:<from-ISO8601>:<to-ISO8601>`; complete cache namespace:
  `payment.ptr.orders.list:updated:<from-ISO8601>:<to-ISO8601>:cdp`.
  Both strict bounds include their literal `+08:00`, preventing timezone or
  interval collisions. No default dates or all-history alias.
- Each exact window keeps its own latest successful snapshot. Shared default
  72-hour TTL is cache policy, not evidence that dynamic orders remain current.
  No automatic historical-window pruning. Live does not publish or fall back;
  failed refresh retains the previous snapshot of the same exact scope.

Proof: requested September 1 00:00 through September 28 00:00 half-open,
with padded native August 31 23:59:59 through September 28 00:00:01, returned
104 unique rows with total 104 in each of two size-500 reads. Complete raw
arrays matched exactly; local scope retained 104 and matched the earlier
complete scope. Three additional tiny intervals around a fractional-millisecond
candidate exercised actual padding rows:

| Requested interval relation to candidate | Complete padded rows | After local interval | Repeat stable |
| --- | --- | --- | --- |
| Contains candidate | 1 | 1, candidate present | Yes |
| Candidate in extra second before start | 1 | 0 | Yes |
| Candidate in extra second after end | 1 | 0 | Yes |

No claim about exact server boundary inclusivity is needed for this design.

## Frozen projection and candidate filters

The following exact projection is frozen for implementation. Every retained
field was observed in nonempty responses; omitted fields stay omitted rather
than becoming default values. Optional null values may be retained with explicit
nullable schema types. Unknown properties are discarded at every nested level.

| Fields | Type |
| --- | --- |
| `ptrOrderId` | Required nonempty string identity |
| `gmtModified` | Required integer epoch milliseconds |
| `productionTrialRunFundOutAbilityVO` | Required object; only keys listed below |
| `caseId`, `caseName`, `caseType`, `allocateOrderId`, `finNetId`, `bizRequestId` | Optional string/null; related IDs remain separately typed by field |
| `creditorAccountAliasName`, `creditorCurrency`, `obo`, `fvt`, `referenceObo`, `purposeCode` | Optional string/null |
| `orderStatus`, `verifyStatus`, `ptrFinalResult` | Optional string/null; separate state dimensions, no derived verdict |
| `failureReason` | Optional string/null; raw operational failure text, explicitly **not guaranteed PII-free** |
| `verifyFvtResult`, `verifyOboResult`, `verifyReferenceOboResult` | Optional string/null, independent per-capability result |
| `spentTime`, `spentTimeInfoSource` | Optional string/null; opaque native values, no inferred unit conversion |
| `transactionRateRef` | Optional string/null |
| `gmtCreate`, `bizRequestTime`, `lastVerificationDt`, `allocatePayoutTime` | Optional integer/null epoch fields |
| `transactionRate` | Optional finite JSON number/null |
| `debtorAmount`, `returnAmount` | Optional object/null; only the monetary keys below |

Baseline keys are optional string/null: `clearingSystemName`,
`debtorAccountAliasName`, `financialInstCode`, `regulatoryRequiredObo`,
`supportFvt`, `supportObo`, `supportReferenceObo`, `integrationMode`,
`communicationMode`. Baseline values remain raw strings; they are not the order's
OBO/FVT test-input flags.

Money keys: `amount` finite JSON number/null; `cent` and `centFactor`
integer/null; `currency`, `currencyCode`, `currencyValue` string/null.
The deployed payment-currency column explicitly renders
`debtorAmount.currencyCode`; that mapping was source-verified.

Omit names, addresses, user IDs, raw account numbers, IBAN/BIC, creator/verifier
identifiers, `virtualDebtorAccount`, free-form `remark`/`purposeCodeDetail`, and
all unknown fields. The retained `failureReason` exception is an operational
text requirement, not a claim to scrub personal information from arbitrary text.

| Candidate | Include/defer and exact local field |
| --- | --- |
| PTR ID | Include `--id` -> `ptrOrderId` |
| Case ID | Include `--case-id` -> `caseId` |
| Updated range | Required acquisition scope `--updated-from`/`--updated-to` as above |
| Entity | Defer: no verified entity field in returned order/baseline |
| Channel | Include `--channel` -> `productionTrialRunFundOutAbilityVO.financialInstCode` |
| Payment account | Include `--debtor-account` -> `productionTrialRunFundOutAbilityVO.debtorAccountAliasName` (alias, not actual account number) |
| Payment currency | Include `--debtor-currency` -> `debtorAmount.currencyCode` |
| Receipt currency | Include `--creditor-currency` -> `creditorCurrency` |
| Clearing network | Include `--clearing-system` -> `productionTrialRunFundOutAbilityVO.clearingSystemName` |
| Payment status | Include `--order-status` -> `orderStatus` |
| Verification progress | Include `--verify-status` -> `verifyStatus` |
| Final result | Include `--final-result` -> `ptrFinalResult` |
| Batch association | Defer: no batch ID observed |
| Real details | Defer `get`: independent identity, completeness and permission contract not verified; list remains a summary |

All ten business filters are whole-value case-sensitive local string matches;
repeated values of one field OR, distinct fields AND. No trimming, wildcards or
comma splitting; missing/null/non-string never match and blank filter arguments
are rejected. Cached/live use the same mappings after complete scoped capture.
No server-side business filter parameters are needed or allowed.

Observed states included order `INIT`, `ACCEPTED`, `FUND_OUT_SUCCESS`,
`FUND_OUT_FAILURE`, `FUND_OUT_RETURN`; verification `INIT`, `VERIFIED`; final
`Y`, `N`. These are sample values, not a closed validation enum. Preserve new
server strings. JSON/table, fields, limit/offset/all, freshness and completeness
flags retain the existing public conventions.

Business failure/authentication/permission envelopes were not induced; use
sanitized synthetic fixtures and shared transport failure handling. Successful
narrow empty time queries returned total zero and an empty list. That proves a
filtered empty interval, not an entirely empty production resource.
