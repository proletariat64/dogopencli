# Funding action relations

Independent `liquidity.rules.funding` package for inquiry-only funding action relations.
The host wheel does not bundle this package.

Install this directory or its verified ZIP with `dogopencli plugins install`.
Use `dogopencli liquidity list rules.funding` for the saved snapshot,
`dogopencli liquidity list rules.funding --live` for acquisition without publication,
and `dogopencli liquidity refresh rules.funding` to replace the saved snapshot only
when the candidate passes host quality policy. Refresh never imports into Duckdog;
use the explicit importer separately.

Native list: `GET /fundRiskActionRelationQuery.json`, `rowStart` offsets,
`pageSize=5000`. Inquiry is encoded in the JSON string `fundRiskActionRelationQueryVO` with the fixed GUAPW3SG tenant both inside and outside the inquiry.
Native `id` is retained with its original JSON type. Full records retain
unknown fields and exact decimals. No page echoes exist; completeness requires a
stable total and agreement of arrival and unique identity counts. Empty or rejected
refresh preserves the preceding snapshot and capture time.

The pinned v0.4.3 release establishes historical provenance. Production UAT and
same-input replay qualify current behavior separately; synthetic tests alone do
not establish production acceptance.
