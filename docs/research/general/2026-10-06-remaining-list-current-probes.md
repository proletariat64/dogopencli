# Remaining Liquidity lists: populated next-batch selection

Observed: 2026-10-06
Scope: general
Status: snapshot

Research baseline: master `a27756b414e49d172546a9d14849e132a4dd271e`, after PR #121.
The installed full-tree offline snapshot currently reports 13 unsupported list
commands, all in Liquidity. Snapshot availability is not production acceptance.
This investigation performs source-verified inquiries only. It neither enables
a command nor runs public CLI UAT or implementation tests.

## Selected list before specification

| Proposed batch | Category | Command | Current positive evidence | Readiness |
| --- | --- | --- | --- | --- |
| H | operations | `rule-status list` | 194 records and reported count 194; 194 unique positive integer IDs, matching tenant; repeated single responses agree | Primary future implementation candidate: bounded counted summary acquisition |
| H | investment | `quote-groups list` | 54 records, 54 distinct native IDs, 48 logical groups; all records match the authorized tenant | Contract-proof specification candidate; implementation remains blocked by authoritative coverage proof |

This revised selection has one future implementation candidate and one
conditional coverage investigation, not two newly enabled leaves. The initial
quote-group-only conclusion was withdrawn after the user's CDP-evidence question
led to discovering the actual rule-status menu. Completely empty lists, already implemented lists or lists awaiting
only UAT, and monitoring HOLD are excluded. Demands was delivered in PR #121 and
is absent from this unsupported selection.

## New native source evidence

Read-only graphify discovery and original PRD inspection preceded the source
crosscheck in [Remaining-list PRD crosscheck](2026-10-06-remaining-list-prd-crosscheck.md).
That report identifies two original frontend callers of the same JSON POST
`/queryQuotationGroup.json` with an empty object: search-control options and
duplicate-name validation. These differ from the table caller that inserts
`pageSize` and `rowStart`.

The two callers are new evidence of the client's intended single-response
dictionary usage. Their intent does not establish an authoritative server
contract against truncation. Neither a second successful response nor equality
to a large-page query creates a count or a verified ending protocol.

## Current inquiry observations

The user-authorized exclusive 9223 browser was locked for this bounded probe.
Only a newly created Liquidity tab was used and closed afterwards; the existing
tabs and authentication profile were preserved. The group inquiries were JSON
POSTs. No create, update, alternate-tenant or arbitrary endpoint was called by
the direct group probes. Additional page observation records requests issued
automatically by native page mounts separately below.

| Native request | HTTP | Native success | Rows | Unique native IDs | Reported total | Comparison with first empty-object response |
| --- | ---: | --- | ---: | ---: | --- | --- |
| Empty object, native dictionary caller | 200 | true | 54 | 54 | Absent | Baseline |
| Table scope: pageSize 5000, rowStart 0 | 200 | true | 54 | 54 | Absent | Entire ordered record array equal |
| Table scope: pageSize 5000, rowStart 5000 | 200 | true | 54 | 54 | Absent | Entire ordered record array equal |
| Empty object, repeated once | 200 | true | 54 | 54 | Absent | Entire ordered record array equal |

All four responses had the same envelope fields: `success`, `data`,
`errorCode`, `errorMessage`, `detailMessage`, `errorContext`. No `totalCount`
was present. This is not a short-page or terminal-page proof; the non-progressing
offset remains a first-enable blocker for a paged interpretation.

Every returned row had a nonempty string native `id`; all 54 were unique.
There were 48 distinct string `quotationGroupId` values, 54 distinct
group/version pairs, and four distinct integer version values. Every
`tntInstId` matched the authorized tenant. Versions must remain separate records;
do not deduplicate by logical group ID.

Observed proposed public fields have these native types:

| Fields | Native type |
| --- | --- |
| `id`, `quotationGroupId`, `quotationGroupName`, `bankId`, `status`, `tntInstId` | string |
| `version` | integer |
| `gmtCreate`, `gmtModified` | string; exact format and configuration-time semantics need verification before publication |

The raw response also includes contacts, operators, free text, attachments,
download URLs, process/review metadata and histories. These are not public
list/cache fields. No raw records or their field values are included in this
report or the proposed issue. A future projection must explicitly allowlist
approved fields and verify any safety treatment of displayed names.

One fresh source-verified GET `/queryTreasuryTransferRuleList.json` used the
current tenant and the native transfer-rule request with pageSize 1000 and
rowStart 0. HTTP was 200, but both outer `resultFlag` and inner `success` were
false, with no rule array or total. The nested error code was an empty string.
This was a business failure, not a successful empty scope; this probe does not
establish that the historical missing-privilege diagnosis is still the cause.
No further treasury probes were made.

Private local artifacts, excluded from Git and the issue body, are under
`.qoder/research/remaining-lists-20261006/`. The summary contains aggregates;
the populated response is stored privately for local evidence inspection only.

## Fresh CDP page and network observation

