# Payment PTR native contract discovery and implementation blocker

Observed: 2026-09-27
Scope: payment
Status: snapshot

## Follow-up after network restoration

The initial blocker below is historical. Subsequent inquiry-only verification
established the [case list contract](2026-09-27-payment-ptr-cases-accounts-contract.md)
and enabled the independently scoped #63 implementation. Accounts remain blocked
by unproved direction isolation. See the [network gap](2026-09-27-payment-ptr-networks-contract-gap.md),
[patrol investigation](2026-09-27-payment-ptr-patrol-contract.md) and
[automation investigation](2026-09-27-payment-ptr-automation-contract.md) for later evidence.
The user reaffirmed the original outflow-only requirement; no shared-library
scope relaxation is part of the implementation.

Orders follow-up verified native zero-based page 0/1 at size 10, total 5,923.
The native date picker sends `modifiedTimeBegin` as `YYYY-MM-DD HH:mm:ss`;
a September 1 selection retained its time-of-day component and returned 93
records. This initial evidence did not establish both boundaries or complete bounded
acquisition. Subsequent [order research](2026-09-27-payment-ptr-orders-contract.md)
proved UTC+8 timestamp filtering and repeated padded complete acquisition; #64
was frozen independently, with no unbounded-history fallback.

## Initial outcome

