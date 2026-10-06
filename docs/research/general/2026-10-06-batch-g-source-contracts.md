# Batch G source contracts and first-enable evidence

Observed: 2026-10-06
Scope: general
Status: snapshot

This note covers six remaining list candidates against master `6f0fbae`.
Current production results and public CLI UAT are recorded in
[the current probe report](2026-10-06-batch-g-current-probes.md).
It does not authorize mutation, broaden tenant access, or enable an inquiry.
Monitoring remains HOLD. Historical failures and empty results are not current
production results.

## Primary product documents

Knowledge-base discovery used read-only `graphify query` for liquidity, funding
requirements, execution tasks, quotation groups and investment management in
`~/dev/dogpdkb/graphify_flatten_ready`. The graph was not rebuilt or saved.
`QuotationGroup` had no matching node; graph similarity to FX quotation does not
establish a Liquidity quotation-group contract. The original documents below
were then read directly. Source filenames are archive identifiers, not current
production dates.

P1: `Liquidity__平台介绍__Liquidity-Product-of-Global-Fund-Platform-Whitepaper__国际流动性产品白皮书-2026-06-29-[197368565].md`,
under the knowledge-base directory above. Lines 385–409 distinguish configured
rules, funding requirements, generated tasks, transfer orders and receipts.
Lines 735–749 distinguish bank inquiries, investment products and trades.
Lines 1039 and 1128–1136 distinguish FTP service pricing, ledger balances,
profit/loss records and customer billing. These are product meanings, not
endpoint, populated schema or present capability proofs. In particular, service
fee orders cannot be labeled investment valuations.

P2: `TB-center__资金平台专业分享__Learning-Training-materials__资金平台能力基线__国际资金平台产品基线__分产品域描述__流动性中心__流动性运营中心-2020-12-18-[19155370].md`.
Lines 9–12 distinguish cash investment, borrowing and cash pools. The historical
investment-management section at lines 286–287 says design pending; it cannot
establish current native behavior.

## Native requests from saved UI source

The saved, locally read production bundle is private evidence from the previous
Batch C investigation (`umi-current.js`). No browser was used for this source
research. Character offsets below identify the saved source and must be
reconfirmed against the current bundle before first enablement. Only contract
field names and fixed public tenant/type values are published here.

| Leaf | Native request and scope | Native response | Source locations |
| --- | --- | --- | --- |
| `operations demands list` | GET `/riskActionTaskQuery.json`; outer `tntInstId=GUAPW3SG` and JSON-string `riskActionTaskQueryVO`. Inner VO contains the same tenant, `source=["FUND_REQUIRE"]`, `rowStart`, `pageSize`, `startExecuteTime`, `endExecuteTime`. | `resultFlag`, `result.dataValue`, `result.count` | model 1833557; caller 7150000–7155300 |
| `operations executions list`, instruction | Same inquiry; `source=["INSTRUCTION_ACCOUNT_FLOW","INSTRUCTION_ACCOUNT_FLOW_MANUAL"]`. | Same envelope | same caller; separate instruction model |
| `operations executions list`, realtime | Same inquiry; `source=["REAL_TIME_INITIATIVE_SUPPLEMENT","REAL_TIME_PASSIVE_SUPPLEMENT","REAL_TIME_INITIATIVE_COLLECTION"]`. Do not merge these variants or expand with guessed types. | Same envelope | native `handlePageSearch` around 7153900 |
| `investment quote-groups list` | JSON POST `/queryQuotationGroup.json`; `pageSize`, `rowStart`, initially 10/0. UI navigation uses `(current-1)*pageSize`. | top-level `data`; UI expects `totalCount` | wrapper 1529440; list caller around 9893934 |
| `pricing bills list`, deposit | Form POST `/accountBookQuery.json`; outer `tntInstId=GUAPW3SG`, JSON-string `clientBillQueryVO={rowStart,pageSize,type:"DEPOSIT",billingStartDate,billingEndDate}`. | `resultFlag`, `result.data`, `result.count` | wrapper 1500576; model 1879283; caller 5389632 |
| `pricing bills list`, loan | Same inquiry and fields, with `type:"LOAN"`. Each accepted type needs independent nonempty evidence. | Same envelope | caller 5400204 |
| `rules treasury-transfer list` | GET `/queryTreasuryTransferRuleList.json`; outer `tntInstId=GUAPW3SG`, JSON-string `transferRuleQueryRequest={rowStart,pageSize,tntInstId:"GUAPW3SG"}`. Initial width 10. No ordinary-transfer entity arrays are established by this caller. | `resultFlag`, `result.transferRuleVOS`, `result.ruleCount` | wrapper 1475579; model 1917817; caller 3193701–3194500 |

Task sources are arrays, not comma-separated strings. UI defaults use
`YYYY-MM-DD HH:mm:ss`, from 29 days before today at midnight to tomorrow at
midnight. The selected-date renderer contains `HH:ss:mm`; this source typo is
not a verified time contract. Midnight probes avoid that ambiguity, but actual
timezone, boundaries and returned row membership still need evidence.

Bills dates are native `YYYYMMDD`. The default is three months ago through
today. No inner tenant field or timezone is inserted by the bill caller. The
UI displays a billing period using `startDate` and `endDate`, not a single
record date. Deposit columns include average deposit balance/rate and total
interest; loan columns include average loan amount/rate and total fees. Native
values must be preserved, without invented percent scaling. A successful empty
response does not establish identity, amounts or periods.

Task tables label `taskId` as Task ID, treasury tables label `ruleNo` as Rule ID.
Column `key` declarations are not native table `rowKey` declarations, and neither
static label proves uniqueness of unseen records. The inspected bill tables do
not establish a bill ID. These observations constrain the next probe; they are
not sufficient for a production schema.

## Remaining first-enable gates

The [quote-group investigation](2026-10-04-liquidity-batch-a-quote-groups-investigation.md)
already observed 54 nonempty rows but repeated offsets and absent total/ending
proof. An identical larger page alone cannot prove an authoritative full
response. Unique sampled `id` is promising, while `quotationGroupId` spans
versions; preserve distinct records and prove declared scope and termination.
Contact details, operator information, attachment/download links and operation
histories are excluded from any proposed public/cache projection.

The [operations contract](2026-10-03-liquidity-issue82-operations-contract.md)
records empty single-day queries and wider-query `099` database failures.
Populated dated scopes, unique identity, execution-state meanings and complete
acquisition remain required. No permission or business failure becomes empty.

The [Batch C gates](2026-10-04-liquidity-batch-c-gates.md) record empty DEPOSIT
and LOAN queries, including broad history. More bounded pages/date probes can
find evidence but cannot replace it. Current identity, period interpretation,
amount/currency evidence and independent public CLI UAT are still required.

Treasury-transfer historically returned a named missing-privilege failure in the
[native probe report](2026-10-01-liquidity-live-probes.md). Recheck only the native
inquiry under the authorized tenant; do not guess alternate privilege/tenant
selectors or treat failure as a zero-row population.

`pricing valuations list` has no verified investment valuation source in this
research. `/getFeeOrderList.json` is already represented by the shipped
`pricing fee-orders list`; an alias would not add the missing business object.

[ADR 0019](../../adr/0019-usable-incomplete-acquisitions.md) allows truthful
incomplete results for verified enabled inquiries. It does not erase the
existing first-release identity, scope, completeness-protocol and UAT gates.
No application code, issue or capability registration was changed by this
source-only research.
