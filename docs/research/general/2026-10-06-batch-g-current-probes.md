# Batch G current inquiry probes

Observed: 2026-10-06
Scope: general
Status: snapshot

This investigation follows the request to implement all reasonable,
native-evidenced remaining lists. It uses master `6f0fbae` in an isolated
worktree and the exclusively authorized CDP 9223 profile. Monitoring stays
HOLD. These are discovery probes, not public CLI production acceptance of an
enabled leaf.

## Source and authorization

Knowledge-base discovery and original product documents are recorded in
[the source-contract note](2026-10-06-batch-g-source-contracts.md). After human
SSO, public CLI `auth check --domain liquidity` returned authenticated and
healthy in headless mode against the Liquidity origin. All business calls use
only the four native inquiry contracts recorded in that note, under the
authorized tenant. No mutation, detail fallback, alternate tenant or privilege
change was attempted.

The saved production UI asset was fetched again: 15,763,128 bytes, SHA-256
`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`.
Its bytes match the previously inspected native bundle. Raw source and private
probe material remain outside tracked files. This report publishes counts,
schema field names and scope metadata only.

## Current results

| Candidate | Probe | Result | First-enable decision |
| --- | --- | --- | --- |
| `investment quote-groups list` | JSON POST, `(pageSize,rowStart)` = `(1000,0)`, `(5000,0)`, `(5000,5000)` | All three succeed with the same ordered 54 records; 54 distinct native IDs; no total or terminal marker | Blocked: offsets do not progress and authoritative full-response coverage is unproven |
| `pricing bills list` | DEPOSIT and LOAN independently, widths 1000/5000, billing dates 20260101–20261006 | Four successful responses, each zero records and count zero | Blocked: no populated identity, period or monetary schema evidence |
| `rules treasury-transfer list` | Native rule-list request, width 1000 | HTTP 200 with `resultFlag=false`; no rule array or rule count | Blocked: current business failure is not an empty population |
| `operations demands list` | Native FUND_REQUIRE source, year and seven daily scopes | Year failed; four valid daily scopes empty, 2026-04-01 returned 79/79 unique tasks, 2026-01-01 returned 1/1; one daily CDP evaluation failed | Enabled candidate with required timestamp bounds and fixed width 5000; independent CLI UAT passed |
| `operations executions list` | Independent instruction and realtime sources, year, seven daily scopes and four historical month windows per variant | Fourteen daily queries succeed empty; two year and eight month queries fail with 099 | Blocked: no populated execution identity/schema/scope evidence |
| `pricing valuations list` | Native caller and PRD inspection | Verified fee-order source is already represented by `pricing fee-orders list`; no independent investment valuation caller established | Blocked: re-labeling fee orders would expose the wrong business object |

Task probes use native timestamp fields at midnight. The wide scope is
2026-01-01 00:00:00 through 2026-10-07 00:00:00 (today plus one day), width
1000. Daily scopes use width 5000. A business failure with a zero-valued result
body is still a failure. CDP evaluation failures do not establish empty data
or a valid endpoint response.

## Boundaries

For demands, successful empty daily scopes were 2026-10-06, 2026-10-05,
2026-09-01 and 2026-07-01. The 2026-09-30 query was a CDP evaluation failure,
not an empty result. The 2026-04-02
follow-up was also populated (reported count 75); it was not an empty-day
sample. Production UAT uses the verified empty 2026-10-06 scope.

The existing [quote-group gate](2026-10-04-liquidity-batch-a-quote-groups-investigation.md)
and [funding/execution first-enable requirements](../../design/liquidity-funding-execution-v0.1.0.md)
require verified native identities, scope, acquisition protocol and independent
CLI UAT. ADR 0019 runtime partial handling does not supply missing first-enable
evidence. Only the independently qualified demand list is registered by this
implementation; the other candidates retain their existing unsupported gates.

## Funding-demand qualification and public CLI acceptance

Repeated fixed-width 5000 inquiries for 2026-04-01 00:00:00 through
2026-04-02 00:00:00 each returned 79 arrivals, 79 unique string task IDs and
reported count 79, with equal identity sets. All returned tenants, sources and
execution dates matched scope; native amounts were finite decimal strings.
The offset-79 inquiry returned zero records with the same reported count.
An equal-start/end query at an observed execution timestamp returned two tasks,
both exactly at that timestamp, proving inclusive boundaries for this caller.

Width 1000 returned a business 099 failure in a follow-up. Width 30 returned
30/30/19 arrivals but only 77 unique task IDs across those three pages. That
small-page acquisition is incomplete and is not the implementation's request
configuration. No duplicates are discarded to claim completeness. The shared
collector still detects missing/conflicting identities and total changes at
runtime, with existing partial/default and strict-result handling.

`liquidity operations demands list` and its root-level refresh require both
`--execute-from` and `--execute-to` in YYYY-MM-DD HH:mm:ss. They query the fixed
FUND_REQUIRE source, use `taskId` identity, preserve decimal strings and unknown
status codes, and validate returned timestamps/tenant/source before output or
publication. No source timezone is inferred. Exact timestamp scopes retain
independent history captures. The whitelist excludes account numbers, aliases,
nested action detail and wire pagination fields. No getter is enabled.

The new branch's public CLI completed ten independent production acceptance
steps against an isolated cache: strict 79/79 refresh, strict 79/79 live,
browser-disconnected offline readback, strict zero-row refresh and offline
readback, failing wide refresh, preserved positive offline readback, rejection
of unbounded live, deferred getter, and describe. Live left the cache bytes
unchanged. The failing wide refresh returned BUSINESS_QUERY_FAILED with
published=false and preserved cache bytes. Offline checks used an unreachable
CDP address and succeeded from cache. Private results are excluded from Git.

The preceding Batch F investigation remains relevant: identical wallet and
non-wallet responses did not establish wallet membership; sampled funds were
empty; no independent balances/offers/sessions/rule-status/routes contract was
verified. This run does not change those conclusions or claim that its sampled
dates cover every historical day.
