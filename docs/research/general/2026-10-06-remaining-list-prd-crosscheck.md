# Remaining Liquidity lists: PRD crosscheck and next-batch candidates

Observed: 2026-10-06
Scope: general
Status: snapshot

Research against master `a27756b414e49d172546a9d14849e132a4dd271e`.
This note performs source inspection only. It does not enable a leaf, create a
specification issue, run business inquiries, or establish production acceptance.
Monitoring remains HOLD and was excluded from investigation. The prior empty
bills and investable-funds scopes were not queried again.

## Recommendation

`operations rule-status list` became the primary next-batch candidate after
fresh CDP menu/query work found a populated native runtime overview. The
[current probe report](2026-10-06-remaining-list-current-probes.md) records
194 counted unique native records and a bounded single-response contract;
its unstable cross-page acquisition must not be used.
`investment quote-groups list` has already observed real rows and an
independent native object. Newly identified
unpaged UI callers provide a concrete path to investigating its snapshot
contract. It remains conditional until declared scope and authoritative
acquisition coverage are proved. A newly located `TransferRunOverview` source
independently confirms the newly located runtime-overview contract; source
inspection alone does not prove its positive data or count coverage.
No additional leaf is currently enabled or fully qualified by this source-only
review. Grouping deferred candidates into one tracker must not
convert missing identities, business failures, or empty schemas into delivery.

## Discovery and primary sources

Read-only `graphify query` against the existing
`~/dev/dogpdkb/graphify_flatten_ready` graph preceded original-source inspection.
Queries for Wallet, routing, Liquidity and quotation groups returned broad or
unrelated nodes; graph similarity to FX groups was not used as Liquidity proof.
The graph was not rebuilt. Literal inspection of the owning Liquidity product
documents closed these discovery gaps. The code-review graph reported the
current repository HEAD and indexed branch as master at `a27756b`; no application
code changes were needed.

Primary document citations below refer to original files under that knowledge
base directory. Their archive filename dates do not prove present deployment:

- P1: `Liquidity__平台介绍__Liquidity-Product-of-Global-Fund-Platform-Whitepaper__国际流动性产品白皮书-2026-06-29-[197368565].md`,
  lines 385–409: rule configuration, triggering, tasks, transfer orders and
  receipts are separate business objects. Lines 735–753: bank inquiry, product
  definitions, investment trades, holdings and valuation are distinct stages.
- P2: `Liquidity__产品规划__CY25__流动性产品思考及规划__流动性CY25-S2产品规划-2025-11-13-[460449362].md`,
  line 54: quotation-group management precedes inquiry rules, inquiry email,
  returned quote import and negotiation. This directly supports quotation
  groups as configuration, not quotes or generic sessions.
- P3: `Liquidity__产品规划__CY26__CY26流动性产品思考及规划-2026-08-18-[490870296].md`,
  line 5: the product workflow is group management, inquiry, quote, negotiation,
  then winning. It also records that the contemplated external trading system
  did not land; planning cannot establish a native offer/session executor.
- P4: `资金方案中心管控__重点项目__结算融合支持WF-AB户__结算融合支持WF-AB户-资金平台-2026-04-18-[86557476].md`,
  lines 77, 117 and 123: wallet-account settlement is a distinct recipient
  account type. This settlement semantics does not establish the membership
  predicate of Liquidity's current wallet-account list.
- P5: `收付款产品__调拨中心产品化能力建设__运营能力建设__运营透明度提升-路由决策状态查询-2026-04-19-[168871821].md`,
  lines 84 and 118: routing traces are queried per transfer document. This is
  not evidence of a global route-configuration list.
- P6: `TB-center__资金平台专业分享__Learning-Training-materials__资金平台能力基线__国际资金平台产品基线__分产品域描述__流动性中心__流动性运营中心-2020-12-18-[19155370].md`,
  lines 286–287: historical investment management was pending design. Current
  UI source and current populated observations take precedence over that
  historical gap; it cannot disprove the modern group object.
