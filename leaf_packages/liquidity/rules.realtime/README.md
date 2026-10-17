# Realtime rules

Independent `liquidity.rules.realtime` package for inquiry-only realtime rules.
The host wheel does not bundle this package.

Install this directory or its verified ZIP with `dogopencli plugins install`.
Use `dogopencli liquidity list rules.realtime` for the saved snapshot,
`dogopencli liquidity list rules.realtime --live` for acquisition without publication,
and `dogopencli liquidity refresh rules.realtime` to replace the saved snapshot only
when the candidate passes host quality policy. Refresh never imports into Duckdog;
use the explicit importer separately.

Native list: `POST JSON /api/realtime/rule/getAll.json`, `rowStart` offsets,
`pageSize=10`. No tenant or timeZone field.
Native `id` is retained with its original JSON type. Full records retain
unknown fields and exact decimals. No page echoes exist; completeness requires a
stable total and agreement of arrival and unique identity counts. Empty or rejected
refresh preserves the preceding snapshot and capture time.

The pinned v0.4.3 release establishes historical provenance. Production UAT and
same-input replay qualify current behavior separately; synthetic tests alone do
not establish production acceptance.

Native detail: `POST json /api/realtime/rule/getDetail.json` with string `Id`; no tenant or timeZone.
Run `dogopencli liquidity get rules.realtime RECORD_ID`. The response must echo
`id` by string equivalence, preserving its native JSON type. Get performs
a real detail inquiry and never publishes or changes the saved list.
