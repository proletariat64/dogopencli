# Collection network configuration argument UAT

Observed: 2026-09-27
Scope: general
Status: snapshot

Implements [#41](https://github.com/proletariat64/dogopencli/issues/41) and
[#45](https://github.com/proletariat64/dogopencli/issues/45); acceptance tickets
[#44](https://github.com/proletariat64/dogopencli/issues/44) and
[#48](https://github.com/proletariat64/dogopencli/issues/48).
Contracts: [clearing system](2026-09-27-collection-clearing-system-contract.md)
and [card template](2026-09-27-collection-card-template-contract.md).

## Method and result

Public CLI entry point exercised against the existing authenticated headless
Chrome on CDP 9222. Only the two verified list inquiries were executed.
An isolated mode-0700 temporary directory held the private configuration and
cache; no raw production rows or filter values are recorded in this report.
The operator cache SHA-256 stayed unchanged. Live inquiries did not change
the private cache. Temporary contract-probe targets were closed.

Both capabilities passed: 230 clearing-system rows and 152 card-template
rows, each with unique nonempty string IDs. IDs agreed between refresh and
the full live query; no observed identity drift. Counts describe this run,
not future invariants or a backend snapshot-isolation guarantee.
The UAT runner completed 595 assertions, including CLI exit/output checks;
these are assertions, not 595 distinct business scenarios.

## Every argument

Each domain filter below passed cached positive/nonmatch, case change,
literal star/suffixed star, surrounding whitespace without normalization,
repeated-value OR, empty/whitespace-only rejection, and a positive live query.
Cross-field AND was checked before the display window. Live output was checked
against its predicate; controlled fake-CDP tests prove exact cache/live equality.

| Command | Argument | Raw field | UAT |
| --- | --- | --- | --- |
| clearing-system list | `--bank-location` | `supportedCountry` | Pass |
| clearing-system list | `--currency` | `supportedCurrency` | Pass |
| clearing-system list | `--system-type` | `clearingNetworkType` | Pass |
| clearing-system list | `--system-name` | `clearingNetworkId` | Pass |
| clearing-system list | `--status` | `status` | Pass |
| card-template list | `--bank-location` | `supportedCountry` | Pass |
| card-template list | `--currency` | `supportedCurrency` | Pass |
| card-template list | `--bank` | `supportedFinancialInst` | Pass |
| card-template list | `--template-name` | `templateName` | Pass |
| card-template list | `--template-id` | `id` | Pass |
| card-template list | `--status` | `status` | Pass |

The eight common arguments were each tested on both commands (13 clearing
arguments, 14 card-template arguments). Inventory came from machine help and
was checked for exact agreement, including absence of deferred arguments.

| Argument | Evidence on each command | Result |
| --- | --- | --- |
| `--limit` | Default 100, one row, final short window; zero/negative reject | Pass |
| `--offset` | Default zero, last row, beyond-end empty; negative rejects | Pass |
| `--all` | All rows, lexical ID ordering; limit/offset conflicts reject | Pass |
| `--live` | Complete scope and each domain filter, no cache publication | Pass |
| `--require-fresh` | Fresh success; private cache timestamp changed to stale, ordinary read allowed and strict read rejected | Pass |
| `--require-complete` | Complete success; private cache completeness flag changed, strict read rejected | Pass |
| `--format` | JSON/table, projection in each; unknown format rejects | Pass |
| `--fields` | One/multiple/unknown fields and nested field; metadata preserved; empty projection rejects | Pass |

All new group/list/refresh/describe paths passed JSON/text help and both
`--help`/`-h` aliases. Group navigation and offline describe passed.
Each refresh published the unfiltered complete private snapshot and rejected
selectors, display flags and positional extras. Missing cache, unknown flags,
deferred warning-state and unsupported profile globals failed explicitly.
Freshness/completeness injections were restored after each check.

## Controlled SIT boundary

`tests/integration/test_collection_network_config_sit.py` exercises the public
CLI with fake CDP responses. It covers both independent capabilities and cache
namespaces, every filter, missing/null/zero/empty/unknown nested values, string
IDs with leading zeros, controlled cache/live agreement and output metadata.

| Acceptance area | Named SIT evidence |
| --- | --- |
| Refresh/offline/live, all domain filters | `test_refresh_then_offline_list`, `test_local_filters_all_args_and_live` |
| AND before window/projection, raw values | `test_filters_before_window_and_projection`, `test_formats_and_fields` |
| Limits, offsets, all and conflicts | `test_windowing_defaults_boundaries_and_conflicts` |
| Freshness/completeness and source isolation | `test_freshness_and_completeness_requirements`, `test_namespaces_are_isolated` |
| Every help path and describe | `test_help_inventory_and_navigation`, `test_describe_offline_schema` |
| Empty/full capacity and malformed coverage | `test_full_scope_boundaries`, `test_zeroed_empty_echo_is_supported`, `test_bad_acquisition_preserves_snapshot` |
| Authentication and business refusal | `test_live_auth_failures_map_to_auth_required`, `test_business_refusal_preserves_snapshot` |
| Lock, interruption, timeout | `test_refresh_lock_contention_maps_to_locked`, `test_interrupted_acquisition_preserves_snapshot`, `test_timeout_preserves_previous_snapshot` |
| Browser, transport and sanitized errors | `test_browser_unavailable_and_cache_miss`, `test_transport_restrictions`, `test_non_json_response_and_token_hygiene` |

Failure coverage includes refusal, malformed/non-JSON envelopes, invalid rows,
duplicate IDs, inconsistent totals, overflow, page echo mismatch, explicit
empty success (page 0 or 1), an exact 1000-row page, HTTP/auth/redirect errors,
transport allowlists, timeout, lock, interruption and browser unavailability.
Refresh failures retain the previous snapshot; live failures never publish.
Only synthetic fixtures simulate those failures: production UAT did not change
business configuration, invalidate authentication or induce server failures.

There is no multi-page acquisition or mutable-total policy to test here:
requests allow only page 1 at size 1000 and fail on incomplete coverage.
The real small-page duplicate/clamp behavior is documented in the contracts.
Successful unfiltered empty production scope was not available; its explicit
envelope acceptance is conservative and covered by SIT. Card-template nested
item arrays were empty in production; nonempty preservation uses synthetic data.

## Verification

Focused implementation tests: 117 passed. Catalog/help regression: 111 passed.
New capability/schema modules pass `ty`; checking the existing CLI reports
25 diagnostics, identical in count and locations to the implementation baseline
`27c6653` (with line shifts only). No repository typecheck gate was configured.
Final full suite: 944 passed, 23 subtests passed in 555.57 seconds. Ruff lint
and formatting passed; doc guard passed across 49 Markdown files; Git whitespace
checks passed. The full suite ran once after implementation; no test was skipped
to accommodate this feature.

The wheel and sdist built successfully at the existing version 0.1.8 (no release
or version bump requested). The wheel was installed into a fresh isolated Python
3.13 environment outside the checkout; both commands passed exact option
inventory, describe and offline full-scope reads from the private UAT cache.

Independent code-review axes against the implementation baseline: Standards
0 actionable findings; Spec 0 actionable findings. The reviewers assessed the
implementation against frozen #41/#45; runtime UAT and repository gates are
separate evidence, not assertions supplied by those reviews.