Following the user's question about actual CDP investigation, this round also
revisited six previously inspected native pages in an owned temporary tab.
It observed table headers and browser network events, recording request methods,
paths and key names only. Tokens, parameter values, response records and body
values were not logged. No operation buttons or detail links were clicked.

| Native page | Actual request observed | What the observation supports |
| --- | --- | --- |
| QueryWalletAccount | GET `/queryintnalbkactlist.json`, with native wallet and account-VO keys | A real wallet-labelled account page and caller exist; prior true/false membership and identity blockers remain |
| ProductPoolView | POST `/incrementProductsPage.json`, with tenant and paging keys | Product definition table: Product Code, Bank ID, Product Nature/Type/Tenor and Status; not an independently dated offer object |
| RFQMgmt | POST `/rfq/subInquiryTask/querySubInquiryTask.json`, with paging keys | Inquiry task table: Inquiry Type/Status, Quotation Status, Win Status and Inquiry Task ID; not proof of separate session identity |
| RealTimeNetwork | POST `/api/ai/decision/network/queryDecisionNetwork.json`, with paging keys | Realtime network table and query; no global route-list contract established by this page |
| RuleView | GET `/queryRuleDetail.json` and `/queryRuleTitleVOS.json`, automatically on page mount | Detail/form page without list headings in this observation; does not prove runtime-list absence |
| RealTimeTaskController | GET `/riskActionTaskQueryDetail.json`, automatically on page mount | Task detail/controller page without list headings in this observation; does not prove runtime-list absence |

The last two pages are not runtime-list positive evidence. Their automatic
detail requests must not be described as a separately tested getter or a list
contract. A rendered page, zero visible DOM rows or absence of a table does not
establish a successful empty API result. Duplicate/fixed table DOM sections also
mean visible row counts are not native record counts.

No independent offers, session or global route list was found in these pages
and the inspected source. The initial runtime-status negative conclusion was
withdrawn after actual menu discovery found TransferRunOverview; see the
correction below. This is a bounded search result, not a claim that no such
capability exists anywhere on the platform.
The wallet-balance gap remains source/membership research; an independent
wallet-balance API was not queried in this round because none was established.

Wallet account inquiries were then freshly repeated at pageSize 1000 and 5000
with wallet=true and false. Both flag values again returned equal ordered rows
at each width. The 1000 query returned 1000/count 3691; the 5000 query returned
3690/count 3691. All rows matched the authorized tenant. Native id had only one
distinct value; accountNo and innerAccountNo were also non-unique, and some
inner-account values were empty. Native accountType values included CA and SVF,
but no source-backed mapping establishes either as the wallet membership
predicate. No wallet-named response field or synthetic identity resolves this.

## Other remaining lists

The PRD crosscheck records the source evidence and dated prior observations for
the following exclusions. Earlier interface probes are distinguished from
fresh page/network observation above; the business endpoints were not all
queried again in this investigation.

| Category | Lists | Why excluded from this batch |
| --- | --- | --- |
| cash | `wallets`, `wallet-balances` | Wallet/non-wallet account rows previously matched; wallet membership and independent balance binding remain unproved |
| operations | `rule-status` | Removed from exclusions after the native TransferRunOverview menu and populated query were discovered; see the correction below |
| investment | `offers`, `quote-sessions` | No independently proven native business object, caller and identity |
| network | `routes` | Per-network route quota detail and route references do not establish a global routes list |
| pricing | `valuations` | Nonempty fee orders belong to the already supported fee-order object, not investment valuations |
| operations | `executions` | Previous bounded daily samples empty; wider scopes failed; no positive record schema |
| investment | `investable-funds` | Prior expanded queries completely empty; excluded by the user's selection condition |
| pricing | `bills` | Prior DEPOSIT/LOAN queries completely empty; excluded by the user's selection condition |
| rules | `treasury-transfer` | Current native business failure, no positive records |
| rules | `monitoring` | HOLD; no investigation or query |

## Specification boundary

The next batch's primary target is a bounded rule-status summary list. Quote
groups remain conditional coverage proof, with a future list/refresh contract.
For quote groups, before implementation can be authorized, establish
an authoritative single-response dictionary scope and coverage contract, or a
genuinely progressing pagination protocol. A frontend options use case, four
equal 54-row responses, or a fabricated total cannot satisfy this gate.

The specification must retain a blocked/no-enable outcome if the gate cannot be
proved. Once it is proved, retain native record identity and versions, settings
semantics, approved projection, independent list caching, hard-failure cache
preservation and ADR 0019 quality behavior. Public CLI + fake CDP + temporary
SQLite remains the test seam; serial production CLI UAT would be a separate
future acceptance step, not a claim made by these native probes.

## Correction: actual rule-status menu and populated native inquiry

The current authenticated GET `/querymenulist.json` returned 207 menu records,
including visible `TransferRunOverview` named 调拨规则状态. This was an actual
CDP inquiry, not a source-only guessed menu. The original PRD page inventory,
document 323959460 line 48, independently describes the transfer-rule running
status screen. Its native page shows Rule Id, Rule Name, Rule Executing Status,
Created Payment, Trans No., Payment Status and Expected Trigger Time.

