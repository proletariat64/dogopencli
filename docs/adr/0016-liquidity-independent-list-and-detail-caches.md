# Independent liquidity list and native-detail caches

Status: accepted
Date: 2026-10-01

Liquidity list refresh and per-object detail refresh are independent. A list refresh publishes the validated list scope without requiring every object's detail. Explicit detail refresh uses the native typed identity, including a version where required, and updates only that object's detail cache. Offline `get` reads genuine cached native detail; it never substitutes a list row, fetches implicitly, or treats a missing cached detail as proof that the business object does not exist. Explicit live `get` remains inquiry-only and does not write the cache.

This deliberately differs from the coupled list/detail acquisition required for certain existing capabilities in [ADR 0003](0003-local-query-snapshots.md). It avoids multiplying a large liquidity list into an obligatory full-detail crawl while retaining offline detail access after explicit acquisition. List and detail captures carry their own identity, source scope, version, capture time and freshness; an older detail must not be represented as belonging to a newer list generation without validated correspondence. Payment and collection acquisition contracts are unchanged.

Incomplete acquisition follows existing practice: invalid or incomplete list acquisition does not replace a valid cache; hard detail failures preserve prior valid detail; permitted live partial results retain explicit incompleteness metadata. The specific VA detail-refusal tolerance in [ADR 0010](0010-collection-va-partial-detail-tolerance.md) remains limited to that capability and is not generalized to liquidity. Detail failure cannot invalidate a separately successful list refresh.
