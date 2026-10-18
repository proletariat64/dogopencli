# Shared List Collection API

## Purpose and boundaries

Issue [#291](https://github.com/proletariat64/dogopencli/issues/291). Make ordinary Leaf List development faster by reusing **mechanisms**, not by assuming Payment, Collection, FX and Liquidity have the same business behavior. The Host remains a local Python CLI, not a remote service. Extend the existing `dogopencli.collect`, endpoint contracts, leaf manifest validator, and runtime; do not create a standalone SDK distribution, a business monolith or any SDK version/negotiation scheme.

An opted-in List Leaf contributes only (a) its native verified `TransportCapability`, (b) `page_body(scope, position, size)`, (c) `parse_rows(body) -> (list[dict], reported_total)` for offset, or `parse_page(body) -> ParsedPage` for numbered/single paging, and (d) optional `validate_rows_scope(rows, scope)`. It still owns `scope`, `filter` and business fields. The Host calls `collect_list` directly for opted-in lists; it does not execute a leaf-maintained paging loop.

Existing leaves without `collection` retain their current collectors and behavior while migrating. This is a bounded migration seam, not an extra permanent framework.

## Ownership and provider isolation

- **Leaf chooses provider.** `leaf.json` declares a `collection.provider`. Domain declarations remain unchanged and do not register SDKs.
- The Host maintains a **fixed, first-party** resolver: `general` is public to all domains; `payment.collection`, `collection.collection`, `fx.collection` and `liquidity.collection` are private to their named owner. Initial private providers may delegate to the same neutral collector; separate business semantics still come exclusively from leaf contracts.
- Only one provider executes an opted-in List operation. No hot loading, SDK switching, third-party provider execution, multiple active contracts or provider versions.
- Validate provider availability and owner-domain match at static manifest validation, installation and runtime. A payment leaf declaring `fx.collection` is invalid even if their JSON looks identical. A leaf using `general` still belongs to its own domain; the provider grants no cross-domain installation permission.
- This is **contract enforcement for trusted Python plugins**, not a Python security sandbox: arbitrary adapter Python imports are outside this guarantee.

## Proposed leaf manifest extension

For a List leaf, `collection` is optional during migration. When present, it is a closed object with no implicit defaults except optional `latest_by`:

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

`paging.mode`: `offset`, `page_number` or `single`. Sizes must be a nonempty, unique, positive list of **individually endpoint-qualified** widths, in descending preference order. `single` has exactly one size; do not invent extra pages. For offset paging, position is absolute zero-based `rowStart`; numbered pages start at `contract.one_based ? 1 : 0`. For a simple native field, declare `primary_id: {"type":"field","fields":["instId"]}`; `field` requires exactly one field and `hash` requires a nonempty reviewed tuple. `latest_by` may be omitted; if present it is a native timestamp or numeric time field. Get-only leaves do not need `collection`. No `version` key or schema-version value exists.

Source manifest config represents **policy**; it never stores a learned page size. The list/get manifest identity can differ, because some real native gets use a different echo field.

## Identity, duplicates, holes and coverage

- Identity must be selected by the leaf developer at design time and reviewed by a human (HIL) against business semantics. A hash cannot make non-unique columns unique. `hash` uses `sha256(canonical([typed_field_values,...]))` in declared field order, so numbers and strings cannot collide by string concatenation. Missing/null/non-scalar key parts are invalid. Collision of a 256-bit digest with different native tuples is a hard error. Do not mutate native row JSON or generate a synthetic source field.
- Maintain a first-seen position per identity; collapse identical cross-page duplicates. On different content for the same identity, retain the row with the greatest parsed `latest_by` value when configured, breaking equal timestamps with last arrival; otherwise the **last loaded row wins**. Preserve explicit diagnostic reasons and counts, including conflicts. For an unverified ordering, last arrival is not a proof that the row is globally newest.
- A duplicate or conflict is *not* automatically proof of complete coverage: a repeated row can conceal an omitted row. Report arrivals, unique count, duplicate count, conflicting count, reported total, and `scope_complete=false` on page overlaps or known holes.
- For a reported fixed unique-object total, require `unique_count == reported_total` and **no anomalous gaps/duplicates** to claim complete. Reject changing totals or invalid response envelopes; do not guess other total semantics. Existing FX with unproven identity/total stays on its current collector.
- Detect short pages before the expected end, empty interior pages and final unique/count shortfall. Advance by the requested page stride (not returned row count), so following valid ranges can still be read and exposed as explicitly partial. Never fill missing data or change effective reported total. A bounded fallback must **restart from position zero** using the next declared width, without mixing candidates.
- If all declared widths fail to prove coverage, return the last validated *partial* candidate for live display with incomplete evidence where possible; strict modes reject it. An unavailable or malformed page producing a hard business/authorization/schema error never becomes partial success. Unsupported request widths are never guessed.

## Page-size fallback and persistence

- Prefer the last **completely successful** size if present and still declared; otherwise use manifest order. When the primary width times out within its per-attempt allocation or produces a validated short/duplicate/gap candidate, retry the **full** requested scope from offset zero using the next allowed size. No fallback on authentication errors, unknown schema, permissions, changed native totals or business failures.
- Share an absolute global deadline and a **single maximum logical-page budget** across all fallback attempts, counting even a page that ends in transport timeout. Each retry of the same page by the existing network retry policy is part of that one logical position; never reset the page allowance on fallback.
- Store only `preferred_page_size` and minimal harmless performance observations in `<config-directory>/collection-state.json`, keyed by a hash of leaf ID, endpoint/method and canonical scope + relevant declared contract. Never persist tokens, business rows, raw scopes, endpoint responses, or mutate the installed leaf manifest. Read corrupt/missing/outdated state as no preference. Atomic replacement and restrictive permissions. Limit retained keys.
- Updates happen **only after proven-complete acquisitions**; an unsuccessful fallback must not promote a width. Learning is best-effort: use a **nonblocking preference-file lock** and skip the optimization when another writer holds it, never stalling an otherwise successful inquiry.

## Host integration and quality policy

- `leaves.registry.validate_manifest` validates the closed `collection` schema, provider boundary and primary-ID fields. The install path already uses the manifest validator. The Host dispatches opted-in List operations through `collect_list`, passing configuration-scoped runtime state; non-opted-in leaves keep their current collector. **For a leaf without a collection declaration, preserve the exact pre-SDK cache contract hash**: omit the absent collection entry and the new empty page-size allowance when fingerprinting. Do not alter bundled pilot adapter bytes merely to demonstrate the opt-in API.
- `EndpointContract` and the existing restricted `validate_request` remain authoritative. The declared allowed page widths must be supported by the endpoint allowlist (top-level or nested JSON-body allowances). No broad HTTP capability or arbitrary method.
- Every candidate records attempt size, page count, arrivals, unique count, duplication, holes, timing, and reason codes in `AcquisitionEvidence.attempts`. Selected records are unchanged business JSON.
- Best-effort live can show validated incomplete records plus warnings. For opted-in SDK lists, **refresh publishes only a proven-complete nonempty result** and preserves prior cache on partial/failed/empty acquisition. This stricter refresh gate is opt-in only; keep existing non-opted-in FX behavior. The selected runtime width is operational and must not alter cache contract identity.
- Do not change Get, auth, business query permissions, Duckdog publication/import, display paging or unrelated migration PRs.

## Acceptance matrix

1. General provider works for a Payment or Liquidity List; a Payment Leaf declaring `fx.collection` fails manifest/install/load. Private provider owner matches and unknown providers fail. Domain declaration remains unchanged.
2. Both field and SHA-256 tuple identity are stable and type-aware. Missing identity fails, hash is *internal*, same-key duplicates use timestamp/latest or last-arrival and keep conflicts visible.
3. Offset and numbered paging validate total/echo and make exactly qualified requests. Same-width duplicate, short/empty interior page and count mismatch yield `complete=false`, not silent success. Changing totals, schema failure and authorization are hard failures.
4. Page-size fallback restarts from zero; attempts are never merged; unknown widths fail at restricted transport. Global deadline and total logical-page cap terminate; fallback cannot reuse another candidate's allowance.
5. A complete candidate persists a preferred width when its optional state lock is available; separate run loads it; corrupt/busy state is harmless. Partial/failure does not change preference or cached business snapshot. An older snapshot from an unchanged non-SDK leaf still replays offline.
6. Existing four pilots, normal/strict live, refresh/offline, portable install and default-only help remain unaffected. Demonstrate opt-in with the synthetic developer leaf and test a native offset pilot's parser via a **test-local qualified wrapper**, without changing its installed source or cache fingerprint. Production migration needs independent acceptance.
7. Test with fake transport and local Python checks. No production CDP/SSO/network mutation, migration completion count, release or automatic PR merge.

## Implementation posture

Prefer small edits to `collect.py`, `contracts.py`, the first-party manifest/registry/runtime and leaf-dev guidance; create a tiny state helper if needed. Do not introduce a public SDK version, autonomous daemon, interface inheritance hierarchy or another domain register. Existing endpoint JSON parsing remains leaf-owned.
