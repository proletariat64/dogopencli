# Asset Trades

POST JSON /assetTransferOrderListQuery.json through the host List SDK.

```bash
dogopencli liquidity list operations.asset_trades --live --require-complete --from-date 2026-09-30 --to-date 2026-09-30 --limit 0
```

- Full native fields, types, exact decimals, nested values and unknown fields are retained. Inquiry-only List; no Get or additional history/detail requests.
- Qualified width10 is based on historical successful requests, not a measured backend maximum. SDK collection owns loops, deadlines, retries, quality and cache publication.
- Duplicates, count gaps and short interior pages remain incomplete. Conflicts keep the last arrival; strict refresh rejects incomplete data and preserves the prior saved capture.
- Fixed tenant GUAPW3SG and timezone GMT+08; required ISO trading-date bounds map to compact native tradingDateBegin/End. Native tradingDate is retained without inferred row-date parsing or local membership filtering.
- Trading date is distinct from gmtCreate and actualValueDate; no source timestamp filtering or timezone conversion is inferred. Native logs already in a row are preserved; no detail enrichment.

Native records are `data.data` and total `data.totalCount`.

Ordinary List reads are offline; `--live` does not publish. Use `refresh --require-complete` with the same acquisition parameters to save a complete capture.

## Native detail

Native asset-transfer orderNo from the List; report/global/end-to-end references are distinct. Native root including assetProductVo and logs already returned; no separate log acquisition or asserted log ownership.

```bash
dogopencli liquidity get operations.asset_trades NATIVE_ID
dogopencli liquidity list operations.asset_trades --live --with-detail --require-complete --from-date 2026-09-30 --to-date 2026-09-30
```

One POST form `/assetTransferOrderDetailQuery.json` request returns `data`. Preserve the whole native root, including unknown fields, exact values and nested arrays. Missing/malformed roots, business rejection and identity/context contradictions fail; no unverified not-found mapping, child/history acquisition, cache write or Duckdog import.
