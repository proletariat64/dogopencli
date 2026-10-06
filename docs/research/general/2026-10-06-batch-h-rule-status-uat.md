# Rule-status bounded list CLI production UAT

Observed: 2026-10-06
Scope: general
Status: snapshot

Batch H UAT for `liquidity operations rule-status list`
([#123](https://github.com/proletariat64/dogopencli/issues/123),
spec [#122](https://github.com/proletariat64/dogopencli/issues/122),
acceptance record in `2026-10-06-batch-h-acceptance.md`). The root coordinator
ran the public CLI serially through the healthy, user-authorized dedicated CDP
9222 profile (liquidity SSO re-established on 2026-10-06 via the sanctioned
headed login flow). Inquiry-only; no production schedule or business state was
mutated. No native rows, identifiers, credentials or profiles are recorded
here — aggregates only.

## Preflight

- `auth check --domain liquidity`: exit 0, authenticated, healthy, headless.

## Checks (all per the spec's UAT list)

- **Nonempty expanded trigger scope** (`2026-01-01 00:00:00` to
  `2026-10-06 23:59:59` UTC): refresh published 194 rows in one counted
  response; offline `list --all --require-complete` returned 194 rows, 194
  unique positive-integer identities, reported_total 194, complete. Observed
  execution states EXECUTED / NON-EXECUTION / PRE_CONDITION_BLOCK; createdOrder
  Y/N; orderStatus empty/PAID; realTriggerTime null in 101 rows, integer
  milliseconds in 93 — matching the 2026-10-06 probe aggregates.
- **Successful empty current-day scope** (`2026-10-06 00:00:00` to
  `2026-10-06 23:59:59`): refresh published 0 rows truthfully; offline list
  reported 0 rows with complete=true under its own snapshot identity,
  distinguishing genuine empty from failure.
- **Equal-endpoint point scope** (from == to at an observed expected-trigger
  second): refresh and offline list returned 11 rows, 11 unique identities,
  complete — equal endpoints accepted and consistent.
- **Live no-write**: `list --live` on the year scope observed 194 arrivals /
  194 unique / reported 194 (default output window 100, has_more); the emitted
  identity window was a subset of the capture; the SQLite cache file sha256
  was byte-identical before and after.
- **Disconnected offline equality**: with the CDP endpoint pointed at an
  unreachable port, offline `list --all` still returned the 194-row capture
  byte-identical (source=cache), proving no browser is needed offline.
- **Failure/cache preservation**: with the same unreachable endpoint, refresh
  exited 1 with BROWSER_UNAVAILABLE and the cache file sha256 was unchanged.

## Result

All UAT checks passed. This establishes the leaf's current verified production
behavior for the exercised scopes only; it does not establish offset pagination
(single bounded response by contract), getters, expanded queryDetailed detail,
or any mutation capability, all of which remain unsupported/out of scope.
