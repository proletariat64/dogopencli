# Automatic-operation tasks

`operations.automatic_tasks` reads native automatic-operation task records from
`POST /riskActionTask/listQuery.json` using the standard List SDK. It is separate
from the funding-demand inquiry at `/riskActionTaskQuery.json`.

```bash
dogopencli liquidity list operations.automatic_tasks --live --from-time 2026-10-23T00:00:00 --to-time 2026-10-23T23:59:59 --limit 0 --require-complete
dogopencli liquidity refresh operations.automatic_tasks --from-time 2026-10-23T00:00:00 --to-time 2026-10-23T23:59:59 --require-complete
dogopencli liquidity list operations.automatic_tasks --limit 0 --require-complete
```

Both created-time bounds are explicit `YYYY-MM-DDTHH:mm:ss` wall clocks in the
frontend's GMT+8 time basis. Offsets and fractions are unsupported. The wire uses
`minDate` and `maxDate` with a space instead of `T`; no clock conversion occurs.
Ordered bounds must be fewer than 31 elapsed days apart, matching the frontend's
truncated-day restriction. The fixed tenant is `GUAPW3SG`.

The source uses absolute zero-based `rowStart`, width 10 and native
`data.totalCount`. The host acquires the source before applying the display
window and retains duplicate, conflict and count-gap evidence. Request or time
budget exhaustion requires narrower dates, not automatic partitioning.

All native fields, types, unknown values, nesting and arrival order are retained.
`taskId` identifies a task record. `gmtCreate` is the queried creation time;
`lastModifiedTime` and `endTime` retain their separate meanings. A modification
after the creation window is valid. Decision, operation and completion statuses
remain distinct, as do successful decision and operation amounts.

The standard SDK selects the complete latest row per `taskId` using strictly
validated `lastModifiedTime`. Its offset-free local clock becomes an internal
calendar/clock ordinal only; no timezone or Unix instant is inferred. Raw values
are preserved. Resolved versions and equal-order last-arrival ties warn and pass
default/strict acceptance when coverage is complete. Missing or invalid ordering
fails; genuine count or traversal gaps remain independent.

Live reads do not replace the saved capture. Complete nonempty explicit refresh
can publish a capture for offline replay. Empty, failed or incomplete refresh
preserves the previous rows and capture time. No automatic Duckdog import, Get,
detail fanout, strategy joins, confirmations, edits or task execution is included.

The manifest declares gmtCreate as an inclusive instant history axis. Public
--from-time/--to-time remain offset-free GMT+8 whole seconds. The leaf converts
these to SDK UTC millisecond boundaries, and rejects fractional-second planned
windows that the native public contract cannot represent.