Implementation work for [#61](https://github.com/proletariat64/dogopencli/issues/61)
started on branch `feat/payment-ptr-61`. All seven native list endpoints were
observed returning business success and nonempty results. This improves on the
[initial research](2026-09-27-payment-ptr-research.md), which had no current PTR
request evidence. **The contracts are not frozen and no executable PTR commands
have been added.** Full acquisition, identity, filters, details and history scope
remain unverified.

The project CLI initially verified the dedicated headless Chrome on CDP 9222 as
authenticated. The browser plugin's empty inventory did not mean the project's
CDP browser was absent. Native observations used the existing project CDP helper
under `inquiry_session` and its shared browser coordination lock. Queries were
observed from the seven specified menu pages and the case/account native iframe
pages; no configuration, approval, PTR launch, verification or export action was
invoked. Credentials and business row values were not included in this report.

Subsequent coordinated probes failed repeatedly with `net::ERR_CONNECTION_RESET`
or a target-websocket timeout. A final serial `dogopencli auth check` and the
supported `dogopencli login --timeout-seconds 60` recovery both returned
`browser_unavailable` with a navigation/websocket timeout. This is a runtime
access failure, not evidence of expired SSO or denied PTR permissions. The user
was asked to restore platform access before production verification resumes.

## Observed native list requests

All API paths in this table are on `https://iglobalfundcontrol.alipay.com`.
Browser-owned authentication parameters are omitted. Parameter presence and
types below are observations, not the final allowed request contract.

| Issue/resource | Method and path | Native parameter observations | Returned rows in observed response |
| --- | --- | --- | --- |
| [#62 networks](https://github.com/proletariat64/dogopencli/issues/62) | GET `/api/fundOutNetwork/query.json` | Query `pageSize=10` | 10 |
| [#63 cases](https://github.com/proletariat64/dogopencli/issues/63) | GET `/api/ptr/case/query.json` | Query `pageSize=10`; one wrapper load also included `?localeType` as a parameter name | 10 |
| [#64 orders](https://github.com/proletariat64/dogopencli/issues/64) | GET `/api/ptr/manage/query.json` | Query `pageSize=10`, `?localeType` parameter name observed | 10 |
| [#65 beneficiary-accounts](https://github.com/proletariat64/dogopencli/issues/65) | GET `/api/ptr/creditorAccount/query.json` | Query `pageSize=10` | 10 |
| [#66 patrol-rules](https://github.com/proletariat64/dogopencli/issues/66) | POST `/api/ptr/inspectionRule/find.json` | JSON `localeType: string`, `pageSize: integer`; a batch-page option load used `pageNo` and `pageSize` | 10 in the rule-page load; 16 in the option load |
| [#67 patrol-batches](https://github.com/proletariat64/dogopencli/issues/67) | POST `/api/ptr/inspection/findBatchList.json` | JSON `pageNo: integer`, `pageSize: integer` | 37 |
| [#68 automation-batches](https://github.com/proletariat64/dogopencli/issues/68) | POST `/api/ptr/auto-batch/query` | JSON `pageNo: integer`, `pageSize: integer` | 10 |

These counts do not prove scope totals or complete coverage. In particular,
auxiliary option loads are not substitutes for the corresponding main list.
No numeric page-base convention, maximum size or pagination termination rule
has been frozen. The unusual `?localeType` name is recorded literally; it must
not be normalized into a guessed required parameter without validation.

All seven responses exposed top-level `success`, `pageNo`, `pageSize`,
`totalCount` and `resultDataList`. Successful responses also contained
`errorContext`, `permissions`, `showButton` and `sofaTracerId`.
`errorContext` presence alone therefore cannot classify a business failure.
No failure/empty-scope response contract was established in this discovery.

## Native page composition

The payment wrapper base remains
`https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/productPTRManagement/`.
The following iframe paths were observed on `https://igfc.alipay.com`:

| Resource | Iframe path |
| --- | --- |
| networks | `/receivedPayment/receivedPaymentPtr/fundOutNetworkBaseline` |
| cases | `/receivedPayment/receivedPaymentPtr/productTrialRunBase/ptrCase` |
| orders | `/receivedPayment/receivedPaymentPtr/productTrialOperationQuery/productTrialOperation` |
| beneficiary-accounts | `/receivedPayment/receivedPaymentPtr/ptrBankAccount` |
| patrol rules | `/receivedPayment/receivedPaymentPtr/inspection` |
| patrol batches | `/receivedPayment/receivedPaymentPtr/inspectionBatch` |

Automation batches rendered directly in the wrapper page. Its observed form
labels were Batch Date, Batch number, Batch Status, Test Case Name, Outflow
channel, Debit account, Clearing network, Payment Currency, Receipt Currency,
Approval Status and Batch Approver. These are labels, not proven backend keys.
Details and Approval were separate controls; Approval was not invoked.

## Observed row structure and implementation implications

The following is a first-row schema sample, not a guarantee that every field is
present or has the same type across the full dataset.

| Resource | Observed structure | Remaining identity/interpretation issue |
| --- | --- | --- |
| networks | Parent fields include `bankAccount`, `currencyCode`, `creditCurrency`, `legalEntity`, `financialInst`, `accountStatus`, `accountType`, `inOrOut`, `isVerifyRange`, `hasVaildCreditorAccount`; nested `fundOutNetworkBaselineDetailVOS` contains `id`, network/configuration fields and verification/patrol results | No top-level ID in the sampled parent. Child `id` must not be assumed to identify the parent. Composite parent identity and nested predicate correlation need verification |
| cases | String `id`, `caseName`, `caseType`, test inputs `obo/fvt/referenceObo`; nested `fundOutAbilityBaselineVO`; amount objects; separate `verifyResult: boolean`, `verifyTime: integer`, `verifyFailReason`, `verifyFundOutOrderId` | Case definition, baseline capabilities and last-verification fields coexist. Full-scope ID/version uniqueness and true detail are unverified |
| orders | String `ptrOrderId`, `caseId`, `allocateOrderId`, `finNetId`; distinct `orderStatus`, `verifyStatus`; `productionTrialRunFundOutAbilityVO`, amount object and audit timestamps | Typed identifiers and status separation are confirmed as field structure. Final-verdict availability, time bounds, enum semantics and true detail still need evidence |
| beneficiary-accounts | String `id` and `creditorCardIndex`; account, currency, entity, region, bank/name/IBAN/BIC, tenant/user and state fields; integer create/modify timestamps | Account number and card index are not interchangeable with row ID. Complete identity, masking/retention and VA/direction scope remain unresolved |
| patrol-rules | String `id`, `inspectionRuleName`, `status`, `processInstanceId`; `inspectionCaseType: array`; integer `enableDate`, create/modify timestamps | Rule identity/version, schedule, approval and associated-object semantics are not yet frozen |
| patrol-batches | String `batchId`, `inspectionCycleType`, `passRate`, `creator`; integer `failCount`, `unFinishedCount`, `totalCount`, create/modify timestamps | Batch totals differ from envelope pagination totals. Full-history scope, unique IDs and child coverage remain unverified |
| automation-batches | String `batchId`, `batchStatus`, `approvalStatus`; integer `batchDate`, `approvedCaseCount`, `caseCount`, `orderCount` | Batch and approval statuses are distinct. Date semantics, aggregate denominators and child/detail coverage remain unverified |

Network child samples separately expose `verifyResult`, `inspectionResult`,
`clearingSystemStatus`, `isExistInspectionRule`, `isPauseInspection`, cost/time
scores and boolean support fields. These differ from case baseline support
fields, which were strings in the sampled response. A common boolean conversion
across all PTR resources would therefore be unsupported.

Case UI labels confirm outflow channel/account, clearing network, interaction
and integration modes, currencies, FVT/OBO, case type and receiving-account
alias. Beneficiary UI labels include bank, account number/alias, currency,
region, account type, card-template validation and account state. Current labels
expand/refine historical candidates but do not establish backend filter keys,
full outflow isolation, or a non-VA-only account scope.

## Resume gates

1. Restore the dedicated browser's platform access and obtain a successful
   serial `dogopencli auth check`; keep one healthy inquiry session for bounded
   follow-up work where practical.
2. Observe native page two/page-size changes before freezing parameter mappings;
   verify repeated reads, total semantics, identities, last/overrun behavior and
   a complete acquisition strategy separately for each resource.
3. Determine every filter's include/defer decision, row/child correlation,
   direction isolation, and genuine read-only detail availability/identity.
4. For orders and both batch resources, freeze time field, bounds, timezone,
   cutoff/update handling, cache scope and freshness before implementing history.
5. Record sensitive-field output/cache policy for account/order records, then
   publish the frozen per-resource contract to its issue and advance only that
   resource to implementation readiness.

Until those gates pass, #62–#68 remain `needs-info`. No app code, placeholder
commands, synthetic claims of production completeness or implementation-ready
PR should replace the missing contract evidence. The branch and private probe
scripts preserve the work needed to resume.
