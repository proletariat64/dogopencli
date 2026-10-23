# Prefunds

GET /queryPreFundingOrderList.json through the host List SDK.

```bash
dogopencli liquidity list operations.prefunds --live --require-complete --status APPROVED --status CLOSED --limit 0
```

- Full native fields, types, exact decimals, nested values and unknown fields are retained. Ordinary List performs no Get or additional inquiry.
- Width 1000 is qualified for complete acquisition, not a measured backend maximum. SDK collection owns loops, deadlines, retries, quality and cache publication.
- Duplicates, count gaps and short interior pages remain incomplete. Conflicts keep the last arrival; strict refresh rejects incomplete data and preserves the prior saved capture.
- Fixed outer and inner tenant GUAPW3SG; exact outer timezone GMt+8. Mandatory qualified status views are separately acquired and canonicalized to frontend ordering.
- Native id identifies the row; prefundingBizNo is a distinct business reference and version is preserved without selecting latest versions. APPROVED_FINAL history and drawdown assembly are excluded.
- Repeated currency selectors apply locally after full native acquisition and do not change its status scope.

Native records are `result.dataValue` and total `result.count`. The GET query contains a serialized `preFundingOrderQueryVO` with inner tenant, statusList, rowStart and pageSize.

Ordinary List reads are offline; `--live` does not publish. Use `refresh --require-complete` with the same acquisition parameters to save a complete capture.

## Selected application detail

```bash
dogopencli liquidity get operations.prefunds NATIVE_APPLICATION_ID
dogopencli liquidity list operations.prefunds --live --with-detail --status APPROVED --status CLOSED --offset 1 --limit 1 --require-complete
```

Get makes one inquiry-only GET `/queryPreFundingOrderDetail.json` with fixed tenant and `preFundingId` from native List `id`. Require outer `resultFlag`, inner `result.success` and exact `result.data.id` echo; retain the whole selected native application root, including approverList, fileUrlList, precision, nesting and unknown fields. The native business `prefundingBizNo` and version remain independent of the selected row ID.

The accepted scope is the selected application. No latest/current-version selection, APPROVED_FINAL historyApplications, drawdownDetails, extra history/drawdown requests, balance recalculation or attachment download. Native arrays already returned remain intact; root success does not prove complete business-history or drawdown coverage. Missing/malformed roots, business failure and identity/tenant contradictions fail without an invented empty/not-found result.

Standard `list --live --with-detail` maps the selected List row `id` unchanged to the Get lookup, after local filtering and the output window. It returns `{record, detail}` pairs without merging the two sources. Get and composition preserve saved List records and capture time and publish no cache or Duckdog data.