- P7: `Liquidity__产品规划__CY24__流动性平台页面梳理-202402-2024-03-13-[323959460].md`,
  line 48: the rule-status page queries the running state of balance-based and
  demand-based transfer-rule operations. It is recorded as running/in use.
  Lines 42 and 44–45 distinguish automatic decision-operation records and
  rule configuration. P1 lines 340–342 also enumerate the rule-status menu.
- P8: `Liquidity__产品规划__FY21__国际流动性产品白皮书-2026-04-18-[83866045].md`,
  lines 301–316 and 338–353: rule configuration defines schedule/trigger
  conditions; automatic and demand-driven rules differ. The historical default
  rule timezone is the paying account's country timezone, not a general
  guarantee that runtime inquiry timestamp strings use GMT+08.

## Newly found quote-group callers

Local private source: `.qoder/research/batch-g-20261006/umi-current.js`, SHA-256
`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`.
The digest was recomputed in this review. This minified source is cited by
zero-based character offsets and original source lines; only fixed inquiry contract fragments
and field names are reproduced, not records or contact data.

The `oW` export wraps `g` at chars 1529458–1529620 (line 35):

```javascript
function g(ce) {
  return (0, A.request)("/queryQuotationGroup.json", {
    data: ce, method: "post", type: "json", skipErrorHandler: !0
  });
}
```

The `dWt` search-control component at chars 9890933–9892040 (line 690) stores an independent
options population `c`, initially empty, using setter `u`. Its initial hook
starts at char 9891915:

```javascript
(0, e.useEffect)(function () {
  (0, zf.oW)({}).then(function (p) {
    if (p.success) return u((p == null ? void 0 : p.data) || []);
    u([]);
  });
}, []);
```

This is a real JSON POST with an empty object. The caller adds no tenant,
paging or search selector. It is distinct from the table component `mWt`, whose
list caller expects `data`/`totalCount` and inserts `rowStart`/`pageSize`.
Nothing in this discovery authorizes guessed fields or a different tenant.

The local option logic selects from `c` using `filter` and `forEach`:

- Group-ID options filter by selected `bankId` and `quotationGroupName`, then
  push `quotationGroupId`.
- Bank options filter by selected `quotationGroupId` and
  `quotationGroupName`, then push `bankId`.
- Group-name options filter by selected `quotationGroupId` and `bankId`, then
  push `quotationGroupName`.

The add/detail form has a second `oW({})` caller at char 9902204 (line 690). It stores
`data` with setter `St`; at chars 9902305–9902600 (line 690) the validator
uses `yt.some(function(Ki){return Ba===Ki.quotationGroupName})` to detect
duplicate names when `!dn.id`. Only this source behavior is recorded; no add or
update request was issued.

These independent unpaged callers support the interpretation that the frontend
intends to load one configuration dictionary for options and name validation.
This is an inference about client intention. Neither caller supplies a server
promise against truncation, a reported count, or a terminal marker. Comparing
its native response to the paged caller is worthwhile evidence work; matching
54 records alone would still not establish authoritative coverage.

The [earlier populated investigation](2026-10-04-liquidity-batch-a-quote-groups-investigation.md)
reported 54 string `id` values, 48 logical `quotationGroupId` values and 54
group/version tuples. Therefore preserve each native record and version; do not
collapse by group ID or manufacture identity from a display label. Public/cache
projection should start with `id`, `quotationGroupId`, `quotationGroupName`,
`bankId`, `status`, `version` and verified configuration timestamps. Verify
tenant identity separately. Exclude contacts, contact lists, operator identities,
free text, attachment/download links and operation histories. Configuration
modification time is separate from `fetched_at` and is not a runtime observation.

## Correction: an actual rule-run overview caller exists

The earlier statement that no independent rule-status caller was established
was too broad. The coordinating investigator discovered the current native
`TransferRunOverview` menu, labelled 调拨规则状态, with `showState=Y`.
This note did not itself query the menu or perform CDP probing. Inspection of
the same saved UI bundle independently confirms the native caller and table,
and P7 directly identifies its intended business meaning. This source evidence
supersedes the earlier no-caller claim in this note and the corresponding dated
Batch F source conclusion; populated runtime acceptance remains separate.

Module 43401 exports `Or`, wrapping `W` at approximately char 1475408
(line 35):

