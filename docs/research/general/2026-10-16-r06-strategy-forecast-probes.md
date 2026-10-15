# R06 strategy-directed forecast discovery

Observed: 2026-10-16
Scope: general
Status: snapshot

This records a bounded production inquiry for issue #191, using the account
selection suggested by the user. T0 Forecast, Hours Maximum and Daily Maximum
still lack nonempty response qualification. No business mutation was performed.

## Strategy cache and account selection

The public strict default Strategy refresh published a complete snapshot of
1,897 native rows. Acquisition included an independent empty terminal request
at offset 1,897. Public strict offline reads reproduced all 1,897 rows from
that snapshot. The offline operation-strategy member filters returned 575
T0 Decision rows and 26 RT Decision rows.

The deployed native UI bundle independently maps the table column
`Effective Operation Strategy` to `operationStrategy` and its filter options
to `T0_DECISION` and `RT_DECISION`. The refresh preserved the default query
scope and source status/version values; no additional version or status
queries were introduced.

Exact alias, entity, bank and currency contexts produced 601 distinct accounts,
with no overlap between the two selected populations. They span 88 banks and
31 currencies. All selected native rows had status `Valid`. Native account
types were 507 OA, 48 FLC, 34 SA, 3 TA and 9 blank values. These observations
did not become additional source filters.

## Inquiry method and results

Each T0 Decision account was queried for T0 Forecast and Daily Maximum. Each
RT Decision account was queried for T0 Forecast and Hours Maximum. Two fixed
date windows were used:

- 20260916 through 20261016, within the native 30-day difference limit.
- 20260911 through 20261010, the active window used by the DI hot-account study.

Requests used verified inquiry endpoints with scalar alias, available native
entity/bank context, native date fields, initial offset zero and native page
widths. At most two requests ran concurrently. The bounded search completed
all 2,404 requests in 295 seconds, within its 600-second deadline.

| Population | Leaf | Accounts | Requests | Successful empty | Failures | Nonempty |
|---|---|---:|---:|---:|---:|---:|
| T0 and RT | T0 Forecast | 601 | 1,202 | 1,202 | 0 | 0 |
| T0 | Daily Maximum | 575 | 1,150 | 1,150 | 0 | 0 |
| RT | Hours Maximum | 26 | 52 | 52 | 0 | 0 |
| Combined | All three | 601 distinct | 2,404 | 2,404 | 0 | 0 |

Every response was HTTP 200 with native `success=true`, `totalCount=0` and
`data.data=[]`. No anomalous success containers or contradictory totals were
observed. Each window completed all 1,202 planned requests; there was no early
stop or deadline exhaustion.

## Evidence boundary

This establishes successful empty inquiries across the selected default-version
Strategy population and two explicit windows. It does not establish global
absence, retirement, algorithm inactivity or coverage of all historical dates.
Strategy membership alone does not prove that a forecast was generated.

No nonempty schema, row identity or pagination progression was demonstrated,
so these three leaves remain discoverable and non-executing. D03 intraday
statistics qualification and public CLI UAT are documented separately.

The task-owned isolated headless browser was used. The research page was closed
and its absence verified; the dedicated profile and unrelated pages were
preserved. Private account contexts and machine evidence remain in ignored
local files with mode 0600. This report contains no account identifiers,
transaction rows, money values or credentials.
