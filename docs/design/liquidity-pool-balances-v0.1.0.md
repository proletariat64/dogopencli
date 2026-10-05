# Cash pool balance snapshots v0.1.0

Authoritative specification: [GitHub Issue #98](https://github.com/proletariat64/dogopencli/issues/98).

The 2026-10-05 operator clarification resolves the original/equivalent currency
and book/available balance meanings. [Research](../research/general/2026-10-05-cash-pool-semantics.md)
separates this direct business contract from public banking background.

`liquidity cash pool-balances list` reads the latest cached capture by default.
`refresh liquidity cash pool-balances` explicitly publishes a capture; `list --live`
queries the source without writing the cache or falling back. This is an independent
runtimes leaf using the existing history capture profile and `pool-balances-v1`
namespace. There is no history command or business-date query. `cash pools` remains
settings, with its existing fields, list/detail contracts and caches unchanged.

The verified source is JSON `POST /cashPoolList.json`, fixed
`tntInstId=GUAPW3SG`, `cashPoolCategory=BANK`, with `rowStart/pageSize` pagination
at width 100, explicit `success=true`, rows at `data.data` and total at
`data.totalCount`. No per-pool enrichment, category/filter guessing or writes occur.
Native nonempty evidence contains 43 pools and 358 members. Production CLI UAT is
reported separately from native sampling and fake-CDP checks.

Each output record is one pool, identified by typed `id`. Members are nested under
`cashPoolMemberVOS` and identified by `(pool.id, member.id)`. Duplicate member
identities and contradictory `cashPoolId` or tenant echoes fail closed. An explicit
BANK category is required. Field projection excludes capacity, limits, forecasts,
rate rules, sweep configuration and configuration timestamps.

| Native field | Meaning |
| --- | --- |
| `currentBalance` | Current book balance |
| `currentAviBalance` | Currently available funds for payment |
| Member original balances | Amounts in member `currency` |
| Member `equv` balances | Bank-converted amounts in member `bankCurrency` |
| `closeBalance`, `closeAviBalance` and equivalent fields | Previous statement-day closing book/available balances, not necessarily yesterday |
| Pool summary balances | Separate source pool totals; native UI displays USD; `mainCurrency` is retained configuration, not their currency |
| Pool `valueDate` | Native pool balance date in YYYY-MM-DD, never a member date |
| Member observation time | Unknown; neither pool date, configuration time nor capture time substitutes |
| `masterAccount`, `isShare` | Native member-level main-account and sharing flags; no pool-wide rule inferred from one member |

Do not sum pool and member amounts together, require pool totals to equal a member
sum, enforce available <= book, infer frozen amounts from differences, or perform
FX conversion. Negative, zero, empty-string, null and absent values remain distinct.
Empty/missing currency stays unknown; a provided nonempty currency must be three
uppercase letters. Provided malformed monetary values, dates, currency formats,
identities, scope or tenant echoes reject publication and preserve the old cache.

Existing ADR 0019 safety rules apply: valid partial collection can be published and
read with persistent incomplete warnings; `--require-complete` rejects it before
publication. Identity conflicts and malformed source values are hard errors, not
partial results. Unknown member time or empty source fields alone do not manufacture
incompleteness. Explicit success with zero rows and total zero is a complete empty
capture; production has no verified BANK empty-scope filter, so this protocol is
covered with fake CDP without inventing a production scope.

Pool-balances and credit-usage are enabled from #98. The operator retired unused
product-baselines, including both list/get catalog entries; quotes is the only
remaining deferred candidate. The original four candidates are two delivered,
one retired and one deferred; #98 stays open. No version bump or release is part
of this change.
