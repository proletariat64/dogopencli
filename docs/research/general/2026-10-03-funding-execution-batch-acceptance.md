# Funding and execution list batch acceptance

Observed: 2026-10-03
Scope: general
Status: snapshot

Outcome: partial; 0/4 new leaves released. All four remain unsupported.

Specification: [#82](https://github.com/proletariat64/dogopencli/issues/82).
Implementation tickets: [#84](https://github.com/proletariat64/dogopencli/issues/84),
[#85](https://github.com/proletariat64/dogopencli/issues/85).
Acceptance ticket: [#86](https://github.com/proletariat64/dogopencli/issues/86).

## Release decision

The batch requires four independently verified, production usable list queries.
It is incomplete: **0/4 leaves have passed every release gate**. All four remain
discoverable and non-executing as `unsupported`; the bounded swap implementation
is a candidate with an empty release allowlist. Empty native queries, successful authentication, local fixtures,
candidate queries and complete narrower scopes are separate evidence; none alone
establishes the four-leaf release condition. The parent specification and all
unfinished implementation/acceptance tickets stay open, and the PR remains draft
until the entire specification is met.

The scope contains `list`, explicit root `refresh liquidity …`, offline cached
list and offline help/describe. It adds no getter or mutation. Authentication and
transport remain shared; a Payment session does not prove Liquidity access.

After reviewing the default pagination blocker, the user authorized a narrower
swap release: both `--trade-from` and `--trade-to` are mandatory. Unbounded,
one-sided and reversed ranges must fail before any transport access. This is a
scope decision, not a backend repair or a complete-default-query claim. Native
near/far value-date filters and additional source filters are not exposed.

The swap candidate keeps an exact native trade-filter scope using the existing
`history` capture profile. It does not merge dated captures, manufacture per-day
coverage or infer a server timezone. Capture-time retention remains distinct
from trade, near-leg and far-leg business dates.

## Native inquiry evidence

The current portal's published UI bundle was independently checked against the
saved native source: 15,763,128 bytes, SHA256
`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`.
This corroborates request callers, encodings and native defaults. It does not
establish nonempty schema, identity, query success or pagination completeness.
Fresh selected scope was read from the native preference contract rather than
expanding the available authorization list. Preference values and credentials
are omitted from this report.

| Leaf | Native result | Remaining release evidence | Public state |
| --- | --- | --- | --- |
| `operations demands list` | Two bounded single-day scopes succeed with 0 rows; native default/previous 30-day and a seven-day scope return business error `099` | No usable nonempty structure, proven identity, date semantics or complete representative collection | unsupported |
| `operations executions list` | Instruction and realtime variants independently succeed with 0 rows in two bounded single-day scopes; broader native windows return business error `099` | No usable nonempty structure, proven identity, execution state meanings or complete representative collection; both source variants remain separate | unsupported |
| `operations swaps list` | Nonempty native default scope: reported 959, 96 pages, 959 arrivals, 952 unique `dealId`, 7 repeated arrivals, no conflicting identity content, `complete=false`; bounded date inquiry independently collected 15/15 | Default scope remains excluded; bounded candidate public CLI UAT is authentication-blocked and local Kimi review has not run | unsupported; candidate only |
| `investment investable-funds list` | Four report-date queries and one explicit forecast-range query succeed with 0 rows | No usable nonempty structure; amount/currency types, funding scope, business observation semantics, identity and representative complete collection remain unproven | unsupported |

The task endpoint is GET `/riskActionTaskQuery.json`, with tenant and a JSON
query VO in URL parameters. Demands uses the native `FUND_REQUIRE` source;
executions keeps instruction and realtime source sets independent. A business
error is a hard failure, not a complete empty capture or usable partial result.

Swaps uses POST `/swapOrderQuery.json` with the native form encoding, tenant and
JSON query VO. The list has its own offset pagination, `dealId` and distinct
trade/near/far date dimensions. The initial native default permits an undated
query; date-constrained checks below do not prove that default scope complete.
Cross-page repetitions are recorded, not converted into complete acquisition
by deduplication, smaller-page retries or a guessed backend correction.

Investable funds uses POST `/queryInvestableFundList.json` with an explicit JSON
body. Report date, forecast date and selected timezone are source dimensions;
`fetched_at` is acquisition time. The chart endpoint is outside this batch.

### Swaps bounded date diagnostics

These are fresh native inquiries, independently acquired from the default scope.
All use the native width of 10. The recorded dates distinguish trade dates;
they do not establish a server timezone or business observation timestamp.

| Native trade range | Reported total | Arrivals / unique identities | Pages | Complete |
| --- | ---: | ---: | ---: | --- |
| 20260901–20261001 | 15 | 15 / 15 | 2 | true |
| 20260930–20261001 | 2 | 2 / 2 | 1 | true |
| 20260930–20260930 | 1 | 1 / 1 | 1 | true |
| 20261001–20261001 | 1 | 1 / 1 | 1 | true |
| 20261003–20261003 | 0 | 0 / 0 | 1 | true |

The September 30 and October 1 single-day requests returned one record each;
their combined inclusive range returned two. This supports the tested date
boundary behavior. The two-page representative range returned 15 distinct
identities without overlap or conflicts. It remains a bounded observation,
not a promise about future backend stability or all historical default pages.

## Public CLI production UAT

No leaf is production accepted. Native endpoint probes are not
substitutes for the public CLI `refresh → cached list` acceptance sequence.

The initial candidate CLI run encountered `AUTH_REQUIRED` on live/refresh;
the independent Liquidity auth check confirmed a redirect to the login page.
Consequently no capture was published, and offline list correctly reported
`CACHE_MISS`. Earlier authenticated probes do not guarantee a later session
stays authenticated. These failures are recorded as authentication blockers,
not candidate parsing or cache defects. Offline range rejection, help and
describe succeeded. A harness-only getter expectation was corrected to the
existing deferred `UNSUPPORTED_CAPABILITY`/exit 1 behavior; no getter was added.

The first candidate attempt completed **10/21 expected cases** before the getter
expectation correction: eight malformed-scope live/refresh rejections and offline
help/describe. The deferred getter also behaved correctly, but failed that
attempt's incorrect expectation. The corrected plan has not passed a rerun.
No count is presented as 21/21, and no native action from that attempt is UAT
accepted. The login recovery wait expired after 600 seconds without SSO completion;
the subsequent independent auth check still reported `auth_required` and a login
redirect. A headed Chrome remains available for completing that authentication.

The private UAT harness invokes the existing public CLI and redirects only the
cache path to a fresh isolated SQLite file. Its config retains the actual
profile/CDP references; it copies no browser credential. Offline cases install
a transport factory that fails on any attempted CDP access, without stopping
the user's Chrome. Full offline results are compared with the exact published
capture's records, scope and `fetched_at`; live cache database/WAL/SHM digests
are checked before and after. Raw responses, scopes and row digests stay in
private files and are excluded from Git, issues and this report.

For each enabled leaf the release record must include nonempty live, explicit
refresh, same-capture offline equivalence, source-verified empty refresh/offline,
live non-publication, offline help/describe, range boundaries and source identity
checks. Any process-only candidate registration is disclosed as candidate UAT;
it does not establish that a deferred command is publicly supported.

## Automated validation and local Kimi CLI

Code review corrections are integrated at `8cb55d2`. Whole-tree Ruff check and
Ruff format check passed (256 Python files). Earlier focused/nearest Liquidity
CLI, projection and capability verification passed 169 tests before those final
review corrections; this historical result is not labeled a final full-suite
pass. The integrated full pytest run was started and its outcome is pending at
this report's commit. Documentation guard verifies this acceptance artifact
and its index link.

The user-required **local Kimi CLI CI/review has not executed**. Automatic approval
review rejected the proposed private-source transmission to its configured
external model route; authorization for that transmission remains pending.
There is no Kimi conclusion or successful Kimi CI claim. Local pytest, Ruff and
code review are reported separately and do not substitute for that requirement.

Synthetic fixtures verify external behavior, failure handling and cache
protection, but do not supply missing production records or business semantics.

## Handoff gates

1. Restore the dedicated Liquidity SSO session and verify both domain auth and
   an actual bounded inquiry. Current authentication does not support unattended
   production UAT; no restored session has been verified.
2. Run the corrected 21-case bounded swap CLI matrix using a fresh private cache.
   Require 15-row nonempty acquisition, representative two-page completeness,
   independent refresh and same-capture offline equivalence, verified empty
   acquisition, live cache preservation, strict mode, date boundaries and offline
   help/describe. Keep all getters deferred.
3. Complete the integrated full pytest result and the approved local Kimi CLI
   CI/review. Address any findings before activating the bounded swap candidate.
4. Obtain each missing nonempty/native contract for demands, both execution
   variants and investable funds, then independently implement and production
   UAT those lists. Keep business errors and unavailable evidence as blockers.
5. Populate only individually passed release entries. Keep #82, #84, #85 and #86
   open and the PR draft while fewer than four leaves satisfy the specification.

## Follow-up boundary

Continue only with the concrete missing evidence for each leaf. Do not add
backend repair campaigns, default-page duplicate tolerance, arbitrary query
interfaces, getters, forecast accuracy, wallets, pool balance or credit usage.
ADR 0019 permits safe incomplete runtime results in supported capabilities;
it does not waive this batch's first-enable nonempty and complete UAT gates.

Private research and native acquisition artifacts are retained outside Git
under `/tmp/issue82-contract-research.md` and `/tmp/issue82-native-evidence/`.
Their availability is local and temporary. Public evidence contains aggregate
counts, reviewed paths and blockers only; raw identifiers and financial records
remain private.
