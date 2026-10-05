# Liquidity Batch F: four bounded inquiry lists

Observed: 2026-10-05
Scope: general
Status: snapshot

Implementation scope: issues #109–#112 on the shared Batch F branch.
All four lists are implemented. Independent per-leaf public CLI production
UAT passed on the integrated source. Local checks and independent Standards/Spec
review passed after the documentation-index fix. Local Kimi has not run:
the external code-payload authorization gate is pending.

The authoritative specifications are [#109](https://github.com/proletariat64/dogopencli/issues/109),
[#110](https://github.com/proletariat64/dogopencli/issues/110),
[#111](https://github.com/proletariat64/dogopencli/issues/111), and
[#112](https://github.com/proletariat64/dogopencli/issues/112).
The user requested one PR for all four tickets. The starting baseline is
`495e90005f41183b0a7e9561b835545d3207b51c` (`master`, v0.2.8).

| CLI list | Accepted inquiry scope | Capture profile | Completion proof |
| --- | --- | --- | --- |
| `risk sla list` | Native default SLA configuration scope; one fixed 5000-row request | settings snapshot | Raw arrivals = unique `slaConfigId` = native total |
| `forecast accuracy list` | One explicit account and record creation query date; at most 100 base records | runtimes history | Complete base coverage and all native metric compositions |
| `risk account-capacity list` | Explicit sorted set of 1–10 distinct account aliases | runtimes history | Exactly one validated native object for each requested alias; no native global total |
| `investment rfqs list` | TARGET_RFQ with paired explicit dates; one fixed 5000-row request | runtimes history | Raw arrivals = unique `inquirySubTaskId` = native total |

All lists use the shared inquiry transport and independent projection schemas
and cache scopes. Default reads are offline; explicit refresh publishes
atomically; live reads never publish or fall back. Source times remain distinct
from capture time; unproven source timezones remain unknown. Existing detail
caches are independent, and no list refresh initiates a detail crawl.

Rules monitoring remains HOLD. FULL_RANGE_RFQ, full-account accuracy,
cross-date accuracy, account discovery, and the other seven Batch F candidates
remain outside this delivery. This PR does not bump, merge, or release.

## Implementation and catalog

Ticket commits `0ed39d7`, `3f20c10`, `d9ab0c0` and `044faa8` are integrated
through `5c95ca0`; `1a4aa4e` updates the still-held monitoring discovery
regression and catalog formatting. Shared catalog counts are 89 supported
(64 lists and 25 detail/history), 42 unsupported, 131 total: 35 settings,
46 runtimes and 8 reference. These are source-branch counts. The published
v0.2.8 baseline remains 85 supported / 46 unsupported until a separate release.

The [reading contract](../../design/liquidity-batch-f-v0.1.0.md) describes
the exact request, projection, native identity, scope and cache rules.
No new business filters, detail getters, cross-scope recovery, local formulas
or full-account enumeration were added. The cold-process CLI check caught a
registry import cycle hidden by test pre-import order; lazy collection-type
imports fix it, and a fresh-process regression covers ordinary CLI startup.

## Independent production public CLI UAT

The dedicated CDP 9223 profile was reachable and headless. A fresh Liquidity
startup-origin authentication check passed; browser control was checked
before each network invocation. There was no launch, restart, credential
change, session takeover or use of a forbidden port. Real responses and
account selections remain in private temporary files outside Git/review.
Three account aliases were explicitly selected from previously observed
native forecast records; capacity did not discover accounts automatically.

Each leaf passed five public CLI steps on the integrated source: strict
refresh, strict cached list, the same list with the browser factory disabled,
offline describe, and strict live list. The integrated run completed **20/20**.
Earlier isolated ticket-source runs also passed, but the integrated result is
the delivery evidence. Refresh and live results were compared independently
to the raw response from that same invocation, not to one another.

| List and declared scope | Native coverage | Native projection and composition |
| --- | --- | --- |
| Risk SLA, native default configuration scope | 49 arrivals / 49 unique slaConfigId / native total 49 | All eight present summary fields matched; no rule arrays or detail calls |
| TARGET_RFQ, 2026-01-01 through 2026-10-05 | 1 arrival / 1 unique inquirySubTaskId / native total 1 | All 17 present fields matched; type echo TARGET_RFQ, parent reference separate |
| Account capacity, three explicit aliases | requested 3 / resolved 3; reported_total null | All ten fields and each alias echo matched; no global native total invented |
| Forecast accuracy, one explicit alias / creation query day 2026-10-05 | 7 base arrivals / 7 unique id / native count 7; 7 metric successes | All 12 base and 11 nested metric fields matched; association is native request binding |

Offline results matched the same saved capture's data, scope, quality and
fetched_at with a browser factory that raises on access. Every live operation
left SQLite and WAL byte hashes unchanged. Exact-scope captures remained
separate in one private SQLite database, with no detail-cache acquisition.
The earlier isolated accuracy run observed 6/6 base records and six metrics;
the integrated run observed seven. The source changed between captures, so
no equality claim is made across those different invocations and no fixed
future count is encoded in tests.

Production empty scopes were not guessed. Successful empty envelopes,
undercoverage, duplicates, conflicts, error containers, failed metrics,
account echo mismatches, client budgets, retention, default/strict handling,
request rejection and cache preservation are verified using synthetic fake
CDP and temporary real SQLite tests. FULL_RANGE_RFQ remains excluded and was
not sent during UAT; the historical source 099 in #112 is retained as evidence.

## Local checks and independent reviews

The four new public CLI test modules cover 152 acceptance cases (35 SLA,
42 accuracy, 33 capacity and 42 RFQ). The capacity cold-process regression
and shared evidence/scope unit cases are additional checks. All isolated
ticket checks passed; root-owned global count expectations were updated
after integration. The integrated Liquidity/policy/snapshot/help/describe
regression suite passed **1209 tests in 730.93 seconds**, using the existing
parent checkout's Python 3.12 environment. Repository Ruff lint/format, doc guard and
whitespace checks pass. The graph indexes 190 Python source/test files and
was refreshed before commits and review against actual default `origin/master`
at `495e90005f41183b0a7e9561b835545d3207b51c`. Dynamic CLI dispatcher
heuristics are not treated as proof of missing runtime test coverage.

The integrated command was:

```bash
rtk proxy /home/ubuntu/dev/dogopencli/.venv/bin/python -m pytest -q \
  tests/unit/plugins/liquidity tests/unit/test_result_policy.py \
  tests/unit/test_acquisition_evidence.py tests/unit/test_snapshot_metadata.py \
  tests/unit/test_account_capacity_cli_bootstrap.py tests/test_catalog.py \
  tests/integration/test_liquidity*.py tests/integration/test_snapshot*.py \
  tests/integration/test_domain_partial_sit.py tests/integration/test_help_sit.py \
  tests/integration/test_describe*.py
```

The full repository suite and other Python versions were not run. This focused
suite includes the affected shared policy, scope decoder, retention, native
details, other Liquidity lists, snapshot/discovery and public CLI seams.

Independent Standards/Spec review used `495e900...1a4aa4e`: Spec had zero
confirmed findings; Standards found two missing documentation-index links.
`95d0928`, integrated through `d03ec51`, fixes that minor index issue without
changing source behavior. No actionable baseline smell was reported.
These were static source reviews; the coordinator separately ran local tests
and production UAT.

Local Kimi 2.1.1 was selected with `/code-review` and `stream-json`, using
the existing environment. Automatic approval review rejected transmitting
the production-code diff and sanitized specification to the external Kimi
service because explicit authorization for that particular sensitive payload
and destination was not established. The repository is private. No Kimi
process started, no review result exists, and no confidence score is claimed.
The explicit payload authorization question remains pending; the PR remains
draft rather than presenting that unrun gate as passed.

At remote code head `d03ec51`, both lint checks passed and Qoder review was
still in progress. The earlier Qoder approval at `9dcbe47` reviewed only the
initial documentation and is not claimed as approval of the implementation.
Remote checks, publication and release are separate from local checks and UAT.
No issue is closed by this unmerged PR.
