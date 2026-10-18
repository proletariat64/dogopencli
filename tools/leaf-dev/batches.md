# Leaf migration batches

This is the current scope map. Business acceptance and isolated worker handoff
follow the [migration procedure](workflow.md). The user assigns worktrees/Codex;
creating these tickets starts no leaf implementation.

Original batch tally: **9/79 packages, 12/106 inquiry actions** marked delivered.
The other 22 batches retain 70 packages/94 actions in the map, including the
partial SDK List deliveries below. These are original batch membership counts,
not counts of unimplemented actions. The four pilots are outside this denominator.
B labels group scope rather than impose execution order. Original list/get sets
stay intact; bounded List-only tickets do not complete their original batch.

The [machine-readable map](batches.json) is the single membership/action source.
Validate it before handing out or transferring work:

```bash
rtk proxy /path/to/host/bin/python -I tools/leaf-dev/leaf.py batches
```

L = list, G = get. Tickets own native contract pointers, special risks and evidence
dependencies. Workers own their listed packages/tests; the coordinator owns shared
guides/helpers, integration, daily installation and the parent progress ledger.

| Batch | Ticket | Leaves / operations | Packages / actions | State |
| --- | --- | --- | --- | --- |
| B01 | [#257](https://github.com/proletariat64/dogopencli/issues/257) | `liquidity.reference.banks` L; `liquidity.investment.benchmarks` L; `liquidity.rules.forecast` L | 3/3 | delivered |
| B02 | [#259](https://github.com/proletariat64/dogopencli/issues/259) | `liquidity.rules.action_mapping` L; `liquidity.rules.funding` L; `liquidity.rules.fx_settlement` L; `liquidity.rules.operation` LG; `liquidity.rules.realtime` LG; `liquidity.risk.thresholds` LG | 6/9 | delivered |
| B03 | [#262](https://github.com/proletariat64/dogopencli/issues/262) | `liquidity.cash.waterlevels` L; `liquidity.forecast.adjustments` L; `liquidity.cash.statements.intraday` L; `liquidity.cash.statements.end_of_day` L; `liquidity.cash.credit_lines` L; `liquidity.cash.credit_usage` L; `liquidity.cash.group_balances` L; `liquidity.cash.pool_balances` L; `liquidity.cash.pools` LG | 9/10 | planned |
| B05 | [#264](https://github.com/proletariat64/dogopencli/issues/264) | `liquidity.investment.holdings` LG; `liquidity.investment.transactions` LG; `liquidity.investment.compound_ledger` LG; `liquidity.investment.benchmark_values` L; `liquidity.investment.returns` L | 5/8 | planned |
| B06 | [#265](https://github.com/proletariat64/dogopencli/issues/265) | `liquidity.rules.notification` G; `liquidity.rules.transfer` LG; `liquidity.rules.waterlevel` LG | 3/5 | planned |
| B07 | [#266](https://github.com/proletariat64/dogopencli/issues/266) | `liquidity.risk.anomalies` LG; `liquidity.risk.events` LG; `liquidity.risk.metrics` L; `liquidity.risk.sla` LG | 4/7 | planned |
| B08 | [#267](https://github.com/proletariat64/dogopencli/issues/267) | `liquidity.operations.asset_trades` LG; `liquidity.operations.forwards` LG; `liquidity.operations.prefunds` LG; `liquidity.operations.demands` LG; `liquidity.operations.transfers` LG; `liquidity.operations.swaps` L | 6/11 | planned |
| B09 | [#268](https://github.com/proletariat64/dogopencli/issues/268) | `liquidity.investment.rfqs` LG; `liquidity.investment.quotes` LG; `liquidity.investment.quote_groups` G | 3/5 | planned |
| B10 | [#269](https://github.com/proletariat64/dogopencli/issues/269) | `liquidity.ledger.customers` G; `liquidity.network.account_capabilities` LG | 2/3 | planned |
| B11 | [#270](https://github.com/proletariat64/dogopencli/issues/270) | `liquidity.network.realtime` LG; `liquidity.network.route_quotas` G | 2/3 | planned |
| B12 | [#271](https://github.com/proletariat64/dogopencli/issues/271) | `liquidity.investment.strategies` G; `liquidity.investment.strategy_results` LG | 2/3 | planned |
| B13 | [#272](https://github.com/proletariat64/dogopencli/issues/272) | `collection.clearing_system` L; `collection.card_template` L; `collection.account_isolation` L | 3/3 | planned |
| B14 | [#273](https://github.com/proletariat64/dogopencli/issues/273) | `payment.rules.same_bank_transfer` L; `payment.rules.cost_reduction` L; `payment.rules.retry` L; `payment.rules.bank_switch` L | 4/4 | planned |
| B15 | [#274](https://github.com/proletariat64/dogopencli/issues/274) | `collection.sla.configs` LG; `collection.va.rules` LG; `collection.va.capacity` L | 3/5 | planned |
| B16 | [#275](https://github.com/proletariat64/dogopencli/issues/275) | `payment.channel` L; `payment.cost` L | 2/2 | planned |
| B17 | [#276](https://github.com/proletariat64/dogopencli/issues/276) | `payment.ptr.cases` L; `payment.ptr.orders` L | 2/2 | planned |
| B18 | [#277](https://github.com/proletariat64/dogopencli/issues/277) | `liquidity.reference.blacklist.account` L; `liquidity.reference.blacklist.bank` L; `liquidity.reference.whitelist.entity` L | 3/3 | planned |
| B19 | [#278](https://github.com/proletariat64/dogopencli/issues/278) | `liquidity.cash.accounts` L; `liquidity.cash.balances` L | 2/2 | planned |
| B20 | [#279](https://github.com/proletariat64/dogopencli/issues/279) | `liquidity.operations.account_strategies` L; `liquidity.risk.account_capacity` L | 2/2 | planned |
| B21 | [#280](https://github.com/proletariat64/dogopencli/issues/280) | `liquidity.forecast.account_cashflows` L; `liquidity.forecast.account_demands` L | 2/2 | planned |
| B22 | [#281](https://github.com/proletariat64/dogopencli/issues/281) | `liquidity.forecast.account_t3` L; `liquidity.forecast.account_demands_intraday` L | 2/2 | planned |
| B23 | [#282](https://github.com/proletariat64/dogopencli/issues/282) | `liquidity.forecast.results` L; `liquidity.forecast.cashflows` L; `liquidity.forecast.accuracy` L | 3/3 | planned |
| B24 | [#283](https://github.com/proletariat64/dogopencli/issues/283) | `liquidity.investment.interest_rates` LG; `liquidity.investment.products` LG; `liquidity.investment.products.history` L | 3/5 | planned |
| B25 | [#284](https://github.com/proletariat64/dogopencli/issues/284) | `liquidity.operations.decisions` LG; `liquidity.operations.decisions.history` L; `liquidity.operations.rule_status` L | 3/4 | planned |

## SDK List delivery

The inventory above tracks original complete action sets. A planned original
batch may have accepted Lists below; deferred Gets and held leaves do not complete
that batch or change its membership/counts. These deliveries comprise 34 SDK
Lists; each new List-only ticket excludes Get acquisition. The four pilots are
outside the inventory and were migrated in [#292](https://github.com/proletariat64/dogopencli/pull/292).

| Batch | Accepted SDK Lists | Delivery | Held List scope |
| --- | --- | --- | --- |
| B01 | 3 | [#294](https://github.com/proletariat64/dogopencli/pull/294) | — |
| B02 | 6 | [#296](https://github.com/proletariat64/dogopencli/pull/296) | — |
| B03 | 9 | [#298](https://github.com/proletariat64/dogopencli/pull/298) | — |
| B05 | 4 | [#302](https://github.com/proletariat64/dogopencli/pull/302) | returns: [#301](https://github.com/proletariat64/dogopencli/issues/301) |
| B06 | 2 | [#307](https://github.com/proletariat64/dogopencli/pull/307) | — |
| B07 | 2 | [#310](https://github.com/proletariat64/dogopencli/pull/310) | metrics: [#305](https://github.com/proletariat64/dogopencli/issues/305); anomalies: [#308](https://github.com/proletariat64/dogopencli/issues/308) |
| B08 | 6 | [#313](https://github.com/proletariat64/dogopencli/pull/313) | — |
| B09 | 1 | [#314](https://github.com/proletariat64/dogopencli/pull/314) | quotes: [#304](https://github.com/proletariat64/dogopencli/issues/304) |
| B10 | 1 | [#311](https://github.com/proletariat64/dogopencli/issues/311) | — |

Held leaves require their ticket evidence before implementation resumes. Frontend
and PDKB research about List/Get relationships is retained in
[#300](https://github.com/proletariat64/dogopencli/issues/300); it does not authorize
Get fanout or SDK business joins.
