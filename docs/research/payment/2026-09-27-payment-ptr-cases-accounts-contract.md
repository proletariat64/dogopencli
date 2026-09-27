# Payment PTR cases and beneficiary account list contracts

Observed: 2026-09-27
Scope: payment
Status: snapshot

## Native evidence and scope

This report supplements [PTR research](2026-09-27-payment-ptr-research.md)
and issues [#63](https://github.com/proletariat64/dogopencli/issues/63) and
[#65](https://github.com/proletariat64/dogopencli/issues/65). Inquiry-only native
Search, pagination and detail controls were inspected in signed-in Chrome.
Only schemas, aggregate counts and equality verdicts were retained. No production
rows, identifiers, authentication material or financial account values are included.

| Resource | Native iframe on `https://igfc.alipay.com` | Observed GET path on `https://iglobalfundcontrol.alipay.com` |
| --- | --- | --- |
| Cases | `/receivedPayment/receivedPaymentPtr/productTrialRunBase/ptrCase` | `/api/ptr/case/query.json` |
| Beneficiary accounts | `/receivedPayment/receivedPaymentPtr/ptrBankAccount` | `/api/ptr/creditorAccount/query.json` |

Both native default requests carry `pageSize=10` and the browser's authentication
parameter; they have no business, status, time or direction filter. The UI's
second page sends `pageNo=1`: pagination is **zero-based**, not one-based.
The authentication parameter is runtime-owned, never user-configurable or logged.

Cases are an outflow model: native labels explicitly say 流出渠道 and 流出银存,
and all 3,292 observed records have `fundOutAbilityBaselineVO`. The case scope is
the complete current outflow case library returned by this endpoint. No explicit
version, case-group or child-case field exists in the observed full-list schema.
This does not establish deleted-record history or every historical version.

Accounts are the **PTR beneficiary library exposed by the payment PTR menu**.
Its complete 844-row schema has no direction or VA/non-VA discriminator. It must
not be advertised as an exclusively outflow-owned account directory, collection
VA pool or physical-account inventory. The legacy iframe's `receivedPayment`
path does not establish inflow ownership either. The user requires the original strict outflow-only scope. Exclusion of records
also usable by inflow remains unverified and blocks implementation of accounts.
The verified acquisition contract below is only `ptr-library`; it must not be
registered as an outflow-only capability. No speculative direction filter may
be added.

## Frozen list acquisition

Native and repeated read-only parameter checks established:

| Check | Cases | Beneficiary accounts |
| --- | --- | --- |
| Default page zero, size 10 | 10 rows; total 3292 | 10 rows; total 844 |
| Native page one, size 10 | 10 rows, no overlap with page zero | Same |
| Last page, size 10 | page 329: 2 rows | page 84: 4 rows |
| First out-of-range page | page 330: zero rows | page 85: zero rows |
| Full page, total + 1 size | 3292 unique rows | 844 unique rows |
| Full page, size 5000 | 3292 unique rows | 844 unique rows |
| Full page, size 10000 | Identical content to size 5000 | Identical content to size 5000 |
| Repeated size 5000 | Identical content | Identical content |
| Independent size-100 pagination sweep | 3292 rows, **duplicate IDs** | 844 rows, **duplicate IDs** |

The paginated sweep demonstrates that count equality alone is unsafe. The cause
of cross-page overlap was not established; neither deduplication nor merging old
cache rows can repair completeness.

Freeze acquisition at **two complete requests with `pageNo=0&pageSize=5000`**.
Require both envelopes to succeed and echo the requested pagination; require
integer nonnegative `totalCount <= 5000`, list length exactly equal to total,
nonempty string IDs unique within each list, and identical retained, allowlisted records by
ID across both reads. Sensitive omitted fields do not enter cache or drift comparison. Reject overflow, truncation, changed totals, duplicate
identities or any content drift; retain the previous snapshot on refresh failure.
Do not fall back to pagination. Stable CLI ordering is by record ID, independently
of backend order. The verified 10,000-size request is research corroboration,
not permission to increase the shipped 5,000 bound silently.

For cases, also require the outflow baseline object on every record. There is
no time window: scope means current endpoint-visible configuration, including
all returned states. Source/namespace candidates are `payment_ptr_cases` /
`payment.ptr.cases.list:outflow-library:cdp` and
`payment_ptr_beneficiary_accounts` /
`payment.ptr.beneficiary_accounts.list:ptr-library:cdp`; do not substitute
`all-history` or an unproved `outflow-only` account namespace.

Default offline, explicit live without publication/fallback, and refresh atomic
publication follow the parent specification. Source metadata identifies the
scope and collection time. The inherited 72-hour freshness default is a cache
policy, not a claim that configuration or embedded verification summaries remain
current for 72 hours; callers needing current state use live or refresh.

## Envelope and error rules

Successful responses contain `success: boolean`, `pageNo: integer`,
`pageSize: integer`, `totalCount: integer`, `resultDataList: array`,
`permissions: array<{permissionCode: string}>`, `showButton: boolean`,
`sofaTracerId: string`, and `errorContext.errorStack` records containing string
`codeLevel`, `codeType`, `errorName`, `errorSpecific`, `systemCode`, `systemName`.
**Successful responses also have errorContext**: its presence is not failure.
Check `success is true`, then validate the page and identity contract. Never
print upstream error messages or trace/authentication values without sanitizing.

Production rejection, expired authentication during these queries and genuinely
empty full libraries were not observed. Cover them with clearly identified
synthetic fixtures, plus shared transport authentication handling. A filtered
empty result does not prove a production empty full-library envelope.

## Complete observed case list schema

Fields below are the union across the complete list. Observed scalar types are
listed; absence is possible unless the acquisition contract explicitly requires
a field. No observed field had a null value; synthetic tests must cover null and
missing optional fields. Do not coerce strings such as OBO/FVT into booleans.

| Shape | Fields |
| --- | --- |
| Required nonempty string identity | `id` |
| Strings | `baselineId`, `caseAutomationRuleId`, `caseName`, `caseType`, `creator`, `creditorAccountAliasName`, `creditorAccountType`, `creditorCurrency`, `fvt`, `lastOperator`, `obo`, `oboAddress`, `oboCountry`, `oboName`, `oboUserId`, `purposeCode`, `purposeCodeDetail`, `referenceObo`, `referenceOboAddress`, `referenceOboCountry`, `referenceOboName`, `referenceOboUserId`, `remark`, `userIban`, `userIbanBIC`, `verifyFailReason`, `verifyFundOutOrderId`, `virtualDebtorAccount` |
| Integer timestamps | `gmtCreate`, `gmtModified`, `verifyTime` |
| Boolean | `verifyResult` |
| Money objects | `creditorAmount`, `debtorAmount` |
| Required object | `fundOutAbilityBaselineVO` |

Each money object has numeric `amount` (fractional amounts observed), integer
`cent` and `centFactor`, and string `currency`, `currencyCode`, `currencyValue`.
Each baseline object has string `clearingSystemName`, `communicationMode`,
`creditorCurrency`, `debtorAccountAliasName`, `debtorCurrency`,
`financialInstCode`, `integrationMode`, `regulatoryRequiredObo`, `supportFvt`,
`supportObo`, `supportReferenceObo`. Some baseline properties are absent on some
rows. No backend enum is a closed vocabulary: preserve returned strings.

`baselineId` and `caseAutomationRuleId` are typed relations when present, not
identity substitutes. `verifyFundOutOrderId` is the last verification's fund-out
order reference; do not call it a case ID or PTR order ID without further proof.
`verify*` fields are verification summaries, separate from case inputs and
baseline capabilities. `verifyResult` is not payment success. An expected
rejection can satisfy a test; negative/effective case types do not imply failure.

### Case candidate filter decisions

All included filters operate locally on the complete captured list for both
cached and live requests. Same-field repeated values are OR; different fields
are AND. Match whole case-sensitive strings, with no trimming or wildcard
expansion; missing/null never match; reject empty/whitespace-only arguments.
No business filters are sent to the backend. UI input IDs listed here establish
native labels only, not untested backend filter contracts.

| Candidate / proposed flag | Decision and returned-field mapping |
| --- | --- |
| Case ID / `--id` | Include: `id` |
| Case name / `--name` | Include: `caseName` |
| Channel / `--channel` | Include: `fundOutAbilityBaselineVO.financialInstCode`; native input `financialInstCode` |
| Payment account / `--debtor-account` | Include alias only: `fundOutAbilityBaselineVO.debtorAccountAliasName`; no bank-number match |
| Payment currency / `--debtor-currency` | Include: `fundOutAbilityBaselineVO.debtorCurrency` |
| Receipt currency / `--creditor-currency` | Include: `creditorCurrency`; retain baseline currency separately |
| Clearing network / `--clearing-system` | Include: `fundOutAbilityBaselineVO.clearingSystemName` |
| OBO / `--obo` | Include input: `obo`; do not confuse with baseline `supportObo` |
| FVT / `--fvt` | Include input: `fvt`; do not confuse with baseline `supportFvt` |
| Non-UD | Defer named semantic filter: native header exists, but equivalence to `referenceObo` not established by current UI/API evidence; preserve raw reference field if exposed |
| Case type / `--case-type` | Include: `caseType`, raw returned string |
| Network relation / `--baseline-id` | Include: `baselineId`; missing values do not match |
| Beneficiary relation | Defer account-ID join/filter: list gives alias/type, no proved beneficiary-library ID |
| Beneficiary alias / `--creditor-account-alias` | Include: `creditorAccountAliasName`; native input is `creditorAccountAlias` |

Interaction/integration and baseline support filters are optional later additions,
not aliases of case inputs. Native inputs are `communicationMode`,
`integrationMode`, `supportFvt`, `supportObo`.

## Complete observed beneficiary list schema

Required `id` is a nonempty string. `gmtCreate` and `gmtModified` are integer
timestamps. Every other observed field is a string:

`bicCode`, `cardAddress`, `changeReason`, `creator`, `creditorAccountAlias`,
`creditorAccountNo`, `creditorAccountType`, `creditorAddress`, `creditorBankName`,
`creditorCardIndex`, `creditorCountry`, `creditorCurrency`, `creditorInstName`,
`creditorLegalEntityCode`, `creditorName`, `creditorRegion`, `extInfo`,
`failReason`, `fundInst`, `ibanCode`, `lastOperator`, `localClearingSystemCode`,
`needCheck`, `status`, `tntInstId`, `useRemark`, `userId`.

The record ID, card index and bank account number are separate fields. Never
deduplicate by alias/account number. `status`, `needCheck` and account type
remain distinct raw properties; no observed mapping proves that type is exactly
Normal/Bad Account, or that needCheck is a binding state. Do not manufacture
these semantic translations from historical documents.

### Beneficiary candidate filter decisions

Use the same local whole-string matching rules as cases. No backend business
filter keys are frozen. The native text/select input IDs differ from row fields.

| Candidate / proposed flag | Decision and returned-field mapping |
| --- | --- |
| Library ID / `--id` | Include: `id` |
| Card index | Defer public filter/storage in the minimal list projection: sensitive linkage field, distinct from ID |
| Channel / `--channel` | Defer ambiguous mapping: both `fundInst` and `creditorInstName` exist; native header alone does not prove which denotes requested channel |
| Alias / `--alias` | Include: `creditorAccountAlias`; native input `accountAliasName` |
| Actual bank account number | Defer public filter/storage; native input `accountNo`, row `creditorAccountNo` is sensitive |
| Currency / `--currency` | Include: `creditorCurrency`; native input `creditorCurrencyCode` |
| Legal entity / `--legal-entity` | Include: `creditorLegalEntityCode` |
| Region / `--region` | Include: `creditorRegion`; country remains distinct `creditorCountry` |
| Account type / `--account-type` | Include raw `creditorAccountType`; native input `accountType` |
| Status / `--status` | Include raw `status`; native input `accountStatus` |
| Test purpose | Defer named enum filter: `useRemark` is optional free text and no dedicated purpose enum was observed |
| Bank name / `--bank-name` | Include: `creditorBankName`; native input `creditorBankName` |
| Card-template check / `--need-check` | Include raw `needCheck`; do not relabel binding state |

## Exhaustive first-release projection allowlists

These are source field names; public snake-case names may be mapped explicitly
without changing their meanings. Preserve optional missing/null values, do not
invent empty strings, defaults or derived conclusions. Unknown fields must not
enter either persisted records or output. Raw/full-response columns must contain
only this selected projection, never the source row.

**Cases top level:** `id`, `baselineId`, `caseAutomationRuleId`, `caseName`,
`caseType`, `creditorAccountAliasName`, `creditorAccountType`,
`creditorCurrency`, `fvt`, `gmtCreate`, `gmtModified`, `obo`, `purposeCode`,
`referenceObo`, `verifyFundOutOrderId`, `verifyResult`, `verifyTime`,
`creditorAmount`, `debtorAmount`, `fundOutAbilityBaselineVO`.

**Case money objects:** `amount`, `cent`, `centFactor`, `currency`,
`currencyCode`, `currencyValue`; reject unexpected structural types and omit
unknown money properties. No arithmetic conversion or float-derived cent values.

**Case baseline object:** `clearingSystemName`, `communicationMode`,
`creditorCurrency`, `debtorAccountAliasName`, `debtorCurrency`,
`financialInstCode`, `integrationMode`, `regulatoryRequiredObo`, `supportFvt`,
`supportObo`, `supportReferenceObo`. Require an object for each case but preserve
missing/null optional properties. No detail-only baseline fields enter the list.

**Beneficiary accounts top level:** `id`, `creditorAccountAlias`,
`creditorAccountType`, `creditorBankName`, `creditorCountry`, `creditorCurrency`,
`creditorInstName`, `creditorLegalEntityCode`, `creditorRegion`, `fundInst`,
`gmtCreate`, `gmtModified`, `localClearingSystemCode`, `needCheck`, `status`.
No nested account objects are included.

All other upstream properties are omitted. This deliberately includes both raw
institution-related account fields without assigning an unproved channel-filter
meaning to either one. Raw state values remain uninterpreted. Configuration
aliases, library IDs and typed relation IDs are needed for inquiry and remain
private cached operational data, never production test fixtures or logs.

## Field retention and detail decision

The minimal list projection must explicitly allowlist business identity,
configuration, typed relationships, timestamps, raw state and capability fields.
For cases, omit personal names/addresses and OBO/reference user IDs,
`userIban`, `userIbanBIC`, creator/operator identities and unstructured remarks
from persisted/public data. For accounts, omit bank account number, IBAN/BIC,
card index, personal names/addresses, tenant/user IDs, creator/operator identities
and unstructured `extInfo`, change/failure/use remarks. This is **omission**, not
a claim that an unmasked bank number is safe because the cache is local. Do not
persist the complete upstream response in the generic raw/debug payload.
Store the allowlisted normalized projection only, in the existing private cache.
Any later extension exposing omitted fields needs an explicit documented
retention/masking contract. Stable library IDs and business aliases remain
available for inquiry; their values still must not enter logs or Git fixtures.

Real native read-only details **do exist**:

- `用例详情` sends `GET /api/ptr/case/detail.json?caseId=…` and returns
  `success=true`, `resultData` containing the case. Its baseline adds
  `debtorAccountNo`, `payOutAbilityId`, `averageReceiptedPeriod`, `timeZone`.
- Account `详情` sends `GET /api/ptr/creditorAccount/detail.json?id=…` and
  returns `success=true`, `resultData` containing account fields.

**Defer both CLI get commands in the first release.** Only one native detail
per resource was observed; full detail identity/completeness, privacy and atomic
publication of all details were not validated. Do not register detail endpoints
in the first-release transport allowlist or pretend list rows are details.
This is an explicit optional-scope decision, not a claim that no detail exists.
No create, copy, edit, run, disable, rebind or result-modification action was used.
