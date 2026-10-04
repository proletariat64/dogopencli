# Liquidity batch B evidence and release gates

Observed: 2026-10-04
Scope: general
Status: snapshot

Feature: [issue #88](https://github.com/proletariat64/dogopencli/issues/88).
Enabled targets: **2/3**. Risk events and risk anomalies expose independently
verified bounded lists. Monitoring rules remain unsupported; the issue remains
open. After master integration: 73 supported (32 settings, 34 runtimes,
7 reference) and 60
unsupported query leaves. No new get/history, version bump or framework.

## Native contracts and evidence

Liquidity authorization was verified separately from Payment SSO. User completed
interactive login on isolated CDP port **9223**; occupied port 9222 stayed
untouched. Exclusive browser coordination remains mandatory; busy locks abort.
The current UI bundle was fetched again, SHA256
`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`.
Native Risk Event/Risk Alert tabs and actual request/response pairs were observed.

| Leaf | Native contract | Identity/completion |
| --- | --- | --- |
| risk events list | JSON POST `/api/risk/event/getAll.json`, `riskMode=RISK_EVENT` | Nonempty string `id`; `data.data`, fixed `data.totalCount`, offset pages |
| risk anomalies list | Same endpoint, source `riskMode=RISK_ALERT` | Independently populated and complete; no local anomaly classification |
| rules monitoring list | GET `/queryRules.json`, serialized `ruleQueryVO` | Current zero rows; monitoring type/filter, nonempty schema and identity unverified |

Risk requests contain exactly fixed `tntInstId=GUAPW3SG`, mode, `timeZone=GMT+08`,
`rowStart`, `pageSize=10`, `startTime` and `endTime`. CLI bounds are required
YYYYMMDD, converted to native YYYY-MM-DD. Only adjacent dates are executable:
`--to-date` must be one day after `--from-date`. Same-day queries returned zero;
the broad native 90-day default had duplicate arrivals and is excluded.

`id` is scoped to tenant, native mode and exact acquisition bounds. The UI's
Risk Time is `gmtCreate`, preserved as `YYYY-MM-DD HH:mm:ss（GMT+08）`.
`gmtModified`, `firstAlertTime`, `nextAlertTime`, `closeRiskTime` remain separate
source times; optional close time may be blank. `riskProcessingTime` is an
integer displayed in minutes; `alertNum` retains its integer counter. Status,
level, category/scenario, event and object strings retain source values without
closed enums or scoring. Projection publishes 17 fields and excludes operators,
free text, nested treatments/logs and unknown additive fields.

For Sep 25–26, all source creation times fall on Sep 25 if interpreted as UTC;
seven anomaly display dates are Sep 26 in GMT+08. Changing request timezone to
GMT+00 changed neither timestamps nor identities. These observations **do not
prove** the backend boundary clock, inclusivity, or that creation time alone
drives filtering. Native date filters remain native filters; help states the
limit. No guessed local date membership or timezone conversion is applied.
Existing history profile retains exact-scope captures by acquisition time;
source-observed coverage stays unknown. `fetched_at` is never business time.

## Complete acquisition and independent CLI UAT

| Native bounds | Events arrivals / unique / reported | Anomalies arrivals / unique / reported |
| --- | --- | --- |
| 2026-09-25 to 2026-09-26 | **3 / 3 / 3**, one page | **95 / 95 / 95**, ten pages (9×10 + 5) |
| 2026-10-01 to 2026-10-02 | 2 / 2 / 2 | 128 / 122 / 128, incomplete |
| 2026-10-03 to 2026-10-04 | 3 / 3 / 3 | 35 / 33 / 35, incomplete |
| 2099-01-01 to 2099-01-02 | 0 / 0 / 0 | 0 / 0 / 0 |

Totals were stable within requests; no observed repeated identity had conflicting
content. Broad events: 214 arrivals, 213 unique, 214 reported. Broad anomalies:
bounded at 100 pages, 1000 arrivals, 975 unique, 12162 reported; never called
complete. No duplicate tolerance, unlimited retry or large-page fallback added.
Duplicates keep incomplete warnings; identity conflicts and total drift fail.

Private candidate registration used the actual public CLI, restricted transport
and separate ignored SQLite cache. Each risk leaf passed strict Sep 25–26 refresh,
offline all-record readback with CDP forbidden, matching count/scope/fetched_at,
full-content equality with complete live inquiry, and unchanged cache bytes after
live. Each passed complete future empty live, empty refresh/offline readback and
preservation of its original date scope. Events: 3 records; anomalies: 95.
An initial anomaly assertion failed without stage information; cause was not
established. Full anomaly rerun with stage diagnostics passed all assertions.
This limitation is retained instead of claiming the initial attempt passed.

Monitoring has not passed UAT: no populated identity or monitoring-specific
filter. Generic rules cannot substitute for monitoring definitions. Its offline
help/describe/snapshot explain the blocker; get/history remain unavailable for
all three targets. Only synthetic fixtures, schema/count summaries enter Git.
Production rows, browser profiles, credentials and private caches remain ignored.

## Local implementation and verification

Reused ListSpec, capability allowlists, collector, projections, offline discovery,
atomic capture store and shared incomplete-result policy. Public CLI + fake CDP
+ real temporary SQLite tests cover multi-page completion, full offline equality,
empty captures, live isolation, default/strict partial publication, conflicts,
total drift, bad identity/time/mode, authentication/transport/envelope failure
preservation, invalid bounds before transport, scope isolation and snapshot.
Existing shared-store tests cover history retention and atomic eviction.
Additional public CLI cases for both risk modes verify empty live over a populated
same-scope capture, aggregate history retention across two exact date scopes,
retention gaps/strict refusal, and matching snapshot/acquisition metadata.
The expanded risk suite passed **35 tests in 37.13s**, while the already-running
full suite retained its original 1,877-case collection. These added cases were
checked separately; they are not counted as part of that full-suite run.

Initial red step: native date conversion absent. Later red: private candidate
snapshot ownership absent; registering actual capability ownership fixed it.
Candidate suite passed **31 tests in 32.72s**. Monitoring refusal and no-get/history
release gates remain separate.

The initial review's actual default `master` advanced to
`06689d759bc7c64fe65cd80f90d716453ec08b40` during this session, verified against
GitHub. Feature comparison uses its merge-base
`f8ada67215d164a745817a1627672639c7028002`, including staged changes, so newer
issue #87/CI changes are not mistaken for feature deletions. PR preparation
then integrates `06689d7`, preserving both batch A lists and both batch B risk
lists. Six overlapping files were resolved, with 51 list leaves total and
73/133 supported query leaves. Existing Python 3.12.3 environment;
Python 3.10/3.11 unrun locally. Current master's CI requires Ruff and Kimi review;
the earlier pytest matrix was removed upstream. No configured static typecheck
or coverage threshold. Completed checks and review are recorded below.

| Local check | Command | Result |
| --- | --- | --- |
| Issue #88 focused CLI | `rtk proxy env PYTHONPATH=src /home/ubuntu/dev/dogopencli/.venv/bin/python -m pytest -q tests/integration/test_liquidity_issue88_gate.py tests/integration/test_liquidity_issue88_risk.py` | 68 passed in 33.12s |
| Snapshot CLI | Same Python, `-m pytest -q tests/integration/test_snapshot_cli_sit.py` | 18 passed in 0.38s after unsupported count changed 64 to 62 |
| Expanded risk acceptance | Same Python, `-m pytest -q tests/integration/test_liquidity_issue88_risk.py` | 35 passed in 37.13s, including four added empty-live/retention cases |
| Full suite | Same Python, `-m pytest -q` | 1,875 passed, 1 skipped, 1 failed; 28 subtests passed in 995.47s |
| Registry contract correction | Same Python, `-m pytest -q tests/unit/plugins/liquidity/test_capability.py` | 13 passed in 0.07s after stale list count changed 46 to 49 |
| Installed console entry | `rtk proxy env PATH=/home/ubuntu/dev/dogopencli/.venv/bin:"$PATH" PYTHONPATH=src /home/ubuntu/dev/dogopencli/.venv/bin/python -m pytest -q tests/test_help_entry.py::test_installed_console_script` | 1 passed in 0.14s; existing venv reused, no install |
| Ruff | `rtk proxy ruff check .` | Passed |
| Formatting | `rtk proxy ruff format --check .` | Passed, 262 Python files |
| Documentation | `rtk proxy make doc-guard PYTHON=/home/ubuntu/dev/dogopencli/.venv/bin/python` | Passed, 102 Markdown files |
| Diff | `rtk proxy git diff --check` | Passed |

The first full-suite attempt was interrupted after identifying the stale snapshot
count; it is not a passing result. The completed run's only failure was the
contract smoke test's stale list-leaf count: expected 46 versus actual 49 (swaps
and two risk lists). Updating that assertion made all 13 tests in its file pass.
No production code changed after this failure; the full suite was not rerun.
Its skipped console-entry test was caused by the executable being absent from
the original PATH. Adding the existing venv to PATH made that individual test
pass; no environment rebuild or installation was needed.
Verification combines the completed full run, its corrected focused file, and
the separately passing expanded risk/console tests. Do not describe the original full
run as green or count its four later-added cases as executed in that run.

