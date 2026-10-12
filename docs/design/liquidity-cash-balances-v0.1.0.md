# Cash balance dates, all entities and acquisition page size v0.1.0

Authority: [GitHub Issue #147](https://github.com/proletariat64/dogopencli/issues/147).

Status: finalized design; #148/#149 runtime implementation integrated on
`feat/cash-balances-spec147`. Full ALL/daily production CLI UAT, final repository
qualification and independent Standards/Spec review remain pending under #150.
The #148 scoped latest smoke is not full #147 rollout evidence.
User-facing behavior is documented in [README](../../README.md) and
[unreleased changes](../../CHANGELOG.md).
Date: 2026-10-12.

Evidence: [source/date/entity/page-width research](../research/general/2026-10-12-cash-balances-date-entities-pagination.md).

## Problem Statement

`dogopencli liquidity cash balances list` exposes latest snapshots but cannot query a business-date interval. Selecting every entity requires manually repeating native `instId`s. Its configured acquisition page width of 30 is unnecessarily small for requests that accept 100 rows, and users cannot choose the acquisition width.

Users want the same inclusive date scope with online `--live` and offline cached reads, explicit refresh for publication, an all-entity shorthand, and a suitable larger verified page width. These must not confuse latest snapshots, source daily observations and locally retained capture history.

## Solution

Keep the existing command and introduce two explicit contract variants:

- **No date bounds:** existing latest balance snapshots, with current/available/opening fields and retained capture history.
- **Both `--from-date` and `--to-date`:** source daily balance history over that inclusive business-date window, not historical copies of the entire latest-snapshot record.

With `--live`, acquire online without publishing. Without `--live`, read only matching cached data. Explicit `refresh liquidity cash balances` acquires and publishes the requested variant and scope. Missing date coverage follows existing cache completeness behavior, never automatic online fallback.

For this leaf, `--all` with no explicit `--entity` selects all entities in the maintained directory and displays all matched rows. With explicit repeated `--entity <instId>`, `--all` retains its existing display-all behavior within those entities. Other list commands are unchanged. Refresh accepts the same all-entity shorthand without introducing display pagination.

Expose latest acquisition `--page-size`, default **100**, supported client range **1–100**. This is a conservative client support bound, not an asserted native hard maximum. Historical inquiry has no native pageSize, so dated mode rejects an explicit `--page-size`; its internal request chunks are not described as backend pages. `--limit` and `--offset` remain display controls.

The design is finalized for implementation, not a claim that production rollout gates have passed. Known source defects remain visible and can block safe scopes.

## User Stories

1. As a liquidity operator, I want inclusive start/end dates, so that I can inspect source balances for a business interval.
2. As a liquidity operator, I want the same date semantics with and without `--live`, so that online and cached results can be compared correctly.
3. As a liquidity operator, I want online inquiries not to write cache, so that publication remains intentional.
4. As a liquidity operator, I want explicit dated refresh, so that I can subsequently analyze those observations offline.
5. As a liquidity operator, I want no-date queries to retain latest-snapshot behavior, so that existing current-balance workflows continue working.
6. As a liquidity operator, I want daily historical output clearly distinguished from current/available/opening snapshots, so that unavailable historical fields are not fabricated.
7. As a liquidity operator, I want `--all` to expand the entity directory, so that I do not manually repeat dozens of identifiers.
8. As a liquidity operator, I want explicit entity arguments to remain native `instId`s, so that display codes are not sent as request identities.
9. As an existing caller, I want `--all --entity <instId>` to remain scoped, so that display-all does not unexpectedly broaden an explicit selection.
10. As a liquidity operator, I want a 100-row latest acquisition default and a page-size override, so that I can avoid unnecessarily small pages.
11. As an automation author, I want unsupported widths and incompatible options rejected before business requests, so that errors are deterministic and actionable.
12. As an offline analyst, I want cached all-entity selection to retain the entity/account set frozen at acquisition, so that cache reads require no browser and do not silently change meaning.
13. As an analyst, I want catalogue gaps and incomplete pagination persisted with warnings, so that partial data remains useful without appearing complete.
14. As a strict caller, I want `--require-complete` to reject incomplete results and publication, so that completeness is an explicit gate.
15. As a liquidity operator, I want scope, identity, authentication and transport failures to preserve existing cache, so that invalid acquisitions do not overwrite usable data.
16. As an analyst, I want amounts, source dates and unknown timezones preserved, so that capture freshness or formatting is not mistaken for business evidence.
17. As a maintainer, I want describe/help and refresh hints to expose the two contracts and option meanings, so that agents can select the correct inquiry safely.
18. As a maintainer, I want bounded whole-command acquisition, so that all entities and long date windows cannot create unbounded request fan-out.

## Implementation Decisions

### CLI and variant resolution

- Reuse the peer liquidity plugin, existing contract variants, source scope normalization, inquiry session, shared transport, acquisition evidence and capture store. No new browser stack, arbitrary HTTP or JavaScript command.
- Both date bounds are optional together; either alone is a usage error. Prefer ISO `YYYY-MM-DD`; accept existing compact `YYYYMMDD` compatibility. Reject invalid dates and reversed intervals before source access. Equal bounds select one day. Use only canonical `--from-date` / `--to-date` for this new feature; do not add legacy aliases that never existed on this leaf.
- Resolve date versus latest mode before defaults and endpoint construction. Keep the historical variants separate even when the requested interval contains today.
- Keep existing no-flag default entity behavior. Explicit entity IDs are nonempty opaque native IDs, deduplicated and sorted for stable scope construction, never mapped from `instCode` implicitly.
- For latest list: unscoped `--all` now means all maintained entities plus all display rows; explicit entities keep selection fixed. Preserve the existing `--all` conflict with explicit `--limit` / `--offset`. The help and release note must name this intentional broadening of previously unscoped `--all`.
- For refresh: `--all` with no explicit entity expands entities; with explicit entities it retains them. Refresh continues to acquire the full selected source set and has no display limit.
- Explicit latest `--page-size` is acquisition-only, accepted on `--live` and refresh. Reject it on cache-only reads instead of pretending to repaginate a stored dataset. Validate integer range 1–100; default 100. The wire width must drive every rowStart increment and collector limit calculation; do not change only the initial body.
- Reject an explicit `--page-size` in dated mode. The entity/account reference contracts retain their separately verified widths of 5000.
- Latest mode retains its verified timezone selector. Daily mode has no verified timezone request field: do not send the implicit latest default, and reject an explicitly supplied timezone for daily mode. Describe the source daily timezone as unknown. Do not reinterpret daily calendar dates as UTC/GMT+08 instants.

### Latest contract and all-entity selection

- Preserve POST `/latestBalanceQuery.json`, JSON fields `tntInstId`, `entitys`, `timeZone`, `rowStart`, `pageSize`, and optional `aliasNames`. Preserve success/rows/total parsing and latest field projection.
- Discover all entities through the existing GET `/entityMaintQuery.json` inquiry. Freeze the distinct native `instId` set once per online acquisition. Reject malformed/missing identities and never replace failed discovery with the old default entity or an empty-array request. A proven complete empty directory may produce a complete empty result without a balance request.
- Use the native combined ID-array request; no unproven ALL sentinel or automatic singleton fan-out. Return scope metadata that distinguishes explicit selection from all-directory selection and records the resolved ID set and catalogue provenance.
- Check every returned latest row's nonempty `entity` against the frozen request set before accepting it. An out-of-scope row is a hard scope failure, not safe partial data and not permission to rewrite its entity from an account catalogue.
- Keep stable reported-total, typed identity, duplicate/conflict and convergence checks. Larger pages do not imply complete data. Do not silently deduplicate 399 arrivals to 396 rows and label them complete.
- All-entity latest acquisition uses one explicit **1800-second** leaf-specific shared deadline, because the observed 28-page width-100 combined scope is likely to exceed the ordinary 900-second budget. Individual request timeouts and the existing 1000-page guard stay bounded. Other leaves and explicit selected-entity latest acquisitions keep their existing budgets. No per-page deadline reset or general retry/fallback framework. Full-scope UAT must prove this budget is suitable before rollout; failure remains actionable and preserves cache.

### Daily contract and account binding

- Add only the verified native daily inquiry: POST `/balStatisticalQuery.json`, JSON body with fixed `tntInstId`, `balanceType=day`, selected `aliasNames`, inclusive compact `queryStartDate` and `queryDate`. Never add latest paging/entity/timezone keys to this endpoint.
- Resolve selected entities to accounts through the existing cash-account inquiry, using `instId`, `aliasName` and `currency`. Optional explicit account aliases intersect that selection. Freeze this mapping once; do not derive entity/currency from alias naming conventions or native chart `id`.
- Acquire reference dependencies online for live/refresh; do not trust unrelated cached catalogues as proof of current online selection. Dependency reads are inquiry-only and do not publish dependency caches implicitly.
- Validate alias-to-entity/currency mapping is unambiguous. Missing mapping, conflicting mapping or returned unrequested aliases fail rather than assigning guessed labels. Accounts outside the frozen selected entity set are excluded explicitly; metadata counts them rather than broadening the entity universe.
- The row array is top-level `data` under top-level `success`. Preserve native `id`, `data`, `statisticalDate` and `balance`; add clearly labelled `aliasName`, `entity` and `currency` from the request binding. Native `data` must echo a selected alias and `statisticalDate` must be a valid calendar day inside the requested chunk.
- Identify daily records by entity, alias, currency and statistical date within tenant/contract scope. Native `id` repeats across dates and is retained as a source attribute, not the daily identity.
- Daily output/table uses source daily `balance`, not inferred `curBalance`, `avlBalance`, opening/closing values or equivalent-currency amounts. Preserve decimal text, null/empty/zero distinctions and existing monetary validation; never divide by 100 or fabricate zero rows for absent days.
- Entity/currency labels describe the frozen current account-directory binding, not proven historical ownership. This mode covers daily source observations for the selected discoverable accounts; it does not promise every deleted historical account.
- Native daily requests are single-response inquiries with no reported total. Initially chunk at most **30 aliases × seven inclusive days**, using disjoint alias/date partitions and the same native request shape. These are verified operational chunk sizes, not claimed native maxima. Empty chunks are valid empty responses, not dense zero-filled histories.
- Keep one aggregate 900-second daily acquisition deadline and at most 1000 native daily chunks, plus bounded dependency queries. Plan chunk count before daily requests; reject an over-budget planned scope with an actionable instruction to reduce the date window/account selection. Do not reset the deadline per chunk, silently truncate a requested range, or claim arbitrary year-to-date scale.
- Completeness covers successful execution of every planned source chunk and inherited catalogue quality, not a guessed aliases-times-days row count. Conflicting duplicate daily identities fail; known missing accounts, incomplete dependencies or missing requested chunks retain truthful incomplete evidence.

### Cache and result policy

- Keep latest retained-history captures and new business-dated captures in independent contract/schema scopes. Daily series time is `statisticalDate`. Old latest captures cannot satisfy a daily business-date request; do not delete or relabel them.
- Scope includes tenant, kind, endpoint/variant/schema, entity selection mode, account filters and applicable timezone semantics. Normalize explicit ID arrays; page size, display limit/offset and chunk layout are execution details, not distinct business scopes.
- Persist each capture's frozen entity/account manifest, observation times and dependency quality. All-directory captures use a stable selection-mode lookup, with their actual resolved manifest retained alongside coverage. Offline ALL reads use the matched capture's manifest, never current online discovery or a silently changed reference cache. Do not stitch different manifests to claim one complete entity universe; a metadata-only difference in fetch time need not create a different universe when entity/account bindings are identical.
- Apply current usable-incomplete behavior uniformly: validated partial default live/cache/refresh can succeed with warnings and `complete=false`; strict mode refuses data/publication. Catalogue 3710/3711 stays incomplete even if daily response chunks all succeed. Do not revert to the older complete-only refresh policy.
- Hard auth, transport, malformed response, source scope or identity-conflict failures remain failures with no publication. A successful combined latest request does not authorize unsafe singleton responses.
- Refresh publishes the balance capture and its selection/dependency evidence atomically. Same-acquisition cached output must equal the acquired validated records after the existing documented projection; do not assert equivalence against a later online request that can observe changed balances.
- Keep existing retention, freshness, snapshot selectors and cache quality behavior. Capture time remains different from source business date. Missing/evicted windows do not trigger network access or get filled from latest snapshots.

## Testing Decisions

- Use the **existing public CLI with fake CDP responses and a temporary cache** as the primary acceptance seam. Cover list, refresh, cache reads, help and describe through that seam. Add focused allowlist tests where unsafe request rejection cannot be asserted cleanly through the public CLI; do not create a separate injectable client framework.
- Prior art: existing liquidity cash/forecast CLI SIT, date normalization/aliases SIT, single-response inquiry tests and usable-incomplete/dated-cache regressions. Test externally visible behavior and native requests, not private call ordering or helper structure except where endpoint sequencing is itself part of the inquiry contract.
- Verify online and offline identical date semantics, both inclusive bounds and equal-day queries, ISO/compact normalization, one-bound errors, malformed dates, reversed intervals and no fallback to latest/capture-time filtering.
- Verify mode-specific response schemas, endpoint/body allowlisting, absence of fabricated paging/timezone keys in daily requests, and rejection of export, mutation, unknown fields and arbitrary endpoints.
- Verify explicit entity IDs, unscoped ALL, explicit entities plus display ALL, default legacy scope, directory deduplication, complete empty directory, failed/malformed directory, account intersection, ambiguous mapping and the corrected instId-versus-instCode distinction.
- Verify offline mode makes zero browser/catalogue/network calls even when Chrome is absent. Test a changed reference cache cannot reinterpret a retained ALL capture, and changed manifests cannot be stitched into false complete coverage.
- Verify page-size default 100, accepted overrides, invalid/noninteger/out-of-range values, cache-only and daily incompatibilities, unchanged other leaves, offset stepping by the effective width, short final page, changed totals, empty nonconvergent pages, duplicate arrivals and conflicting identities.
- Include sanitized regression fixtures for the observed 399-arrival/396-identity gap and out-of-scope singleton row. Scope inconsistency is a hard failure; missing coverage alone follows default/strict partial policy. Never use raw production identifiers in fixtures.
- Verify daily alias/date chunk boundaries do not overlap, larger intervals split correctly, repeated native IDs across dates are valid, valid empty responses remain empty, returned aliases/dates remain scoped, and failed chunks do not produce false coverage or a partial publication after hard failure.
- Verify dependency incompleteness, selection provenance, strict no-publication and old-cache preservation, quality persistence across offline reads, daily/latest isolation, dated retention, and no dense zero inference.
- Verify aggregate deadline/chunk/page guards are not reset and over-budget scope errors are actionable. No acceptance claim for an arbitrary maximum-size historical range.
- Run focused SIT, repository pytest/Ruff gates required for implementation, and document validation. This design-only task changes no runtime code.
- Before enabling new behavior, run inquiry-only production CLI UAT for full latest ALL at width 100, an explicitly scoped latest positive/empty range, daily positive/nonzero/empty windows, batch-versus-singleton content comparison, an entity-wide daily window, strict/default known catalogue incompleteness, explicit refresh and browser-disconnected cached equivalence. Record exact scope, effective width/chunking, counts, quality, elapsed time and whether publication occurred. Known hard failures must remain blocked; do not mark them passed just because source requests returned HTTP 200.

## Out of Scope

- Server export/download workflows, including `/dayEndBalanceExport.json`; mutation/approval/refreshing backend business state.
- Full historical current/available/opening/converted snapshot fields, intraday history and inferred daily balance type.
- A historical/deleted-account membership service, historical ownership reconstruction or a global archival completeness promise.
- Fixing source pagination, incorrect entity echoes or missing catalogue records by guessing, dropping records or rewriting source identities.
- Other liquidity/payment/collection leaves, generic page-size fallback/retry frameworks, parallel browser pools, global timeout changes and ledger issue #144.
- Unbounded historical windows, automatic network fallback for cache reads, automatic dependency cache refresh/publication and migration/deletion of old captures.

## Further Notes

Research observation date: 2026-10-12; source baseline commit `0a3c460b191d`. Native source hash: `cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`.

Current evidence:

- Entity directory: 71/71 unique native instIds.
- All-entity latest width 100: two non-overlapping 100-row pages, fixed reported total 2787. Full scan not performed.
- Positive latest width 100: 399 arrivals, only 396 unique identities, and one inconsistent out-of-scope entity echo. This is **not** passed strict UAT and may block that selected scope independently of the page-size change.
- Widths 50 and 100 succeed; 500/1000/5000 are rejected on the exercised latest contract. The rejection text claims maximum 30 but 31/50/100 succeeded; do not document that text as a proven hard cap. User-reported success at 500 was not reproduced for this request shape.
- Daily inquiry: two 30-account/seven-day runs each returned 210 unique alias/day rows with identical content; inclusive endpoints, a nonzero same-day EOD match and a successful old empty window were observed. Native daily value semantics beyond raw `balance` and timezone remain unproven.
- Account catalogue: 3710/3711, still incomplete; 3665 rows belong to the current directory's 71-ID universe, 45 are outside it. Default historical entity-wide acquisition must retain inherited incompleteness; strict mode cannot honestly pass without resolving coverage.

Related: liquidity scope tracking #72, native cash/forecast #76, usable-incomplete #78 and canonical date options #127. This work changes the old fixed page-width/latest-only design through a separately qualified dated variant, while respecting independent capture profiles and current partial-result policy. It does not reinterpret the historical claim that `--as-of` selects retained captures.
