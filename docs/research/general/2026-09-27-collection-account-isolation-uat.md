# Account-isolation CLI acceptance

Observed: 2026-09-27
Scope: general
Status: snapshot

Issue #51 production UAT passed **315 assertions** on the public CLI, using
99 configuration rows and a private SQLite cache under ignored `tmp/`.
All 16 list options were exercised. Live and refreshed ID sets matched; both
reported complete datasets. The operator cache and WAL hashes were unchanged.
No raw rows, IDs, account values or credentials are included in this report.

## Production method and coverage

The dedicated authenticated headless Chrome used CDP 9222. DI browser
instructions and launcher were read before access. The CLI held its normal
browser coordination lock. The first sandboxed attempt could not touch the
profile lock; UAT was rerun with filesystem permission and then passed.
No production mutations were executed. New targets were closed by normal
session cleanup. Private directories/files were created with umask 0077.

The public CLI was invoked with captured stdout/stderr, retaining rows only
in process memory and the private cache. Every offline inquiry used an
unreachable CDP address (9223), establishing that cached reads/help/describe
do not need the live browser. Every live command checked private-cache hashes
before/after. Raw production output was not logged or committed.

Named UAT cases:

- **Discovery**: exact 16-option inventory, cold-cache CACHE_MISS, help aliases,
  JSON/text help and describe; invalid/conflicting options and refresh selectors.
- **Live scope**: live/all/fresh/complete returns the full scope without publication.
- **Refresh/offline**: complete atomic refresh followed by cached full scope with
  unreachable CDP; unique string identities, lexical order and quality metadata.
- **Display**: default 100-row window, explicit offsets/limits at beginning/end
  and beyond end, all, JSON/table, identity projection and unknown fields.
- **Domain filters**: each field's positive sample, repeated OR, nonmatch, case
  variants, literal star, whitespace, invalid empty values, live predicate and
  combined AND before windowing. Assertions compare against full-snapshot rows.
- **Freshness**: zero-TTL private configuration permits ordinary stale reads and
  rejects require-fresh, then the original private TTL is restored.

## Argument-to-test mapping

SIT file: `tests/integration/test_collection_account_isolation_sit.py`.
All 55 focused cases passed at implementation acceptance.

| Argument | Named public-CLI SIT | Production UAT case |
| --- | --- | --- |
| --opening-rule-id | test_each_filter_is_local_exact_and_live_preserves_cache; test_filter_sort_window_project_and_identity_precision | Domain filters |
| --business-line | test_each_filter_is_local_exact_and_live_preserves_cache | Domain filters |
| --business-region | test_each_filter_is_local_exact_and_live_preserves_cache; test_filter_sort_window_project_and_identity_precision | Domain filters |
| --customer-group | test_each_filter_is_local_exact_and_live_preserves_cache | Domain filters |
| --scene-code | test_each_filter_is_local_exact_and_live_preserves_cache | Domain filters |
| --collection-region | test_each_filter_is_local_exact_and_live_preserves_cache; test_filter_sort_window_project_and_identity_precision | Domain filters |
| --currency | test_each_filter_is_local_exact_and_live_preserves_cache | Domain filters |
| --transaction-type | test_each_filter_is_local_exact_and_live_preserves_cache | Domain filters |
| --limit / --offset / --all | test_common_options_and_help_inventory; test_filter_sort_window_project_and_identity_precision | Display, Live scope |
| --live | test_each_filter_is_local_exact_and_live_preserves_cache; test_bad_acquisition_preserves_old_cache | Live scope, Domain filters |
| --require-fresh | test_freshness_completeness_and_cache_miss | Live scope, Refresh/offline, Freshness |
| --require-complete | test_freshness_completeness_and_cache_miss | Live scope, Refresh/offline |
| --format / --fields | test_common_options_and_help_inventory; test_filter_sort_window_project_and_identity_precision | Display |

## Synthetic-only branches and limits

Production does not cover malformed/refused/auth-expired responses, duplicates,
truncation, more than 1000 records, exactly 1000 records, unfiltered empty scope,
missing optional fields, leading-zero identities, large integer-like strings,
lock contention, timeout or interruption. Named SIT cases cover these without
altering production or authentication: `test_scope_boundaries_and_no_next_page`,
`test_verified_null_zero_empty_replaces_snapshot`,
`test_bad_acquisition_preserves_old_cache`,
`test_invalid_envelope_never_publishes_or_leaks`,
`test_failures_lock_auth_browser_timeout_interrupt`,
`test_request_allowlist_rejects_selectors_mutations_and_pagination` and the
filter/identity cases above. Filter-generated empty results are independently
observed in the [contract](2026-09-27-collection-account-isolation-contract.md).

Backend customerTags/currency filters return broader results. UAT verifies
the documented local whole-string behavior, including commas and literal stars;
it does not claim backend filtering equivalence. Timestamp units/timezone and
closed enum vocabularies remain unverified. Counts are not hardcoded invariants.

## Final regression, packaging and static validation

The final full suite passed **1007 tests and 23 subtests** in 612.97 seconds.
The focused help/catalog/describe regression run passed 157 cases.

An isolated installed wheel (Python 3.13) passed offline help, exact argument
inventory, describe schema and missing-config error checks outside the repository.
New plugin/description modules pass ty. The CLI has 20 existing ty diagnostics,
also reproduced from an isolated master source tree; this change adds none.
Ruff lint/format and documentation guards pass.

Issue #52 is not accepted: the
[bank-account rule completeness blocker](2026-09-27-collection-bank-va-rule-blocker.md)
persists. No bank-va command or partial snapshot is shipped.

## Independent review

Two read-only review agents examined `master...aaf2bf9` independently after
code-review-graph refresh/impact analysis. Standards: 0 actionable findings.
Specification: 0 findings against #51 plus its frozen contract and #52's
explicit completeness gate. The graph covers the new plugin and SIT file;
dynamic CLI test coverage was verified from the tests, not inferred solely
from graph edges.
