# Account capabilities

Inspect native account capability configuration through the host List SDK.

```bash
dogopencli liquidity list network.account_capabilities --live --require-complete --limit 0
dogopencli liquidity refresh network.account_capabilities --require-complete
dogopencli liquidity list network.account_capabilities
```

Native records are `data.data`; coverage uses native `data.totalCount`, never response length as an invented total.

- POST JSON /serviceInfoQuery.json with only fixed tenant GUAPW3SG, absolute rowStart offsets and pageSize=1000. Acquisition is the tenant scope; no date partition or local filter is inferred.
- Native id is an integer row identity, including zero or negative integers; booleans and string coercion are excluded. aliasName, ruleId and other business references do not replace id.
- All native fields, value types, exact decimals, nested values, unknown fields and raw states are retained without projection or interpretation.
- Width 1000 is qualified for complete acquisition, not a measured backend maximum. SDK collection owns loops, retries, quality and cache publication.
- Duplicates, count shortfall and interior page gaps remain incomplete. Conflicts keep the last arrival and remain incomplete; strict refresh rejects incomplete acquisition and preserves prior cache.
- Ordinary List performs no detail enrichment or dataset import; explicit Get and supported --with-detail query native detail independently.

Ordinary List reads are offline. Live acquisition does not publish a cache; refresh publishes only accepted data. Native nested values already returned by List are preserved without additional inquiries.

## Native detail

Native integer id from the List; aliasName and ruleId are different references. Native account capability root; comma strings, exact native numbers, arrays and unknown fields remain unchanged. No rule lookup or UI transformations.

```bash
dogopencli liquidity get network.account_capabilities 7
dogopencli liquidity list network.account_capabilities --live --with-detail --require-complete --limit 1
```

One POST json `/serviceInfoDetail.json` request returns `data`. Preserve the whole native root, including unknown fields, exact values and nested arrays. Missing/malformed roots, business rejection and identity/context contradictions fail; no unverified not-found mapping, child/history acquisition, cache write or Duckdog import.
