# Payment PTR patrol contracts — 2026-09-27

Observed: 2026-09-27
Scope: payment
Status: snapshot


Inquiry-only native production observation for #66 and #67. Raw records,
identifiers, authentication material and account data were not saved. Evidence
below contains structural information and aggregate counts only. No create,
update, enable, approve, run, retry or verify action was invoked.

## Patrol rules: transport verified; outflow scope unresolved

Native route: `https://igfc.alipay.com/receivedPayment/receivedPaymentPtr/inspection`,
embedded by the verified payment `productPTRManagement/patrolRuleLibrary` menu.
API origin: `https://iglobalfundcontrol.alipay.com`.

### List and acquisition

POST `/api/ptr/inspectionRule/find.json`, JSON body
`{"pageNo":0,"pageSize":1000}`; `ctoken` is supplied by the authenticated
transport, never caller data. Native batch-page rule dropdown uses exactly this
acquisition. Native rules list uses page size 10; UI page two sends pageNo 1.
The response envelope contains `success`, `pageNo`, `pageSize`, `totalCount`,
`resultDataList`, plus permission/display metadata and trace/error fields.

Observed on 2026-09-27: total 16; pages 0 and 1 return 10 and 6 rows; 16 unique
nonempty string `id` identities. Repeated page 0 returned identical rows.
Separately, the native size-1000 request returned all 16 rows, 16 unique IDs,
and its repeat returned identical rows. A single bounded full-page acquisition
is therefore supported while total <= 1000 and count == total. Reject overflow,
count mismatch, duplicate/missing identity and malformed envelope; never label a
partial result complete. Do not silently raise the cap.

List keys: `id`, `inspectionRuleName`, `status`, `inspectionCaseType` (string
array), `creator`, `lastOperator`, `enableDate`, `gmtCreate`, `gmtModified`;
`processInstanceId` and `lastUpdateReason` are optional. Timestamp values observed
as integer epoch milliseconds. Observed status values AUDIT and VALID, case types
POSITIVE and NEGATIVE are examples, not closed enums. Retain unknown values.

Defer list/refresh/describe until an outflow discriminator or authoritative outflow-only provenance is verified. Local exact predicates can
use verified stored fields (identity, rule name, status and case-type membership)
only if explicitly documented. Do not equate approval status, rule status and
schedule/cycle. List does not supply the latter two separately.

### Detail

Native read-only Details link is
`/receivedPayment/receivedPaymentPtr/inspection/view?ruleId=<list-id>`.
It issues GET `/api/ptr/inspectionRule/findRuleDetail.json` with query keys
`ruleId` and transport `ctoken`. Envelope: success and `resultData`.
Native click plus repeat GET succeeded; resultData.ruleId matched the requested
list identity. Defer get in the first release; the independent native contract is recorded for
future detail caching and identity-consistency implementation. Do not call list
data full detail.

Detail keys: `ruleId`, `inspectionRuleName`, `status`, `inspectionCaseType`,
`creator`, `lastOperator`, `lastUpdateReason`, `enableTime`, `gmtCreate`,
`gmtModify`, `ptrInspectionGradeStandard` array. List/detail timestamp names
are different: enableDate/enableTime and gmtModified/gmtModify. Preserve mapping.
Grade entries contain cycleType, inspectionNumber (integer), judgmentType,
minTransactionCount/maxTransactionCount (integers), statisticalMethod and
transactionRange (string). Observed week, SAME_ATTRIBUTE_CHANNEL/NORMAL and TOTAL
are examples only. Nested grade rows have no verified independent identity and
must stay attached to the rule detail.

### Native filters and deferred CLI filters

Native UI and deployed source map institution -> financialInst, account ->
bankAccount (account aliasName), network -> clearingNetworkName (clearingSystemName),
standard-account flag -> whetherStandard (Y/N), receiving market -> creditRegion
(marketCode), cross-currency flag -> crossCurrency (Y/N), debit currency ->
debitCurrency, patrol batch -> inspectionBatchId. These fields are absent from
observed list and detail rows. Do not implement local predicates by guessing
relationships or inventing joins. Defer these CLI filter flags pending explicit
scoped acquisition design and native filtered-response verification.

