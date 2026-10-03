# Liquidity batch A implementation and evidence

Observed: 2026-10-04
Scope: general
Status: snapshot

Specification: [#87](https://github.com/proletariat64/dogopencli/issues/87).
Tickets: [decisions #90](https://github.com/proletariat64/dogopencli/issues/90),
[transfers #91](https://github.com/proletariat64/dogopencli/issues/91),
[quote investigation #92](https://github.com/proletariat64/dogopencli/issues/92),
[acceptance #93](https://github.com/proletariat64/dogopencli/issues/93).
Implementation: [draft PR #94](https://github.com/proletariat64/dogopencli/pull/94).

## Release status

Mandatory lists accepted: **0/2**. Quote investigation: **1/1 concluded**, optional
quote list: **0/1 enabled**. Global actual counts remain **69 supported / 64
unsupported**, out of 133 query leaves. The mandatory target would add two
supported leaves; native samples and candidate code do not change actual counts.
The PR remains draft and the full specification stays open.

| Leaf | Current evidence | Missing release evidence |
| --- | --- | --- |
| decisions list | current caller, nonempty types, independent inclusive start/creation bounds, full native 264/264 acquisition, gated implementation | registered production CLI lifecycle UAT and final local CI/review |
| transfers list | current caller/encoding, nonempty types, separate raw states, bounded native queries, gated implementation | complete representative acquisition, transaction/display-time mapping, registered CLI lifecycle UAT and final local CI/review |
| quote-groups list | investigation concludes offsets repeat and no native ending protocol is proven | authoritative complete-response or pagination protocol, identity/version scope and independent first-release gates |

## Native verification

An independent Liquidity auth check initially passed on the existing headless
Chrome at CDP 9222; Payment authorization was not reused as proof. Current native
UI source matched the saved source exactly: 15,763,128 bytes, SHA256
`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`.
Only the three reviewed inquiry endpoints were probed. No business mutation,
detail cascade, new browser stack, credential copying or production-cache writes
were performed. Raw production data remains private outside Git.

Decisions use POST JSON `/api/ai/decision/report/getAllNew.json`, success envelope,
`data.data` records and `data.totalCount`. Native integer `id` is the identity;
`reportId`, `groupId` and associated `orderNo` remain distinct. Start Time maps to
`executionTimeStart`, while Created Time maps to `gmtCreate`. Both independent
native timestamp ranges are inclusive: an exact start-time point returns records
at that point and neighboring second points return none; exact creation-time
points return records with that creation time. No source timezone is inferred.
The candidate requires both pairs as `YYYY-MM-DD HH:mm:ss` strings.

The September 30 scope, with both ranges from 00:00:00 through 23:59:59, completed
27 native pages of width 10: **264 arrivals, 264 unique ids, fixed reported total
264, zero duplicate arrivals and zero identity conflicts**. All rows passed tenant
and both time-range checks. All 264 native rows also passed the candidate business
projection without copying native values into fixtures. A separate October 3
scope returned eight rows, demonstrating another nonempty date scope; this is not
CLI lifecycle acceptance or a cache-equivalence proof.

Transfers use POST form `/transferOrderQuery.json` with `tntInstId` and a
JSON-string `transferOrderQueryRequestVO`. The native jQuery wrapper passes a data
object; its `type: json` marker does not turn the body into JSON. A JSON-body
comparison returned a different failure envelope and is excluded. Native records
are `result.data`, with matching top-level `count` and `result.count`. The typed
identity is string `orderNo` within the tenant and exact query scope.

Bounded September 30 offset queries returned nonempty pages against count 4,954;
October 3 returned nonempty data against count 441. A known-order probe matched
only its native September 30 scope and not adjacent days, but displayed `gmtCreate`
was October 1 with a GMT+08 suffix. Exact display/shifted timestamp comparisons
returned no match. These observations do not prove a timezone conversion or date
mapping. The candidate retains exact native history scopes, never partitions or
filters locally by displayed `gmtCreate`, and remains gated. `orderStatus`,
`receiptStatus` and `executeResult` remain separate raw fields; Receipt Status is
the verified UI label, and no bank-success meaning is invented.

See the independent [quote investigation](2026-10-04-liquidity-batch-a-quote-groups-investigation.md)
for the identical 54-row offset responses, identity/version distinctions and
continuation conditions. No optional list is enabled.

## Implementation and local validation

Both candidate implementations reuse the existing list registry, restricted
transport, acquisition, history captures, atomic store, result policy and CLI.
Default queries are offline; refresh alone publishes; live never writes or falls
back. Strict partial acquisition refuses publication, default safe partial keeps
warnings, and hard failures preserve old captures. List records do not replace
native detail/history records. Both release allowlists remain empty.

The merged public CLI/fake-CDP/temporary-SQLite candidate suites passed **58 tests**.
They cover bounds before access, typed identities and tenant checks, privacy,
precision, raw states, pagination, empty captures, live isolation, offline
readback, partial/strict behavior, hard failures and independent detail caches.
Worker Ruff/format/diff gates passed. A pre-existing registry-count test expected
46 while the baseline already includes 47 list leaves; the integration corrects
that count without enabling another leaf. Final local Kimi JSON CI and independent
Standards/Spec review are pending. Their results will record exact source commits,
actual commands and `confidence: ?/5`, separately from production acceptance.

## Browser blocker and continuation

Full-transfer acquisition and public CLI production UAT are blocked by repeated
preflight `browser_unavailable: target websocket failure: Connection timed out`.
An initial existing-login recovery returned authenticated headless and enabled the
complete decision acquisition. Later sequential transfer preflight and the same
recovery failed again before transfer business requests. CDP reachability and the
earlier successful auth observation do not establish current availability.

Restore the existing dedicated Chrome connection, re-check Liquidity authorization,
then acquire a complete representative transfer scope and resolve native date
boundaries. Run candidate and actual registered public CLI nonempty/empty lifecycle
matrices for each releasable leaf, including its own refresh/offline equivalence,
live no-write behavior and detail-cache independence. Enable each leaf only after
all its first-release gates pass. Keep #87/#90/#91/#93 open while required delivery
remains incomplete; quote investigation completion does not change the 2-list
denominator. No package version bump or release is included.
