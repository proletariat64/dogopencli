# Unified incomplete policy: current source evidence

Observed: 2026-10-03
Scope: general
Status: snapshot

Core, Payment, Collection and PTR collectors, shared cache; offline source inspection only. This supplements the earlier acquisition-compatibility report and the unified-incomplete specification. Statements below distinguish current behavior from recommendations; no production observations are claimed.

## Evidence boundary

`code-review-graph` was called first with the exact current worktree root. Its statistics reported zero indexed files/nodes/edges and `last_updated=null`; its `file_summary` query explicitly warned that an empty graph cannot establish relationships. Read-only research rules prohibit graph rebuilding. Known source paths from the previous report were inspected directly; this is targeted source evidence, not graph coverage or an exhaustive architectural analysis. No code changes or test execution were performed for this research note.

The previous report's “single-response duplicate arrivals are deduplicated to complete” finding is already addressed in this source snapshot: `src/dogopencli/plugins/liquidity/collect.py:162-169` checks both raw rows and unique rows against a reported total. `tests/integration/test_liquidity_partial_regressions.py:117-139` already covers duplicate arrivals for reported totals 1 and 2. Keep regression coverage; do not describe this as an outstanding implementation defect.

## Current collector behavior

| Contract | Current source evidence | Migration implication |
| --- | --- | --- |
| Core fixed totals | `src/dogopencli/collect.py:152-177` verifies row scope and pagination echo; `:183-204` rejects changing totals, budgets and early empty pages; `:205-240` deduplicates identical identity/content, rejects conflicting identity content, and requires consistency plus raw arrivals = reported total = unique rows. | Coverage shortage can become usable partial evidence. Scope, schema, identity conflict and transport failures remain separately typed failures. |
| Independent rebuild | `src/dogopencli/collect.py:88-120` makes one independently collected replacement candidate with the original deadline. `src/dogopencli/plugins/payment/cost.py:39-60` and `src/dogopencli/plugins/payment/sla.py:44-63` declare their verified larger page size; `tests/integration/test_cost_cli_sit.py:605-625` proves that a new candidate may have a different total. | Preserve declared sizes and independent candidates; no cross-attempt concatenation or cache hole filling. |
| Collection cost | `src/dogopencli/plugins/collection/cost.py:34-47` fixes pageNo=0/pageSize=1000; `:84-101` raises INCOMPLETE_RESULT inside parsing for excess total, missing rows or duplicate identities. | Publishing validated partial candidates requires separating coverage evidence from parser failure. Preserve fixed request restrictions and shape checks; no Payment 10000 fallback. |
| VA capacity | `src/dogopencli/plugins/collection/va_capacity.py:40-52` declares running totals; `src/dogopencli/collect.py:178-182,230-240` waits for a short page and evaluates the final total. | Do not impose fixed-total equality across intermediate pages; a converged deficit remains an incomplete cause. |
| PTR cases | `src/dogopencli/plugins/payment/ptr.py:224-234` requires bounded unique single-page coverage. `:238-270` performs two independently complete reads, compares total and complete normalized content, and shares the remaining deadline. Registry wiring is `src/dogopencli/plugins/__init__.py:313-329`. | Count equality alone cannot replace a required stability proof. Drift is distinct from a small coverage shortage. |
| PTR orders | `src/dogopencli/plugins/payment/ptr_orders.py:282-302` fixes the padded native request at page size 500; `:357-374` proves the entire padded acquisition stable before trimming to the public half-open window. | Do not trim first and hide padding drift. Existing parsers require changes if a future policy admits partial PTR coverage; ordinary exception swallowing cannot establish safety. |
| Liquidity overlap | `src/dogopencli/plugins/liquidity/collect.py:46-65,122-139` collapses identical native identities and rejects conflicts, but marks complete only when arrivals = reported total = unique count. `tests/unit/plugins/liquidity/test_collect.py:89-99` exercises 12 arrivals / 11 unique / reported total 12. | Deduplication cleans returned rows; it does not recreate the missing twelfth identity. This example must stay incomplete even if publication becomes permitted. |

