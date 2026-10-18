# investment.holdings

Inspect native investment business records through inquiry-only endpoints.

JSON POST /portfolioQueryList.json; fixed tenant GUAPW3SG; rowStart offsets of width 500; data.data and fixed data.totalCount.

Native fields, amounts, rates, nulls, unknown fields and response order are retained without conversion.

The host List SDK deduplicates native identities and uses the last arrival for conflicting records; conflicts or count gaps remain incomplete. Only complete nonempty refresh publishes; empty, failed or incomplete refresh preserves the previous snapshot. Live never publishes.

Runtime/date-partition Duckdog import has no supported contract for this leaf; installation initializes an empty binding only.

Fixed status=[ACTIVE, INACTIVE]. date selects the complete portfolio snapshot, never a row valueDate filter.

Use `dogopencli liquidity list investment.holdings -h` for required query parameters and `dogopencli liquidity describe investment.holdings` for field descriptions.
