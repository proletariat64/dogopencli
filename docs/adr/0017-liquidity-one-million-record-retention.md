# Bounded liquidity retention with oldest-first time-series eviction

Status: accepted
Date: 2026-10-01

For v0.2.1, each liquidity business leaf retains at most 1,000,000 primary business records in its cache, counted across that leaf's retained dates, captures and filter variants rather than separately per partition. The cap is a user-selected product policy, not a measured SQLite capacity limit. Keep the existing SQLite approach; do not add another engine, performance-budget framework or package binaries for this phase.

Retain explicitly acquired runtime history until the cap is exceeded. For a time-series leaf, atomically keep the newest 1,000,000 records and evict the oldest by its verified series time, with a stable identity tie-breaker. Dated business records use their verified business-date/time dimension; retained snapshot captures use capture time as the history axis without relabelling it as source observation time. If ordering cannot be established, refuse the refresh rather than dropping arbitrary records. Settings, reference and other non-time-series leaves do not use oldest-first eviction: overflow rejects refresh and preserves the old cache.

Eviction is deliberate retention, not tolerance of failed acquisition. Emit a warning on stderr while preserving machine-readable stdout; metadata records the dropped count, retained count and exact retained coverage/cutoff, including a stable tie-break boundary where eviction splits a timestamp. Missing or evicted coverage is never reported as an empty complete dataset or a nonexistent object. Queries requiring discarded coverage use existing incomplete-result behavior. Validate acquisition for the scope being published, then publish records, eviction and coverage atomically; never trim the old generation before successful validation. The cap does not imply a byte/memory bound or a million-record performance result.

Retention narrows the published scope. Completeness may be true only for that exact validated retained scope; acquisition coverage and discarded history remain explicit. A successful refresh with an eviction warning does not satisfy a query demanding complete coverage of a broader window.