Local Kimi Code CLI 2.1.1 loaded the user's `/code-review` skill and returned valid
stream-json, exit 0. Actual invocation used `rtk proxy kimi --output-format
stream-json -p '/code-review ...'`; this installed version rejects `--auto` with
`-p`. Review inspected the production diff and saved validation evidence without
rerunning tests, production UAT, authentication or Greptile. No correctness
defects were found. Minor import/date-selection style observations were left
alone. Monitoring's missing contract and unproven server date edges were accepted
only as the explicitly documented partial-delivery boundary, not full completion.

Kimi's **single overall CI-pass confidence: 4/5**. At review time the full suite
was still running; Python 3.10/3.11 were unrun, and the first anomaly UAT assertion
remains unexplained despite a passing complete rerun. This is one CI score, not
per-finding scores or a claim that all three spec targets passed UAT.

Earlier discovery-only commit `a9db73c` had 0/3 enabled, skipped shared-browser
UAT and interrupted full suite. Its Kimi 3/5 score does not describe this work.

## PR integration verification

Current master `06689d7` is integrated before PR publication. Resolved the six
overlapping files by retaining both batch A decisions/transfers and batch B
events/anomalies, with their separate native validation, projections, fields and
verification dates. Combined registry and snapshot assertions now reflect
73 supported, 60 unsupported and 51 list leaves. No production inquiry was
repeated for this integration; the native risk contract and implementation remain
the same as the accepted two-leaf source.

