# Batch F1 wallet membership and wallet balances: evidence chain

Observed: 2026-10-06
Scope: general
Status: snapshot

Evidence record for [issue #116](https://github.com/proletariat64/dogopencli/issues/116) (Batch F F1, parent [#72](https://github.com/proletariat64/dogopencli/issues/72)). The 2026-10-06 CDP probes were completed by the batch investigator on the dedicated CDP 9223 session; this document records the evidence chain and the decision to keep both leaves deferred. No list is enabled, no production CLI UAT was run, and no new probing is part of this change.

## Evidence chain

PRD sources (read-only graphify queries against the knowledge base, then direct source inspection):

- The WF-AB settlement PRD (source P3 in #116) distinguishes Wallet Account from Bank Account and identifies a recipient wallet balance account, but it is a settlement document; it does not bind those objects to Liquidity's wallet menu.
- A historical platform capability baseline (P4) records a wallet-account menu screen; a menu entry supplies no membership predicate or balance observation schema.

Native probes (2026-10-06, dedicated CDP 9223, serial, no mutation):

- The wallet menu's current page (QueryWalletAccount) calls `GET /queryintnalbkactlist.json` with top-level keys `wallet`, `tntInstId` and `bankAccountQueryVO` (a JSON string carrying the native tenant, `rowStart=0` and `pageSize`). The wallet page fixes `wallet=true`; `wallet=false` was queried once as a research control and is not exposed as a CLI variant.
- At `pageSize=1000`, wallet=true and wallet=false each returned 1000 rows with `count=3691`; at `pageSize=5000`, each returned 3690 rows with `count=3691`. Per page width, the ordered raw records are identical between the two flag values, and the native id column held only one distinct value.
- The response envelope is `resultFlag=true` with rows at `result.bankAccountPropertyVOList` and the total at `count`. These fields are observed but cannot be frozen as an executable wallet schema: the flag does not select a distinct wallet population, so wallet membership, row identity and acquisition completeness are all unproven.
- No independent native wallet-balance caller was found, and none is bound to wallet membership.

## Decision

Both leaves stay deferred with named blockers; investigation ending this round is not delivery:

- `liquidity cash wallets list` — `reference`, status `filter-unverified`: wallet=true/false returned identical ordered account rows at pageSize 1000/5000; wallet membership is not established. No wallet filter is exposed on the cash accounts list.
- `liquidity cash wallets get` — `reference`, status `filter-unverified`: wallet membership is not established.
- `liquidity cash wallet-balances list` — `runtimes`, status `unverified`: no verified independent native wallet-balance caller bound to wallet membership. Normal-account balances are not renamed as wallet balances, and no guessed request is registered.

The two leaves release independently. Before either is enabled, the PRD and business owners must confirm how Wallet Account maps to the current Liquidity tenant, with an explainable positive sample or a native membership field; the balance inquiry must be bound to the same membership with verified currency, amount and business observation-time semantics. First release still requires a nonempty schema, native identity, scope/time/amount semantics and a safe request contract, followed by per-leaf serial production CLI UAT.

Prior evidence: [October 1 live probes](2026-10-01-liquidity-live-probes.md) and the [October 2 cash/forecast business probe](2026-10-02-cash-forecast-business-probe.md). The 2026-10-06 page-width-identical full-list comparison supersedes the earlier first-page-only wallet observation; dated observations remain historical evidence.
