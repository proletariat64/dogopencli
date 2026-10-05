# Credit usage source-state snapshots v0.1.0

Authoritative specification: [issue #98](https://github.com/proletariat64/dogopencli/issues/98),
2026-10-05 credit-usage clarification. The [source and operator evidence](../research/general/2026-10-05-credit-usage-semantics.md)
is separate from production CLI UAT. Only credit-usage is added in this slice;
pool-balances was delivered earlier, while product baselines and quotes remain
unsupported. #98 stays open. No version bump is included.

## Inquiry and capture

`liquidity cash credit-usage list` reads the latest cached capture by default.
`refresh liquidity cash credit-usage` explicitly publishes a capture;
`list --live` queries without writing cache or falling back. The independent
runtimes namespace `credit-usage-v1` uses existing history capture semantics.
There is no business-date query, history command, detail getter or new filter.
Existing `cash credit-lines` settings fields, identity and cache remain unchanged.

The native GET `/queryBankCreditLineByParams.json` fixes `tntInstId=GUAPW3SG`.
The `bankCreditLineQuery` JSON string contains only `rowStart`/`pageSize`, width 100.
Both `resultFlag` and `result.success` must explicitly indicate success. Rows are
at `result.data`; top-level `count` must agree with `result.count`. The verified
nonempty source contains 84 parents and 667 nested members. Native sampling does
not replace the separate public CLI production UAT report.

## Source tree and values

One record is one native credit line with `bankAccountCreditLineList` children.
Typed `line.id` identifies its parent, and `(line.id, member.id)` identifies a
member. `creditLineId` echoes the native parent. Do not infer an upstream credit
line from a Sub Limit label or turn `mergeFlag` into a new hierarchy. Keep every
member, including repeated display-group values, without collapsing or summing.

| Source fields | Reading meaning |
| --- | --- |
| Parent `amount`, `usedAmount`, `availableAmount` | Native credit amount, used and available fields |
| Parent `currency` | Native UI Credit CCY |
| `shareTag` | Source shared/nonshared flag; shared lines need no invented account cap |
| Member `creditAmount`, `usedCreditAmount`, `availableCreditAmount` | Native member credit amount family |
| Member `equvAmount`, `usedAmount`, `availableAmount` | Separate native equivalent/original-display amount family |
| Member `creditCurrency` | Native UI CreditLine CCY; may be blank for shared lines |
| Member `currency` | Account currency; never guessed from another field or amount ratio |
| Member `mergeFlag`, `isMasterAccount` | Native display grouping and main-account flag |

The CLI reads business data; it does not audit whether allocations or usage are
financially correct. Do not parse or normalize money strings, check currency or
date formats, enforce allocation bounds, compare parent/member sums or used/available
relationships, or calculate FX. Preserve comma-formatted strings, decimal precision,
negative values, zero, empty strings, null, missing fields and unknown business
values. No amount or currency repair is permitted.

Protocol, container, identity, parent-link, tenant and pagination checks still
protect which objects and scope were read. Identity/tenant conflicts, malformed
record/member containers and non-success envelopes fail closed without replacing
cache. These are reading-protocol checks, not financial validation. Existing
ADR 0019 partial/strict handling applies: safe incomplete captures can publish
with persistent warnings; `--require-complete` refuses publication. Explicit
successful zero total and zero records is a complete empty capture; fake CDP
covers it because no native empty-scope filter has been verified.

## Observation time

The source provides no usage observation timestamp. It remains unknown for parents
and members. `fetched_at` is capture time; configuration `gmtModified` and validity
`startTimestamp`/`expiryTimestamp` are not observation times and are excluded from
this runtime projection. Unknown business time/amount/currency does not make a
complete acquisition incomplete or establish daily/realtime synchronization.

## Acceptance evidence boundary

Focused tests exercise the public CLI, fake CDP and temporary SQLite through the
existing framework: raw-value preservation, shared/nonshared tree, strict rollback,
safe partial publication, explicit success-empty, disconnected reads, live cache
isolation and settings compatibility. Native production UAT and external review
are recorded separately by the coordinating delivery task. No live examples or
source identifiers/amounts are used in Git, test fixtures or external reviews.
