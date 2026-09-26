# Collection VA capacity complete argument UAT

Observed: 2026-09-26
Scope: general
Status: snapshot

Complete argument-level acceptance for the collection VA capacity surface
(`collection va capacity list`, `refresh collection va capacity`, help and
describe) closing
[#39](https://github.com/proletariat64/dogopencli/issues/39), against the
specification [#36](https://github.com/proletariat64/dogopencli/issues/36),
the verified contract in
[2026-09-26-collection-va-capacity-contract.md](2026-09-26-collection-va-capacity-contract.md)
and the implementation from
[#38](https://github.com/proletariat64/dogopencli/issues/38). Every accepted
argument is mapped to a named case; deferred filters map to rejection
coverage. Counts are snapshots of the 2026-09-26 production account, not
invariants. No production row values, account or VA identifiers, tokens or
raw responses were persisted; live rows were held in memory only for
counting and identity comparison.

## Method and boundaries

- Dedicated Chrome on CDP **9222** only; `dogopencli auth check` returned
  `authenticated: true, healthy: true` before and after the session. Ports
  9330–9340 untouched. Inquiry-only: one real refresh and read-only list
  calls; no create/edit/allocation/import/export actions.
- Production UAT ran against a **private cache** under `tmp/uat-va-capacity/`
  with its own config; the operator's main cache digest was compared before
  and after and was untouched.
- Failure branches that would require manufacturing production failures
  (authentication loss, malformed envelopes, pagination drift, truncation,
  duplicate identities, interruption, lock contention, timeout, failed
  refresh preserving the old snapshot) are covered by the synthetic SIT
  suite `tests/integration/test_collection_va_capacity_cli_sit.py` (26 test
  functions) and the shared unit tests; those are marked **synthetic**
  below and were not re-executed against production.

## 1. Argument inventory vs help (pass)

- Help JSON for `collection va capacity list` exposes exactly the frozen
  inventory: `--va-rule-id`, `--bank-va-rule-id`, `--limit`, `--offset`,
  `--all`, `--live`, `--require-fresh`, `--require-complete`, `--format`,
  `--fields`. **Pass** — matches #36 exactly; no more, no less.
- `refresh collection va capacity` accepts no options and no positionals.
  **Pass.**
- The deferred `--warning-state` and all other surveyed UI filters
  (`--currency`, `--account-no`, `--verbose`, `--config-dir` as a
  subcommand-local flag) are rejected with exit 2 `INVALID_ARGUMENT`.
  **Pass.**
- Refresh selector rejection: `refresh collection va capacity
  --va-rule-id 1`, `--all` and an extra positional all exit 2
  `INVALID_ARGUMENT`. **Pass.**
- Bare `refresh collection va` keeps its existing rule-refresh behavior and
  now lists `capacity` as a child; verified by SIT (not by an unnecessary
  production rule sweep). **Pass (synthetic).**

## 2. Refresh, offline reads, live no-cache-write (pass)

- Cold private cache: `collection va capacity list` before any refresh fails
  with exit 1 `CACHE_MISS`. **Pass.**
- `refresh collection va capacity`: exit 0, namespace
  `collection.va.capacity.list:capacity:cdp`, 532 rows, complete metadata.
  **Pass.**
- Offline reads from the snapshot: default window returns 100 rows of 532
  with `has_more: true`, `complete: true`, uniform 22-field rows; `--all`
  returns 532 rows, 532 unique `ruleId` identities, sorted by identity.
  **Pass.**
- `--live`: exit 0, `source: live`, `complete: true`, no snapshot id; the
  private cache file digest is unchanged by the live read (no cache
  writes/fallback). **Pass.**
- Live vs cache identity comparison: 532 live vs 532 cached, intersection
  532, zero one-sided identities, zero shared rows with changed fields —
  no production drift occurred between refresh and live read on
  2026-09-26. Drift would be disclosed, not failed. **Pass.**

## 3. Display windows: `--limit` / `--offset` / `--all` (pass)

- Default 100-row window, end window (`--offset` near the total) and
  beyond-end window (empty page, metadata intact) all behave per spec.
  **Pass.**
- `--all` combined with `--limit` or `--offset` exits 2
  `INVALID_ARGUMENT`. **Pass.**
- `--limit 0`, negative `--limit` and negative `--offset` exit 2
  `INVALID_ARGUMENT`. **Pass.**
- Filter-before-window ordering verified: filtered result sets window
  after filtering with unchanged completeness metadata. **Pass.**

## 4. Formats and fields (pass)

- `--format json` (default) and `--format table` both render the snapshot.
  **Pass.**
- `--fields` single field, multiple fields, unknown fields (dropped with
  metadata preserved) and nested-value selection behave per spec. **Pass.**
- `--fields ""` and whitespace-only selections exit 2 `INVALID_ARGUMENT`.
  **Pass.**

## 5. Freshness and completeness (pass, private copies)

- A private copy backdated past the freshness window reads fine by default
  and is rejected by `--require-fresh`. **Pass.**
- A synthetic incomplete snapshot copy is rejected by `--require-complete`
  and readable without it. **Pass (synthetic state on a private copy).**
- The operator's main cache digest was identical before and after all
  read-only queries; unrelated snapshots were not touched. **Pass.**

## 6. Domain filters (pass)

Both accepted filters were exercised against the production snapshot and
live:

- `--va-rule-id` (row field `ruleId`) and `--bank-va-rule-id` (row field
  `bankAccountVaId`): positive match and nonmatch cases return the expected
  sets; nonmatch is an **empty success**, not an error (the server-side
  failure envelope never reaches the user because filtering is local).
  **Pass.**
- Repetition (same-field OR) and cross-field AND behave per spec. **Pass.**
- Case is significant and a literal `*` is not a wildcard for local
  filtering. **Pass.**
- Missing/null fields never match — covered synthetically (all production
  rows carry all 22 fields). **Pass (synthetic).**
- Cached/live agreement: the same positive and nonmatch filters return
  matching result sets from cache and from `--live`. **Pass.**
- Invalid values (empty, whitespace-only) exit 2 `INVALID_ARGUMENT` —
  covered by SIT and inventory rejection cases. **Pass.**

## 7. Navigation, help and describe (pass)

- `dogopencli collection`, `collection va`, `collection va capacity`
  navigation nodes list the new surface. **Pass.**
- `help collection va capacity list` and `help refresh collection va
  capacity` work in JSON and text, as do the `--help`/`-h` aliases.
  **Pass.**
- `describe collection va capacity` returns capability
  `collection.va.capacity.list` with schema and usage guide in JSON and
  text. **Pass.**
- Unknown commands under the new group (`collection va capacity get`)
  exit 2. **Pass.**

## 8. Synthetic failure coverage (pass, SIT only)

Authentication/browser loss, permission refusal, malformed and empty
envelopes, pagination drift, truncation, duplicate identities,
interruption, lock contention, timeout and failed-refresh snapshot
preservation are covered by the 26 SIT functions plus shared unit tests;
the full suite result is recorded under Gates. No production failure was
manufactured and no business write was executed. **Pass (synthetic).**

## 9. Wheel smoke (pass)

- Built `dogopencli-0.1.7` wheel plus the feature code installed into an
  isolated venv; `--version`, help and describe work offline from the
  installed wheel; a missing source configuration fails cleanly with
  `CONFIG_ERROR`. **Pass.**

## 10. Gates (pass)

- `pytest -q`: full suite green (count recorded in the #39 closing
  comment).
- `ruff check .` and `ruff format --check .`: clean.
- `python scripts/doc_guard.py`: PASS including this report's index row.

## #36 acceptance reconciliation

All frozen arguments have evidence above; the deferred `--warning-state`
has rejection evidence; the running-estimate `totalCount`, identity and
empty/failure-envelope boundaries behave as verified in #37. No gap
remains between the #36 acceptance matrix and the shipped surface.
