# Risk sla

Inspect native risk sla through bounded inquiry-only requests.

```bash
dogopencli liquidity list risk.sla --live --require-complete --limit 0
```

- Inquiry-only native JSON and unknown nested fields are retained without projection. Native zero values remain unchanged.
- Widths are based on historical successful requests, not measured backend maxima. SDK quality reports duplicate identities, count shortfall and page gaps; strict refresh publishes complete acquisitions only.
- Conflicts keep the last arrival and remain incomplete. Rejected refresh preserves the prior saved capture.
- One POST with only rowStart=0 and pageSize=5000. List sends no tenant/filter keys and has no offset fallback or detail enrichment.
- Native totalCount and native string slaConfigId establish observed List coverage. Source version remains a separate native string.

POST `/api/risk/sla/slaConfigPageQuery.json`; records `data.data`, native total `data.totalCount`, identity `slaConfigId`.

The host SDK owns collection loops, retries, quality evidence and cache publication. Ordinary List reads are offline; `--live` acquires without publishing. Use `refresh --require-complete` with the same acquisition parameters to save a complete capture.

## Native detail

`dogopencli liquidity get risk.sla RECORD_ID` queries `/api/risk/sla/slaConfigDetailQuery.json` using native `slaConfigId` and validates root `slaConfigId`. The lookup is the same value as native List `slaConfigId`; the original fields, nested arrays, JSON types and exact values are retained. Separate history, logs and child endpoints are unqueried. Get never publishes cache or Duckdog data.

`dogopencli liquidity list risk.sla --live --with-detail --limit 1` returns selected `{record, detail}` pairs, preserves List order/quality and the saved List, and fails the entire query on any Detail failure.
