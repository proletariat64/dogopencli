# Investable-funds list contract and release gate

Observed: 2026-10-03
Scope: general
Status: snapshot

Feature: [issue #82](https://github.com/proletariat64/dogopencli/issues/82),
`dogopencli liquidity investment investable-funds list`. This is a `runtimes`
inquiry. Native UI evidence and successful empty inquiries are discovery
evidence; they do not establish a populated schema or permit release.

## Native inquiry evidence

The saved published Liquidity UI bundle identifies the table inquiry as
`POST /queryInvestableFundList.json` with JSON encoding and explicit
`Content-Type: application/json;charset=utf-8`. Its request contains:

- `tntInstId` from the verified tenant and `timeZone` from the native timezone
  preference, defaulting to `GMT+08` when that preference is absent;
- `reportDate`, formatted as `YYYY-MM-DD`, defaulting to the browser's current
  day; the native form prevents selection of future report dates;
- `startForecastDate` and `endForecastDate`, also `YYYY-MM-DD` when supplied,
  defaulting to two empty strings;
- `rowStart` and `pageSize`, initially `0` and `10`; page navigation maps to
  `(current - 1) * pageSize`;
- an optional native `currency` filter, passed through from the form.

The table reads `data.data` and `data.totalCount` after top-level
`success=true`. Historical response evidence includes pagination echoes and
zero records with total zero. The native UI also requests
`queryInvestableFundGragh.json` for its chart. That chart is a separate
inquiry and is outside this list implementation.

On 2026-10-03, the current production bundle was checked against the saved
bundle and matched its hash. The fresh authorized portal environment still
reported `GMT+08`. Five bounded first-page table inquiries used native
`pageSize=10`, `rowStart=0`, the authorized tenant and this native timezone:

| Report date | Forecast range | Result |
| --- | --- | --- |
| `2026-10-03` | Native empty range | `success=true`, zero rows, total zero |
| `2026-10-02` | Native empty range | `success=true`, zero rows, total zero |
| `2026-09-30` | Native empty range | `success=true`, zero rows, total zero |
| `2026-09-01` | Native empty range | `success=true`, zero rows, total zero |
| `2026-09-30` | `2026-09-30` through `2026-10-30` | `success=true`, zero rows, total zero |

These observations verify successful empty inquiry responses in the tested
scopes only. They do not show that all report scopes are empty, establish
nonempty record types, or prove full pagination and production UAT. The
native date format was preserved; no alternate endpoint, chart, business
mutation, synthetic business identity or indefinite broadening was used.

The table displays these source fields:

| Native field | Native heading | Evidence limit |
| --- | --- | --- |
| `forecastDate` | Forecast Date | Row type and date boundary semantics unverified |
| `currency` | CCY | Populated currency scope unverified |
| `originalInvestableAmount` | Original Investable Funds | Amount type, units and precision unverified |
| `reserveAmount` | Reserve Funds | Amount type, units and precision unverified |
| `investedAmount` | Invested Capital | Amount type, units and precision unverified |
| `adjustedInvestableAmount` | Adjusted Investable Funds | Amount type, units and precision unverified |

These headings are static UI evidence, not a typed record schema. Do not
derive any monetary relationship or translate amounts through JavaScript
numbers. Source null, empty-string and zero states must remain distinct once
the populated contract is established.

## Identity and time semantics

The native table supplies no row key or object identifier. In particular,
`(forecastDate, currency)` is not yet proven unique and must not be installed
as an identity on the strength of column names. A populated sample and
representative page boundaries must establish the record grain, identity and
its scope before a `ListSpec` can be registered. List positions and whole-row
hashes cannot replace this evidence.

`reportDate` scopes the report and `forecastDate` identifies a forecast
dimension. Neither is the capture's `fetched_at`. Precise source observation
time, timezone interpretation, inclusion boundaries and full-report coverage
remain unverified. The history or dated cache profile must follow the
verified contract; it is not selected from these field names.

## Release and tests

Until nonempty schema, identity, monetary scope, date semantics, complete
acquisition and standalone production UAT are verified, this leaf stays
discoverable and non-executing. There is no executable inquiry contract and
no typed sample invented from UI headings. This list never releases a `get`.

After contract verification, use the existing CLI test entry with fake CDP
and a temporary SQLite cache. Test user-visible refresh/cached-list record
and scope equality, full empty publication, read-only live cache bytes,
pagination boundaries, identity conflicts, scope rejection, strict incomplete
behavior and rollback. Synthetic cases do not satisfy production UAT.
Production verification and local Kimi CLI CI/review are independent gates.

The committed refusal tests exercise offline help/describe and execution
failure through the public CLI. With CDP disconnected and a pre-existing
cache file, they verify that list does not read or change the cache, that
live/refresh/get cannot execute, and that describe supplies no invented
populated schema. Passing these tests proves the release gate, not a shipped
list query. Nonempty acquisition and release remain blocked.

## Sources

- [Historical inquiry report](2026-10-01-liquidity-live-probes.md),
  `investment investable-funds list` cases: `business-38-r1/r2/r3` and
  `previous-day-33-r1`; all had no populated schema.
- Saved published UI bundle, inquiry wrapper character offset `1523773`,
  report/default/filter mapping `8386634` and `8387658`, and table definition
  around `8389000`. These are source bundle pointers, not production UAT.
- [Funding and execution batch spec](../../design/liquidity-funding-execution-v0.1.0.md)
  and ADRs [0016](../../adr/0016-liquidity-independent-list-and-detail-caches.md),
  [0018](../../adr/0018-liquidity-capture-store-and-retention.md),
  [0019](../../adr/0019-usable-incomplete-acquisitions.md).
