# Collection network configuration snapshots

Status: accepted for implementation — #41–#48.

Clearing-system and card-template lists use independent CDP sources and cache
namespaces. Their [clearing-system](../research/general/2026-09-27-collection-clearing-system-contract.md)
and [card-template](../research/general/2026-09-27-collection-card-template-contract.md)
contracts support one complete first-page acquisition at pageSize=1000, with
raw nonempty string `id` identity. Clearing-system small pages produced
repeated identities, and both endpoints clamp beyond-end pages back to page 1.
Therefore single-page rows must equal totalCount and all IDs must be unique;
a scope over 1000 or a truncated response fails explicitly, preserving the old
snapshot. Multi-page fallback and VA capacity's running-total logic do not apply.
An exact full page succeeds only if totalCount is exactly 1000. The verified
empty shape allows pageNo 0 or 1, size 1000, zero total and no rows.

The two capabilities share configuration-list orchestration and a plugin for
the verified envelope, while endpoints, filters, schema and sources stay explicit.
Local string filters run before lexical identity sorting/windowing/projection.
The shared transport, collector and existing capabilities retain their contracts.
Only pageNo=1/pageSize=1000 is allowlisted; optional backend selectors stay outside
the CLI transport, avoiding accidental differences in backend filter semantics.

Relationship labels open separate queries; no joins, detail or relationship
fetching is part of this slice. Card-template item arrays were observed empty,
so their element schema and detailed template completeness remain unverified.
Raw values and future nested extensions are preserved. Configuration levels,
timestamps and missing relationship fields are never inferred or fabricated.
