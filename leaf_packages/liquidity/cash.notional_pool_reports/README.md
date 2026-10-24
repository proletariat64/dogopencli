# Notional cash pool closing-balance reports

Read native `/cashPoolReportList.json` records with fixed `cashPoolType=Notional_Cash_Pool`. One record represents a named pool membership, account alias, currency and value date. The reviewed `(cashPoolName, aliasName, currency, valueDate)` tuple uses the existing List SDK composite identity; mutable `closingBalance` does not change identity. Blank source `id` and `bankTransNo` remain unchanged. Physical and Sweeping transaction reports belong to independent leaves and retain their native IDs.

```bash
dogopencli liquidity list cash.notional_pool_reports --start-date 2026-10-17 --end-date 2026-10-23 --timezone GMT+08 --live --limit 0 --require-complete
```

Dates are explicit ISO `YYYY-MM-DD`; requests use native `YYYYMMDD`. Both bounds are inclusive. End must be on or after start and before one calendar month after it, including month-end clipping. Explicit `GMT+08` selects the qualified native source timezone; account aliases do not establish timezone. Tenant, pool type, dates and timezone remain acquisition scope.

Native rows, original field names, decimal strings, unknown fields, nesting and order are preserved. Native `cashPoolType` can be blank; fixed request scope identifies the type without enriching rows. Source `totalAmount` remains untouched per-page metadata under `acquisition.native_metadata`, with page association; it is not computed from rows or relabeled as available cash. Recorded `closingBalance` is not live available cash.

The standard SDK owns offset paging, native total/identity quality checks and publication. Live does not publish; complete nonempty explicit refresh replaces the capture. Empty, failed or incomplete refresh preserves prior rows, metadata and capture time. Offline replays the retained capture. No Get, fanout, history, pool configuration, report edits, business operations or automatic Duckdog import.

Native report membership/date selections can change when the requested range changes. A wider capture is not a historical daily dataset and must not be locally sliced to claim the narrower endpoint response. Completeness describes the full native response for its own exact request scope.