```javascript
function W(e) {
  return (0, w.K)("/queryTransferRulePreRunRecords.json", {data: e});
}
```

Component `tu`, chars 2640879–2653310 (line 116), is wrapped as
`bu=T.A.create()(tu)` and exported as `gB2`. The native query reads outer
`tntInstId` and JSON-string `transferRuleRecordQueryRequesVO` (preserve this
source spelling). Its ordinary search/page handlers set inner `tntInstId`,
`rowStart`, `pageSize`, `queryDetailed:"false"`, `triggerStartTime`,
`triggerEndTime`; initial status selections are empty native arrays
`executeStatusList`, `createdOrderList` and `orderStatusList`. The date-picker
formats `YYYY-MM-DD HH:mm:ss` and defaults to today's 00:00:00–23:59:59.
These are trigger-window fields, not the supported task caller's
`startExecuteTime`/`endExecuteTime`. Do not insert guessed task source filters.

The summary handler accepts `resultFlag` and consumes `result.data` as
`transferRuleRecordList`, with `result.count` as the table total. Paging uses
`rowStart=(current-1)*pageSize`. Its explicit visible fields are:

| Field | Native label / meaning established by source |
| --- | --- |
| `ruleId`, `ruleName` | Rule Id, Rule Name |
| `executeStatus` | Rule Executing Status |
| `createdOrder` | Created Payment (`Y`/`N`) |
| `bizNo` | Trans No. |
| `orderStatus` | Payment Status |
| `expectTriggerTime` | Expected Trigger Time, rendered via `momentFormatTimeUtc` |
| `businessType` | Business Type |

The UI enumerates executing statuses `NON-EXECUTION`, `TRIGGER_TIMEOUT`,
`PRE_TASK_BLOCK`, `PRE_CONDITION_BLOCK`, `EXECUTED`, and payment statuses
`INIT`, `SUBMITTED`, `SUBMITTED_FAILURE`, `PAID`, `PAYMENT_FAILURE`,
`RECEIPTED`, `RECEIPT_FAILURE`. These literals establish source vocabulary,
not proof of returned current rows or a complete state machine.

Expanded rows use the same endpoint with `queryDetailed:"true"`, the selected
`ruleId`, the same trigger window, offset zero and width 1000, and load
`result.data` into nested `transferRuleRecords`. Therefore ordinary summary
rows and expanded underlying records are different native projections. The
summary is a rule-run overview; source alone does not determine whether each
row represents a rule, one expected trigger occurrence, an aggregate, or a
representative execution. Do not call each summary row an actual transaction
or one completed execution. `NON-EXECUTION` and `createdOrder=N` explicitly
allow observations without a generated payment.

Before a spec qualifies this candidate, establish populated native summary
records, returned types and true row grain, a native unique identity, stable
count units and a progressing or authoritative bounded acquisition. Column
`key` declarations do not prove identity; neither `ruleId` nor `bizNo` may be
assumed unique, and a constructed rule/time tuple is not a substitute for
native proof. The source supplies no explicit table `rowKey` for this summary.
Verify whether the trigger filters select `expectTriggerTime` or another
native timestamp, inclusive/exclusive boundaries, and the actual source
timezone/encoding. A helper name containing `Utc` and browser-local picker
defaults do not resolve that contract. Preserve future expected triggers as
expected times, independently of actual execution and `fetched_at`.

The first list scope should retain the sourced summary projection
`queryDetailed:"false"`; expanded queries, nested account identifiers and
getters are separate scope. A positive summary response alone cannot waive
identity/coverage/time gates or replace independent production CLI UAT.

## Candidate qualifications

