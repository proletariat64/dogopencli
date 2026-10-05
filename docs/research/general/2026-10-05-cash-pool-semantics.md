# Cash pool semantics: business clarification and bank references

Observed: 2026-10-05
Scope: general
Status: snapshot

Related: [issue #98](https://github.com/proletariat64/dogopencli/issues/98).
This is a semantics investigation, not implementation or production CLI UAT.
Public sources describe bank products; they do not validate private API field
names, actual bank configuration, observed dates or completeness of our captures.
No private account names, identifiers or amounts were sent in public searches.

## Current business contract supplied by the user

The user clarified the following on 2026-10-05. These are current product-owner
semantics, not deductions from public bank documents:

| Native concept | Meaning and handling |
| --- | --- |
| Member `currentBalance` / `currency` | Current book account balance in the account currency (corrected by the user). Preserve negative values; they can represent the participant drawing on shared pool funds. |
| Member `currentAviBalance` / `currency` | Currently available account funds for payment. Restrictions such as freezes can reduce availability; do not infer the restriction type or amount from the difference alone. |
| Member `equvCurrentAviBalance` / `bankCurrency` | Bank-converted available funds, distinct from converted book balance. |
| Member `equvCurrentBalance` / `bankCurrency` | Book account balance translated using the bank's conversion into its equivalent/reporting currency. Do not relabel this using `currency`. |
| Member `closeBalance` | Closing balance for the preceding statement day. This need not be the preceding calendar day. |
| `masterAccount` | Identifies the main account for the pool's sweeping arrangement. The user describes end-of-day participant sweeps for the relevant structure. |
| `isShare` | Whether balances are shared for participant funding; `N` does not mean there is no physical concentration or no pool membership. |
| Pool `valueDate` | Date of the pool-level balance. Do not invent a member observation date from it. |
| Pool balance | Separate bank-reported pool-level book and available balances, strongly related to converted participant balances but governed by bank configuration. It is a distinct business measure; do not require equality with a computed member sum. |

The user's final sentence about `isShare=N` was unfinished; no additional
restriction on onward funding or payments is inferred from that fragment.
Preserve native `currentBalance` and `currentAviBalance` separately; the user's
available-balance explanation does not authorize merging two distinct fields.

## Public bank evidence

1. **Citi — physical concentration, notional aggregation and shared liquidity.**
   Citi distinguishes actual automated concentration, whose timing/amount/frequency
   are configurable, from virtual netting of credit and debit balances. It also
   offers sharing of available balances for payment funding. This supports keeping
   sweep behavior and balance sharing separate concepts.
   [Citi Liquidity Management Services](https://services.citi.com/solutions/liquidity-management-services),
   sections Cash Concentration, Notional Pooling and Real-time Liquidity Management.
   Its July 2026 comparison additionally describes preserving entity ownership and
   original currency positions while drawing against a net multi-currency pool.
   [Citi Notional Pooling: Multi and Single-Entity Constructs](https://services.citi.com/content/dam/platforms/public/services-citi-com/doc/liquidity-notional-pooling/Notional-Pooling-Multi-and-Single-Entity-Constructs.pdf),
   page 1.

2. **J.P. Morgan — separate local and equivalent balances; structure-specific sums.**
   The Access guide distinguishes participant-account currency and the FX rate for
   converting that balance. Its physical concentration view explicitly defines
   its own current/prior-day structure totals as sums of participating balances.
   It separately exposes master/participant roles, sweep type, frequency and
   execution times. That is evidence for this particular bank view, not a universal
   invariant for every pool-level availability measure or our private endpoint.
   [J.P. Morgan Access user guide](https://pages.paymentsolutions.chase.com/rs/984-MQH-261/images/1085200_Liquidity_Guide.pdf),
   updated 2023-07-11, pages 6 and 12.

3. **HSBC — notional FX conversion differs from actual FX.**
   HSBC's JAS case study combines physical sweeping into header accounts with a
   multi-currency notional pool. Different currency balances are notionally
   translated to a base currency to determine offsets, without a physical FX
   transaction. It also describes configurable pooling/concentration parameters.
   [HSBC global liquidity structure case study](https://www.business.hsbc.com/en-gb/insights/global-liquidity-structure-delivering-increased-efficiency-and-reduced-costs),
   2025-04-22, Global Liquidity Solutions section.

4. **Standard Chartered — sharing limits and sweep timing are configurable.**
   The bank explicitly allows customers to define how much participating accounts
   share. Its offerings include end-of-day, real-time, just-in-time, multi-bank and
   cross-currency sweeps, as well as multi-currency notional pooling. Therefore a
   main-account flag alone cannot establish universal sweep time or zero-balancing.
   [Standard Chartered Liquidity Management](https://www.sc.com/en/corporate-investment-banking/transaction-banking/liquidity-management),
   introduction, Tighten control and Optimise yield sections.

5. **Bank of China — product labels and funding rules vary.**
   BOC describes physical concentration into a core account, scheduled intraday
   sweeps, and an equal-status pool with no main account. It describes its local
   nominal pool as intraday information aggregation followed by end-of-day physical
   sweeping. This differs from Citi's usual notional mechanism and shows why a
   generic product name cannot replace the actual bank agreement. Its equal-status
   pool supports participant funding deficits with specified allocation rules.
   [BOC 流动性管理](https://www.boc.cn/cbservice/cb14/201507/t20150731_5396294.html),
   2015-07-31, 现金池 section.

## Internal knowledge-base corroboration

The coordinating agent used `graphify query` / `graphify explain` and then checked
the referenced source documents under
`/home/ubuntu/dev/dogpdkb/graphify_flatten_ready/`:

- `Liquidity__平台介绍__领域知识__流动性__常见流动性管理手段-2023-02-22-[6653650].md`,
  lines 37–41, distinguishes physical pooling, notional pooling and sweeping.
- `Accounting__平台能力__需求跟进__YIP__跨团队方案__流动性资金池扫款同主体场景登账-PRD-2024-09-10-[375554298].md`,
  lines 26–31, describes actual master/subaccount sweeps both intraday and at
  end-of-day. It links a BOCHK Sweeping PRD; that linked target was not fetched
  and is not treated as inspected evidence.

These historical documents corroborate mechanisms, not current private API field
definitions. The current field interpretation above comes from the user.

## Consequences for issue #98

These are design conclusions from the user's contract, supported by the product
mechanisms above, rather than claims that bank documentation proves our API:

- Withdraw the broad claim that original/equivalent account currency semantics
  are unknown: the user supplied that association. Keep account, converted and
  pool-level amounts distinct; preserve their native currency fields.
- Do not require pool balance to equal the member sum. Do not replace a bank's
  reported pool balance with a recomputed total or classify an inequality as an
  acquisition failure. Avoid adding pool and member totals together.
- Member timestamps may remain unknown. A pool date plus a separately identified
  capture timestamp supports an honest snapshot; it does not prove synchronized
  member balances, realtime freshness or daily member history.
- Accept negative participant balances and nonsharing structures. Do not infer an
  external borrowing source, lending entity or usable limit from the sign alone.
  Preserve native unknown/empty values; do not silently replace them with zero or
  automatically reject an otherwise usable snapshot.
- A missing or inconsistent native pool currency still needs an explicit unknown
  or bank-specific field mapping; the generic product definition cannot manufacture
  that mapping. The currency of a displayed pool amount must not be taken from
  an unrelated configuration label without evidence.
- No universal bank FX-rate, haircut or availability formula was established by
  these sources. Do not invent one or make its absence a blocker to displaying
  native reported amounts with their known/unknown metadata.

No command was enabled and no runtime, cache, pagination, identity or completeness
gate was verified by this research. Re-evaluate those separately against the
current implementation and captured native evidence.
