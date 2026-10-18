# investment.benchmark_values

Inspect native investment business records through inquiry-only endpoints.

JSON POST /queryStrategyBenchmarkList.json; fixed tenant GUAPW3SG; rowStart offsets of width 5000; data.data and fixed data.totalCount.

Native fields, amounts, rates, nulls, unknown fields and response order are retained without conversion.

Refresh retains one nonempty acquisition. Empty or failed refresh preserves the previous snapshot; live never publishes.

Runtime/date-partition Duckdog import has no supported contract for this leaf; installation initializes an empty binding only.

Identity is effectiveDate, strategyBenchmarkType, currency and colorType; blank native id is retained. Values are native percent strings without scaling.

Fixed timeZone=GMT+08; valueDateStart/End bound effectiveDate (YYYYMMDD). Full native fields are retained; no synthetic primaryId is generated.

Use `dogopencli liquidity list investment.benchmark_values -h` for required query parameters and `dogopencli liquidity describe investment.benchmark_values` for field descriptions.
