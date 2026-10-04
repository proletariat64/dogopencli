# Liquidity batch C: verified strategy results and remaining gates

Specification: [issue #89](https://github.com/proletariat64/dogopencli/issues/89).
Baseline: `f8ada67215d164a745817a1627672639c7028002`, version `0.2.5`.
Actual enabled/target lists: **1/4**. Strategy variants accepted: **2/2**.
Integration baseline after #87/#88: `045c3840cd072a1b6e8e3f72881bbb5b4bb0bd33`.
Catalog: **74 supported / 59 unsupported** query leaves. #89 stays open.

## Production browser and source evidence

The user confirmed issue #88 had finished and CDP **9223** was free. Independent
Liquidity authorization passed on the existing dedicated browser; the control
lock was idle. All requests used the existing restricted transport and browser
coordination. Cookies, tokens, profiles and production records are absent from
this report and Git. Private UAT caches and count/type-only summaries stay under
ignored `tmp/issue89/`. No forbidden CDP ports were contacted.

Current UI scripts were read from the authorized PortfolioMgmt page. The
observed static bundle was 15,763,128 bytes:
`https://gw.alipayobjects.com/render/p/yuyan/180020010000002482/S090011910164/umi.js`.
The relevant UI callers establish inquiry semantics, methods, encodings and
native request scope. No mutation caller was invoked.

| List | Current native evidence | Release decision |
| --- | --- | --- |
| benchmark-values | JSON POST `/queryStrategyBenchmarkList.json`; 20260928–20261004 reports 165, first 10 rows nonempty; all 10 native `id` values blank. Fields: id, strategyBenchmarkType, currency, colorType, effectiveDate, value; native renderer appends percent | Unsupported: no verified usable native identity; private candidate collection failed `INVALID_RESPONSE`, publishes nothing. Do not guess a composite from display columns |
| strategy-results | JSON POST `/api/increment/decision/task/queryPage.json`; fund 50/50 in five pages; product 7/7 in one page; independent nonempty native identity/type/time/amount evidence | Enabled for both explicit task variants with required trigger bounds |
| valuations | Query GET `/getFeeOrderList.json`; current and September scopes empty, August 20260801–20260831 returns 2/2 fee orders. Native tab is Efficient Service; fields include feeAmount, pricingCurrency, transAmount, serviceDate, bizOrderNo, id | Unsupported: fee-order semantics conflict with valuation naming. Nonempty records do not waive that gate |
| bills | Form POST `/accountBookQuery.json`; DEPOSIT current 90-day and 20200101–20261004 scopes empty; LOAN broad history also empty | Unsupported: neither type has first-release nonempty identity/amount/currency/period evidence |

The broad fee-order 20200101–20261004 request returned business failure, while
bounded August succeeded. No large-window fallback is enabled. Pricing findings
are investigation evidence, not production UAT acceptance of a CLI contract.

## Enabled strategy contract

Both current native task callers use `tntInstId=GUAPW3SG`, `rowStart` offsets,
`pageSize=10`, JSON POST, success envelope, `data.data` rows and `data.totalCount`.
The selector is explicit `FUND_DECISION_TASK` or `PRODUCT_DECISION_TASK`.
Both `--trigger-from` and `--trigger-to` are required YYYYMMDD dates. Their native
wire values are YYYY-MM-DD 00:00:00 and YYYY-MM-DD 23:59:59 in GMT+08.
The native task `id` is used by the UI detail link; separate strategy IDs are
references. Identity is typed `(taskType, id)` within tenant and exact scope.
No detail endpoint is enabled by this work.

`triggerDate` and `resultTime` are epoch milliseconds. `valueDate` and expected
investment start/end are separate YYYYMMDD business dates. Native trigger dates
are checked against the requested GMT+08 day range before publication/output.
A history profile preserves each exact task type and trigger range; capture time
never supplies business-time coverage. Existing per-leaf retention includes all
variants and captures under the same 1,000,000-record ceiling.

Public/cache projection preserves 16 observed business fields, native decimal
strings, trailing precision, null, empty string and zero. `investmentAmount`
is labeled Investable Amount equi.USD in both native UIs. Product
`maximumExceptedIncome` is labeled Maximum Expected Interest Income equi.USD;
its fund unit and `maximumExpectedRateOfReturn` unit remain unknown. The native
rate UI binds another field, so it does not establish the latter's unit.
No local currency conversion, return calculation or state interpretation occurs.
Strategy status does not prove execution or realized income. `decisionUser`,
`mainStrategyVo` and unknown free text are stripped before cache or public output.

## Registered public CLI production UAT

On 2026-10-04, the actual registered CLI, isolated cache and CDP 9223 passed
independently for both task types with trigger range **20260706–20261004**:

| Variant | Reported / unique records | Pages | Result |
| --- | --- | --- | --- |
| FUND_DECISION_TASK | 50 / 50 | 5 × width 10 | complete=true, missing_count=0, strict refresh published |
| PRODUCT_DECISION_TASK | 7 / 7 | 1 × width 10 | complete=true, missing_count=0, strict refresh published |

Each passed strict refresh, full cached read, disconnected full cached read
(the transport factory rejects any browser contact), and strict full live read:
**8/8 public CLI commands**. Offline record identities/content and fetched_at
matched the same committed capture. Both live reads preserved the SQLite file
byte for byte. Each cached record excluded private user/nested free-text fields.
Completeness uses the unchanged collector's raw-arrival = unique = reported
reconciliation, with fixed totals, no conflicts and no duplicate tolerance added.
Different-time live and refresh records are not used as an equality proof.

Additional single-day CLI UAT on native **20260918** passed: fund **21/21**
in three pages and product **2/2** in one page, strict and nonempty with the
GMT+08 scope validator. Both left cache bytes unchanged. The stored acquisition
metadata separately reports arrivals/unique/reported = **50/50/50** and
**7/7/7**, duplicate_count=0 for both committed captures.

Private sanitized evidence: `registered-uat-summary.jsonl`,
`native-probe-summary.jsonl`, `history-probe-summary.jsonl`, and
`bounded-probe-summary.jsonl`, `day-scope-summary.jsonl`, and
`acquisition-evidence-summary.jsonl` under ignored `tmp/issue89/`.

## Local validation and review

The public CLI + fake CDP + real temporary SQLite tests cover both registered
variants: native date mapping, invalid scopes before contact, precision and
privacy, exact variant/cache isolation, complete empty captures, live cache
isolation, default/strict partial behavior, conflicting identity, fixed-total
drift, authentication/business failures, wrong tenant/type/date and old-cache
preservation. Unsupported discovery/refusal covers the three remaining leaves.
Offline describe checks native units and unknown units separately by variant.
Snapshot counts and README reflect the actual registry. Existing shared
collector/store/retention tests remain the regression gates.

Checks use `rtk proxy env PYTHONPATH=src
/home/ubuntu/dev/dogopencli/.venv/bin/python -m pytest`, existing global Ruff,
and `rtk proxy git diff --check`. There is no configured typechecker.

| Check | Result |
| --- | --- |
| Focused registered CLI, unsupported gates, snapshot and documentation | 75 passed, 20 subtests passed |
| Full pytest | 1,984 passed, 1 skipped, 28 subtests passed; one stale catalog-count assertion failed |
| Failed-case rerun (`--lf -q`) | Passed after correcting 51 → 52 registered list leaves |
| Catalog unit tests + documentation guards | 23 passed, 20 subtests passed after the count correction |
| `rtk proxy ruff check .` | Passed |
| `rtk proxy ruff format --check .` | Passed, 274 files formatted |
| `rtk proxy git diff --cached --check` | Passed |
| Offline snapshot | 74 supported / 59 unsupported |

Local Kimi used the existing installed CLI in prompt mode with
`--output-format stream-json` and explicit `/code-review`, against actual
`origin/master` **045c384**. The first broad review stalled and was stopped;
it is not acceptance evidence. A bounded production-diff review completed
with **exit 0** and final structured JSON. The CLI interleaved subprocess stdout
into its stream; the raw output is retained in `kimi-review.raw.log`, and the
34 JSON event records were normalized into parseable `kimi-review.jsonl`.
Kimi independently ran Ruff lint and formatting successfully; it did not duplicate parent pytest
or run production UAT. No Greptile command was used.

Standards: two low-severity judgement calls only (in-place date-hook consistency,
and path-derived shared release name). Kimi explicitly confirmed correct
behavior; no documented-standard breach or correctness fix was identified.
Spec: no findings; tenant, inquiry contract, identity, date/variant scope,
projection/privacy, gated leaves and exact history cache keys were traced.
**confidence: 4/5**: verified source paths and Ruff gates; the full suite was
still pending during review and Kimi did not rerun production UAT. Review
output is retained privately in ignored `tmp/issue89/kimi-review.jsonl` and
`kimi-final-review.json`.

The final automated evidence covers all 1,986 collected cases: 1,985 pass
across the full run plus the corrected failed-case rerun, and one is skipped.
The full 18-minute run was not repeated after the test-only catalog-count fix;
production code was unchanged. The count test now also reaches its loop that
validates every shipped native contract.

The branch was fast-forwarded to completed #87/#88 before the final local gates.
All shared registrations, projections and schema evidence were preserved when
applying the saved #89 edits. There is no full #89 completion, version bump,
publication or issue closure.

## Remaining decisions

- Benchmark: obtain a native usable identity contract for the populated records,
  then prove complete collection and separate registered CLI UAT. Display-column
  combinations, hashes and row ordinals are not replacement identity evidence.
- Valuations: propose a separate inquiry name such as `pricing fee-orders list`,
  with an explicit compatibility decision for the existing unsupported valuations
  leaf. Do not rename or enable it silently in this batch. Reverify amount/date
  semantics, complete collection and CLI UAT after that decision.
- Bills: obtain an authorized populated native type/period scope, verify each
  accepted type independently and run complete collection plus CLI UAT.

ADR 0019 usable partial results apply to enabled inquiries; they do not lower
any remaining first-release prerequisite. No new get/history was added.