## Patrol batches: bounded query verified; boundary/direction gates remain

Native menu embeds
`https://igfc.alipay.com/receivedPayment/receivedPaymentPtr/inspectionBatch`.
POST `/api/ptr/inspection/findBatchList.json` supplies the list. Native default
page size is 10, zero-based page numbers. The rule-page dropdown independently
uses pageNo 0/pageSize 10000; this is not an approved unbounded CLI history scope.
Native batch page has a creation-date range picker. Its deployed source maps
createDate to createStartDate/createEndDate formatted YYYY-MM-DD. Native range
2026-09-01 through 2026-09-27 produced a successful empty result (totalCount 0,
resultDataList omitted). Browser timezone is Asia/Shanghai. Exact nonempty range,
server boundary behavior, repeat stability and detail are still being checked.

### Nonempty history and boundary evidence

The same endpoint with pageNo 0/pageSize 10, createStartDate 2024-12-01 and
createEndDate 2024-12-31 returned total=rows=unique batchId count=7. Repeat rows
were identical. Removing the UI createDate array yielded identical rows. Date
bounds alone therefore suffice; never require arbitrary browser Date objects.
A native September 2026 range produced successful totalCount=0 with no
resultDataList key; the parser must recognize this verified empty envelope.

Browser timezone was Asia/Shanghai, but server date filtering did not match
Shanghai calendar days. A 2024-12-30 through 2024-12-30 query returned one row
created at UTC hour 0 on December 30, excluding another created at UTC hour 16
on December 29 (both are December 30 in Shanghai). A December 29–30 query returned
both. This is consistent with UTC calendar-day filtering and contradicts simply
adopting browser timezone. Exact midnight/end-of-day inclusion and general server
timezone contract remain unproven. Do not promise exact inclusive Shanghai dates.
Require an explicit bounded-history scope and resolve this boundary contract
before enabling batch refresh; do not substitute an unbounded full-history fetch.

Batch rows: batchId, creator, inspectionCycleType and passRate strings;
failCount, totalCount, unFinishedCount, gmtCreate and gmtModified integers.
Pass rate is supplied as a string; retain source semantics and do not infer PTR
pass from payment success. Native batchId is distinct from ruleId and orderId.

### Detail and native filter decisions

Read-only native Details navigation opens
`/receivedPayment/receivedPaymentPtr/inspectionBatch/view?id=<batchId>`.
It calls POST `/api/ptr/inspection/batchDetail.json` three times with batchId,
batchTypeCode (init, fail, processing), pageNo 0 and pageSize 1000. All three
observed responses were successful and empty. The page contains separate
not-started, failed and pending-result tables. This is not a complete child-order
list: successful children have no observed section. Defer get/child expansion
until nonempty schemas, identities, completeness and passing-child treatment are
verified; never label these three sections all children.

Native batch filter labels/fields are account/bankAccountAlias,
network/clearingSystemName, standard flag/whetherStandard, receiving market/
creditRegion, creation range/createDate and rule name/inspectionRuleName. Only
creation-range request behavior was verified. These relationships are absent from
batch summary rows; defer local relationship filters instead of guessing joins.

## Direction provenance and release decision

Both native inquiries were reached through payment PTR production menu entries.
However, neither rule nor batch summary response exposes a direction field, and
native list requests supply no direction discriminator. Observed rule detail
also lacks a direction marker. Its grade transactionRange string is not verified
to encode direction. Deployed list/detail code did not establish a business
outflow-only discriminator; common accounting D/C enums are unrelated evidence.
Menu position alone cannot prove that shared PTR endpoints exclude inflow data.

The retained specification requires outflow-only scope. Rule list and independent
detail transports are verified, but direction remains unclassified. Defer rule
list/refresh/describe/get from this release until live evidence establishes
outflow-only provenance or an explicit discriminator. Do not label shared or
unclassified data payment outflow solely because it appears in the payment menu.

Batch summaries likewise remain unclassified execution history. They require
verified outflow relation, an exact date-window contract and appropriate freshness
semantics. Defer patrol-batches for this release. Its verified inquiry/date/detail
observations above are retained to avoid repeating research.
