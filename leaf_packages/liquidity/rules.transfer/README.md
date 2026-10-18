# Transfer rules

Inspect native configuration through inquiry-only requests.

## Queries

```bash
dogopencli liquidity get rules.transfer NATIVE_ID
```

```bash
dogopencli liquidity list rules.transfer
```

## Native contract

- Fixed GUAPW3SG tenant. Native fields, nested values, exact decimals and unknown fields are retained.
- Native get sends ruleId as a string to GET /queryTransferRuleDetail.json; no implicit list lookup.
- Single GET with fixed rowStart=0, pageSize=5000 and empty debitEntity/creditEntity arrays; no offset fallback.
- Completeness requires raw arrivals = unique ruleId count = result.ruleCount. All native conditions remain intact; list summaries are independent of get.

The list retains full native records, including nested and unknown fields. The pinned historical implementation projected a subset of configuration fields; the current contract preserves native values without projection.
