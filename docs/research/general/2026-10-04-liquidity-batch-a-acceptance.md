# Liquidity batch A implementation and evidence

Observed: 2026-10-04
Scope: general
Status: snapshot

Specification: [#87](https://github.com/proletariat64/dogopencli/issues/87).
Tickets: [decisions #90](https://github.com/proletariat64/dogopencli/issues/90),
[transfers #91](https://github.com/proletariat64/dogopencli/issues/91),
[quote investigation #92](https://github.com/proletariat64/dogopencli/issues/92),
[acceptance #93](https://github.com/proletariat64/dogopencli/issues/93).
Implementation: [PR #94](https://github.com/proletariat64/dogopencli/pull/94).

## Release status

Mandatory production CLI lists accepted: **2/2**. Quote investigation: **1/1
concluded**; optional quote list: **0/1 enabled**. The source registry contains
**71 supported / 62 unsupported / 133 total** query leaves, including **49 list
leaves**. Supported kinds are 32 settings, 32 runtimes and 7 reference. The baseline
was 69 supported, 64 unsupported and 47 lists. This change does not publish a
package version or perform a production business mutation. Final Standards and Spec reviews passed with no findings. All mandatory gates
are complete; production acceptance and local review remain separate evidence.

| Leaf | Accepted production evidence | Remaining boundary |
| --- | --- | --- |
| decisions list | registered refresh, offline equivalence, complete live without writes, empty lifecycle, scope isolation; 264 unique rows | exact native timestamp strings; no inferred source timezone |
| transfers list | registered refresh, offline equivalence, complete live without writes, empty lifecycle, scope isolation; 4,954 unique rows | native Transaction Date scope; display timestamp mapping is unproven |
| quote-groups list | investigation concluded | unsupported: complete-response or ending protocol and identity/version scope remain unproven |

## Native contracts and boundaries

Independent Liquidity authorization was verified; Payment authorization was not
reused as proof. Current native UI source matched the saved source: 15,763,128
bytes, SHA256
`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`.
Only reviewed inquiry endpoints were used. Raw production records, identifiers,
responses, configuration and browser profiles remain private and outside Git.

Decisions use POST JSON `/api/ai/decision/report/getAllNew.json`, `data.data`
records and `data.totalCount`. Native integer `id` is the identity; `reportId`,
`groupId` and associated `orderNo` remain distinct. Start Time maps to
`executionTimeStart`, and Created Time maps to `gmtCreate`. Native point and
neighboring-second probes verified both independent inclusive ranges. All four
bounds are required as exact `YYYY-MM-DD HH:mm:ss` strings. No timezone conversion
is inferred. The September 30 native acquisition completed 27 pages of width 10:
**264 arrivals, 264 unique ids, fixed total 264, zero duplicate arrivals and zero
identity conflicts**. Every row passed tenant, time-scope and typed projection
checks. October 3 also returned eight rows in a separate native scope.

Unnecessary debit and credit alias names were removed from the projection and
schema. Entity and bank ids identify the corresponding debit and credit business
sides; they remain distinct from account data. Populated sanitized fixtures prove
alias omission from output, descriptions and SQLite. Operator, account, free-text
and nested response fields remain excluded.

Transfers use POST form `/transferOrderQuery.json`, with `tntInstId` and a
JSON-string `transferOrderQueryRequestVO`. The native jQuery caller passes a data
object; its `type: json` marker does not encode a JSON request body. JSON-body
comparison failed and is excluded. Native `result.data` records use nonempty
string `orderNo` identity within the tenant and exact native query scope.
Top-level `count` must match `result.count` and remain fixed during acquisition.
Required `YYYYMMDD` Transaction Date bounds map to native inclusive day strings;
other debit and credit ranges remain blank as in the verified caller.

Independent October 3 native acquisition completed **470 arrivals, 470 unique
order numbers and fixed total 470**, with width 10. A known-order native probe
matched October 3 and overlapping ranges, but not either adjacent day; displayed
`gmtCreate` was October 4. This establishes native query selection, not a server
timezone or a mapping from displayed creation time to Transaction Date. The
implementation preserves the exact native history scope and raw `gmtCreate`.
It never filters or partitions by displayed creation time. `orderStatus`,
`receiptStatus` and `executeResult` remain separate raw fields. Receipt Status is
the verified UI label; no bank-success interpretation is invented.

An active October 3 registered refresh correctly failed with `INVALID_RESPONSE`
when total changed from 472 to 478 after 26 pages. A separate width-50 feasibility
probe also encountered total drift; it did not prove complete acquisition and did
not change the implementation. Both lists retain native width **10**. The
previously verified September 30 scope provided the stable registered transfer
acceptance below. Separate captures at different times are not required to have
the same total; a single fixed-total acquisition is.

See the [quote investigation](2026-10-04-liquidity-batch-a-quote-groups-investigation.md)
for identical 54-row offset responses, identity/version distinctions and
continuation requirements. No optional quote list is registered.

## Registered public CLI production UAT

Product source was pinned to
`9476c93baf3388c9a9cd4789d97ebb2946fe9926`. The later
`e02fd2ae1007d110b13588bee2dceb6c28769671` commit changes only two snapshot test
expectations. Source release flags were used directly, without a registry
bootstrap. A separate candidate-mode check had already passed decisions 264 and
transfers 472; it is not counted as registered acceptance.

Each registered test used the actual public CLI, the existing CDP transport and
an independent private SQLite backup of the configured cache. The original cache
was opened read-only and never refreshed. A recording wrapper retained private
status/body evidence without cookies, tokens, evaluated expressions or final
URLs. Offline commands used a transport factory that rejects all browser access.

| Registered CLI check | Decisions | Transfers |
| --- | --- | --- |
| bounded nonempty scope | September 30; both full timestamp ranges | September 30 Transaction Date |
| strict complete refresh | 27 pages, 264 arrivals/unique ids/total | 496 pages, 4,954 arrivals/unique ids/total |
| offline full readback | exact allowlisted native projection, same scope/fetched-at | exact allowlisted native projection, same scope/fetched-at |
| complete nonempty live | passed; database bytes unchanged | passed, 496 pages; database bytes unchanged |
| October 10 empty live | complete zero; no write | complete zero; no write |
| strict empty refresh and offline | complete zero published/read back | complete zero published/read back |
| nonempty scope after empty refresh | original capture preserved and readable | original capture preserved and readable |
| offline help and describe | passed without CDP | passed without CDP |
| offline snapshot | supported/present, 264 rows, no write/CDP | supported/present, 4,954 rows, no write/CDP |

These private cache backups contained **zero** existing native decision/detail/
history and transfer/detail namespaces. Production checks prove absence of detail
cascades and no new native-detail writes; they do not prove preservation of
populated native details. Meaningful public-CLI/fake-CDP/real-SQLite tests separately
seed populated native detail/history caches and prove preservation and readability.

The original CDP 9222 session repeatedly timed out. With user authorization, an
isolated dedicated Chrome profile on CDP **9228** was opened for human company
SSO. The user confirmed sign-in. Independent Liquidity checks then passed in
headed and headless modes, and routine UAT used headless Chrome. The original
browser/profile was preserved; no credentials were copied and no SSO was
automated. The earlier browser/authentication blocker is resolved for this run.

## Implementation and local CI/review

The two lists reuse the existing registry, restricted transport, acquisition,
history captures, atomic store, result policy and CLI. Default queries are offline;
refresh publishes atomically; live neither writes nor falls back. ADR-0019 safe
partial behavior remains available, strict partial refuses publication, and
hard contract failures preserve old captures. New list caches remain independent
of native detail/history caches. No getter, quote/history protocol, cache schema,
browser stack or shared error-policy rewrite is included.

Local Kimi CLI ran with `/code-review` prompts for independent Standards and Spec
reviews and **`stream-json`** output. Initial full reviews at `43546e7` passed;
field-necessity feedback led to alias removal and documented business-id purpose.
Incremental Standards review at `9476c93` passed with no findings, confidence 4/5.
Final Standards addendum and Spec review at `e02fd2a`, including the synchronized
working-tree README and acceptance report, both passed with no findings and
confidence 4/5. They covered release flags, production evidence and snapshot
expectations. Their pending-gate notes record the review-time snapshot; the
completed companion review supersedes that workflow item. Review evidence is
limited to sanitized source, tests and documents;
private browser and production records are excluded.

The first release CI at `9476c93` reported 410 passed and two failed snapshot
assertions that still expected the unsupported baseline. Their failure evidence
was retained. The assertions were updated to the released supported count and to
list-cache independence from populated native history. Product code was unchanged.
A fresh local Kimi JSON CI at **`e02fd2a`** passed **412 tests plus 20 subtests**,
Ruff check, format check (265 files), document guard (104 Markdown files) and
`git diff --check master...HEAD`. Every listed gate ran once with exit 0; process
exit alone was not treated as a CI pass. CI result confidence is 5/5 for those
observed checks.

Tests use public CLI dispatch, fake CDP and temporary SQLite for typed identities,
request rejection, independent ranges, pagination/total drift, precision, privacy,
empty captures, live isolation, partial/strict behavior, hard failures, native
cache independence and snapshot behavior. The 58 new-list tests are part of the
412-test gate. A pre-existing registry assertion incorrectly expected 46 lists;
the baseline had 47, and the released branch has 49.

The pytest gate used `rtk proxy env PYTHONPATH=<worktree>/src
/home/ubuntu/dev/dogopencli/.venv/bin/python -m pytest -q` for new-list suites,
existing Liquidity CLI/partial/history/operations suites, snapshot CLI/domain
suites, Liquidity capability/projection/fields/envelope/collect/store suites,
result policy and document guard. Other gates were `rtk proxy ruff check .`,
`rtk proxy ruff format --check .`, `rtk proxy make doc-guard` and
`rtk proxy git diff --check master...HEAD`. Private JSON summaries retain exact
commands and exit codes. Graph impact inspection covered the actual master diff;
public-CLI tests cover the dynamically dispatched projection/scope paths that
static call analysis does not resolve fully.

Overall local CI/review **confidence: 4/5**. Both final review processes exited 0;
the initial Spec storage restriction and the Standards API timeout were resolved
by the authorized local invocation and automatic CLI retry, respectively. Neither
failed attempt was treated as an approval.
This rating does not substitute for production UAT. No package version bump,
package release or PR merge is included. Quote groups remain unsupported.
