# investment.holdings

Inspect native investment business records through inquiry-only endpoints.

JSON POST /portfolioQueryList.json; fixed tenant GUAPW3SG; rowStart offsets of width 500; data.data and fixed data.totalCount.

Native fields, amounts, rates, nulls, unknown fields and response order are retained without conversion.

The host List SDK deduplicates native identities and uses the last arrival for conflicting records; conflicts or count gaps remain incomplete. Only complete nonempty refresh publishes; empty, failed or incomplete refresh preserves the previous snapshot. Live never publishes.

Runtime/date-partition Duckdog import has no supported contract for this leaf; installation initializes an empty binding only.

Fixed status=[ACTIVE, INACTIVE]. date selects the complete portfolio snapshot, never a row valueDate filter.

Use `dogopencli liquidity list investment.holdings -h` for required query parameters and `dogopencli liquidity describe investment.holdings` for field descriptions.

## Native detail

`dogopencli liquidity get investment.holdings RECORD_ID` queries `/queryIncrementOrderDetail.json` using native `orderId` and validates root `orderId`. The lookup is the same value as native List `investmentNo`; the original fields, nested arrays, JSON types and exact values are retained. Separate history, logs and child endpoints are unqueried. Get never publishes cache or Duckdog data.

`dogopencli liquidity list investment.holdings --live --with-detail --limit 1 --date YYYY-MM-DD` returns selected `{record, detail}` pairs, preserves List order/quality and the saved List, and fails the entire query on any Detail failure.
