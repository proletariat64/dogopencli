# PTR case and order implementation and validation

Observed: 2026-09-27
Scope: payment
Status: snapshot

## Delivered scope

Branch `feat/payment-ptr-61` implements the independently frozen case-library
slice of [#63](https://github.com/proletariat64/dogopencli/issues/63), under
[parent #61](https://github.com/proletariat64/dogopencli/issues/61).
The [frozen issue comment](https://github.com/proletariat64/dogopencli/issues/63#issuecomment-5852780520)
and [native contract](2026-09-27-payment-ptr-cases-accounts-contract.md) define
its acquisition, field projection and filters.

The independently frozen bounded-order slice of
[#64](https://github.com/proletariat64/dogopencli/issues/64) is also delivered;
its [frozen comment](https://github.com/proletariat64/dogopencli/issues/64#issuecomment-5852953383)
and [native contract](2026-09-27-payment-ptr-orders-contract.md) define the
required UTC+8 half-open modification interval and padded complete acquisition.

Commands: `payment ptr cases list`, `payment ptr orders list`, explicit `--live`,
`refresh payment ptr cases`, `refresh payment ptr orders`, help and describe.
Orders require `--updated-from` and `--updated-to` on list and refresh. No get or mutations.

The user ultimately retained the original outflow-only requirement. The
account and patrol libraries were not admitted as shared configuration scopes.
The five other resource commands remain unregistered with evidence gaps recorded
on #62 and #65–#68. This work does not close the parent roadmap.

## Production evidence versus CLI UAT

Native inquiry research established 3,292 unique cases and equal full reads at
5,000/10,000/5,000, plus the documented schema and outflow baseline relation.
That evidence establishes the query contract; it is not an end-to-end CLI UAT.

Two CLI UAT attempts used a private configuration and cache location under
ignored `tmp/ptr-implementation/uat-private/`. Both failed at the shared
browser/authentication probe with `BROWSER_UNAVAILABLE`, before any PTR
business request. A subsequent serial `auth check` and one supported
`login --timeout-seconds 60` recovery also failed at the target-websocket probe.
This does not establish expired SSO or denied business permission.

Both initially failed attempts verified the operator cache digest was unchanged.
After the user confirmed network restoration again, the same public CLI UAT
succeeded: refresh published 3,292 projected cases, every one of the 12 local
filter flags returned matching production rows, and a combined-filter live read
returned the selected case. Private-cache digests before/after live were equal;
the operator cache digest also remained unchanged. Raw values stayed in memory
or the private SQLite cache, never terminal output or Git.

A second offline pass over that production snapshot validated all 3,292 rows
against describe's JSON Schema, the default 100-row window, limit/offset/fields,
JSON/table output, fresh/complete requirements, repeated-value OR and cross-field
AND, invalid parameters and absent deferred commands. Private and operator
caches remained unchanged. **The production CLI UAT blocker is resolved for #63.**

## Bounded orders production CLI UAT

The first order CLI attempt failed at the browser probe before the business query.
After network recovery, the same private-cache public CLI run passed for
`2026-09-01T00:00:00+08:00` through `2026-09-27T00:00:00+08:00`:

- Refresh published 104 projected orders after two complete padded reads.
- All 104 rows passed describe's schema; every one of the 10 local filters passed.
- Combined-filter live queries, fields, output window, table, fresh and complete checks passed.
- Live left the private cache unchanged; the existing 3,292-case snapshot was unchanged.
- An uncached different interval produced `CACHE_MISS`; invalid dates, blank filters
  and conflicting output windows produced `INVALID_ARGUMENT` with exit 2.
- The operator cache digest was unchanged. Raw values remained in private storage or memory.

Both #63 and #64 have successful production CLI acceptance. The remaining five
resources retain their independent contract gates. Synthetic order tests also
cover timestamp padding, half-open local boundaries, padded-scope drift, the
500-row cap, atomic failed-refresh preservation, independent interval snapshots,
authentication expiry and request allowlisting. Production never induced failure
or mutation to exercise those rejection paths.

## Case public parameter verification matrix

All fixture data are synthetic. SIT runs public CLI dispatch, shared transport
allowlisting, the parser, collection, and actual temporary SQLite publication.

| Surface | Synthetic proof | Production CLI UAT |
| --- | --- | --- |
| refresh; default offline list | Two complete reads, lexical identity ordering, atomic cache read | Passed after network recovery |
| --live | Same complete acquisition/filtering; no cache publication or fallback | Passed after network recovery |
| --id, --name, --case-type | Per-flag live/cached exact match, OR, case sensitivity, literal wildcard, whitespace rejection | Passed against private production snapshot |
| --channel, --debtor-account, --debtor-currency, --clearing-system | Per-flag nested baseline local match, missing/null and AND boundaries | Passed against private production snapshot |
| --creditor-currency, --obo, --fvt | Per-flag live/cached whole-string matching | Passed against private production snapshot |
| --baseline-id, --creditor-account-alias | Per-flag matching on the exact typed relation/alias field | Passed against private production snapshot |
| --limit, --offset, --all | Window separate from completeness, invalid/conflicting values rejected | Passed against private production snapshot |
| --fields | Top-level projection; omitted sensitive fields cannot be recovered | Passed against private production snapshot |
| --format json/table | JSON envelope and table execution | Passed against private production snapshot |
| --require-fresh | Fresh snapshot accepts; 73h-old snapshot fails under default72h | Passed against private production snapshot |
| --require-complete | Complete scope independent of output window and freshness | Passed against private production snapshot |
| help/describe | Offline command discovery; JSON Schema validates representative retained rows | Installed-wheel smoke passed |
| authentication expiry | Explicit SSO landing raises AUTH_REQUIRED; cached scope remains available | Not induced in production |
| absent cache/source isolation | Other payment configuration cannot satisfy PTR namespace | Private UAT refresh isolated; operator cache digest unchanged |
| failed acquisition | Wrong echo, missing identity/baseline, duplicate, truncation, refusal, drift preserve prior cache | Native overlap observed; CLI failure scenarios synthetic |
| sensitive fields/precision | Allowlist at all nested levels, poisoned-cache rejection; Decimal and arbitrary-precision integer retention | Passed production schema/projection validation; extreme numeric bounds synthetic |
| request restrictions | Fixed origin/path/GET and page0/5000 only; detail, filters and other requests rejected | Native list query verified |
| full empty scope | Strict echoed zero-total/empty-array success | Synthetic only; never observed unfiltered empty production library |

## Local verification

Focused CLI/describe and capability tests passed before the full suite. The
92 capability tests cover both resources, including the arbitrary-precision integer regression.
The combined focused CLI, help, describe and capability run passed 306 tests.
Ruff check and formatting pass; documentation guard passes. A wheel built and
installed into an independent temporary virtual environment passed offline list
help, refresh help and describe from outside the repository.

An ephemeral `ty` check of all four new modules passes. Checking all changed
application files reproduces 27 pre-existing diagnostics in CLI/registry,
verified against the original HEAD; no new diagnostics remain. No typechecker
configuration or project dependency was introduced.

Final full regression: **1,293 tests and 23 subtests passed** in 803.79 seconds.
The final wheel was rebuilt after both resources were implemented; independent
installed help and describe smoke checks passed for cases and orders.

## Independent review

Standards axis: no documented-standard violations. One low-priority judgement:
case and order local filter matching repeats the same small loop. It remains
resource-local in this slice; a future shared matcher could prevent divergence.
Spec axis: no implementation defect or scope creep. Acquisition, parsing, CLI
integration and tests received independent review; order reading metadata had a
separate independent reviewer because the main spec reviewer authored that file.
The initial production CLI UAT finding was resolved by successful private-cache
runs after network restoration; native research and CLI acceptance remain distinct.
