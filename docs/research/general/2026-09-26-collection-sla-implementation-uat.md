# Collection SLA implementation and acceptance

Observed: 2026-09-26
Scope: general
Status: snapshot

Specification: [#27](https://github.com/proletariat64/dogopencli/issues/27). Tickets: [#28](https://github.com/proletariat64/dogopencli/issues/28) → [#29](https://github.com/proletariat64/dogopencli/issues/29). Draft PR: [#30](https://github.com/proletariat64/dogopencli/pull/30).

## Work plan

- [x] Create isolated PR branch and draft PR; preserve master and prior research.
- [x] Recheck native production list/detail inquiry contract on dedicated CDP 9222.
- [ ] Implement #28 in its own worktree; merge reviewed commit to PR branch.
- [ ] Verify #28 core through public CLI and read-only production queries.
- [ ] Implement #29 in its own worktree after #28; merge to PR branch.
- [ ] Reconcile every exposed argument with public-CLI SIT and read-only UAT evidence.
- [ ] Run required gates and full suite, perform standards/spec review, fix findings.
- [ ] Update PR description, mark ready only when acceptance complete, clean implementer worktrees.

## Boundaries

Production business operations remain inquiry-only. Browser port 9222 only; never 9330–9340, including tests. Native Search and Details plus their verified query requests are allowed; no business create/edit/approve/delete/sync or data upload. Production rows and credentials remain out of artifacts and logs. UAT uses a temporary local cache and existing records; only sanitized outcomes are retained. Incomplete or blocked cases are not passes.

## Evidence

Current read-only recheck used native Search on the observed collection SLA page: HTTP 200, success=true, pageNo=0/pageSize=10, totalCount=55. A verified unfiltered pageNo=0/pageSize=1000 replay returned 55 rows, 55 unique nonempty string slaConfigId values, matching totalCount.

Native Details navigated to the observed `/receivedPayment/sla/fundInSla/view` route. With unrelated bootstrap calls intentionally blocked, no automatic detail response was captured before explicit replay. Replaying the historically native-verified exact detail endpoint for one current list ID returned HTTP 200, success=true and a nonempty resultData whose ID and all shared fields matched the list. The list-only viewProcessInstanceRequired difference remains. This sample is a contract recheck, not all-detail implementation UAT. No business writes or raw response artifacts were produced.

Historical contract: [collection SLA research](2026-09-23-collection-sla-query.md).