Affected tests passed **540/540 in 102.31s** with the existing venv on PATH:

```bash
rtk proxy env PATH=/home/ubuntu/dev/dogopencli/.venv/bin:"$PATH" PYTHONPATH=src \
  /home/ubuntu/dev/dogopencli/.venv/bin/python -m pytest -q \
  tests/unit/plugins/liquidity \
  tests/integration/test_liquidity_issue87_decisions.py \
  tests/integration/test_liquidity_issue87_transfers.py \
  tests/integration/test_liquidity_issue88_risk.py \
  tests/integration/test_liquidity_issue88_gate.py \
  tests/integration/test_snapshot_cli_sit.py \
  tests/integration/test_snapshot_domain_sit.py \
  tests/test_catalog.py tests/integration/test_help_sit.py \
  tests/integration/test_describe_cli.py tests/test_help_entry.py
```

Ruff passed; formatting passed for 270 Python files; document guard passed for
105 Markdown files; diff/conflict-marker checks passed. The full suite was not
repeated for this merge. Local Kimi integration review completed in stream-json,
exit 0, with Standards and Spec axes. Both merge sides and combined counts were
verified preserved; no hard standards violation or confirmed correctness defect
was found. Overall CI-pass confidence remains **4/5**, with the documented UAT
and date-edge limitations and no post-merge full-suite rerun. Style judgements
were not patched. Its minor non-null-schema allegation is not supported by the
actual describe provider: `x-observed-type` records sampled types, nullability is
explicitly unknown, and no required/non-null field assertion is emitted.

## Monitoring continue conditions

Verify native monitoring type/filter and object mapping; obtain nonempty
sanitized structure, rule identity, configuration status/time semantics and
complete representative acquisition. Implement/prove its public CLI lifecycle,
then independent inquiry-only UAT and local Kimi review. #88 completes at 3/3.

## Sources

- [Issue #88](https://github.com/proletariat64/dogopencli/issues/88).
- [Historical empty inquiries](2026-10-01-liquidity-live-probes.md): starting
  evidence only, superseded for the two populated bounded risk contracts.
- Current `umi.js` SHA above: wrapper offset 1516395, endpoint map 1560677,
  event caller 7067707, alert caller 7037486, event table 7070123, alert table
  7040831. Actual network observations confirmed modes, fields and counts.
- ADRs 0016–0019: independent list/detail, bounded retention, capture store and
  safe incomplete-result policy.
