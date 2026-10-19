# Forwards

POST JSON /forwardOrderList.json through the host List SDK.

```bash
dogopencli liquidity list operations.forwards --live --require-complete --limit 0
```

- Full native fields, types, exact decimals, nested values and unknown fields are retained. Inquiry-only List; no Get or additional history/detail requests.
- Qualified width10 is based on historical successful requests, not a measured backend maximum. SDK collection owns loops, deadlines, retries, quality and cache publication.
- Duplicates, count gaps and short interior pages remain incomplete. Conflicts keep the last arrival; strict refresh rejects incomplete data and preserves the prior saved capture.
- Tenant GUAPW3SG history, with paging only; no invented dates or local filters. Native tradeDate/valueDate and rates/amounts remain unchanged.

Native records are `data.data` and total `data.totalCount`.

Ordinary List reads are offline; `--live` does not publish. Use `refresh --require-complete` with the same acquisition parameters to save a complete capture.

## Native detail

Native forward orderNo from the List; sent unchanged under wire forwardId. Native forward root; no hedging order acquisition or amount/date reinterpretation.

```bash
dogopencli liquidity get operations.forwards NATIVE_ID
dogopencli liquidity list operations.forwards --live --with-detail --require-complete
```

One POST form `/forwardOrderDetail.json` request returns `data`. Preserve the whole native root, including unknown fields, exact values and nested arrays. Missing/malformed roots, business rejection and identity/context contradictions fail; no unverified not-found mapping, child/history acquisition, cache write or Duckdog import.
