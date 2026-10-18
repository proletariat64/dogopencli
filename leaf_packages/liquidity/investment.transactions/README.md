# investment.transactions

Inspect native investment business records through inquiry-only endpoints.

JSON POST /queryIncrementOrderList.json; fixed tenant GUAPW3SG; rowStart offsets of width 5000; data.data and fixed data.totalCount.

Native fields, amounts, rates, nulls, unknown fields and response order are retained without conversion.

The host List SDK deduplicates native identities and uses the last arrival for conflicting records; conflicts or count gaps remain incomplete. Only complete nonempty refresh publishes; empty, failed or incomplete refresh preserves the previous snapshot. Live never publishes.

Runtime/date-partition Duckdog import has no supported contract for this leaf; installation initializes an empty binding only.

Use `dogopencli liquidity list investment.transactions -h` for required query parameters and `dogopencli liquidity describe investment.transactions` for field descriptions.
