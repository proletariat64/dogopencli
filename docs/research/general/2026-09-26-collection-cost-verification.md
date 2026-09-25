# Collection transaction-cost implementation verification

Observed: 2026-09-26
Scope: general
Status: snapshot

## Scope and work checklist

[Issue #21](https://github.com/proletariat64/dogopencli/issues/21) is implemented on local branch `feat/21-collection-cost`. This is a follow-on collection milestone, separate from the historical payment-only v0.1.0 scope. No release version is assigned.

- [x] Create and check out the new branch; preserve existing workspace changes.
- [x] Add collection cost list, live list, explicit refresh, offline help and describe.
- [x] Enforce the verified fixed type and request at the shared transport boundary.
- [x] Prove isolated caches, exact values, failure retention and read-only requests with synthetic public CLI tests.
- [x] Diagnose the initial live failure without changing query scope or business state.
- [x] Complete final regression tests and documentation checks after the transport fix.
- [x] Complete live list, temporary local refresh and offline read verification.
- [x] Record the final result in ticket #21.

## Implementation boundaries

The only collection business request is POST `https://iglobalfundcontrol.alipay.com/api/fundCost/query.json` with `costTypeCode=FUND_IN_CHANNEL_TRANS_FEE`, `pageNo=0` and `pageSize=1000`. Unknown endpoints, actions, domain filters, missing fixed values and other cost types are rejected before browser access. Existing payment request behavior is preserved.

Collection uses the shared cost envelope parser and existing cache/output paths. The collection parser additionally requires exact page metadata, a nonnegative total within the observed capacity, unique nonempty string identifiers and a row count equal to the total. Duplicate/conflicting identifiers, larger totals and truncation fail without changing page size or publishing partial results. Only a successful zero total may omit the list; null remains invalid.

Default reads are offline. Live queries do not publish or serve stale cache as fallback. Explicit refresh atomically replaces only the collection namespace after complete validation. Rate structures, exact decimal values and unknown fields remain intact; no actual fee calculation is offered. Schema annotations distinguish observed structure from verified requirements and unknown business meaning.

VA fees, pool/physical-account queries, rules, SLA, signing and orders remain excluded. Pool/account discovery is stopped at the user's request.

## Page-readiness failure and regression

The existing authentication probe succeeded on the dedicated headless Chrome at port 9222. Public collection live queries nevertheless failed with `TIMEOUT`. Sanitized diagnostic classification showed an in-page `SecurityError` while accessing the cookie, before the business fetch. No cookie value or raw exception payload was recorded.

Inspection found that the shared query transport opened a fresh target and evaluated the query immediately, without waiting for that target to finish navigation. A successful separate authentication probe cannot establish readiness of a new target. The regression reproduces this with initial blank/loading states and asserts that no business fetch occurs before two stable ready samples.

The fix explicitly navigates the owned query target and reuses the existing bounded settle primitive before fetching. Login landings return `AUTH_REQUIRED`; unverified origins are rejected. Browser startup, login automation, endpoint scope and retry limits are unchanged. Tests also assert that redirect cases send no business request and that owned targets close. Existing test doubles now model fresh navigation state per target and implement the navigation/readiness steps. The deadline regression accounts for target creation, session setup, navigation and readiness within one request budget; the dead-session regression still proves cleanup and retry with a new target.

## Verification method and limits

Synthetic SIT uses the public CLI, fake CDP, formal parser, shared transport restrictions and real temporary SQLite caches. Production verification uses the existing dedicated browser and a private temporary cache under ignored `tmp/`; it captures command output in memory and reports only counts, quality flags and error codes. The temporary cache is removed after each attempt. No production records, account values or credentials enter this report or fixtures.

Before the readiness fix, the full suite passed 571 tests and 23 subtests; help catalog expectations were updated for the new collection group. Final post-fix results are recorded below when complete. Production auth/permission failures and interruption behavior are synthetic tests, not deliberately induced live failures.

Code-review-graph was refreshed for this branch and compared with the actual default branch, `master`. Its current index covers tracked files; new untracked collection modules and SIT tests were inspected directly, so graph test-gap warnings alone do not represent final test coverage.

## Production result

After the readiness fix, the unmodified public command path passed all three UAT steps:

| Step | Observation |
| --- | --- |
| `collection cost list --live --all` | 556 rows, 556 unique identifiers, all fixed collection type, complete=true; no cache file created |
| `refresh collection cost` | Complete snapshot of 556 rows published to a private temporary cache |
| `collection cost list --all --require-fresh --require-complete` | 556 cached rows, complete=true, stale=false; browser access was disabled at the inquiry seam |
| Cleanup | Temporary cache and its temporary configuration removed |

These counts are observations, not test constants. The public CLI used the existing authenticated session; no production business state changed. No persistent user configuration was edited.

## Final local checks

- Full suite: **574 passed, 23 subtests passed** after all readiness and test-double changes.
- Ruff check and format check: passed (108 Python files formatted).
- Documentation guard: passed; all nine documentation-guard tests passed.
- `git diff --check`: passed.
- Branch remains `feat/21-collection-cost`; no commit, push, PR or release was created. Existing unrelated `uv.lock` changes were left intact.

The current commands require `[sources.collection_cost]` with `kind = "cdp"` in the user's configuration; UAT supplied this only through temporary configuration.

后续全参数验收：见 [84 个 CLI UAT 用例](2026-09-26-collection-cost-argument-uat.md)，覆盖全部公开选项及其边界，不再将最初三项验收视为全参数覆盖。
