# Liquidity capture store and retention implementation

> Cache, detail persistence and retention decisions below are superseded by [ADR 0020](0020-temporary-query-cache-and-duckdog.md) and #157. Native inquiry authorization and contracts remain historical evidence.

Status: accepted
Date: 2026-10-01

Implements [ADR 0016](0016-liquidity-independent-list-and-detail-caches.md)
and [ADR 0017](0017-liquidity-one-million-record-retention.md) on the
existing SQLite cache ([ADR 0003](0003-local-query-snapshots.md)).

## Layout

Each liquidity business leaf owns one `__index__` namespace listing its
retained captures; every capture is its own namespace of validated primary
records. Per-object native details live in a separate per-leaf detail
namespace, upserted one object at a time, independent of list captures.

- `snapshot` profile (settings/reference leaves): one current capture per
  scope; a refresh atomically replaces it. Overflow beyond the
  1,000,000-record cap rejects the refresh and preserves the previous cache.
- `history` profile (full current runtime listings): every explicit refresh
  is a retained capture; capture time is the history axis and is never
  relabelled as source observation time.
- `dated` profile (business-window runtime acquisitions): captures retain by
  their verified business window; each record must carry its verified series
  time or the refresh is rejected before anything is published.

## Retention

When a time-series leaf exceeds the cap, eviction runs inside the same
transaction as the new publication: whole oldest captures drop first, and
the boundary capture is trimmed by exact (series time, identity, position)
order, so precisely the newest 1,000,000 records remain. The index keeps
the truthful record: dropped and retained counts, the retained cutoff and
the tie-break boundary. A stderr warning reports the eviction; stdout
stays parseable. Queries demanding evicted or missing windows follow the
existing incomplete-result behavior; retention narrows the published scope
and completeness is only ever claimed for the exact retained scope.

The cap counts primary records across a leaf's retained dates, captures and
filter variants. It is a product policy, not a proven SQLite capacity
limit; no million-record performance claim is made.
