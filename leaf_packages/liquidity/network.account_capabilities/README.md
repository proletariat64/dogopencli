# Account capabilities

Inspect native account capability configuration through the host List SDK.

```bash
dogopencli liquidity list network.account_capabilities --live --require-complete --limit 0
dogopencli liquidity refresh network.account_capabilities --require-complete
dogopencli liquidity list network.account_capabilities
```

Native records are `data.data`; coverage uses native `data.totalCount`, never response length as an invented total.

- POST JSON /serviceInfoQuery.json with only fixed tenant GUAPW3SG, absolute rowStart offsets and pageSize=10. Acquisition is the tenant scope; no date partition or local filter is inferred.
- Native id is an integer row identity, including zero or negative integers; booleans and string coercion are excluded. aliasName, ruleId and other business references do not replace id.
- All native fields, value types, exact decimals, nested values, unknown fields and raw states are retained without projection or interpretation.
- Historical successful acquisitions support width10 as a starting value, not a measured backend maximum. SDK collection owns loops, retries, quality and cache publication.
- Duplicates, count shortfall and interior page gaps remain incomplete. Conflicts keep the last arrival and remain incomplete; strict refresh rejects incomplete acquisition and preserves prior cache.
- List only. Account capability detail and ledger customer inquiries are outside this package; no detail enrichment or dataset import is performed.

Ordinary List reads are offline. Live acquisition does not publish a cache; refresh publishes only accepted data. Native nested values already returned by List are preserved without additional inquiries.
