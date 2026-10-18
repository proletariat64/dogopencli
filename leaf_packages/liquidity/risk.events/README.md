# Risk events

Inspect native risk events through bounded inquiry-only requests.

```bash
dogopencli liquidity list risk.events --live --require-complete --from-date 20260925 --to-date 20260926 --limit 0
```

- Inquiry-only native JSON and unknown nested fields are retained without projection. Native zero values remain unchanged.
- Widths are based on historical successful requests, not measured backend maxima. SDK quality reports duplicate identities, count shortfall and page gaps; strict refresh publishes complete acquisitions only.
- Conflicts keep the last arrival and remain incomplete. Rejected refresh preserves the prior saved capture.
- Fixed tenant GUAPW3SG, riskMode=RISK_EVENT, timeZone=GMT+08. Adjacent YYYYMMDD CLI bounds map to native YYYY-MM-DD; unbounded acquisition is unsupported.
- Native Risk Time gmtCreate and other GMT+08 source times are retained. Server boundary clock and inclusivity remain unproven; no local date membership or anomaly classification is inferred.
- List only. Risk detail, sub-events and treatment histories are separate inquiries and are not acquired.

POST `/api/risk/event/getAll.json` with absolute rowStart offsets and pageSize=10; records `data.data`, native total `data.totalCount`, identity `id`. Every record must match the fixed risk mode and retain validated native times and integer durations/counters.

The host SDK owns collection loops, retries, quality evidence and cache publication. Ordinary List reads are offline; `--live` acquires without publishing. Use `refresh --require-complete` with the same acquisition parameters to save a complete capture.
