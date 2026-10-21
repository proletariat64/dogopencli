# cash.balances

Read latest account snapshots or daily closing book-balance observations:

```bash
dogopencli liquidity list cash.balances --live --entity ALIPAYGM --limit 0 --require-complete
dogopencli liquidity list cash.balances --live --entity ALIPAYGM --account-alias ACCOUNT --from-date 2026-10-01 --to-date 2026-10-07 --limit 0 --require-complete
dogopencli liquidity refresh cash.balances --entity ALIPAYGM --require-complete
dogopencli liquidity list cash.balances --limit 0
```

No dates selects POST `/latestBalanceQuery.json`: fixed tenant GUAPW3SG,
`entitys`, `aliasNames`, `timeZone=GMT+08`, native `rowStart` and `pageSize`.
Default entity is ALIPAYGM; repeated explicit entities select their union.
`--entity ANY` freezes native instId values from the registered local Duckdog
entity selector. ANY is never sent to the backend, and an empty selected universe
never submits an unscoped inquiry. Latest width defaults to 100; `--page-size`
accepts 1 through 100 for live/refresh only. Native `balId` identifies snapshots.
A fixed source total, distinct identities and all arrivals establish coverage.

Paired inclusive dates select POST `/balStatisticalQuery.json` with
`balanceType=day`, native account aliases and compact dates. YYYY-MM-DD and
YYYYMMDD inputs normalize to the same scope. Daily mode has fixed GMT+08 and
rejects explicit timezone/page-size options. Native amounts, precision, nulls,
blank strings and nested records stay unchanged; no division or zero fill occurs.

Daily labels use a frozen current account roster from
`/queryintnalbkactlist.json`, independently collected by the qualified host
short-page policy. The full roster must have unambiguous alias-to-entity/currency
bindings before selection. An explicit alias must belong to a selected entity.
Each output preserves its native observation and adds these validated current
labels; they do not establish historical ownership. Daily identity is
`(entity, aliasName, currency, statisticalDate)`; native chart `id` is retained
without treating it as account identity.

Acquisition uses disjoint chunks of at most 30 aliases and seven days, at most
1000 chunks. One 900-second budget includes all inquiries and roster acquisition.
Every required chunk must succeed; alias/date scope violations, malformed amounts,
conflicting identities and failed dependencies prevent complete publication.
Frozen selection, roster evidence and each successful chunk remain in acquisition
metadata through offline replay. Missing dates remain absent. Capture time does
not establish source observation freshness.

Bare offline List replays the saved query. Exact entity/alias/date filters apply
to saved rows; they do not acquire broader history. No Get, forecast calculation,
legacy runtime import or unsupported Duckdog balance import is exposed.
