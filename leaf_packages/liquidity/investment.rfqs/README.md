# TARGET_RFQ inquiry subtasks

`liquidity.investment.rfqs` uses the host List SDK with native
`inquirySubTaskId` identity and one bounded 5000-width inquiry.
`inquiryTaskId` remains a parent reference; distinct subtasks stay distinct.

```bash
dogopencli liquidity list investment.rfqs --live --require-complete --limit 0 --from-date 2026-01-01 --to-date 2026-10-05
dogopencli liquidity refresh investment.rfqs --require-complete --from-date 2026-01-01 --to-date 2026-10-05
dogopencli liquidity list investment.rfqs --limit 0
```

Both ISO dates are required for acquisition and map to native compact dates.
The JSON request contains exactly five fields: rowStart0, pageSize5000,
inquiryType TARGET_RFQ, inquiryStartDate and inquiryEndDate. Tenant context
comes from the verified application session; no tenant request field is sent.
The historical date range is a qualification starting point, not proof of
current records or a measured maximum width.

Full native JSON remains intact, including parent references, nested/unknown
fields and nullable/blank/zero/negative counter, status and time values.
Source timezone and date-bound timestamp membership are unproven. No
financial arithmetic, related-source join or detail enrichment is performed.

The SDK retains the last conflicting arrival and marks coverage incomplete.
Strict live/refresh rejects duplicate identities, conflicts and count gaps;
failed, incomplete or empty refresh preserves the previous saved capture.
Counts or arrivals above 5000 fail without offset/fallback acquisition.
Live writes no capture; refresh and offline reads use task-owned temporary
cache. They do not import runtime records into Duckdog.

Only the TARGET_RFQ source is exposed. FULL_RANGE_RFQ and unqualified source/filter
combinations remain outside this package's accepted inquiry contract.

## Native detail

Native child inquirySubTaskId from the List; sent as inquiryTaskId. Never pass the List parent inquiryTaskId. Native TARGET_RFQ child detail and institution members already in inquiryOrderListVOList. Returned inquiryTaskId identifies the selected child; no parent, quote or history fanout.

```bash
dogopencli liquidity get investment.rfqs NATIVE_ID
dogopencli liquidity list investment.rfqs --live --with-detail --require-complete --limit 1 --from-date 2026-01-01 --to-date 2026-10-05
```

One GET query `/rfq/subInquiryTask/queryInquiryTaskDetail.json` request returns `data`. Preserve the whole native root, including unknown fields, exact values and nested arrays. Missing/malformed roots, business rejection and identity/context contradictions fail; no unverified not-found mapping, child/history acquisition, cache write or Duckdog import.
