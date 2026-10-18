# investment.returns

Inspect native investment business records through inquiry-only endpoints.

JSON POST /accrualBaseList.json; fixed tenant GUAPW3SG; rowStart offsets of width 5000; data.data and fixed data.totalCount.

Native fields, amounts, rates, nulls, unknown fields and response order are retained without conversion.

Refresh retains one nonempty acquisition. Empty or failed refresh preserves the previous snapshot; live never publishes.

Runtime/date-partition Duckdog import has no supported contract for this leaf; installation initializes an empty binding only.

Accrual identity is (investmentNo, transactionDate); cash identity is transactionId. The adapter validates each route independently; the manifest has no common identity across the two routes.

Accrual sends transactionId=[], queryBeginTime/queryEndTime; cash sends postingDateBegin/End empty and settlementDateBegin/End. Fixed timeZone=GMT+08. Basis and date bounds are acquisition-only, unavailable offline.

Use `dogopencli liquidity list investment.returns -h` for required query parameters and `dogopencli liquidity describe investment.returns` for field descriptions.
