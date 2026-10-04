# Liquidity batch B evidence and release gates

Observed: 2026-10-04
Scope: general
Status: snapshot

Feature: [issue #88](https://github.com/proletariat64/dogopencli/issues/88).
Actual enabled targets: **0/3**. Investigation and offline refusal checks do
not constitute delivery of these lists. The current worktree's liquidity registry
remains 69 supported and 64 unsupported query leaves. No version bump,
new executable endpoint, populated schema, `get` or `history` is introduced.

## Evidence boundary

The 2026-10-01 inquiry report records only empty responses for all three
targets. On 2026-10-04, the previously saved published UI bundle was inspected
locally; it was not fetched again or verified against current production.
The saved bundle SHA256 is
`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`.
Static caller declarations are discovery evidence, not proof of populated
record types, identity uniqueness, backend range enforcement or completeness.

| Target | Kind | Historical source evidence | Remaining first-release gates |
| --- | --- | --- | --- |
| `risk events list` | runtimes | JSON `POST /api/risk/event/getAll.json`; UI caller sets `riskMode=RISK_EVENT`; observed container `data.data`, total `data.totalCount` | Current caller and native scope; nonempty record types and native identity with tenant/scope; event observation dates, timezone and boundaries; complete representative acquisition; independent production UAT |
| `risk anomalies list` | runtimes | Same endpoint and empty envelope; separate UI caller sets `riskMode=RISK_ALERT` | Current business distinction and backend enforcement of mode; nonempty anomaly structure and native identity; observation dates/timezone; complete representative acquisition; independent production UAT |
| `rules monitoring list` | settings | `GET /queryRules.json`, query fields `tntInstId` and JSON-string `ruleQueryVO`; empty `result.ruleVOList`, total `count` | Current monitoring rule-type filter and object mapping; nonempty structure and native rule identity; configuration status/time semantics; count unit and completion protocol; complete representative acquisition; independent production UAT |

The risk list callers set `rowStart=0`, `pageSize=10`, the native tenant and
environment timezone. They format selected `riskDate` bounds as `YYYY-MM-DD`;
when absent, start is the browser day minus 90 days and end is an empty string.
These historical defaults do not establish inclusion boundaries, timezone
conversion, observation-time semantics or a supported CLI date parameter.
Events and anomalies must never be two copies of one unscoped query, or a
classification inferred from record contents.

The historical monitoring caller serializes a form VO into `ruleQueryVO`,
including pagination and entity/form filters. Its table displays Rule ID
using `ruleNo`, while view navigation uses `ruleId`. Neither is a verified
unique record identity from a nonempty sample. Generic `queryRules` must not
be enabled until the monitoring-specific native rule type/scope is established.
Rule status and next-trigger/update times describe configuration, not an
occurred risk event. Source severity/status values must stay open; unknown
values cannot be locally translated into a risk score or a closed enum.

Knowledge-base graph queries led to the July operations/risk product solution
and September risk-event upgrade PRD. They describe risk observations and
rule configuration separately. They do not prove current production API
fields, enums, mode mappings or read-only/completion contracts. Saved UI
caller evidence is the source of the historical mode values above.

## Browser availability and production UAT

Only discovery metadata was read from the configured CDP endpoint on port
9222. It was reachable and reported headless Chrome. Target inventory already
contained multiple Liquidity and login pages. Local profile coordination
locks were idle, which does not establish availability of an externally
shared browser. Given the user's other development sessions, the browser
was conservatively treated as occupied.

Per the user's instruction, production probing and UAT were **skipped**.
No target was created, attached, navigated or closed; no authentication flow,
profile change or business inquiry was performed. The inventory observation
is not liquidity authorization proof or a conclusive lock-owner diagnosis.
Production UAT passed targets: **0/3**, with all three unattempted this session.

## Offline implementation and verification

The three existing deferred registrations now expose individual scope and
release blockers through offline help, describe, execution errors and snapshot.
Evidence status remains `empty-scope`; populated `data_schema` properties and
query options remain absent. Cached list returns `UNSUPPORTED_CAPABILITY`;
undeclared live/strict options and refresh routes are rejected before transport.
Existing deferred `get` remains unavailable and no `history` is registered.

Public CLI tests use disconnected fake CDP and temporary real SQLite,
missing and corrupt cache files. They check offline discovery, default/live/
strict/refresh refusal, unchanged or absent cache files, detail/history refusal,
and snapshot availability of all three targets. The discovery test failed
before the blocker descriptions were added, then passed. These tests prove
release gates and preservation, not enabled list lifecycle contracts T01–T12.

Local automated checks and Kimi review results are recorded below. They do
not substitute for production UAT. No typechecking gate is
configured in `pyproject.toml` or the repository CI workflow; do not claim a
Python-version matrix or static type check from one local pytest run.

## Local verification record

Comparison base: remote default branch `master`, `origin/master` SHA
`f8ada67215d164a745817a1627672639c7028002`, verified against GitHub. The change
was staged but uncommitted during review, so the comparison is
`rtk proxy git diff origin/master`, including staged and working-tree files.

| Check | Actual command | Result |
| --- | --- | --- |
| CLI release gates | `rtk proxy env PYTHONPATH=src /home/ubuntu/dev/dogopencli/.venv/bin/python -m pytest -q tests/integration/test_liquidity_issue88_gate.py` | 73 passed; final assertion change also passed 73 tests in 2.41s |
| Ruff (executed by Kimi) | `rtk proxy ruff check .` | Passed, exit 0 |
| Format (executed by Kimi) | `rtk proxy ruff format --check .` | Passed, exit 0; 260 files already formatted |
| Diff (executed by Kimi and primary agent) | `rtk proxy git diff origin/master --check` | Passed, exit 0 |
| Document gate (primary agent) | `rtk proxy make doc-guard PYTHON=/home/ubuntu/dev/dogopencli/.venv/bin/python` | Passed, 102 Markdown files |
| Full suite (Kimi) | `rtk proxy env PYTHONPATH=src /home/ubuntu/dev/dogopencli/.venv/bin/python -m pytest -q` | Interrupted; last saved output contains 544/1882 outcomes with four failure markers; no final summary, not passed |
| Production UAT | None | Skipped; 0/3 targets attempted or passed |

The first discovery-only run used the same focused-test command before the
three descriptions were updated: **6 failed**, because historical mode/filter
evidence was absent from help/describe. After the descriptions changed, that
run passed **6 tests**. Later refusal/snapshot cases expanded the file to
73 tests. These are recorded session observations, not a new production sample.

Kimi Code CLI version `2.1.1` loaded the user's `/code-review` skill; output
used `--output-format stream-json`. This version rejects combining `--auto`
with `-p`, so the executed review omitted `--auto`. An earlier review stopped
with `ECOMPROMISED` after its OAuth lock file disappeared; its full-suite and
final-review results cannot be claimed. The retry used the same installed
environment, with no authentication or browser changes. Python is `3.12.3`;
the remote Python 3.10/3.11/3.12 matrix has not been run here.

The retry's Standards subagent additionally launched `rtk pytest -q` despite
the full-suite-once instruction and then waited on it. The Kimi process and
both task processes subsequently no longer existed, while persisted task
metadata still said `running`. Those stale states cannot prove an active
test run or a passing result. Recovery resumes only the review and explicitly
forbids another full suite or waiting on those stale tasks.

Mapping the main run's four failure markers to the unchanged collected test
order identified the existing Collection cases below. They passed individually
without Collection code changes: **4 passed in 7.08s**. This is a focused
reproduction attempt, not proof that the interrupted full suite is green or
that its failure cause is established.

```bash
rtk proxy env PYTHONPATH=src /home/ubuntu/dev/dogopencli/.venv/bin/python -m pytest -q --tb=short \
  tests/integration/test_collection_va_capacity_cli_sit.py::test_namespace_isolation_vs_other_caches \
  'tests/integration/test_collection_va_rule_cli_sit.py::test_list_rejects_incomplete_or_bad_data[False-changes3-INVALID_RESPONSE]' \
  'tests/integration/test_collection_va_rule_cli_sit.py::test_list_rejects_incomplete_or_bad_data[False-changes4-INVALID_RESPONSE]' \
  'tests/integration/test_collection_va_rule_cli_sit.py::test_list_rejects_incomplete_or_bad_data[True-changes12-INVALID_RESPONSE]'
```

Kimi's Spec axis requested concrete validation records and exact refusal
exit-code assertions. The records above address the first item. Focused tests
now assert exit 1 for unsupported list/get and exit 2 for undeclared options,
refresh and history; all 73 passed. The recovered aggregate review found no
documented-standard violations or open correctness findings. Three minor
Standards suggestions concerned repeated reason text, overlapping test fixtures
and unused parametrized arguments; they do not require broader refactoring.
The red-step record remains explicitly a session observation.

Kimi's single overall CI-pass confidence is **3/5**. Completed focused checks
passed, but the interrupted full suite and unrun Python-version matrix prevent
a passing-CI claim. Production UAT remains unrun and all three targets remain
unsupported. No per-finding confidence scores were requested. Final commit
identification is supplied by the Git commit containing this report; no issue
closure is implied.

## Continue conditions

Once the shared CDP is available, independently verify liquidity authorization
and each current native UI caller before inquiry-only production requests.
Obtain a nonempty sanitized sample and establish native identity, scope and
time semantics per leaf. Verify events/anomalies modes separately, and establish
the monitoring rule-type filter. Preserve raw/unique/reported counts and verify
representative completion with no duplicated, omitted or conflicting records.

Only then register the evidenced `ListSpec`, projection, allowlist and appropriate
snapshot/history/dated profile using the existing collector and capture store.
Use the agreed public CLI + fake CDP + temporary SQLite seam to implement T01–T12,
including refresh/offline equality for one capture, empty publication, live
isolation, partial/strict behavior, hard-failure rollback and retention isolation.
Complete independent production UAT before enabling each leaf. Report enabled
targets as a numerator over three; keep issue #88 open until all three pass.

## Sources

- [Issue #88 specification](https://github.com/proletariat64/dogopencli/issues/88).
- [Historical inquiry report](2026-10-01-liquidity-live-probes.md): risk events
  `business-05-r1/r2/r3`, `previous-day-05-r1`; risk anomalies
  `business-06-r1/r2/r3`, `previous-day-06-r1`; monitoring
  `core-39-r1/r2/r3`. No populated record schema was verified in these cases.
- Saved published UI bundle: risk inquiry wrapper character offset `1516395`,
  anomaly caller around `7037486`, event caller around `7067707`; rules wrapper
  `1490903`, list caller `3082374`, VO/table mapping around `3083900`.
- Knowledge-base source documents `434365484` (July risk product solution) and
  `550788372` (September risk-event upgrade), located through read-only
  `graphify query`; product requirements, not production verification.
- ADRs [0016](../../adr/0016-liquidity-independent-list-and-detail-caches.md),
  [0018](../../adr/0018-liquidity-capture-store-and-retention.md) and
  [0019](../../adr/0019-usable-incomplete-acquisitions.md). Usable partial results
  remain valid for enabled capabilities; this does not relax first-release gates.