## Cache publication and reads

`src/dogopencli/cache.py:264-325` publishes metadata and records in one SQLite transaction and rolls back failures. It stores `backend_complete` and `dataset_complete` rather than inherently requiring true. Current refusal to publish partial candidates comes from callers: for example `src/dogopencli/cli.py:477-495` rejects incomplete costs and hardcodes complete metadata afterward. A policy migration must remove that caller gate and persist the actual quality flag together with its reasons.

`src/dogopencli/cached_query.py:75-79` validates stored record count against snapshot `row_count` and uniqueness. Therefore partial snapshot `row_count` must be actual stored rows. Preserve the backend reported total in separate quality evidence; setting row_count to reported_total would make a valid partial snapshot look corrupt. `:131-136` already lets ordinary incomplete snapshots be read and rejects them only when `require_complete` is requested. `:26-43` exposes the complete flags, but does not persist or expose the reasons for their value.

An existing offline test explicitly demonstrates this distinction: `tests/integration/test_collection_va_capacity_cli_sit.py:496-517` creates synthetic incomplete metadata, proves ordinary reads work, and proves strict reads fail. This is evidence of current cache mechanics, not proof that current refresh publishes incomplete acquisitions.

Missing-detail semantics must remain separate from missing-list coverage. `src/dogopencli/plugins/collection/va_rule_inquiry.py:49-61` refuses to confirm an absent identity in an incomplete list and refuses a missing detail. `:124-145` currently requires complete list coverage and permits only an explicit business-refused detail; `:160-177` then atomically publishes a complete list / incomplete dataset before raising INCOMPLETE_RESULT. A new result object should preserve actual `published=true` and avoid losing that fact in a post-commit exception.

Payment SLA refresh fetches real details for each collected baseline (`src/dogopencli/cli.py:696-719`); Collection SLA validates actual list/detail pairs (`:984-998`). Publishing a partial list does not authorize substituting list rows for details or ignoring detail schema/identity failures.

## Recommendations for the specification

1. Allow validated partial data to be published and queried under the user's new default policy. Persist `complete=false`, structured reasons and counts atomically with the rows; warn on refresh and subsequent cache reads. An explicitly requested completeness gate still rejects before publication or data exposure.
2. Distinguish duplicate observation from coverage shortfall. Record arrivals, unique count, duplicate count, backend total, total semantics, and identity conflicts. Reported total 12 / unique 11 is incomplete with an explainable gap; do not report complete because the duplicate was removed.
3. Complete with a duplicate warning is defensible only where the domain contract proves total counts distinct native identities, unique count equals that total, requested scope and required stability proofs pass, and duplicate content agrees. Current source declares no generic “duplicates are safe complete” rule. Default ambiguous totals or missing proof to incomplete, while still allowing a valid partial result to be useful.
4. Preserve native rows where no verified identity exists. `src/dogopencli/plugins/liquidity/collect.py:158-161` currently preserves such row occurrences; `tests/unit/plugins/liquidity/test_collect.py:262-281` covers identical cashflow rows. Whole-row hashing is not a business identity proof.
5. Do not infer “small missing fraction” from one boolean. Reasons and counts permit downstream AI analysis to make that judgment. Leave no-total ratios unknown; local filtering/windowing must not change acquisition quality.
6. Separate coverage/stability quality from malformed responses, identity conflicts, wrong scope, auth/permission errors and transport/budget failure. Those latter failures do not create a trustworthy partial candidate merely because earlier requests succeeded. Preserve allowlisted inquiry-only requests and atomic publication.

Existing tests are current-behavior evidence, not target acceptance. For example `tests/integration/test_cost_cli_sit.py:456-490` expects ordinary partial live exit 0, whereas `:653-675` expects incomplete refresh rejection and preservation of an old cache. These assertions must change deliberately when the new spec is implemented; their passing today cannot prove the future default policy.
