# Liquidity spec v0.2.3 implementation and CLI inquiry UAT

Observed: 2026-10-02
Scope: general
Status: snapshot

Date: 2026-10-02 (Asia/Shanghai). Specification: [#76](https://github.com/proletariat64/dogopencli/issues/76).
Implementation baseline: `feat/sub-cmd-lm` / `a01562075f31eab50224fb35eea1de0cd27867f8`, after PR #75.
The historical specification and business probe retain their original `c06551a`
baseline; those observations have not been rewritten.

## Release decision

Eight accepted native contracts are implemented and explicitly activated after
local CI/apex verification and per-leaf CLI UAT. Seven pass complete-scope inquiry
UAT. The user separately authorized `forecast results list` to use the same
truthful backend-defect compatibility as cash accounts; fresh full-scope UAT
confirms partial live output and fail-closed total-change/cache protection.
**Compatibility is not backend repair or source completeness.** Account-filtered
success is independent evidence, never a substitute for full-scope coverage.

| Leaf | Kind | Width | CLI production UAT | Release |
| --- | --- | ---: | --- | --- |
| cash balances list | runtimes | 30 | 12/12 full scoped rows; 1/1 account filter; live, explicit refresh and disconnected offline | Enabled |
| cash groups list | settings | 100 | 1/1, with native group-code filter; settings/member configuration only; live, refresh, offline | Enabled |
| cash group-balances list | runtimes | 100 | 1/1 parent with nested members; independent USD runtime scope/cache; live, refresh, offline | Enabled |
| cash pools list | settings | 100 | BANK, 43/43 parents; no per-row detail acquisition; live, refresh, offline | Enabled |
| cash pools get | settings | none | Two genuine pool identities, each live, independent detail refresh and disconnected offline; id echo, BANK and inUse=Y | Enabled |
| cash credit-lines list | settings | 100 | 84/84 parents, nested credit/account configuration; live, refresh, offline | Enabled |
| cash statements end-of-day list | runtimes | 1000 | 6/6 populated single-day scope and a separately known valid 0/0 scope; live, refresh, offline | Enabled |
| forecast results list | runtimes | 5000 | Prior 7504/7502; fresh full live 20135 arrivals/20129 unique; strict and refresh reject changing totals. Scoped 6/6 cache survives failed refresh and disconnected read | Enabled, accounts-compatible backend limitation |

UAT uses the current dedicated profile, headless Chrome and CDP 9222. Liquidity
startup-origin authentication was verified independently of Payment. Browser
credentials stay in the browser. No production mutation, export, arbitrary
endpoint or arbitrary JavaScript command is exposed or executed.

Two private CLI runs retain 18 successful cash list-mode cases and 15 follow-up
cases. Four follow-up cases fail their expected-success release condition:
forecast full live, full refresh, the resulting absent offline cache, and an
explicit creation-time full-scope inquiry. The other 11 follow-up cases pass,
including valid empty EOD and both native pool details in all three modes.
An earlier run failed before business acquisition while preparing the isolated
candidate catalog; it does not count as business UAT. Historical native-response
replay is focused SIT evidence, not fresh production acceptance.

Private outputs and isolated SQLite caches remain under Git-ignored
`tmp/spec76-cli-uat-20261002T022457Z/` and
`tmp/spec76-cli-uat-20261002T022914Z/`, with directory mode 0700 and private files.
Raw arguments, identifiers and rows are not included in this report. Offline
checks install a transport factory that raises if any browser access is attempted;
they do not stop the user's Chrome or affect its authenticated profile.

## Released scope options

- Balances: repeatable `--entity` (native `entitys`, default Z21 when omitted),
  repeatable optional `--account` (`aliasNames`), `--timezone GMT+08`.
- Groups and group-balances: repeatable optional `--group-code` (native JSON
  array `userGroupCode`), `--equi-currency USD` only.
- Pools: fixed BANK; getter requires typed `--pool-id`, fixed `inUse=Y`.
  No category or state override is offered.
- Credit-lines: no unverified source search options.
- EOD: repeatable required `--entity` (`instIds`) and `--account`
  (`bankAccountAliasName`), required `--currency`, `--from`/`--to` YYYYMMDD,
  `--timezone GMT+08`. Account aliases are not account numbers.
- Forecast with known backend limitation: `--from`/`--to`, native HHmmss creation-time bounds,
  optional account arrays. No timezone request or inferred server timezone.
  Native amount-filter fields remain null; CLI amount options are not released.

Generic display/cache options retain shared behavior. Liquidity does not expose
`--as-of` or promise explicit historical-capture selection. Offline queries use
the existing scope/window and retained-coverage selection rules. CLI scope and
refresh scope use the same declarative options. Repeatable source options apply defaults
only when omitted, never append a default entity to an explicit selection.

## Data and storage invariants

- Reuse shared CDP/auth/allowlist/transport, ListSpec/DetailSpec, strict offset
  acquisition and atomic cache storage. No alternate browser or storage stack.
- Plugin projections apply exact configuration/member whitelists. New parent
  fields do not automatically enter settings. Runtime amount/used/available/
  capacity fields are excluded from configuration. Native pool detail includes
  observed shared sweep configuration through nested whitelists, not executed
  sweep actions.
- Group runtime data is separately acquired and cached despite sharing the
  group endpoint. USD equivalent currency is fixed request-scope metadata;
  original member currencies are not summed. Native observation times are
  separate from capture age and configuration modification times.
- Preserve native decimal strings (including observed thousands separators),
  finite Decimal/int values, zero, empty string and null. Do not divide responses
  by 100. Reject malformed amounts, booleans/containers and invalid identities.
- Validate nested member ids, duplicate identities and parent-relation echoes.
  Null/missing member lists remain null/missing rather than fabricated empties.
  Primary retention counts remain parent records, not exploded member rows.
- List scope identities bind tenant, kind, native method/path, schema/projection
  version, fixed request scope, currency/timezone and business source filters.
  Pool detail keys independently bind native identity and fixed BANK/Y contract.
- New projected leaves use nonzero partial-live results. Incomplete refresh
  returns `meta.complete=false`, `meta.published=false`, and preserves a valid
  prior cache. PR #75 account-list retention/freshness fixes remain intact.
- Forecast candidate acquisition never launches per-row realized-balance or
  accuracy requests. Its full-scope failure publishes no cache; subsequent
  offline inquiry correctly returns CACHE_MISS rather than a fabricated zero.

[Projected field/type evidence](2026-10-02-liquidity-spec76-field-evidence.md)
feeds the reproducible description generator. Observed types are not guarantees
for all future data. Existing leaf descriptions retain their historical dates;
new source-contract declarations record 2026-10-02 when released. Pending public
descriptions instead expose their specific release blockers.

## Directory migration and deferred leaves

Remove `cash groups get`, `cash credit-lines get`, and `forecast results get`
from active help/describe/query discovery. Group members and credit-line members
are native list expansions, not server getters. Forecast chart/realized-balance
calls do not establish a typed prediction-record getter. Their removal is not
successful business execution or proof that no other backend API exists.

The seven original B/D leaves stay non-executing with specific reasons:
account detail business error 999/shared list ids; unverified wallet membership
and native wallet balances; pool balance observation/currency aggregation gaps;
shared/merged credit usage observation gaps; accuracy cross-page duplicates and
unverified nonzero/error/formula/day-boundary semantics. Existing account count
3690/3691 behavior remains a separately tracked backend defect.

The forecast full-scope defect is separate from the older accuracy defect.
Earlier full-scope inquiries at width 5000 reported 7504 and collected 7502 unique
IDs. Fresh ordinary live observed 20135 arrivals/20129 unique and six cross-page
repetitions; strict live then observed native totals 20135-to-20200, and refresh
20484-to-20515. All use unchanged width/offset and validated dates. Do not infer a
shared backend root cause or extrapolate the earlier 4419-row single-page probe
into completeness. The user-approved accounts-compatible exception permits a
truthful query interface, never incomplete publication, source-count correction,
mutations or automatic smaller-page retry/fallback. Backend repair remains open.
See the [backend report and association advice](2026-10-02-forecast-results-backend-count-bug.md).

No production multi-page EOD or credit-line dataset, other pool category,
non-USD group equivalent currency, wider forecast range or amount-filter
combination was accepted from these bounded samples.

## Verification and remaining gate

Focused synthetic acceptance: 240 liquidity unit/integration tests pass after
implementation and migration, including native encoding, error/auth behavior,
identity echoes, projection types, scoped cache isolation, independent list/get,
partial results, failed refresh rollback, and unstable cross-page credit sorting.
Repository verification chronology (the final result is recorded below):

- Full pytest before the final public release-gate freeze: **1526 passed,
  23 subtests passed** in 822.03 seconds. Final focused verification after
  enforcing the CI gate and adding eight public-refusal cases: **240 passed**
  in 30.38 seconds. No second full-suite pass is claimed for the gate-only update.
- Ruff check: passed; Ruff format check: passed (222 Python files).
- Sampled description generator `--check`: passed.
- Changed-file active LSP: no unsuppressed error findings; 11 confirmed clean,
  one push-only check inconclusive. A stale new-file import finding was marked
  false-positive after successful runtime imports and the complete pytest run.
- code-review-graph refreshed and analyzed against the actual default branch
  `origin/master`. Main-worktree indexing omits untracked additions; the isolated
  committed review snapshot was rebuilt with all 135 Python files, including the
  new source/test modules. Graph estimates are not test or correctness proofs.
- Doc Guard: **passed, 86 Markdown files**, after resolving the 10 handoff
  convention errors. Three historical reports received only snapshot metadata;
  their historical baselines, observations and paths remain intact. The design
  copy received an explicit historical/current-state distinction. The directory
  policy and validator now accept versioned `docs/design/<slug>-vX.Y.Z.md` Issue
  copies only with a valid version and authoritative repository Issue link;
  `docs/spec/`, unversioned design files, wrong-host/fenced-only source links
  remain rejected. `make test-doc-guard`: **10 tests passed**.

Initial local Greptile attempts were blocked by authentication. The user restored
login on 2026-10-02; `whoami` succeeded, and the actual local CLI review completed
with exit 0 against isolated snapshot `34b713c0ae98` and base `a015620`.
That result is **review completed, not finding-free**: it reported P1 pool detail
identity type coercion, P2 explicit null balance loss, and P2 stale design status.
All three findings are corrected: versioned detail echoes require exact type and
value (legacy coercion stays compatible); explicit native nested balance nulls
remain null rather than disappearing; the historical design distinguishes its
frozen state from implementation. Two independent saved native pool details pass
strict parser/projection replay. Final focused verification: **256 tests and
20 subtests passed** in 35.23 seconds, including eight public-refusal cases and a
forecast-specific synthetic 7504/7502 contract regression. That regression proves
fixed width 5000, native offsets 0/5000, truthful ordinary/strict live errors and
metadata, byte-identical rollback, and disconnected reading of the prior complete
cache; it does not identify the production backend root cause. The first apex-effort local re-review completed on snapshot `095845a7e10f`,
confirming those three fixes and reporting two additional findings: P1 dated
response/window validation and P2 an unavailable `--as-of` claim. Full pytest on
that snapshot passed **1541 tests and 28 subtests** in 835.99 seconds.

The date gap was reproduced with out-of-window EOD and forecast rows, then fixed
at acquisition before live output or cache publication. Both declarations bind
native `%Y%m%d`, observed in six EOD and 4419 archived forecast rows; saved-response
request-window replay passes. Validation reuses the retention series parser and
rejects missing/empty/invalid dates, wrong formats, and dates before/after the
requested window. Legacy unversioned contracts remain unchanged. Twelve new
regression cases verify INVALID_RESPONSE, unchanged prior cache and disconnected
reading; no dates are silently filtered or inferred. The report now explicitly
states that Liquidity does not expose `--as-of`.

After these two fixes: **268 focused tests and 20 subtests passed** in 54.42
seconds; Ruff, description-generation check and Doc Guard pass. All nine changed
Python paths in the active LSP probe are confirmed clean with no errors.

Final second apex review on `657bec2cdb9b`: **exit 0, confidence 5/5,
comments=[]**, explicitly confirming all five previous findings are fixed and
no new actionable issue remains. The final complete pytest run after the date
fixes passed **1553 tests and 28 subtests** in 844.76 seconds. Ruff check/format,
Doc Guard (86 Markdown files), description generation and changed-file LSP
checks pass. The local CI/review authentication and documentation blockers are
resolved; remaining forecast disposition is a separately authorized
accounts-compatible backend-limitation/UAT decision, not an unresolved CLI
review finding. No GitHub workflow or remote PR review substitutes for the local CLI.

The review snapshot is `/tmp/dogopencli-spec76-review-tjlpwf8o`, with local base
branch `spec76-baseline` at `a015620`. Reviews run from that directory with
`greptile review --branch spec76-baseline --agent --json`; the next corrected
snapshot adds `--apex`, authorized by the user on 2026-10-02.
No changes were staged or committed in the original worktree, no push or PR was
created, and Python/runtime package versions remain unchanged.


## Final public release and forecast compatibility UAT

`UAT_COMPLETE_PASSED` contains seven leaf names; `UAT_COMPATIBILITY_PASSED` contains
forecast results only. `RELEASED` explicitly includes both evidence sets. The
backend-limited leaf has a prominent description note and retains nonzero
incomplete-result behavior. No public bypass flag, count normalization, per-row
accuracy enrichment, incomplete-cache publication or unverified amount option
was introduced. Existing 60 executing leaves stay intact; with eight additions
and three withdrawn getter removals, discovery has **133 paths: 68 executing,
65 deferred**. All sampled descriptions are regenerated for the active contracts.

After the user renewed SSO, headless Liquidity PortfolioMgmt authentication was
verified independently of Payment at CDP 9222. Fresh isolated production CLI UAT
in `tmp/spec76-cli-uat-20261002T144041Z/` confirms:

- Genuine narrower refresh: six complete records, its own scoped cache.
- Full ordinary live: 20135 native arrivals, 20129 unique IDs; fixed page width
  5000, offsets 0/5000/10000/15000/20000. Six cross-page repetitions, none within
  a page. Available data, error/warnings INCOMPLETE_RESULT, complete=false,
  exit 1 and unchanged cache; native total is never rewritten.
- Strict live: native count changes 20135-to-20200 across pages, so INVALID_RESPONSE,
  exit 1 and data=null; this is the existing fail-closed contract, not suppressed.
- Full refresh: native count changes 20484-to-20515; INVALID_RESPONSE, no dataset
  or publication and byte-identical previously complete scoped cache.
- Transport-disconnected offline: full scope correctly has CACHE_MISS; the
  independent narrower scope still reads all six complete retained records.

The first private harness expected only INCOMPLETE_RESULT for strict live and
stopped on the stronger count-change rejection. Inspection classified the actual
error; the continuation accepted only that exact backend-total-change failure
and completed refresh/offline checks. It did not rerun a smaller page or accept
arbitrary errors. The same-full-scope cache rollback guarantee is additionally
proven in synthetic SIT; no complete full production cache is fabricated.

Historical 7504/7502 native CLI rows also pass the final date/window validator.
Activation is based on full-scope compatibility evidence and explicit user
authorization, not on substituting the narrower complete scope for it. The final
activation-focused check and apex review are recorded below.
There is no version bump, package publication or GitHub PR in this work.

## Final activation verification and local review

Activation-focused pytest: **269 tests and 20 subtests passed** in 55.41 seconds.
Final full pytest after activation: **1554 tests and 28 subtests passed** in
852.58 seconds. Ruff check/format (223 files), description-generation consistency,
Doc Guard (87 Markdown files) and all seven activation changed-path LSP probes
pass. The actual public forecast route reads the genuine six-record complete
scope offline with a throwing transport factory, without candidate registration.

The activation review snapshot is `e62f9e0c4461`. Its final local
`greptile review --apex --branch spec76-baseline --agent --json` attempt failed
with ECONNRESET before an interrupted review existed. `--resume` confirmed no
interrupted review. One bounded fresh retry was rejected by the service:
`you've used all 50 trial reviews for this account`.

The final activation **apex attempt is quota-blocked, not passed**. That error
was not generalized into proof that ordinary reviews are unavailable. At the
user's explicit request, the same activated snapshot `e62f9e0c4461` was reviewed
with `greptile review --branch spec76-baseline --agent --json` (no effort flag).
It completed **exit 0, effort=base, confidence 5/5, comments=[]**, confirming all
five earlier findings are fixed and no new actionable issue remains.

**The required final local CLI review gate is passed via ordinary review.**
No quota reset, subscription upgrade, new-account workaround, remote PR/comment
or source-data mutation was performed. Prior corrected-core apex 5/5 and final
activation ordinary 5/5 are distinct results; the failed activation apex is not
misreported as passing. This does not establish unlimited ordinary usage or
precise premium quota policy. Private ordinary review output and commit-bound
metadata are retained alongside the failed apex logs.
