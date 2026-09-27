# Account-isolation review follow-up

Observed: 2026-09-27
Scope: general
Status: snapshot

## Findings and decisions

- Kimi duplication finding: extracted the five identical acquisition, filtering,
  sorting and identity methods into `ConfigurationListCapability`. Each concrete
  capability retains its own endpoint contract and response parser. Page origin,
  size, rejection messages and local matching behavior are preserved.
- Kimi naming finding: renamed shared CLI helpers to `_collection_config_cached`
  and `_list_collection_config` so names cover all three callers.
- [Greptile empty-response finding](https://github.com/proletariat64/dogopencli/pull/53#discussion_r4112797947):
  valid. Null-list/all-zero metadata was observed only with backend filters.
  Unfiltered refresh/live now reject it as INVALID_RESPONSE without publication
  or fallback. This corrects the original frozen empty rule. Properly echoed
  empty arrays remain accepted; unfiltered emptiness is still synthetic-only.
- [Greptile diagnostic finding](https://github.com/proletariat64/dogopencli/pull/53#discussion_r4112797948):
  valid. Shared cache and incomplete-live errors now name the actual capability.
- PR #35 was inspected separately. Its misleading VA-rule refresh documentation
  is already corrected in `va_rule_reading.py`; refused detail acquisition may
  publish a partial snapshot. Its O(n) single-ID cache validation suggestion is
  nonblocking and deferred: changing VA-rule cache validation is outside #53.
- The #52 blocker report remains because the requested work explicitly covered
  both #51 and #52. No bank-account VA command is introduced. ADR status was
  added while updating the empty-response decision; unrelated formatting nits
  and historical AGENTS scope drift remain outside this change.

## Verification

Before structural edits, both configuration SIT files passed 172 cases.
Six new cases failed against the old behavior: four null/zero combinations
(live/refresh, cold/populated cache) and two corrupted-cache diagnostics.
The cases exercise the public CLI, fake CDP and real temporary SQLite.

Post-change validation:

- Both configuration SIT files: 177 passed in 180.40s (60 account-isolation
  cases and 117 network-configuration cases). All six regression cases passed.
- Request-allowlist test rerun after canonical page-body cleanup: passed.
- Ruff lint and formatting, affected capability module type checks: passed.
- Documentation guard (56 Markdown files) and its 9 tests: passed.
- Isolated installed-wheel smoke: all three configuration capabilities and
  offline help/describe passed.
- Graph refreshed with the new shared module (97 source/test files), then
  changes analyzed against default branch master. Static test-link gaps were
  checked against the public-CLI SIT coverage above.

The earlier 1007-test full suite and 315-assertion production UAT predate this
review follow-up; production was not queried again for this correction.
