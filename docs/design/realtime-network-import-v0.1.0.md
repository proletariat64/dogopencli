# Realtime network enrichment storage v1

B03 implements specification [#174](https://github.com/proletariat64/dogopencli/issues/174)
and tracker [#166](https://github.com/proletariat64/dogopencli/issues/166) at the external duckdog
import boundary. It does not alter CLI acquisition, list cache, or selectors.
The original enrichment writer was recovered from an execution archive: it
consumed a saved complete realtime list, acquired each scoped live get, and
published rows containing `_detail` and `_detail_meta` through the settings
importer. It had no historical standalone script or saved enriched-input mode.
The durable replacement is `scripts/duckdog/import_realtime.py`.

Apply `scripts/patches/b03-duckdog-import.patch` to the external settings owner
(after the B01 patch). The patch is reviewable source, not an automatically
applied production change. The realtime entrypoint requires its version marker
and refuses an unpatched owner. The baseline owner snapshot in
`tests/fixtures/duckdog/import_settings.py` includes this patch for reproducible
synthetic storage verification. Other selector publication remains unchanged.

Explicit saved enriched-input publication:

```bash
python scripts/duckdog/import_realtime.py --settings-importer <owner-script> \
  --root <dataset-root> --input <saved-enriched-envelope.json>
```

Alternatively, `--list-input <saved-list-envelope.json>` performs the original
scoped get acquisitions, then validates and publishes. It never silently queries
an unbounded list. Both modes require an explicit destination and owner path.
No actual production acquisition or publication is part of the test suite.

## Representation and reconstruction

The view keeps `_row_order`, `_record` JSON and the existing native identity
column. Parquet keeps the complete record JSON. List fields retain native values
and presence. Reserved enrichment fields belong to the importer:

- `_detail_storage`: `{ "version": 1, "state": "record" | "full" | "absent" }`.
- `_detail_meta`: untouched independently acquired get metadata.
- `_detail`: full detail for `full`, only associations for aggregate `record`,
  omitted for identical legacy `record` or `absent`.

For `record`, remove the three reserved fields from `_record` to obtain the
original list root; overlay the retained association object from `_detail`.
For `full`, `_detail` is the effective object. For `absent`, no detail was
acquired and no acquisition metadata is fabricated. `effective_detail` exposes
these rules and reads legacy rows without a marker using their existing
`_detail`. Consumers must distinguish `absent` from a successfully acquired
association whose value is null or an empty array. Future marker versions are
rejected by reconstruction rather than guessed.

Structural comparison preserves object field presence, JSON types, ordered
arrays, precision, business times and configuration versions. Object key order
is immaterial. JSON numbers use integers and Decimal without floating-point
conversion. Boolean values never compare equal to numbers. Duplicate JSON keys
and non-finite values are rejected. Typed root identities, live provenance,
get identity, acquisition timestamps and source request scope are validated
before storage. Native realtime identities remain nonempty strings, as in the
public inquiry contract. Association scopes bind to the independently acquired
detail root, including history aliases/action and route/account/application
tenant; changed root context is retained in full. Successful components require
matching payloads, capture timestamps and counts. Unverified and inapplicable
components retain null payloads without fabricated acquisition evidence. Saved
list JSON is strictly validated before any live detail command. Acquisition metadata is outside business comparison.

The accepted B02 aggregate root contains only the 26 fields declared in
`realtime-network-detail-v0.1.0.md`. Associations `operationHistory` and
`routeDetails` and all component metadata survive, including incomplete
history, empty arrays and null associations. Deduplication requires the accepted
network native contract and component identities. Unknown root fields or
undecomposable versions retain the full valid detail. No patch/delta format is
introduced.

## Publication and historical inventory

The external owner writes staged Parquet, then replaces the view and registry
inside a transaction. Before commit, realtime publication verifies every JSON
record in both view and Parquet, the registry generation/digest/count and
acquisition metadata. Failure rolls back the transaction and removes only the
new failed candidate. Successful realtime imports preserve previous Parquet
generations; history cleanup is not part of B03. Other selectors keep their
existing replacement behavior. Normal replacement still requires invoking an
explicit import operation.

List acquisition ordering and detail refresh ordering are independent. A newer
list capture retains the existing replacement rule; an older list is rejected
even if its details are newer. For an unchanged list capture, a refresh can
replace enrichment only when its original ordered list roots match, no detail
capture regresses, and at least one detail capture advances. Differing detail at
the same capture time is rejected. Identical saved input still reuses its
generation. Registry `fetched_at` and the original list acquisition metadata
remain unchanged by a detail refresh; detail capture times stay in `_detail_meta`.
The entrypoint requires the updated owner patch's detail-refresh capability.

Every realtime replacement also compares independently acquired component times
for matching native identities and request scopes. An older network, history or
route observation cannot replace a newer one, even when the root capture or list
capture advances. Equal component times require identical component business
payloads. Unchanged association payloads at equal times remain usable; observations
in different validated scopes are ordered independently. The entrypoint requires
the updated owner patch's component-ordering capability. Legacy rows without
component evidence retain their existing detail-capture ordering rule.

An authorized read-only inventory on 2026-10-14 observed one current generation
with 204 rows in both view and Parquet. All 204 nested detail objects repeated
their list root under recursive type-aware structural comparison. The schema
exposes only record JSON and identity, so schema inspection alone cannot detect
nested enrichment. This is historical coverage of the observed generation,
not a fixed expected duplicate count or proof of unavailable generations.
Existing data was not rewritten, imported or removed.

Acceptance uses synthetic temporary DuckDB/Parquet publication through the
owning entrypoint, full readback, invalid-input preservation, injected transaction
failure, historical generation retention, legacy reconstruction and an unrelated
selector. B02 production CLI UAT is separate from this storage proof.
