# Transfer orders

Read native records through the host List SDK.

```bash
dogopencli liquidity list operations.transfers --live --require-complete --limit 0 --from-date 2026-09-30 --to-date 2026-09-30
dogopencli liquidity refresh operations.transfers --require-complete --from-date 2026-09-30 --to-date 2026-09-30
dogopencli liquidity list operations.transfers --limit 0
```

POST **form** `/transferOrderQuery.json` with outer tenant and a JSON-string `transferOrderQueryRequestVO`; this is not a JSON request body. Require outer resultFlag and inner success. Records are `result.data`; top-level `count` and `result.count` must agree. Native `orderNo` identifies one row.

Fixed GUAPW3SG tenant. POST form /transferOrderQuery.json contains a serialized transferOrderQueryRequestVO with fixed empty debitEntity/creditEntity arrays and blank debit/credit date bounds.

Required ISO Transaction Date bounds expand to native 00:00:00 and 23:59:59. Native source timezone and the relationship to displayed gmtCreate remain unproven; no local date-membership filtering.

Absolute rowStart offsets use pageSize=1000. Top-level count must equal result.count; records are result.data. Other native filters are unsupported.

Preserve full native rows, nested logs, unknown fields and nullable monetary strings. orderStatus, receiptStatus and executeResult remain separate raw states; no bank-success inference or detail enrichment.

The host SDK owns retries, completeness and publication. Duplicate/conflicting identities and count gaps remain incomplete; strict refresh preserves the prior capture on rejection. Widths are historical successful request sizes, not measured backend maxima.

Ordinary List reads are offline. Live acquisition does not publish; refresh saves only a complete nonempty capture. Native fields already in the response remain intact; Get runs only when explicitly requested; ordinary Lists perform no additional inquiry.

## Native detail

Native transfer orderNo from the List; orderId/reportId are separate references. Native baseResult.data transfer root; no account enrichment, HTML unescaping, status interpretation or additional log inquiry.

```bash
dogopencli liquidity get operations.transfers NATIVE_ID
dogopencli liquidity list operations.transfers --live --with-detail --require-complete --limit 1 --from-date 2026-09-30 --to-date 2026-09-30
```

One POST form `/transferOrderQueryDetail.json` request returns `baseResult.data`. Preserve the whole native root, including unknown fields, exact values and nested arrays. Missing/malformed roots, business rejection and identity/context contradictions fail; no unverified not-found mapping, child/history acquisition, cache write or Duckdog import.
