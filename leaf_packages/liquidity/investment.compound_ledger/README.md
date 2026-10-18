# investment.compound_ledger

Inspect native investment business records through inquiry-only endpoints.

JSON POST /compoundOrderList.json; fixed tenant GUAPW3SG; rowStart offsets of width 5000; data.data and fixed data.totalCount.

Native fields, amounts, rates, nulls, unknown fields and response order are retained without conversion.

Refresh retains one nonempty acquisition. Empty or failed refresh preserves the previous snapshot; live never publishes.

Runtime/date-partition Duckdog import has no supported contract for this leaf; installation initializes an empty binding only.

get uses form POST /compoundOrderDetail.json, only compoundOrderNo, and requires matching native orderNo.

Use `dogopencli liquidity list investment.compound_ledger -h` for required query parameters and `dogopencli liquidity describe investment.compound_ledger` for field descriptions.
