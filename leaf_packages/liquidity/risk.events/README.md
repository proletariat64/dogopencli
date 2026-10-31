# Risk events

Inspect native risk events through bounded inquiry-only requests.

```bash
dogopencli liquidity list risk.events --live --require-complete --from-date 20260925 --to-date 20260926 --limit 0
```

- Inquiry-only native JSON and unknown nested fields are retained without projection. Native zero values remain unchanged.
- Widths are based on historical successful requests, not measured backend maxima. SDK quality reports duplicate identities, count shortfall and page gaps; strict refresh publishes complete acquisitions only.
- Conflicts keep the last arrival and remain incomplete. Rejected refresh preserves the prior saved capture.
- Fixed tenant GUAPW3SG, riskMode=RISK_EVENT, timeZone=GMT+08. Ordered inclusive YYYYMMDD CLI days use Beijing GMT+08:00. Each day expands to 00:00:00–23:59:59 and converts to explicit GMT+0 query-clock seconds; request timeZone remains GMT+08. Equal-day and cross-day ranges are supported. No automatic daily decomposition.
- Native Risk Time gmtCreate and other GMT+08 source times are retained. GMT+0 query-clock bounds are eight hours behind Beijing across U.S. DST changes. Beijing October26 maps to October25 16:00:00 through October26 15:59:59. No anomaly classification or raw timestamp relabeling is performed.
- List acquisition does not query Detail, sub-events or treatment histories.

POST `/api/risk/event/getAll.json` with absolute rowStart offsets and pageSize=1000; records `data.data`, native total `data.totalCount`, identity `id`. Every record must match the fixed risk mode and retain validated native times and integer durations/counters.

The host SDK owns collection loops, retries, quality evidence and cache publication. Ordinary List reads are offline; `--live` acquires without publishing. Use `refresh --require-complete` with the same acquisition parameters to save a complete capture.

## Native detail

`dogopencli liquidity get risk.events RECORD_ID` queries `/api/risk/event/detail.json` using native `riskEventId` and validates root `id`. The lookup is the same value as native List `id`; the original fields, nested arrays, JSON types and exact values are retained. Separate history, logs and child endpoints are unqueried. Get never publishes cache or Duckdog data.

`dogopencli liquidity list risk.events --live --with-detail --limit 1 --from-date YYYYMMDD --to-date YYYYMMDD` returns selected `{record, detail}` pairs, preserves List order/quality and the saved List, and fails the entire query on any Detail failure.

History uses the existing SDK calendar contract on `gmtCreate`, with canonical ISO bounds and explicit windows only. `gmtModified` remains separate native modification evidence; cross-range equivalence is not declared.
The EVENT temporal model is an owner-approved reuse of anomalies semantics; it is not independently proved by anomalies production evidence.
