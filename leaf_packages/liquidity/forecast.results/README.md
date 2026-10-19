# Forecast results

Native forecast records via the standard List SDK. Acquire with paired inclusive
`--from-date` / `--to-date` (ISO or compact). Optional repeated `--account-alias`
values use OR; account, date and creation-time bounds combine with AND.
`--record-from-time` / `--record-to-time` accept HH:mm:ss or HHmmss and default
to the full day for acquisition. Source timezone is unknown.

```bash
dogopencli liquidity list forecast.results --live --from-date 2026-03-08 --to-date 2026-03-08 --limit 0 --require-complete
dogopencli liquidity refresh forecast.results --from-date 2026-03-08 --to-date 2026-03-08 --require-complete
dogopencli liquidity list forecast.results --limit 0
```

GET `/bankCashForecastRecordQuery.json` uses tenant GUAPW3SG and a restricted
JSON-string VO, native offset width5000, `result.dataValue`, `result.count` and
native string `id`. Width5000 is qualified for an observed1332 records, not a
maximum-capacity claim. Full native values and arrival order remain unchanged.

Bare offline reads replay saved scope. Explicit local filters retain acquisition
provenance; a changed source query has unproved coverage and strict reads reject it.
Incomplete, duplicate or drifting native totals never replace complete cache.
No Get, accuracy, cashflow, dependent query or local forecast calculation.
