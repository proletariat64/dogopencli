# cash.balances

Read native account day-end balances from one source:
POST `/dayendBalDetailQuery.json`.

```bash
dogopencli liquidity list cash.balances --live --account-alias ACCOUNT --from-date 2026-10-01 --to-date 2026-10-07 --limit 0 --require-complete
dogopencli liquidity list cash.balances --live --entity ALIPAYGM --from-date 20261001 --to-date 20261007 --limit 0
dogopencli liquidity refresh cash.balances --account-alias ACCOUNT --from-date 2026-10-01 --to-date 2026-10-07 --require-complete
dogopencli liquidity list cash.balances --limit 0
```

## Dates and account scope

Live List and Refresh require both inclusive dates, in YYYY-MM-DD or YYYYMMDD
format. Invalid dates and reversed ranges fail before any business request.
Dates select native `valueDate`; they are not converted to UTC or a machine-local
calendar. No implicit latest or yesterday query exists.

Each native request contains `tntInstId=GUAPW3SG`, one nonblank `aliasName`,
compact `startDate` and `endDate`, and SDK-controlled `rowStart` and `pageSize`.
The qualified native page width is 500; other widths are not declared.
The endpoint does not receive entity, bank, currency or timezone filters.
Repeated explicit `--account-alias` values are deduplicated and queried directly,
without requiring a current directory entry. An explicit entity scope is still
validated against native returned records.

Without explicit aliases, the existing entity selector determines the scope:
default ALIPAYGM, repeated explicit entities, or `--entity ANY` frozen from the
registered local Duckdog entity selector. ANY is never sent to the balance
endpoint. Account aliases are enumerated in this order:

1. Configured Duckdog account directory.
2. Saved `cash.accounts` directory.
3. Live `GET /queryintnalbkactlist.json` through the List SDK.

An absent source, no matching usable accounts or missing enumeration fields can
advance to the next source. Configured corruption, malformed records, budget
failures and live query errors remain errors. A usable matching source is
selected even when its coverage is incomplete or unknown; quality does not
trigger a fallback that hides its limitations. The chosen source, quality,
freshness and deduplicated alias list are frozen for the operation.

Directory status, approval, enablement and balance-module flags do not filter
balances. The directory selects query objects only; its entity, bank and currency
fields never replace native balance fields. Current directory membership does
not prove historical ownership or coverage of all historical accounts.

Incomplete directory coverage retains `ACCOUNT_DIRECTORY_INCOMPLETE`; unknown
coverage retains `COVERAGE_UNPROVEN`. Qualified incomplete results follow the
shared result policy, and `--require-complete` rejects them. If no usable source
exists and no complete live directory proves the entity has no accounts, the
operation fails with `SOURCE_DATA_MISSING`. A complete live directory proving an
empty selected scope requires zero balance requests.

## Native records and identity

Each output row is one native day-end record. Preserve `entity`, `bankId`,
`aliasName`, `accountNo`, `currency`, `valueDate`, `openBalance`,
`openAvlBalance`, `closeBalance`, `closeAvlBalance`, `timeZone`,
`statementCreateTime`, `updateTime`, `source` and unknown native fields.
Amounts and time strings retain their original values and precision. Missing
balances are not zero-filled or supplemented from another balance source.

The SDK composite identity is
`(entity, bankId, aliasName, currency, valueDate)`. Its `latest_by` comparison uses
a temporary numeric ordering value derived by strictly parsing native
`updateTime` as YYYY-MM-DD HH:MM:SS. This orders source times within one key; it
is not a Unix timestamp or a claim about the source timezone. No machine-local
conversion or inferred account timezone is applied. The temporary field exists
only in internal record copies and is removed from output and saved business
records. A native field colliding with its reserved name is rejected.

The greatest source time selects the SDK candidate; equal times use last
arrival. No balance-value tie-break is applied. Identical duplicates, conflicting
content and pagination anomalies retain SDK evidence. Selecting a candidate does
not accept a conflict: same-key different content remains a shared-policy error
with exit 1. There is no generated business ID, `record/history` wrapper or
leaf-owned latest-record algorithm.

## Coverage and replay

The SDK traverses each account independently, retaining its native total,
arrivals, unique identities and page counts. Acquisition evidence also retains
the directory source and quality, frozen plan, queried/successful/failed accounts
and successful empty accounts. Counts from different accounts are not presented
as one backend total. All queries share bounded request and time budgets.

Execution completeness means every selected alias completed its requested date
range and pages. It does not establish that the directory includes every
historical account or that every account has an updated balance. A successful
empty account query, an unqueried account and a failed query are distinct.
`valueDate`, `statementCreateTime`, `updateTime` and acquisition time have separate
meanings; successful acquisition does not prove the latest business date.

Live List does not publish a business snapshot. Refresh follows the host policy:
accepted nonempty results may publish with their original quality evidence;
failure, strict rejection and successful empty acquisition preserve the prior
snapshot. Offline List replays only the saved day-end source and its explicit
date scope, without live directory fallback or inferred dates. Old-source caches
are not migrated or accepted under this contract.

No Get, automatic Duckdog balance publication, sync qualification or business
mutation is added.

## Bounded workflow history

The adapter's `history_contract` declares inclusive calendar `valueDate` bounds
and requires explicit account aliases for durable history planning. Explicit
windows retain separately labeled native observations; no multi-day/daily query
equivalence is asserted. Source modification time remains distinct from calendar
business dates and acquisition time. See the host bounded-history guide for
planning, package resume, coverage inspection and exact offline preservation.
