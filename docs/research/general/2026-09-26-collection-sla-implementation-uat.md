# Collection SLA implementation and acceptance

Observed: 2026-09-26
Scope: general
Status: snapshot

Specification: [#27](https://github.com/proletariat64/dogopencli/issues/27). Tickets: [#28](https://github.com/proletariat64/dogopencli/issues/28) → [#29](https://github.com/proletariat64/dogopencli/issues/29). Draft PR: [#30](https://github.com/proletariat64/dogopencli/pull/30).

## Work plan

- [x] Create isolated PR branch and draft PR; preserve master and prior research.
- [x] Recheck native production list/detail inquiry contract on dedicated CDP 9222.
- [x] Implement #28 in its own worktree; merge reviewed commit to PR branch.
- [x] Verify #28 core through public CLI and read-only production queries.
- [x] Implement #29 in its own worktree after #28; merge to PR branch.
- [x] Reconcile every exposed argument with public-CLI SIT and read-only UAT evidence.
- [ ] Run required gates and full suite, perform standards/spec review, fix findings.
- [ ] Update PR description, mark ready only when acceptance complete, clean implementer worktrees.

## Boundaries

Production business operations remain inquiry-only. Browser port 9222 only; never 9330–9340, including tests. Native Search and Details plus their verified query requests are allowed; no business create/edit/approve/delete/sync or data upload. Production rows and credentials remain out of artifacts and logs. UAT uses a temporary local cache and existing records; only sanitized outcomes are retained. Incomplete or blocked cases are not passes.

## Evidence

Current read-only recheck used native Search on the observed collection SLA page: HTTP 200, success=true, pageNo=0/pageSize=10, totalCount=55. A verified unfiltered pageNo=0/pageSize=1000 replay returned 55 rows, 55 unique nonempty string slaConfigId values, matching totalCount.

Native Details navigated to the observed `/receivedPayment/sla/fundInSla/view` route. With unrelated bootstrap calls intentionally blocked, no automatic detail response was captured before explicit replay. Replaying the historically native-verified exact detail endpoint for one current list ID returned HTTP 200, success=true and a nonempty resultData whose ID and all shared fields matched the list. The list-only viewProcessInstanceRequired difference remains. This sample is a contract recheck, not all-detail implementation UAT. No business writes or raw response artifacts were produced.

Historical contract: [collection SLA research](2026-09-23-collection-sla-query.md).

## Core production UAT (#28)

On PR merge commit `925f1db`, the public CLI passed 108 core cases using a private temporary SQLite cache and the existing dedicated CDP9222 session. Actual list and atomic refresh each returned the current 55 configurations; all55 cached details were individually queried and their IDs checked in memory. No IDs, entity values or raw output are retained here. The disposable cache is separate from the operator's normal cache.

Live get matched the corresponding actual cached detail. The local cache file digest was unchanged across live get/list. Offline cases used an unreachable CDP setting (9223) without stopping/restarting the real browser; they succeeded without browser availability. Freshness rejection used only a temporary config TTL of zero, restored afterwards. No production state was altered to manufacture failures.

An initial sandbox-limited attempt failed while touching the dedicated profile's existing coordination lock, before any query. The authorized rerun permitted that local lock access and passed. This is an execution-environment limitation, not a production authentication or business error. Partial first-run output was not counted as accepted UAT.

| Public surface | Executed acceptance | Outcome |
| --- | --- | --- |
| `list` default, `--live` | Default offline; live complete list; live digest unchanged | Pass |
| `get --id`, `--live` | Every one of55 cached IDs; one live detail equals its cached record | Pass |
| `refresh collection sla` | Complete list + every detail; atomic successful publication verified by subsequent reads | Pass |
| list `--limit` | Nondefault1, zero rejected; default100 handled by default list | Pass |
| list `--offset` |1 and end-of-list boundary; negative rejected | Pass |
| list `--all` | Full output; explicit limit/offset conflicts rejected | Pass |
| list/get `--require-fresh` | Fresh success; stale allowed by default; explicit stale requirement fails CACHE_STALE | Pass |
| list/get `--require-complete` | Actual complete scope/detail succeeds; incomplete failure branch proven in synthetic SIT | Pass; no production corruption |
| list/get `--format` | Explicit JSON and table | Pass |
| list/get `--fields` | Single/multiple raw fields, metadata preserved; empty selection rejected | Pass |
| get `--id` validation | Missing/empty rejected locally; list-only flag rejected on get | Pass |
| command `--help`, `-h`, `help PATH` | List/get/refresh parity; JSON default and text help; offline execution | Pass |
| `describe ... --format` | List/get, default/explicit JSON and text; description help offline | Pass |
| bare navigation | collection, collection sla, collection sla configs, refresh collection | Pass |

Business leaves do not inherit authentication-only `--config-dir`, `--verbose`, `--quiet`, `--no-color` or `--version` options; no such new globals were added. Config selection for UAT used the existing environment-variable contract. Final help inventory and any new filter arguments are reconciled after #29.

Core SIT: 114 passing focused tests across collection SLA, payment SLA and collection cost; documentation guard tests9 passed/15 subtests. Core Ruff and format checks passed. Synthetic SIT covers failure/interruption retention, restrictions and envelope anomalies that were not deliberately created in production. Final suite and review remain pending until the filter slice is integrated.

## Filter UAT and final argument reconciliation (#29)

On merged commit `66f6581`, 28 additional filter cases passed using the same real refreshed local snapshot and explicit production read-only queries. For each of `--business-line`, `--entity`, `--currency` and `--region`, cached and live single-value and repeated-argument queries matched the expected literal local predicate. Empty values were rejected; local nonmatches returned empty data. Cross-field AND and filtering-before-windowing passed.

The current55-row snapshot has1 distinct businessCategory,7 legalEntityCode values,10 creditorCurrency values and10 creditorRegion values. Business-line repetition consequently used the same existing value twice; differentiated OR/case/literal-star/null/missing-field behavior is independently demonstrated with synthetic public-CLI SIT. Do not infer backend business-line selectivity from this dataset. No production values are recorded.

Eight supplemental cases passed for explicit JSON help and rejection of five authentication-only flags on the business list command. One cached missing-detail case returned NOT_FOUND without contacting production. Three projection checks confirmed existing shared behavior: unknown field names are omitted, while valid requested fields remain; empty selection syntax is rejected. Spec#27's ambiguous matrix phrase was clarified to this existing shared contract rather than changing payment/cost projection behavior.

The safe CLI acceptance total is **148 passed**:108 core +28 filter +8 help/global-boundary +1 cached not-found +3 projection checks. These include actual read-only production queries and offline/local validation against their refreshed snapshot, not148 independent production network calls. Initial environment-blocked attempts are excluded.

Final public help inventory:

| Command | Every exposed capability argument | Evidence |
| --- | --- | --- |
| `collection sla configs list` | `--business-line`, `--entity`, `--currency`, `--region` | Four filter sets above; each cached/live single and repeated form, empty rejection and local nonmatch; cross-field AND and display-window interaction |
| same list | `--limit`, `--offset`, `--all`, `--live`, `--require-fresh`, `--require-complete`, `--format`, `--fields` | Core matrix above; JSON/table, single/multiple projection, limit/offset boundaries and conflicts, stale/complete coverage |
| `collection sla configs get` | `--id`, `--live`, `--require-fresh`, `--require-complete`, `--format`, `--fields` | Core matrix; all55 offline IDs and current live detail, missing/empty inputs, stale rejection, both formats and projection |
| `refresh collection sla` | No capability-specific options | Actual unfiltered complete list + all-detail publication; no selector passthrough |
| both `describe` leaves | `--format json|text` | Offline default/explicit JSON and text plus help |
| help entry points | `help PATH`, PATH `--help`/`-h`, help format JSON/text | List/get/refresh parity and group navigation; help works with unavailable browser |

No newly exposed arguments remain without a case. The business paths expose no inherited authentication-only globals; explicit rejection of `--config-dir`, `--verbose`, `--quiet`, `--no-color` and `--version` was checked. Browser authentication itself was reused, not changed merely to test error handling.

## Engineering gates and review

- Filter-focused SLA SIT:52 passed; catalog7 passed; help/describe155 passed and1 skipped.
- Final Ruff lint passed; formatting check119 files; documentation guard37 Markdown files; whitespace check passed.
- First full repository gate:638 passed,23 subtests passed,1 failed in the existing concurrent cold-cache reader/writer test. Failure occurred while promoting a new SQLite database to WAL (`database is locked`); cache implementation and this test were unchanged against origin/master. Investigation/fix and a new final gate remain pending.
- Standards review:0 actionable findings against `origin/master...66f6581`.
- Spec review:0 implementation defects; projection wording discrepancy reconciled as described above.
- Graph refreshed and impact analyzed against actual default `origin/master`; its static gap warnings for dynamically dispatched CLI handlers were checked against the public CLI SIT tests, not taken as evidence of missing execution coverage.

## Remaining evidence limits

Successful production queries cover the current configuration set, not a permanent row count, backend transaction guarantee or server maximum capacity. Acquisition beyond the verified1000-row request fails safely; no speculative paging fallback was added. Permission/auth failures, interruption, empty/incomplete/malformed responses and failed-refresh preservation are validated with synthetic SIT instead of manufacturing production incidents. Those negative branches are not claimed as observed production failures. Business data stayed read-only throughout.
