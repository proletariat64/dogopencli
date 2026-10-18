# Waterlevel rules

Read native configuration records through the host List SDK.

```bash
dogopencli liquidity list rules.waterlevel --live --limit 0
dogopencli liquidity refresh rules.waterlevel --require-complete
dogopencli liquidity list rules.waterlevel
```

GET `/bankAccountBufferQuery.json` uses zero-based rowStart offsets, pageSize=5000, fixed tenant GUAPW3SG and null credit-date bounds. Records are `result.dataValue`, total is `result.count`, identity is native string or integer `bufferId`. Native nested values, including `daytimeBufferVos`, are retained.

Repeated `--currency` flags select exact local currency values without narrowing acquisition. The frontend account detail/version expansion is separate from this List.

The width is supported by historical successful requests, not a measured backend maximum. The SDK owns deadlines, retries, completeness and cache publication. A short final page is valid; duplicate identities, count shortfall and interior page gaps are incomplete. Conflicts keep the last arrival while remaining incomplete. `--require-complete` rejects incomplete acquisitions and leaves the prior cache intact.
