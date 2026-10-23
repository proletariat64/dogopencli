# Client agreement action mappings

Independent `liquidity.rules.action_mapping` package for inquiry-only client agreement action mappings.
The host wheel does not bundle this package.

Install this directory or its verified ZIP with `dogopencli plugins install`.
Use `dogopencli liquidity list rules.action_mapping` for the saved snapshot,
`dogopencli liquidity list rules.action_mapping --live` for acquisition without publication,
and `dogopencli liquidity refresh rules.action_mapping` to replace the saved snapshot only
when the candidate passes host quality policy. Refresh never imports into Duckdog;
use the explicit importer separately.

Native list: `GET /clientAgreementConfigQuery.json`, `rowStart` offsets,
`pageSize=1000`. Inquiry is encoded in the JSON string `clientAgreementConfigQueryVO` with the fixed GUAPW3SG tenant both inside and outside the inquiry.
Native `id` is retained with its original JSON type. Full records retain
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
