# Waterlevel rules

Inspect native configuration through inquiry-only requests.

## Queries

```bash
dogopencli liquidity get rules.waterlevel NATIVE_ID
```

```bash
dogopencli liquidity list rules.waterlevel
```

## Native contract

- Fixed GUAPW3SG tenant. Native fields, nested values, exact decimals and unknown fields are retained.
- Native get sends aliasName as a string to GET /bankAccountBufferListByAliasName.json; no implicit list lookup.
- List uses rowStart offsets with pageSize=5000 and null credit-date bounds. No page echoes; fixed result.count and raw/unique agreement prove coverage.
- Get returns the native account-scoped dataValue object array. Every row must echo the requested aliasName. The envelope count is not the detail cardinality.

The positional get identity is an account `aliasName`; each returned row retains its own `bufferId`. Display field selection applies to each array member.
