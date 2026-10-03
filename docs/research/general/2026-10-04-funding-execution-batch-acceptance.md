# Funding and execution list batch acceptance after authentication recovery

Observed: 2026-10-04
Scope: general
Status: snapshot

Outcome: bounded swap enabled, registered production CLI UAT passed 21/21;
one of four leaves accepted. Final release-delta Kimi review is pending approval.

Specification: [#82](https://github.com/proletariat64/dogopencli/issues/82).
Implementation tickets: [#84](https://github.com/proletariat64/dogopencli/issues/84)
and [#85](https://github.com/proletariat64/dogopencli/issues/85).
Acceptance ticket: [#86](https://github.com/proletariat64/dogopencli/issues/86).
This is a new observation following the
[October 3 acceptance snapshot](2026-10-03-funding-execution-batch-acceptance.md);
that snapshot retains its original authentication failures and validation history.

## Current release decision

The local Kimi baseline CI/review passed at `909bd0c`. The bounded swap release
from `5b40bbb` was then merged into the integration branch at `56add6f`; its
allowlist contains only `liquidity.operations.swaps.list`. Actual registered
public-command production UAT passed 21/21 without candidate bootstrap.
The source registration is therefore **1/4 enabled**. This is an integration
branch acceptance observation, not a claim that the complete batch or a package
release has shipped. A separate final release-delta Kimi run remains pending.

Only the user-approved bounded swap scope can proceed to release: both
`--trade-from` and `--trade-to` are required. Unbounded, one-sided and reversed
ranges are rejected before transport access. Native near/far date filters and
additional source filters remain outside the accepted CLI contract. There is
no getter or business mutation in this batch.

| Leaf | Latest acceptance evidence | Support decision |
| --- | --- | --- |
| `operations demands list` | October 3 bounded inquiries returned empty results or business error `099`; no new nonempty evidence is claimed | unsupported; nonempty structure, identity, date semantics and representative complete acquisition remain missing |
| `operations executions list` | October 3 instruction and realtime inquiries had independent empty/error observations; no new nonempty evidence is claimed | unsupported; both variants need nonempty structure, identity, state meanings and complete acquisition |
| `operations swaps list` | October 4 candidate and actual registered public CLI matrices each passed 21/21, including independent nonempty and empty refresh/offline checks | enabled for required bounded dates; final release-delta Kimi run pending approval |
| `investment investable-funds list` | October 3 five report/forecast date inquiries succeeded empty; no new nonempty evidence is claimed | unsupported; amount/currency types, funding scope, observation semantics, identity and complete acquisition remain missing |

The four-leaf specification remains incomplete. Keep #82, #84, #85 and #86 open
and the PR draft while fewer than four leaves pass all release gates. A successful
bounded swap does not repair or enable its unbounded native default, whose prior
959 arrivals contained 952 unique identities and seven repeated arrivals.
The saved aggregate does not locate those repetitions within or between pages.

## Authentication recovery

The user completed company SSO. Recovery reused the existing shared login API
and dedicated browser profile, with its environment's `startup_url` explicitly
set to the verified Liquidity entry. Normal `dogopencli login` still selects the
Payment entry by default; a successful Payment login is not recorded as Liquidity
authorization. There is no second authentication or browser stack.

The domain-specific recovery completed its headless handoff successfully. An
independent Liquidity auth check then reported healthy/authenticated, and the
subsequent bounded business inquiries succeeded. These are separate observations
from the October 3 CDP reachability and pending SSO state. Credentials remain in
the existing browser; the isolated UAT config retains profile/CDP references and
does not copy tokens. Authentication is a verified current observation, not a
guarantee that the session will remain valid indefinitely.

## Candidate production CLI UAT

The corrected private 21-case CLI matrix ran after authentication recovery and
passed **21/21**. It used process-only candidate catalog registration while the
baseline integration branch's production release flag was empty. The harness
invokes the existing public CLI, preserves the actual profile/CDP configuration
and uses a fresh isolated SQLite cache. All offline cases reject any attempted CDP
transport access.

| Acceptance case | Observed result |
| --- | --- |
| Nonempty live before cache | 15 arrivals, 15 unique `dealId`, reported total 15; zero duplicate arrivals, zero missing records, `complete=true`; cache unchanged |
| Independent refresh, then disconnected cached list | Published 15 records; offline full records, scope and `fetched_at` exactly match the committed capture |
| Live after refresh and strict live | Each returns 15 complete records; database/WAL/SHM cache digests unchanged |
| Complete empty refresh, disconnected list and live | Source-verified 20261003 range publishes and reads 0 complete records; live writes no cache |
| Inclusive trade-date boundaries | 20260930 and 20261001 each return one complete record within the native trade-date range |
| Missing, one-sided and reversed bounds | Eight live/refresh cases reject with `INVALID_ARGUMENT`/exit 2 before CDP transport access |
| Offline help and describe | Succeed without CDP access or cache changes |
| Getter gate | Remains deferred with `UNSUPPORTED_CAPABILITY`/exit 1; no native detail query |

The representative nonempty scope is 20260901–20261001, acquired at native width
10 across two pages. `dealId` is the order identity within the tenant and exact
native filter scope. Trade, near-leg and far-leg dates remain separate source
dimensions; `fetched_at` is acquisition time. The existing `history` capture
profile retains each exact source scope without cross-capture date merging or
an inferred server timezone. Live and refresh are independent inquiries; only
the offline result is required to equal its own committed refresh capture.

The 21-case result does not erase the October 3 authentication-blocked 10/21
attempt or its separate corrected 11/11 offline prerequisites. Those remain
historical observations in the previous report.

## Registered public-command UAT

The same 21-case inquiry-only matrix passed **21/21**, exit 0, against actual
integration source `56add6f`, with no process-only candidate bootstrap. The
registered command acquired 15 arrivals, 15 unique identities and 15 collected
records against reported total 15, with zero duplicates and missing records;
completeness, scope and dataset checks were true. Its independent refresh and
disconnected cached list matched records, source scope and `fetched_at` exactly.

The registered matrix also passed strict live, complete empty refresh/cache/live,
inclusive date boundaries, all eight invalid-range rejections, offline help and
describe, and continued getter deferral. Live preserved cache digests. Candidate
and registered matrices are separate 21-case observations; neither count is a
claim of additional accepted business leaves.

## Local CI and Kimi CLI

The existing corrected integration source previously passed all 1809 pytest tests
and 28 subtests across four exhaustive shards covering 64 files exactly once;
the previous report contains the actual counts, durations and initial-regression
correction. The bounded release passed 262 focused tests. These are
local synthetic validation, independent of production UAT and Kimi conclusions.

The local Kimi CLI JSON baseline CI/review completed **PASS** at `909bd0c`, using
`--output-format stream-json -p`. Its pytest run passed 1809 tests and 28 subtests
in 951.32 seconds; Ruff check, Ruff format check, documentation guard and
`git diff --check` all exited 0. An earlier runner timeout was superseded by this
completed run. The five reported style judgement calls were left untouched.
The minor spec-test gap for getter refusal while the swap list is installed was
fixed in the bounded release and covered by its focused checks.

The baseline result applies to `909bd0c`, independently of the later registered
release and production UAT. Automatic approval review rejected the additional
release-delta Kimi invocation because it requested explicit consent to send
private source to `api.kimi.com`. That permission request is pending; the
additional run has not executed and has no result. This does not invalidate the
completed baseline review.

Post-merge checks actually ran against `56add6f`: Ruff check, Ruff format check
for 257 Python files, documentation guard for 100 Markdown files and
`git diff --check` all passed. The 262 focused tests covered the exact release
source subsequently cherry-picked into this integration commit.
Adding this October 4 snapshot and README index passed documentation guard for
101 Markdown files and `git diff --check` in its isolated documentation worktree.

## Remaining gates and continuation evidence

1. Resolve the explicit `api.kimi.com` consent request before the additional
   release-delta Kimi run, then record its actual result if authorized.
2. Preserve the distinction between the passing baseline review, bounded release
   focused checks and actual registered production UAT.
3. Obtain the missing nonempty/native contracts for demands, both execution
   variants and investable funds before implementing and independently enabling
   them. Their earlier empty samples do not establish populated schemas.
4. Keep the four-leaf issue/tickets open and the PR draft until the complete
   batch is accepted. Do not add backend repair, duplicate tolerance, arbitrary
   requests, getters or other deferred leaves.

Private candidate results are at
`/tmp/issue82-swaps-cli-uat-20261004/summary.json`; registered results are at
`/tmp/issue82-swaps-registered-uat-20261004/summary.json`. The completed baseline
Kimi summary is `/tmp/issue82-kimi-ci-20261003T174436Z/summary.json`.
Stable continuation copies are retained under the main worktree's ignored
`tmp/issue82-evidence/`, including `swaps-registered-uat-20261004/`,
`kimi-ci-baseline-20261004/` and `delivery-status-20261004.json`.
The current Kimi run pointer is
`/tmp/issue82-kimi-run-current.json`. Raw stream JSONL, source/code payload,
credentials and native records remain private and are not reproduced here.
