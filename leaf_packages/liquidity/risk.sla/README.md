# Risk sla

Inspect native risk sla through bounded inquiry-only requests.

```bash
dogopencli liquidity list risk.sla --live --require-complete --limit 0
```

- Inquiry-only native JSON and unknown nested fields are retained without projection. Native zero values remain unchanged.
- Widths are based on historical successful requests, not measured backend maxima. SDK quality reports duplicate identities, count shortfall and page gaps; strict refresh publishes complete acquisitions only.
- Conflicts keep the last arrival and remain incomplete. Rejected refresh preserves the prior saved capture.
- One POST with only rowStart=0 and pageSize=5000. No tenant/filter keys, offset fallback, detail query or rule/recipient enrichment.
- Native totalCount and native string slaConfigId establish observed List coverage. Source version remains a separate native string.

POST `/api/risk/sla/slaConfigPageQuery.json`; records `data.data`, native total `data.totalCount`, identity `slaConfigId`.

The host SDK owns collection loops, retries, quality evidence and cache publication. Ordinary List reads are offline; `--live` acquires without publishing. Use `refresh --require-complete` with the same acquisition parameters to save a complete capture.
