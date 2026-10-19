# Shared List Collection API

## Purpose and boundaries

Issue [#291](https://github.com/proletariat64/dogopencli/issues/291). Make ordinary Leaf List development faster by reusing **mechanisms**, not by assuming Payment, Collection, FX and Liquidity have the same business behavior. The Host remains a local Python CLI, not a remote service. Extend the existing `dogopencli.collect`, endpoint contracts, leaf manifest validator, and runtime; do not create a standalone SDK distribution, a business monolith or any SDK version/negotiation scheme.

A single-source SDK List supplies a verified native `TransportCapability`, pure
`page_body(scope, position, size)` and parser, plus optional
`validate_rows_scope(rows, scope)`. It owns `scope`, `filter` and business fields;
the host executes `collect_list`. Declared independent sources use those same
native hooks and the flat assembly seam below, without a leaf-maintained query loop.

Existing leaves without `collection` retain their current collectors and behavior while migrating. This is a bounded migration seam, not an extra permanent framework.

## Ownership and provider isolation

- **Leaf chooses provider.** `leaf.json` declares a `collection.provider`. Domain declarations remain unchanged and do not register SDKs.
- The Host maintains a **fixed, first-party** resolver: `general` is public to all domains; `payment.collection`, `collection.collection`, `fx.collection` and `liquidity.collection` are private to their named owner. Initial private providers may delegate to the same neutral collector; separate business semantics still come exclusively from leaf contracts.
- Only one provider executes an opted-in List operation. No hot loading, SDK switching, third-party provider execution, multiple active contracts or provider versions.
- Validate provider availability and owner-domain match at static manifest validation, installation and runtime. A payment leaf declaring `fx.collection` is invalid even if their JSON looks identical. A leaf using `general` still belongs to its own domain; the provider grants no cross-domain installation permission.
- This is **contract enforcement for trusted Python plugins**, not a Python security sandbox: arbitrary adapter Python imports are outside this guarantee.

## Leaf manifest

For a List leaf, `collection` is optional during migration. When present, it is a closed object with no implicit defaults except optional `latest_by`, `max_pages` and `budget_seconds`:

```json
{
  "collection": {
    "provider": "general",
    "paging": {
      "mode": "offset",
      "page_sizes": [500, 100, 50]
    },
    "primary_id": {
      "type": "hash",
      "fields": ["accountAlias", "currency"]
    },
    "latest_by": "gmtModified"
  }
}
```

`paging.mode`: `offset`, `page_number`, `single` or the explicitly qualified
`single_response` described below. Sizes must be nonempty, unique, positive
(except the explicit unpaged declaration below),
individually endpoint-qualified and descending. `single` and `single_response`
have exactly one size. Offset position is absolute zero-based `rowStart`;
numbered pages start at `contract.one_based ? 1 : 0`.
A field identity has exactly one native field; `hash` uses a reviewed tuple.
Optional `latest_by` chooses a conflicting row while leaving coverage incomplete.
Unproven identity requires empty manifest `identity` and forbids `latest_by`.
Optional `max_pages` (1–1000) and `budget_seconds` (1–900) narrow host bounds.
Get-only omits `collection`; no version negotiation is added.

Source manifest config represents **policy**; it never stores a learned page size. The list/get manifest identity can differ, because some real native gets use a different echo field.

## Qualified response without a native total

Use `paging: {"mode": "single_response", "page_sizes": [5000]}` only after
separate qualification that one response covers the exact declared native query.
The width is a qualified request value, not a demonstrated capacity maximum.
The capability implements pure `parse_rows(body) -> (native_rows, None)` and
declares verified native identity. The host makes one logical page request;
there is no offset iteration, alternate width, rebuild or learned width.
Existing bounded transport retries still apply to that request.

For a native endpoint with no pagination fields, declare `page_sizes: [0]` and
`EndpointContract.page_size=0`. Zero means unpaged, not a capacity limit; the
leaf request builder must omit pagination fields. Only `single_response` accepts
this declaration, and its size must still match the endpoint-qualified contract.
Do not invent a positive width for an unpaged endpoint.

Evidence keeps `reported_total=null`, `total_semantics="unknown"` and
`coverage_basis="qualified_single_response"`; arrivals, unique count and duplicate
count remain separate observations. Completeness follows the accepted response
contract, never a fabricated total. A source ignoring requested pageSize is not
rejected solely for returning more rows. Duplicate/conflict and native failures
still prevent strict success/publication. Empty refresh preserves prior cache.
Ordinary modes still require native totals; a missing total alone does not qualify
this mode. See [the executable sample](../../tools/leaf-dev/example-single-response/).

## Declared independent sources

For an accepted relationship, declare `collection.sources` instead of top-level
`paging`. Keep the provider and aggregate `primary_id`; each named source declares
only `paging` and its own `primary_id`. Source names exactly match the leaf hooks;
sources cannot nest. The [sources sample](../../tools/leaf-dev/example-sources/)
shows the complete declaration and native mapping.

The adapter supplies pure `source_capability(name, parameters)`,
`source_scope(name, parameters)` and `assemble(records_by_source, parameters)`,
plus aggregate `scope` and `filter`. Source capabilities use the same request and
parser hooks as ordinary Lists. The host's `collect_sources` reuses `collect_list`
for all required sources under one global deadline and logical-page budget,
including fallback attempts. It calls assembly only after all sources are complete.
Any failed/incomplete source fails the aggregate atomically and preserves prior
cache. An empty child array can follow a successful complete source with no match;
it cannot stand for a failed or unqueried source.

The leaf owns reviewed parent references, source date meanings, cardinality and
output order. Assembly returns uniquely identified roots, preserves each native
child according to that model and performs no inquiry. The SDK guesses no join,
amount, version, timestamp or business grain. No holdings lookup or automatic
source expansion is implied.

Aggregate evidence keeps `reported_total=null`, `total_semantics="assembled_roots"`
and `coverage_basis="validated_sources"`. `acquisition.sources` maps each source
name to its exact `scope` and independent `acquisition` evidence, retaining native
totals and identity diagnostics through refresh/offline replay. Root count is an
observed output count, not the sum of child totals or a native parent total.
Raw source scopes never enter the preference file; its existing hashed keys apply.

## Identity, duplicates, holes and coverage

- Identity must be selected by the leaf developer at design time and reviewed by a human (HIL) against business semantics. A hash cannot make non-unique columns unique. `hash` uses `sha256(canonical([typed_field_values,...]))` in declared field order, so numbers and strings cannot collide by string concatenation. Missing/null/non-scalar key parts are invalid. Collision of a 256-bit digest with different native tuples is a hard error. Do not mutate native row JSON or generate a synthetic source field.
- Maintain a first-seen position per identity; collapse identical cross-page duplicates. On different content for the same identity, retain the row with the greatest parsed `latest_by` value when configured, breaking equal timestamps with last arrival; otherwise the **last loaded row wins**. Preserve explicit diagnostic reasons and counts, including conflicts. For an unverified ordering, last arrival is not a proof that the row is globally newest.
- A duplicate or conflict is *not* automatically proof of complete coverage: a repeated row can conceal an omitted row. Report arrivals, unique count, duplicate count, conflicting count, reported total, and `scope_complete=false` on page overlaps or known holes.
- For a reported fixed unique-object total, require `unique_count == reported_total` and **no anomalous gaps/duplicates** to claim complete. Reject changing totals or invalid response envelopes; do not guess other total semantics. An unproven identity uses `primary_id: {"type":"unproven","fields":[]}` and `contract.has_identity=False`. Preserve every native arrival without deduplication; exact repeated JSON is diagnostic only. Outside a separately qualified `single_response` contract, unknown totals cannot establish completeness; count equality does not prove it. Stop an unproven read on overlap, a short page or the logical-page cap, retaining validated arrivals with explicit incomplete evidence; strict modes and refresh reject it. No synthetic ID or hash is justified.
- Detect short pages before the expected end, empty interior pages and final unique/count shortfall. Advance by the requested page stride (not returned row count), so following valid ranges can still be read and exposed as explicitly partial. Never fill missing data or change effective reported total. A bounded fallback must **restart from position zero** using the next declared width, without mixing candidates.
- If all declared widths fail to prove coverage, return the last validated *partial* candidate for live display with incomplete evidence where possible; strict modes reject it. An unavailable or malformed page producing a hard business/authorization/schema error never becomes partial success. Unsupported request widths are never guessed.

## Page-size fallback and persistence

- Prefer the last **completely successful** size if present and still declared; otherwise use manifest order. When the primary width times out within its per-attempt allocation or produces a validated short/duplicate/gap candidate, retry the **full** requested scope from offset zero using the next allowed size. No fallback on authentication errors, unknown schema, permissions, changed native totals or business failures.
- Share an absolute global deadline and a **single maximum logical-page budget** across all fallback attempts, counting even a page that ends in transport timeout. Each retry of the same page by the existing network retry policy is part of that one logical position; never reset the page allowance on fallback.
- Store only `preferred_page_size` and minimal harmless performance observations in `<config-directory>/collection-state.json`, keyed by a hash of leaf ID, endpoint/method and canonical scope + qualified widths. Never persist tokens, business rows, raw scopes, endpoint responses, or mutate the installed leaf manifest. Read corrupt/missing state or a no-longer-qualified width as no preference. A still-qualified preferred width is only request ordering; every candidate is revalidated, so adapter-source or identity fingerprints are unnecessary. Atomic replacement and restrictive permissions. Limit retained keys.
- Updates happen **only after proven-complete acquisitions**; an unsuccessful fallback must not promote a width. Learning is best-effort: use a **nonblocking preference-file lock** and skip the optimization when another writer holds it, never stalling an otherwise successful inquiry.

## Host integration and quality policy

- `leaves.registry.validate_manifest` validates the closed `collection` schema, provider boundary and primary-ID fields. The install path already uses the manifest validator. The Host dispatches opted-in List operations through `collect_list`, passing configuration-scoped runtime state; non-opted-in leaves keep their current collector. Fingerprint the complete current endpoint contract, collection policy and adapter source. Historical cache hashes are not preserved: no live historical data requires compatibility. All four bundled pilots use the SDK; independent batch packages retain their own active collectors until separately assigned.
- `EndpointContract` and the existing restricted `validate_request` remain authoritative. The declared allowed page widths must be supported by the endpoint allowlist (top-level or nested JSON-body allowances). No broad HTTP capability or arbitrary method.
- Every candidate records attempt size, page count, arrivals, unique count, duplication, holes, timing, and reason codes in `AcquisitionEvidence.attempts`. Selected records are unchanged business JSON.
- Best-effort live can show validated incomplete records plus warnings. For opted-in SDK lists, **refresh publishes only a proven-complete nonempty result** and preserves prior cache on partial/failed/empty acquisition. The bundled FX pilot also uses this gate; unproven results cannot be published. The selected runtime width is operational and must not alter cache contract identity.
- Keep native Get and business query permissions, Duckdog publication/import, display paging and unrelated migration packages intact. Shared transport classifies HTTP 401/403 as authorization failures.

## Acceptance matrix

1. General provider works for a Payment or Liquidity List; a Payment Leaf declaring `fx.collection` fails manifest/install/load. Private provider owner matches and unknown providers fail. Domain declaration remains unchanged.
2. Both field and SHA-256 tuple identity are stable and type-aware. Missing identity fails, hash is *internal*, same-key duplicates use timestamp/latest or last-arrival and keep conflicts visible.
3. Offset and numbered paging validate total/echo and make exactly qualified requests. Same-width duplicate, short/empty interior page and count mismatch yield `complete=false`, not silent success. Changing totals, schema failure and authorization are hard failures.
4. Page-size fallback restarts from zero; attempts are never merged; unknown widths fail at restricted transport. Global deadline and total logical-page cap terminate; fallback cannot reuse another candidate's allowance.
5. A complete candidate persists a preferred width when its optional state lock is available; separate run loads it; corrupt/busy state is harmless. Partial/failure does not change preference or cached business snapshot. Current-contract snapshots replay offline; no historical-hash fallback exists.
6. All four bundled pilots execute via the SDK with no leaf-owned collector. Exercise native values, scope, normal/strict live, refresh/offline, portable install and declaration-only help. The FX pilot uses the native transaction number `uniqueId` and compares unique rows with native `totalCount`; complete acquisitions support refresh/offline, while duplicate/conflicting/short candidates are rejected by strict modes. Production migration needs independent acceptance.
7. Test with fake transport and local Python checks. No production CDP/SSO/network mutation, migration completion count, release or automatic PR merge.

## Implementation posture

Prefer small edits to `collect.py`, `contracts.py`, the first-party manifest/registry/runtime and leaf-dev guidance; create a tiny state helper if needed. Do not introduce a public SDK version, autonomous daemon, interface inheritance hierarchy or another domain register. Existing endpoint JSON parsing remains leaf-owned.

## Bundled pilot contracts

| Leaf | Paging / qualified widths | Identity / coverage |
| --- | --- | --- |
| payment.sla.baselines | Native zero-based pages, 10000 then 5000 | Native `id`; filters stay in the native request; get retains its own endpoint. |
| collection.cost | Single fixed request, 1000 | Native `itemId`, fixed `FUND_IN_CHANNEL_TRANS_FEE`; no invented second page. |
| liquidity.reference.entities | Native rowStart offsets, 5000 | Native `instId`; tenant and nested inquiry fields are allowlisted. |
| fx.trade | Native zero-based pages, 50; 100 pages / 120 seconds | Native transaction number `uniqueId`; compare unique rows to `totalCount`. Broad queries may fail; use a qualified BCode/scene/symbol/type/fulfilled/date scope. |

Only existing endpoint-qualified widths are declared. Neither this table nor fake
transport acceptance qualifies production ordering or snapshot consistency.
