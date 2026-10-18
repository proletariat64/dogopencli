# Risk event thresholds

Independent `liquidity.risk.thresholds` package for inquiry-only risk event thresholds.
The host wheel does not bundle this package.

Install this directory or its verified ZIP with `dogopencli plugins install`.
Use `dogopencli liquidity list risk.thresholds` for the saved snapshot,
`dogopencli liquidity list risk.thresholds --live` for acquisition without publication,
and `dogopencli liquidity refresh risk.thresholds` to replace the saved snapshot only
when the candidate passes host quality policy. Refresh never imports into Duckdog;
use the explicit importer separately.

Native list: `POST JSON /api/risk/benchmark/riskEventBenchmarkQuery.json`, `rowStart` offsets,
`pageSize=10`. Fixed GUAPW3SG tenant; no timeZone.
Native `benchmarkId` is retained with its original JSON type. Full records retain
unknown fields and exact decimals. No page echoes exist; completeness requires a
stable total and agreement of arrival and unique identity counts.

The manifest selects the host List SDK: general provider, native offset paging
and the declared native identity/width. The leaf builds requests and parses native
responses; the host owns the collection loop and quality evidence. Duplicates,
conflicts and short or empty interior pages remain incomplete. Conflicts retain
the last arrival without claiming it is newest. Strict queries and refresh reject
incomplete acquisitions; empty or failed refresh preserves the preceding snapshot
and capture time.

The pinned v0.4.3 release establishes historical provenance. Production UAT and
same-input replay qualify current behavior separately; synthetic tests alone do
not establish production acceptance.

Native detail: `POST form /api/risk/benchmark/riskEventBenchmarkDetailDetail.json` with string `benchmarkId`; no tenant or timeZone.
Run `dogopencli liquidity get risk.thresholds RECORD_ID`. The response must echo
`benchmarkId` by string equivalence, preserving its native JSON type. Get performs
a real detail inquiry and never publishes or changes the saved list.
