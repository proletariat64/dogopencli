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

## Native account configurations

`dogopencli liquidity get rules.waterlevel ACCOUNT_ALIAS` queries the account alias, not the current List bufferId. The native configuration array is returned intact, including every version/member and successful empty arrays. `--fields` projects each member without changing array shape or cardinality.

Each member must have an unambiguous native bufferId and matching aliasName; native types, nested fields and order remain unchanged. No latest/current selection, wrapping or same-object List binding is supplied. List acquisition remains unchanged; Get never writes its saved data or imports Duckdog records.
