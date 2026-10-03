# Issue #82 operations list contract prerequisites

The demands, executions and swaps leaves are `runtimes`. Demands and executions
still have no usable nonempty native records. Current swaps evidence provides
nonempty records and a complete bounded trade-date inquiry, while its unbounded
listing has overlapping pages. Empty query success establishes neither a
nonempty record contract nor an eligible production release.
The implementation specification is
[Issue #82](https://github.com/proletariat64/dogopencli/issues/82).

## Native inquiry evidence

| Leaf / variant | Native inquiry | Source discriminator | Record container | Reported total |
| --- | --- | --- | --- | --- |
| `operations demands list` | GET `/riskActionTaskQuery.json` | `FUND_REQUIRE` | `result.dataValue` | `result.count` |
| `operations executions list`, instruction | GET `/riskActionTaskQuery.json` | `INSTRUCTION_ACCOUNT_FLOW`, `INSTRUCTION_ACCOUNT_FLOW_MANUAL` | `result.dataValue` | `result.count` |
| `operations executions list`, realtime | GET `/riskActionTaskQuery.json` | `REAL_TIME_INITIATIVE_SUPPLEMENT`, `REAL_TIME_PASSIVE_SUPPLEMENT`, `REAL_TIME_INITIATIVE_COLLECTION` | `result.dataValue` | `result.count` |
| `operations swaps list` | POST `/swapOrderQuery.json` | authorized native entity scope | `result.swapOrderVOList` | `result.count` |

These are inquiry contracts from the native UI and current production probes.
Demands and executions have no executable `ListSpec` contract. Swaps has a
candidate declaration gated by production CLI UAT and CI. Authentication,
permission and transport failures remain real
failures and cannot be represented as empty results.

For task queries, URL query fields are `tntInstId` and a JSON-string
`riskActionTaskQueryVO`. The VO carries `tntInstId`, `source`, `rowStart`,
`pageSize`, `startExecuteTime` and `endExecuteTime`. Demands and the two execution
source sets must remain isolated. UI defaults and displayed field names do
not prove typed row structure, identity, status meanings, time zone or inclusive
date boundaries.

For swaps, the historical successful encoding was form-urlencoded with
`tntInstId` and JSON-string `swapOrderQueryVO`. Native trade, near-leg value and
far-leg value date filters are different business dimensions. Authorized native
entity scope must not be silently broadened. The current native selected entity
preference is absent, so both entity sides are explicit empty arrays. Reusing
an earlier selected entity produced empty results and did not reproduce the
current native default. The CLI candidate fixes the current empty arrays and
does not expose additional unverified entity filters.

The UI labels `dealId` as Deal ID and supports a query deep link by `dealId`.
Its column `key` is not a table `rowKey`; no claim of a native `rowKey="dealId"`
is made. Current records establish a nonempty string Deal ID within the tenant
and query scope. `orderId`, `hedgeOrderId` and `gapId` remain separate native
identifiers. Same-identity different content is a hard failure. Observed
same-content cross-page repeats do not prove coverage.

Both historical envelope flags, `resultFlag` and `result.success`, were true.
Native pagination uses `rowStart`/`pageSize`, with width 10 for the candidate.
Reported total zero alone does not prove populated pagination boundaries.

## Current source observations, 2026-10-03

| Leaf / scope | Source result | Consequence |
| --- | --- | --- |
| Demands and both execution variants, current one-day scopes | Successful empty lists | No nonempty schema, identity or state semantics; unsupported |
| Demands and both execution variants, native broader date scopes | Error `099`, database exception | Real backend error; no empty substitution or backend repair in this batch |
| Swaps, native unbounded default | 96 pages; reported/arrivals 959, unique 952, 7 repeated arrivals, no content conflict | Complete acquisition unproved; this scope is excluded |
| Swaps, trade dates 20260901–20261001 | 2 pages; reported/arrivals/unique 15, no duplicates or conflicts | Representative bounded pagination evidence |
| Swaps, 20260930–20261001 | 2 records; each date alone gives 1 | Native inclusive trade boundaries verified |
| Swaps, trade date 20261003 | Complete zero records | Native complete-empty scope evidence |

The user approved the bounded trade-date-only swap inquiry after the unbounded
overlap was found. Both `--trade-from` and `--trade-to` are mandatory YYYYMMDD
dates; missing, invalid or reversed bounds fail before network access. Neither
the unbounded native scope nor backend overlap repair is part of this delivery.

`tradeDate`, `nearLegValueDate` and `farLegValueDate` are distinct native YYYYMMDD
business dates. Only trade dates define this CLI scope; near/far filters are
not exposed. Source time zone and timestamp freshness are not inferred from
`fetched_at`. `gmtCreate`/`gmtModified` are native integers and optional
`gmtSend`/`gmtReturn` were integer or null. Capture metadata does not establish
a source observation time.

Native swap amounts and FX rates were strings. The candidate preserves those
strings and decimal precision, does not divide by 100, and distinguishes null,
blank and zero. It preserves raw status values without assigning unverified
business meanings. Installed describe records observed field types without
source values or a closed state enum.

The candidate uses the existing history cache profile: each exact trade-date
scope has independent capture history. It does not join captures to fabricate
coverage for another range. Runtime safe partial/default and strict behavior
continue through the existing collector and common result policy. Production
release still requires independent CLI UAT and local Kimi CLI CI/review.

## Release prerequisites

Each leaf stays unsupported until the following evidence exists independently:

1. Current native read-only inquiry, usable nonempty records and verified
   structure/types/nullability.
2. Native unique identity within the declared scope. Shared endpoints do not
   imply shared identity or business scope; positions and whole-row hashes
   must not be substituted for identity.
3. Validated date/filter scope and business semantics. Execution state meanings
   must be verified, preserving raw unknown values. Swap trade and settlement
   dates must remain distinct. `fetched_at` is capture time only.
4. Representative full acquisition with validated termination, reported total
   units, raw arrivals, unique count and cross-page boundaries. No identity
   conflict, duplicate or omission may be hidden by deduplication.
5. Existing public CLI behavior: explicit refresh and exact capture offline
   equivalence; complete-empty capture; live no-write proof; default/strict
   incomplete quality; refresh failure preserving prior cache; offline
   help/describe; and per-leaf production read-only UAT.

For demands and executions, if evidence becomes available, implement declarative
leaf contracts using the existing shared transport, collector, result policy and
list capture store.
Choose history versus dated retention from verified time semantics. Test through
public CLI plus fake CDP and temporary SQLite, then pass the independent
production gate. Synthetic tests cannot supply native evidence.

## Evidence and limits

Historical empty probes and their published native UI evidence are recorded in
[2026-10-01 liquidity live probes](2026-10-01-liquidity-live-probes.md),
sections `operations demands list`, `operations executions list` and
`operations swaps list`. The native UI source is useful for inquiry and filter
mapping, but static field names do not replace nonempty native records. Current
production observations are summarized above without private record values.

No `get` is in this batch. Swap UI detail copies a list record locally and is
not a native detail endpoint. No backend repair, mutation, unrelated leaf,
arbitrary request or additional transport framework is part of this work.
