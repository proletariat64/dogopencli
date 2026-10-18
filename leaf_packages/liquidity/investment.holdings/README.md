# investment.holdings

Inspect native investment business records through inquiry-only endpoints.

JSON POST /portfolioQueryList.json; fixed tenant GUAPW3SG; rowStart offsets of width 500; data.data and fixed data.totalCount.

Native fields, amounts, rates, nulls, unknown fields and response order are retained without conversion.

Refresh retains one nonempty acquisition. Empty or failed refresh preserves the previous snapshot; live never publishes.

Runtime/date-partition Duckdog import has no supported contract for this leaf; installation initializes an empty binding only.

Fixed status=[ACTIVE, INACTIVE]. date selects the complete portfolio snapshot, never a row valueDate filter. get sends investmentNo as orderId.

get uses form POST /queryIncrementOrderDetail.json, only orderId, and requires matching native orderId.

Use `dogopencli liquidity list investment.holdings -h` for required query parameters and `dogopencli liquidity describe investment.holdings` for field descriptions.
