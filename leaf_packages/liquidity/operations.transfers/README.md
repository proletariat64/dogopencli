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

Absolute rowStart offsets use pageSize=10. Top-level count must equal result.count; records are result.data. Other native filters are unsupported.

Preserve full native rows, nested logs, unknown fields and nullable monetary strings. orderStatus, receiptStatus and executeResult remain separate raw states; no bank-success inference or detail enrichment.

The host SDK owns retries, completeness and publication. Duplicate/conflicting identities and count gaps remain incomplete; strict refresh preserves the prior capture on rejection. Widths are historical successful request sizes, not measured backend maxima.

Ordinary List reads are offline. Live acquisition does not publish; refresh saves only a complete nonempty capture. Native fields already in the response remain intact; no Get or additional inquiry is performed.
