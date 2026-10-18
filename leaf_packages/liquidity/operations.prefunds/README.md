# Prefunds

GET /queryPreFundingOrderList.json through the host List SDK.

```bash
dogopencli liquidity list operations.prefunds --live --require-complete --status APPROVED --status CLOSED --limit 0
```

- Full native fields, types, exact decimals, nested values and unknown fields are retained. Inquiry-only List; no Get or additional history/detail requests.
- Qualified width10 is based on historical successful requests, not a measured backend maximum. SDK collection owns loops, deadlines, retries, quality and cache publication.
- Duplicates, count gaps and short interior pages remain incomplete. Conflicts keep the last arrival; strict refresh rejects incomplete data and preserves the prior saved capture.
- Fixed outer and inner tenant GUAPW3SG; exact outer timezone GMt+8. Mandatory qualified status views are separately acquired and canonicalized to frontend ordering.
- Native id identifies the row; prefundingBizNo is a distinct business reference and version is preserved without selecting latest versions. APPROVED_FINAL history and drawdown/detail assembly are excluded.
- Repeated currency selectors apply locally after full native acquisition and do not change its status scope.

Native records are `result.dataValue` and total `result.count`. The GET query contains a serialized `preFundingOrderQueryVO` with inner tenant, statusList, rowStart and pageSize.

Ordinary List reads are offline; `--live` does not publish. Use `refresh --require-complete` with the same acquisition parameters to save a complete capture.
