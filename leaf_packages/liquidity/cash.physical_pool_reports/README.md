# Physical Cash Pool operating reports

Read native `/cashPoolReportList.json` records with fixed `cashPoolType=Physical_Cash_Pool`. Native `id` identifies one report record. The standard List SDK owns complete offset acquisition, native total checks and cache publication.

```bash
dogopencli liquidity list cash.physical_pool_reports --start-date 2026-10-17 --end-date 2026-10-23 --timezone GMT+08 --live --limit 0 --require-complete
```

Dates are required ISO `YYYY-MM-DD`; requests use source `YYYYMMDD`. End date must be on or after start and before the one-calendar-month boundary, including month-end clipping. `--timezone GMT+08` explicitly selects the verified native environment option. Scope retains tenant, report type, dates and selected timezone.

Native rows, decimal text, unknown fields, nested content and ordering remain unchanged. Source rows can carry an empty `cashPoolType`; the fixed request scope remains authoritative. `totalAmount` is retained as original per-page source metadata under `acquisition.native_metadata`, including type and page association. It is not recomputed or relabeled as cash balance. A recorded `closingBalance` is not current available cash.

Live List leaves saved captures unchanged. Complete nonempty refresh may replace the capture; offline List replays it. Empty, failed or incomplete refresh preserves the previous capture. No detail calls, pool configuration, report edits or business operations are exposed. Notional pool reports belong to an independent leaf and are not queried here.
