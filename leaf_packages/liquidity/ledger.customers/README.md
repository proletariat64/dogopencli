# Ledger customers.

## Native detail

Native customerNo from the customer page, together with the required version context. Native customer detail for explicit customerNo/version. The source may omit version echo, so successful root acquisition does not independently prove the returned version. No latest-version inference or List.

```bash
dogopencli liquidity get ledger.customers NATIVE_ID --customer-version 1
```

One GET query `/bookCustomer/detail.json` request returns `data`. Preserve the whole native root, including unknown fields, exact values and nested arrays. Missing/malformed roots, business rejection and identity/context contradictions fail; no unverified not-found mapping, child/history acquisition, cache write or Duckdog import.

`--customer-version` is mandatory. A missing native version echo remains missing; request context is not a fabricated response field or independent proof of the returned version. If the source supplies a contradictory version, the query fails.
