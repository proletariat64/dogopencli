# Leaf migration batches

[机器清单](batches.json)定义批次成员和原始 list/get 范围；[流程](workflow.md)定义开发与验收。
清单随已验收的 SDK 实现合并，未合并的历史 WIP 不计交付。
四个 bundled pilots 单独统计，不占原始 **79 packages / 106 actions** 的分母。

## 基础能力

| 能力 | 当前交付 |
| --- | --- |
| List SDK + 4 pilot Lists | [#292](https://github.com/proletariat64/dogopencli/pull/292) |
| Get SDK + 显式 List/Detail 组合 | [#321](https://github.com/proletariat64/dogopencli/pull/321) |
| 原生数组 Get、嵌套身份路径、已确认的单响应及独立多源 List | [#323](https://github.com/proletariat64/dogopencli/issues/323)；SDK 不推断业务关联 |
| SDK 开发手册、接口、可执行样例 | [手册](handbook.md)、[接口](interfaces.md)、[List+Get](example/)、[Get-only](example-get-only/)、[单响应](example-single-response/)、[独立多源](example-sources/) |
| 校验、打包、宿主检查、HTTP smoke、capture/compare | [leaf.py](README.md)、[plugin-helper](../../.agents/skills/plugin-helper/SKILL.md) |
| 关系发现与 HIL helper | [leaf-relations](../../.agents/skills/leaf-relations/SKILL.md)；[#316](https://github.com/proletariat64/dogopencli/pull/316) |

SDK 内置于宿主，不另发独立 SDK 包。候选 wheel/ZIP 验收不代表正式版本已发布。
新增 leaf 复用匹配的已验证宿主；只有宿主输入变化才协调重建。

四个 pilots 是 `payment.sla.baselines`、`collection.cost`、
`liquidity.reference.entities`、`fx.trade`：**4 Lists + 1 Get** 全部 SDK 化。
Get SDK 最初四个案例是 pilot SLA 加上 B02 的 `rules.operation`、
`rules.realtime`、`risk.thresholds`；其余三个 pilot 原本没有 Get。
Get 和 `list --live --with-detail` 不发布业务缓存或导入 Duckdog。

## B01–B10 交付

B04 已并入 B03，见 [#262](https://github.com/proletariat64/dogopencli/issues/262)。
这九个批次共 **41 leaves / 61 actions**：

- **37/38 Lists、23/23 Gets**，合计 **60/61 actions**；**40/41 leaves** 全操作完成。
- 整批完成 B01、B02、B03、B05、B06、B08、B09、B10；B07 仅 `risk.metrics` List 保持 HOLD。
- 全局逐 leaf/action 累计为 **40/79 完整 leaves、60/106 actions**；仍有 39 leaves、46 actions 未完成。
- `batches.json.status` 只标整批：`leaf.py batches` 的 delivered 汇总为 **37 packages / 54 actions**，
  另有 B07 的 3 leaves / 6 actions 已交付；两个统计口径不能相加重复计数。

| Batch | SDK List / 原范围 | SDK Get / 原范围 | 全操作完成 leaves | 范围依据 |
| --- | --- | --- | --- | --- |
| B01 | 3/3 | 0/0 | 3/3 | [#257](https://github.com/proletariat64/dogopencli/issues/257) |
| B02 | 6/6 | 3/3 | 6/6 | [#259](https://github.com/proletariat64/dogopencli/issues/259) |
| B03 | 9/9 | 1/1 | 9/9 | [#262](https://github.com/proletariat64/dogopencli/issues/262) |
| B05 | 5/5 | 3/3 | 5/5 | [#264](https://github.com/proletariat64/dogopencli/issues/264) |
| B06 | 2/2 | 3/3 | 3/3 | [#265](https://github.com/proletariat64/dogopencli/issues/265) |
| B07 | 3/4 | 3/3 | 3/4 | [#266](https://github.com/proletariat64/dogopencli/issues/266) |
| B08 | 6/6 | 5/5 | 6/6 | [#267](https://github.com/proletariat64/dogopencli/issues/267) |
| B09 | 2/2 | 3/3 | 3/3 | [#268](https://github.com/proletariat64/dogopencli/issues/268) |
| B10 | 1/1 | 2/2 | 2/2 | [#269](https://github.com/proletariat64/dogopencli/issues/269) |

## 保留的 HOLD

`liquidity.risk.metrics` List 由 [#305](https://github.com/proletariat64/dogopencli/issues/305)
跟踪：原生响应无 total，单次非空结果仍缺少整份响应覆盖范围的资格证明。
它不因 SDK 提供 `single_response` 就自动满足完整性要求，B07 和父任务保持未完成。

已确认的复杂关系由 leaf 表达：waterlevel Get 返回按账户 alias 查询的完整配置数组，
不绑定当前 List 行；quotes Get 保留完整根和嵌套身份；returns 以 `investmentNo` 为根，
保留 accrual/cash 原生子记录及各源独立范围。源内无记录不证明该父对象全部历史无记录。
后续复杂关系继续经 helper 发现、实验和 HIL 确认后开发。

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
| B03 | [#262](https://github.com/proletariat64/dogopencli/issues/262) | `liquidity.cash.waterlevels` L; `liquidity.forecast.adjustments` L; `liquidity.cash.statements.intraday` L; `liquidity.cash.statements.end_of_day` L; `liquidity.cash.credit_lines` L; `liquidity.cash.credit_usage` L; `liquidity.cash.group_balances` L; `liquidity.cash.pool_balances` L; `liquidity.cash.pools` LG | 9/10 | delivered |
| B05 | [#264](https://github.com/proletariat64/dogopencli/issues/264) | `liquidity.investment.holdings` LG; `liquidity.investment.transactions` LG; `liquidity.investment.compound_ledger` LG; `liquidity.investment.benchmark_values` L; `liquidity.investment.returns` L | 5/8 | delivered |
| B06 | [#265](https://github.com/proletariat64/dogopencli/issues/265) | `liquidity.rules.notification` G; `liquidity.rules.transfer` LG; `liquidity.rules.waterlevel` LG | 3/5 | delivered |
| B07 | [#266](https://github.com/proletariat64/dogopencli/issues/266) | `liquidity.risk.anomalies` LG; `liquidity.risk.events` LG; `liquidity.risk.metrics` L; `liquidity.risk.sla` LG | 4/7 | partial |
| B08 | [#267](https://github.com/proletariat64/dogopencli/issues/267) | `liquidity.operations.asset_trades` LG; `liquidity.operations.forwards` LG; `liquidity.operations.prefunds` LG; `liquidity.operations.demands` LG; `liquidity.operations.transfers` LG; `liquidity.operations.swaps` L | 6/11 | delivered |
| B09 | [#268](https://github.com/proletariat64/dogopencli/issues/268) | `liquidity.investment.rfqs` LG; `liquidity.investment.quotes` LG; `liquidity.investment.quote_groups` G | 3/5 | delivered |
| B10 | [#269](https://github.com/proletariat64/dogopencli/issues/269) | `liquidity.ledger.customers` G; `liquidity.network.account_capabilities` LG | 2/3 | delivered |
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
