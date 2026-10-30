# Funding-demand tasks

Read native records through the host List SDK.

```bash
dogopencli liquidity list operations.demands --live --require-complete --limit 0 --from-time 2026-04-01T00:00:00 --to-time 2026-04-02T00:00:00
dogopencli liquidity refresh operations.demands --require-complete --from-time 2026-04-01T00:00:00 --to-time 2026-04-02T00:00:00
dogopencli liquidity list operations.demands --limit 0
```

GET `/riskActionTaskQuery.json` with outer tenant and a JSON-string `riskActionTaskQueryVO` containing the fixed tenant/source, native execution bounds and fixed rowStart=0/pageSize=5000. Require outer resultFlag and inner success; records are `result.dataValue`, native total is `result.count`.

Fixed GUAPW3SG tenant and FUND_REQUIRE source. One GET /riskActionTaskQuery.json uses a serialized riskActionTaskQueryVO, rowStart=0 and pageSize=5000.

Both offset-free execution-time bounds are required. Public values use T; wire values use a space. Equal bounds are permitted and native boundaries are inclusive. Offset-free executeTime values use owner-confirmed Beijing GMT+08:00. History uses the same inclusive axis with canonical UTC millisecond bounds; fractional-second windows are rejected, not rounded.

Native result.dataValue records and result.count describe the queried task scope. Counts or arrivals above 5000 are rejected; narrow the bounds. No offset fallback, automatic partitioning or alternate source.

All native fields, types, nesting and unknown values are retained. No detail lookup, source join or status interpretation.

The host SDK owns retries, completeness and publication. Duplicate/conflicting identities and count gaps remain incomplete; strict refresh preserves the prior capture on rejection. Widths are historical successful request sizes, not measured backend maxima.

Ordinary List reads are offline. Live acquisition does not publish; refresh saves only a complete nonempty capture. Native fields already in the response remain intact; Get runs only when explicitly requested; ordinary Lists perform no additional inquiry.

## Native detail

Native FUND_REQUIRE taskId from the List; sourceId is a different reference. Native result.riskActionVO only; same-envelope decision/execution report siblings and separate child/history endpoints are outside this Get.

```bash
dogopencli liquidity get operations.demands NATIVE_ID
dogopencli liquidity list operations.demands --live --with-detail --require-complete --limit 1 --from-time 2026-04-01T00:00:00 --to-time 2026-04-02T00:00:00
```

One GET query `/riskActionTaskQueryDetail.json` request returns `result.riskActionVO`. Preserve the whole native root, including unknown fields, exact values and nested arrays. Missing/malformed roots, business rejection and identity/context contradictions fail; no unverified not-found mapping, child/history acquisition, cache write or Duckdog import.
