# Leaf migration batches

[机器清单](batches.json)定义批次成员和原始 list/get 范围；[流程](workflow.md)定义开发与验收。
交付只计已合并、已验收的当前 SDK 实现，未合并分支和历史实现不计入。
四个 bundled pilots 单独统计，不占原始 **79 packages / 106 actions** 的分母。

## 已交付的基础能力

| 能力 | 当前交付 |
| --- | --- |
| List SDK + 4 pilot Lists | [#292](https://github.com/proletariat64/dogopencli/pull/292) |
| Get SDK + 显式 List/Detail 组合 | [#321](https://github.com/proletariat64/dogopencli/pull/321)；4 个现有 Get 已迁移 |
| SDK 开发手册、接口、可执行样例 | [手册](handbook.md)、[接口](interfaces.md)、[Get SDK](../../docs/agents/get-sdk.md)、[List+Get](example/)、[Get-only](example-get-only/) |
| 插件校验、打包、宿主检查、HTTP smoke、capture/compare | [leaf.py](README.md)，[plugin-helper](../../.agents/skills/plugin-helper/SKILL.md)；[#285](https://github.com/proletariat64/dogopencli/pull/285)、[#321](https://github.com/proletariat64/dogopencli/pull/321) |
| 关系发现与 HIL helper | [leaf-relations](../../.agents/skills/leaf-relations/SKILL.md)；[#316](https://github.com/proletariat64/dogopencli/pull/316) |

SDK 内置于宿主，不另发独立 SDK 包。候选 wheel/ZIP 的构建验收不代表正式版本已发布。
新增 leaf 继续使用已验证宿主；只有宿主输入变化才按流程重建。

四个 pilots 是 `payment.sla.baselines`、`collection.cost`、
`liquidity.reference.entities`、`fx.trade`：**4 Lists + 1 Get** 全部 SDK 化。
Get SDK 的四个真实案例是 pilot SLA 的 1 个 Get，加上 B02 的
`rules.operation`、`rules.realtime`、`risk.thresholds` 3 个 Get；其余三个 pilot 原本没有 Get。
Get 和 `list --live --with-detail` 只取得原生根详情，均不发布业务缓存或导入 Duckdog。

## B01–B10 当前交付

B04 已并入 B03，见 [#262](https://github.com/proletariat64/dogopencli/issues/262)；不另造批次。
这九个批次共 **41 leaves / 61 actions**：

- 已交付 **34/38 Lists、3/23 Gets**，合计 **37/61 actions**。
- **19/41 leaves** 的原始全部操作已交付；整批完成的是 B01、B02。
- 剩余 **20 Gets + 4 HOLD Lists**，不能据 List-only PR 已合并就关闭原始批次。
- 在全局 79/106 分母中，逐 leaf 统计为 **19/79 完整 leaves、37/106 已交付 actions**；
  仍有 60 leaves 未完整交付、69 actions 未交付。B11–B25 仍按各自 ticket 计划。

`batches.json.status` 只标整批完成：`planned` 也可能已有部分操作交付。
`leaf.py batches` 的 delivered 汇总只覆盖 B01/B02 整批（9 packages / 12 actions），
不等于逐 leaf/action 的累计交付。下表的 partial 是可读进度，不改变机器清单的状态格式。

| Batch | SDK List 已交付/原范围 | SDK Get 已交付/原范围 | 全操作已交付 leaves | 合并依据 |
| --- | --- | --- | --- | --- |
| B01 | 3/3 | 0/0 | 3/3 | [#294](https://github.com/proletariat64/dogopencli/pull/294) |
| B02 | 6/6 | 3/3 | 6/6 | [#296](https://github.com/proletariat64/dogopencli/pull/296) + [#321](https://github.com/proletariat64/dogopencli/pull/321) Get |
| B03 | 9/9 | 0/1 | 8/9 | [#298](https://github.com/proletariat64/dogopencli/pull/298) |
| B05 | 4/5 | 0/3 | 1/5 | [#302](https://github.com/proletariat64/dogopencli/pull/302) |
| B06 | 2/2 | 0/3 | 0/3 | [#307](https://github.com/proletariat64/dogopencli/pull/307) |
| B07 | 2/4 | 0/3 | 0/4 | [#310](https://github.com/proletariat64/dogopencli/pull/310) |
| B08 | 6/6 | 0/5 | 1/6 | [#313](https://github.com/proletariat64/dogopencli/pull/313) |
| B09 | 1/2 | 0/3 | 0/3 | [#314](https://github.com/proletariat64/dogopencli/pull/314) |
| B10 | 1/1 | 0/2 | 0/2 | [#315](https://github.com/proletariat64/dogopencli/pull/315) |

## HOLD List

| Batch / leaf | 当前缺口 | 跟踪 |
| --- | --- | --- |
| B05 `liquidity.investment.returns` | 日收益与现金事件的粒度、父子关联、根主键与独立覆盖待确认 | [#301](https://github.com/proletariat64/dogopencli/issues/301) |
| B07 `liquidity.risk.metrics` | 原生响应无 total；单次响应不能直接当作完整覆盖 | [#305](https://github.com/proletariat64/dogopencli/issues/305) |
| B07 `liquidity.risk.anomalies` | 分页重复及 unique/total 缺口；严格完整性未通过 | [#308](https://github.com/proletariat64/dogopencli/issues/308) |
| B09 `liquidity.investment.quotes` | 当前前端与历史契约的 total、分页、时区约定不一致 | [#304](https://github.com/proletariat64/dogopencli/issues/304) |

关系 helper 已交付不等于这些业务决策已解决；原生嵌套本身也不是 HOLD 的充分理由。
各 HOLD 保持原范围和证据要求，等待单独确认，不计已完成。

## 待交付 Get 清单

以下均为 `liquidity.` 下的叶子，仅登记原范围，不代表已完成 simple/complex 判定或已获开发授权。

| Batch | Get |
| --- | --- |
| B03 | `cash.pools` |
| B05 | `investment.holdings`、`investment.transactions`、`investment.compound_ledger` |
| B06 | `rules.notification`、`rules.transfer`、`rules.waterlevel` |
| B07 | `risk.anomalies`、`risk.events`、`risk.sla` |
| B08 | `operations.asset_trades`、`operations.forwards`、`operations.prefunds`、`operations.demands`、`operations.transfers` |
| B09 | `investment.rfqs`、`investment.quotes`、`investment.quote_groups` |
| B10 | `ledger.customers`、`network.account_capabilities` |

## 原始批次范围

L = list，G = get。原始 action 集合保持完整；全操作通过前不将整个 leaf 或 batch 记为 delivered。
成员与操作以机器清单为准，运行以下命令校验：

```bash
rtk proxy /path/to/host/bin/python -I tools/leaf-dev/leaf.py batches
```

| Batch | Ticket | Leaves / operations | Packages / actions | State |
| --- | --- | --- | --- | --- |
| B01 | [#257](https://github.com/proletariat64/dogopencli/issues/257) | `liquidity.reference.banks` L; `liquidity.investment.benchmarks` L; `liquidity.rules.forecast` L | 3/3 | delivered |
| B02 | [#259](https://github.com/proletariat64/dogopencli/issues/259) | `liquidity.rules.action_mapping` L; `liquidity.rules.funding` L; `liquidity.rules.fx_settlement` L; `liquidity.rules.operation` LG; `liquidity.rules.realtime` LG; `liquidity.risk.thresholds` LG | 6/9 | delivered |
| B03 | [#262](https://github.com/proletariat64/dogopencli/issues/262) | `liquidity.cash.waterlevels` L; `liquidity.forecast.adjustments` L; `liquidity.cash.statements.intraday` L; `liquidity.cash.statements.end_of_day` L; `liquidity.cash.credit_lines` L; `liquidity.cash.credit_usage` L; `liquidity.cash.group_balances` L; `liquidity.cash.pool_balances` L; `liquidity.cash.pools` LG | 9/10 | partial |
| B05 | [#264](https://github.com/proletariat64/dogopencli/issues/264) | `liquidity.investment.holdings` LG; `liquidity.investment.transactions` LG; `liquidity.investment.compound_ledger` LG; `liquidity.investment.benchmark_values` L; `liquidity.investment.returns` L | 5/8 | partial |
| B06 | [#265](https://github.com/proletariat64/dogopencli/issues/265) | `liquidity.rules.notification` G; `liquidity.rules.transfer` LG; `liquidity.rules.waterlevel` LG | 3/5 | partial |
| B07 | [#266](https://github.com/proletariat64/dogopencli/issues/266) | `liquidity.risk.anomalies` LG; `liquidity.risk.events` LG; `liquidity.risk.metrics` L; `liquidity.risk.sla` LG | 4/7 | partial |
| B08 | [#267](https://github.com/proletariat64/dogopencli/issues/267) | `liquidity.operations.asset_trades` LG; `liquidity.operations.forwards` LG; `liquidity.operations.prefunds` LG; `liquidity.operations.demands` LG; `liquidity.operations.transfers` LG; `liquidity.operations.swaps` L | 6/11 | partial |
| B09 | [#268](https://github.com/proletariat64/dogopencli/issues/268) | `liquidity.investment.rfqs` LG; `liquidity.investment.quotes` LG; `liquidity.investment.quote_groups` G | 3/5 | partial |
| B10 | [#269](https://github.com/proletariat64/dogopencli/issues/269) | `liquidity.ledger.customers` G; `liquidity.network.account_capabilities` LG | 2/3 | partial |
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

## 暂保留的非 SDK WIP

| Branch | 未合并 PR | 处理 |
| --- | --- | --- |
| `feat/b03-issue262` | [#286](https://github.com/proletariat64/dogopencli/pull/286) | 暂保留，最后另行清理 |
| `feat/b05-issue264` | [#289](https://github.com/proletariat64/dogopencli/pull/289) | 暂保留，最后另行清理 |
| `feat/b06-issue265` | [#287](https://github.com/proletariat64/dogopencli/pull/287) | 暂保留，最后另行清理 |

这些分支已有历史开发与验收记录，但不是当前已合并的 SDK 交付，不据此关闭批次。
后续任务以当前 master、对应批次 ticket 和 SDK 手册为起点；原始批次与 HOLD 的收尾分别验收。