| Remaining list | Business object and current evidence | Next-batch treatment |
| --- | --- | --- |
| `investment quote-groups` | Versioned quotation-group settings; 54 previously observed real records. Two native unpaged callers found above. | Primary conditional candidate: investigate authoritative snapshot semantics and current scope/identity before implementation. |
| `cash wallets` | Native `QueryWalletAccount` fixes `wallet=true` on `/queryintnalbkactlist.json`; source chars 6415995 and 6418702. Its table labels Wallet A/C No. and exposes ordinary account fields, not a proven membership discriminator. | Defer: the [existing comparison](2026-10-06-batch-f1-wallet-contract.md) found identical wallet/non-wallet rows and unusable native IDs. UI wording and account fields do not repair this. |
| `cash wallet-balances` | `/querybalancelist.json` wrapper and account-balance caller exist at chars 1487006, 1545425 and 2691638; the native VO is `accountBalanceQueryVO`, without a wallet-bound predicate in that caller. | Defer: independent wallet membership, balance identity, currency/amount and observation time are unproved. An account balance is not automatically a wallet balance. |
| `operations rule-status` | P7 explicitly defines the rule-status page; `TransferRunOverview` has a real `/queryTransferRulePreRunRecords.json` summary caller and native execution/payment/expected-trigger fields, detailed above. | Conditional evidence candidate: qualify populated summary grain, native identity, trigger time scope and count/paging. Earlier no-caller claim is retracted; RUN/PAUSE configuration and decision tasks remain different objects. |
| `investment offers` | Product definitions, institution inquiries, returned quotes, negotiation and winning are separate in P1–P3. | Defer; no independently dated acceptable-offer object/caller/identity is proved. Existing quotes alone do not establish an extra leaf. |
| `investment quote-sessions` | RFQs, sub-inquiries and group configuration are observed objects; none establishes separate session granularity. | Defer; require native session identity, lifecycle and inquiry/quote relationship, or an explicit naming/scope decision. |
| `network routes` | Native `/queryWhaleRouteDetail.json` wrapper at char 1501759; caller at 4398031 sends `routeId`, `aliasName`, `tntInstId` and consumes `result.data.dynamicQuotas`/`staticQuotas`. P5 is transfer-document routing trace semantics. | Defer; network quota detail and network-row route references do not establish a global route-settings list or ending protocol. No detail probe performed. |
| `operations executions` | Independent instruction/realtime task sources share `/riskActionTaskQuery.json`; known sources have empty daily samples and business failures for wider scopes. | Exclude from populated implementation scope until a positive source sample proves identity/status/time/scope. Failures cannot count as empty. |
| `rules treasury-transfer` | Native list contract exists, but current research records a business failure and no populated rule schema. | Exclude until current successful populated native inquiry and privilege evidence exist; no privilege bypass or guessed selector. |
| `pricing valuations` | P1 locates valuation in investment holdings, not service fee orders; no independent valuation caller is established. | Defer; supported fee-orders cannot be renamed as valuation. |
| `pricing bills`, `investment investable-funds` | Prior scoped probes were completely empty and no populated schema is qualified. | Exclude from this requested batch; do not repeat the empty ranges. |
| `rules monitoring` | HOLD. | Excluded entirely. |

The current dated probe evidence is recorded in
[Batch G current probes](2026-10-06-batch-g-current-probes.md) and the
[Batch F wallet](2026-10-06-batch-f1-wallet-contract.md),
[rule-status](2026-10-06-batch-f2-rule-status-contract.md),
[investment](2026-10-06-batch-f3-investment-contract.md) and
[routes](2026-10-06-batch-f4-routes-contract.md) notes. This review reread those
reports but did not rerun their native queries; their counts are dated evidence,
not a live refresh by this note. The Batch F rule-status no-caller conclusion
has been corrected above using current menu discovery, saved primary UI source
and P7; it must not be treated as the latest source inventory.

## First-enable gates

For the group candidate, first prove the exact unpaged request's safe query
behavior and native success/envelope, declared authorized scope, unique native
record identity including version history, and authoritative single-response
coverage or a progressing pagination protocol. An options dictionary's intended
use and repeatable record equality are corroboration, not a manufactured total.
Freeze the approved public projection and keep sensitive nested fields out of
output, cache and fixtures. A proposed spec must retain a no-enable outcome when
coverage or scope remains unproved.

Once that evidence exists, any enablement still requires focused fake-transport
checks, independent list cache behavior, empty-scope/hard-failure preservation,
strict/incomplete behavior under ADR 0019, and independent serial production CLI
acceptance. For other leaves, positive records alone would not waive the
business-object, native identity and acquisition gates. Source research or
closing an investigation is not delivery.
