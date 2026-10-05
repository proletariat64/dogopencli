# Cash pool balances: implementation and production UAT

Observed: 2026-10-05
Scope: general
Status: snapshot

Specification: [#98](https://github.com/proletariat64/dogopencli/issues/98).
The operator-confirmed [balance semantics](2026-10-05-cash-pool-semantics.md)
and [implementation contract](../../design/liquidity-pool-balances-v0.1.0.md) define
this BANK-only runtime snapshot. Other #98 candidates remain unsupported.

## Implementation and scope

Implementation commit `6c810d2`, integrated as `382f2bd`, adds
`liquidity cash pool-balances list` and explicit refresh, with an independent
capture namespace. Book and available balances remain separate; member original
and bank-equivalent amounts retain their own currencies. Pool totals and dates
are independent source facts. Unknown member observation time and blank currency
remain unknown. No aggregation, conversion or synchronization is inferred.

At the pool-balances delivery checkpoint, the branch had 76 supported and 57 unsupported leaves against the independent
v0.2.6 baseline (75/58). Of four #98 candidates, one is implemented and UAT-passed;
credit usage, product baselines and quotes remain deferred. These branch counts
do not include the separately unmerged #97 work. #98 stays open; no default-branch
merge or version publication is claimed. The subsequent
[credit-usage delivery](2026-10-05-credit-usage-uat.md) records the next #98 slice
and its updated counts separately.

## Production CLI UAT

Eight public CLI commands passed against integration commit `382f2bd` using the
dedicated Liquidity browser. The user completed SSO after an initial authentication
expiry; headless authentication was independently verified before the successful
run. An initial private response-recording wrapper omitted the transport timeout
argument; the wrapper was corrected to forward it unchanged. No product code was
changed to obtain a passing result.

| Check | Result |
| --- | --- |
| Existing pools settings refresh and cached read | Passed; baseline capture established |
| Pool-balances strict refresh | Complete 43/43 pools, 358 nested members |
| Cached balances | Every projected field equals the same native response; typed pool/member identities and parent links match |
| Disconnected cached balances | Same records and fetched_at; browser factory raises if contacted |
| Strict live balances | Native fields and identities match; SQLite database and WAL hashes unchanged |
| Existing pools cached read after balances operations | Same fields, records and fetched_at; no runtime balance fields introduced |
| Offline describe | Passed without browser access |

The native pool dates were 2026-10-05. Book and available balances differed in
four pools and ten members; 98 members had unknown bank currency. These source
states were preserved, not treated as incompleteness. Sensitive responses and
identifiers remain outside Git; this report contains only aggregates and checks.
The fixed BANK scope has no verified production empty-filter variant. Explicit
success-empty protocol is tested through fake CDP, without inventing a filter.

## Local checks and review

197 unique focused tests ultimately passed across grouped runs, with 20 subtests
passing and one skip. This includes 21 new public CLI/fake-CDP/SQLite tests. The
combined run initially had two obsolete registration/date assertions; those were
corrected and the entire affected file (39 tests) passed on rerun. The combined
group and full suite were not rerun. Ruff lint/format and documentation checks
passed. Independent Standards and Spec reviews found no implementation defects;
the production UAT gate identified by Spec review is now satisfied.

After explicit user authorization, local Kimi reviewed commit `79ff75f` with
confidence **4/5** and found no functional or Spec defects. Its two low-severity
findings (a stale contract-count comment and dated documentation-index wording)
are corrected in this follow-up. Kimi did not rerun tests or production UAT.
The user also authorized GitHub publication; the branch is pushed and
[Draft PR #100](https://github.com/proletariat64/dogopencli/pull/100) is open.
Local checks, production UAT, external review, remote checks and release remain
separate evidence; this report does not claim merge or release completion.
