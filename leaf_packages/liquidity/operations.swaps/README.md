# Swap orders

Read native records through the host List SDK.

```bash
dogopencli liquidity list operations.swaps --live --require-complete --limit 0 --from-date 2026-09-01 --to-date 2026-10-01
dogopencli liquidity refresh operations.swaps --require-complete --from-date 2026-09-01 --to-date 2026-10-01
dogopencli liquidity list operations.swaps --limit 0
```

POST **form** `/swapOrderQuery.json` with outer tenant and a JSON-string `swapOrderQueryVO`. Require outer resultFlag and inner success. Records are `result.swapOrderVOList`, native total is `result.count`; native `dealId` identifies one row.

Fixed GUAPW3SG tenant. POST form /swapOrderQuery.json contains a serialized swapOrderQueryVO with fixed empty near-leg entity arrays and blank near/far leg date bounds.

Required ISO trade-date bounds map to inclusive native YYYYMMDD bounds. Unbounded acquisition and other filters are unsupported. No source timezone is inferred.

Absolute rowStart offsets use pageSize=1000; records are result.swapOrderVOList and native total is result.count. Near/far dates are independent fields, not extra queries or computed tenors.

Preserve complete native JSON, nested values, unknown fields, nullable/grouped decimal strings, native integers and boolean flags. No leg join, rate conversion or detail enrichment.

The host SDK owns retries, completeness and publication. Declared latest_by selects the complete native row with greatest required integer gmtModified for each dealId; equal-order differing rows use last arrival with a warning. Valid selection is accepted in default and strict modes when traversal is complete. Native counts and actual coverage gaps remain separate; rejected refresh preserves the prior capture. Widths are historical successful request sizes, not measured backend maxima.

`gmtModified` is required on every row and compared numerically without epoch-unit or timezone inference. Missing, null, boolean, fractional or string ordering values fail. Native timestamps and complete selected rows remain unchanged.

Ordinary List reads are offline. Live acquisition does not publish; refresh saves only a complete nonempty capture. Native fields already in the response remain intact; no Get or additional inquiry is performed.