Native source wrapper at character 1475408 calls GET
`/queryTransferRulePreRunRecords.json`. The summary form in the component at
characters 2640879–2653310 supplies `tntInstId` and JSON-stringified
`transferRuleRecordQueryRequesVO`. The inner VO supplies tenant, rowStart,
pageSize, string `queryDetailed=false`, triggerStartTime/triggerEndTime and
the form's serialized triggerDate; native status/payment selector arrays are
empty. Only the summary query was used. The source's expanded-record action
uses `queryDetailed=true` plus ruleId; it was not queried as a substitute list.

The native summary query was first triggered through the inspected form's
read-only submit handler and its actual network response was read through CDP.
The initial current-day response was genuinely successful and empty. The
source-backed timestamps were then expanded as the user requested:

| Native scope | Page size | Outer / inner success | Rows / count | Unique native IDs |
| --- | ---: | --- | --- | ---: |
| 2026-10-06, native initial UI query | 10 | true / true | 0 / 0 | 0 |
| 2026-01-01 00:00:00 through 2026-10-06 23:59:59 | 5000 | true / true | 194 / 194 | 194 |
| Same expanded scope | 1000 | true / true | 194 / 194 | 194 |
| Same expanded scope, repeated single response | 5000 | true / true | 194 / 194 | 194 |
| January 2026, inclusive timestamps | 5000 | true / true | 150 / 150 | 150 |
| Equal UTC start/end at an observed expected trigger | 5000 | true / true | 4 / 4 | 4 |
| Equal UTC start/end one second before that trigger | 5000 | true / true | 0 / 0 | 0 |
| Equal UTC start/end one second after that trigger | 5000 | true / true | 0 / 0 | 0 |
| 2026-10-06, explicit single-response scope | 5000 | true / true | 0 / 0 | 0 |

The 1000/5000/year-repeat ordered raw arrays were identical. Every populated
year record had a unique positive integer native id and matching tenant.
ruleId was unique in this sample, but that does not make it the record identity
or prove one row per rule for all scopes. bizNo had only 57 distinct values and
may be empty. These are native summary records, not a claim of all individual
executions, payments or expanded history.

### Pagination warning and bounded contract

Page size 30 at offsets 0, 30, 60, 90, 120, 150 and 180 yielded
30/30/30/30/30/30/14 rows, each with count 194. Offset 194 returned zero rows
with count 194. However, the accumulated 194 rows had only **193 unique IDs**
and did not equal the large-response record array. This populated pagination
cannot be used for complete collection; no sorting or backend cause is assumed.

A future release can use one fixed pageSize 5000 / rowStart 0 request within
required trigger bounds, matching the existing bounded demands approach.
Success requires count to be a nonnegative native integer no greater than
5000, returned row count equal to that count, all IDs distinct, and all schema,
tenant and scope checks to pass. Reject overflow or count/identity mismatch
before output or cache publication; narrow the time scope rather than fall back
to this unstable pagination. Unlike quote groups, this inquiry supplies a native
count and the positive single-response sample accounts for it exactly.

### Status and time evidence

Observed executeStatus values were EXECUTED, NON-EXECUTION and
PRE_CONDITION_BLOCK; createdOrder was N/Y; orderStatus included empty, INIT,
PAID and PAYMENT_FAILURE. These are runtime-summary fields, not RUN/PAUSE
configuration. Preserve the distinctions rather than collapsing them to a
generic success flag or inferring payment from execution status.

expectTriggerTime, gmtCreate and gmtModified were 13-digit integer epoch
milliseconds; realTriggerTime was integer epoch milliseconds in 93 rows and
null in 101 rows. expectTriggerDate was an eight-character native string.
The source renders expected trigger time through momentFormatTimeUtc, which
explicitly calls `.utc()`. The point probe and its adjacent empty points agree
with UTC wire timestamps and show inclusive equal endpoints. January records
were within the UTC wire bounds and their IDs were a subset of the year scope.
The browser itself was Asia/Shanghai (UTC+08); browser timezone is not the
meaning of the native UTC wire timestamps. Scheduling timezone in historical
PRDs may belong to the payer-account country and must not be conflated with
this query/display convention.

Future scope validation must apply to expected trigger time, not creation,
modification, actual-trigger or capture time. The raw summary also carries
debitAmount, account aliases, entities, task/order references and environment
metadata. Amount units and extra field semantics were not proved; omit them
from the initial approved projection. No production row values are published.

This evidence makes rule-status worth the next implementation batch, subject
to a precise summary-only specification and later implementation authorization.
No app code, registration, feature PR or production CLI UAT was performed.

## Published specification

[Batch H #122](https://github.com/proletariat64/dogopencli/issues/122) specifies
the bounded rule-status summary list as the primary future implementation target
and quote-group coverage proof as a conditional target. It links parent #72 and
explicitly preserves this round's research/specification-only authorization.
The new local research notes have not been committed or published as a PR.
