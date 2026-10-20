# Leaf migration batches

[机器清单](batches.json)定义批次成员和原始 list/get 范围；[流程](workflow.md)定义开发与验收。
清单随已验收的 SDK 实现合并，未合并的历史 WIP 不计交付。
四个 bundled pilots 单独统计。原始基线为 **79 packages / 106 actions**；
经数据负责人确认，B07 的 `risk.metrics` 拆为两个独立 List，当前清单为 **80 packages / 107 actions**。

## 基础能力

| 能力 | 当前交付 |
| --- | --- |
| List SDK + 4 pilot Lists | [#292](https://github.com/proletariat64/dogopencli/pull/292) |
| 可选短页、稳定洞恢复 | [#339](https://github.com/proletariat64/dogopencli/pull/339)、[#340](https://github.com/proletariat64/dogopencli/pull/340)；仍需逐源资格化 |
| 显式 custom Python 查询入口 | [#341](https://github.com/proletariat64/dogopencli/pull/341)；业务编排与失败资格化归 leaf |
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
这九个批次共 **42 leaves / 62 actions**：

- **39/39 Lists、23/23 Gets**，合计 **62/62 actions**；**42/42 leaves** 全操作完成。
- 整批完成 B01、B02、B03、B05、B06、B07、B08、B09、B10；当前范围无 HOLD。
- 全局逐 leaf/action 累计为 **66/80 完整 leaves、91/107 actions**；仍有 14 leaves、16 actions 未完成。
- 进度工具按完整 leaf 累计；部分完成批次仍保留 HOLD 范围。

| Batch | SDK List / 原范围 | SDK Get / 原范围 | 全操作完成 leaves | 范围依据 |
| --- | --- | --- | --- | --- |
| B01 | 3/3 | 0/0 | 3/3 | [#257](https://github.com/proletariat64/dogopencli/issues/257) |
| B02 | 6/6 | 3/3 | 6/6 | [#259](https://github.com/proletariat64/dogopencli/issues/259) |
| B03 | 9/9 | 1/1 | 9/9 | [#262](https://github.com/proletariat64/dogopencli/issues/262) |
| B05 | 5/5 | 3/3 | 5/5 | [#264](https://github.com/proletariat64/dogopencli/issues/264) |
| B06 | 2/2 | 3/3 | 3/3 | [#265](https://github.com/proletariat64/dogopencli/issues/265) |
| B07 | 5/5 | 3/3 | 5/5 | [#266](https://github.com/proletariat64/dogopencli/issues/266) |
| B08 | 6/6 | 5/5 | 6/6 | [#267](https://github.com/proletariat64/dogopencli/issues/267) |
| B09 | 2/2 | 3/3 | 3/3 | [#268](https://github.com/proletariat64/dogopencli/issues/268) |
| B10 | 1/1 | 2/2 | 2/2 | [#269](https://github.com/proletariat64/dogopencli/issues/269) |

## B07 指标拆分

[#305](https://github.com/proletariat64/dogopencli/issues/305) 记录数据负责人确认的两个独立 simple Lists：
`liquidity.risk.deposit_concentration` 固定查询 `CONCENTRATION_RATE`；
`liquidity.risk.credit_usage` 固定查询 `CREDIT_USAGE_RATE`（银行交易对手额度使用率）。
各自查询同一接口，保留原生整数 `id`、完整记录和每行独立的 `reportTime`，不对齐时间或合并结果。
`single_response` 仅覆盖该租户与指标已发布的响应集合；原生 total 保持未知，
不据此证明所有银行或历史时点均有记录。两项分别完成原生结果比较、独立缓存和安装验收，B07 全范围完成。

已确认的复杂关系由 leaf 表达：waterlevel Get 返回按账户 alias 查询的完整配置数组，
不绑定当前 List 行；quotes Get 保留完整根和嵌套身份；returns 以 `investmentNo` 为根，
保留 accrual/cash 原生子记录及各源独立范围。源内无记录不证明该父对象全部历史无记录。
后续复杂关系继续经 helper 发现、实验和 HIL 确认后开发。

## B11–B20 后续迁移

按批次推进；不能表达或缺少验收证据的整个 leaf 暂停，集中 HIL 后再处理，不更改清单分母。

- B11/#270：两项 leaf / 三项 actions 保持未完成。custom 已可表达依赖查询，但 `network.route_quotas` 原生根无标量身份，且内部 Detail 同样要求原生身份；这也阻塞 realtime 的条件路由关联。历史覆盖独立保留，不以 root-only 或补造身份绕过。
- B12/#271：两个 leaf / 三项 actions 完成。`investment.strategies` 仅 Get；`investment.strategy_results` 按显式任务类型查询 List/Get，原生根与嵌套数据保留。
- B13/#272：三个收款配置 List 完成，固定首个 1000 容量按原生 total 与唯一身份验证；卡模板保留原生嵌套数组，不承诺未验证的明细语义。
- B14/#273：四个付款规则 List 完成，原生单响应全量及精确本地筛选；银存切换保留单接口原生层级，嵌套条件须在同一分支成立。
- B15/#274：三个完整 leaf / 五项 actions 完成；`va.capacity` 使用已批准的标准短页策略，独立原生／pinned、live/refresh/offline及HTTP生命周期通过，#339已合并、批次票已关闭。
- B16/#275：`payment.channel` 原生行身份及完整范围未资格化；`payment.cost` 的网络筛选返回 24 条原生记录、仅 3 条精确匹配，历史 live 与缓存筛选语义不同。两个整叶 HOLD，保留研究并集中确认，不计交付。
- B17/#276：两个 PTR List 完成，复用 custom 实现两次成功完整稳定读取、字段白名单及填充范围验证后修剪；两项原生／pinned、live/refresh/offline及同ZIP HTTP生命周期通过。
- B18/#277：账户黑名单、主体白名单两个 List 完成；银行黑名单已批准 latest-per-bank 投影，但原生版本行身份及完整范围仍待资格化，整叶 HOLD。
- B19/#278：`cash.accounts` List 已合并#341，三源原生目录、完整尝试覆盖及同ZIP HTTP生命周期通过；用户批准单条详情失败保留为failed，普通live exit0+warning/incomplete，strict/refresh拒绝，不伪称完整详情数据。`cash.balances` 的 latest/daily 双模式可用custom表达，仍需独立目录／日期块资格化；不在当前三叶开发范围。
- B20/#279：`operations.account_strategies` List 完成，保留原生复合身份、全部版本和状态；旧额外空终页探测由 SDK 标准完整性机制替代。`risk.account_capacity` List 完成，custom 按原1–10显式账户范围逐一校验原生alias回显；原生／pinned、live/refresh/offline及同ZIP HTTP生命周期通过。

B11–B20 累计交付 19 leaves / 22 actions；未完成6 leaves / 7 actions归#332，保留各自来源资格化／业务决策。

## B21–B25 迁移

集中 HIL 归 [#333](https://github.com/proletariat64/dogopencli/issues/333)；保留原票与全部操作范围。

- B21/#280：两个账户现金流／需求 List 整叶 HOLD。原有 alias-only 查询会依次从 Duckdog、缓存、实时目录补全主体和银行；不能静默改为必填上下文。明确上下文的原生非空查询已验证，不等同完整 leaf 交付。
- B22/#281：`forecast.account_t3` List 使用原生八字段身份、账户和 forecastDate 范围，标准 SDK 完整性；`forecast.account_demands_intraday` 的账户解析边界仍 HOLD，原生 96 时隙不补零、不合成 total。
- B23/#282：`forecast.results` List 按原生账户、valueDate 和记录创建时刻范围查询，完整保留原生记录；`forecast.cashflows` 缺少原生身份，`forecast.accuracy` 的依赖编排现可用 custom 表达，但指标根只有请求上下文、缺少 SDK Detail 所需的原生身份，两项整叶 HOLD。
- B24/#283：`investment.products` 的 List/Get 完成，原生 physical product ID、完整单响应及独立详情保留；`interest_rates` 的银行来源按报价日期组计数，`products.history` 的独立版本身份／覆盖语义待确认，两项整叶 HOLD。
- B25/#284：`operations.decisions` List/Get 与 `operations.rule_status` List 完成；决策 List 保留限定字段、Get 保留完整原生根，规则状态保留 UTC 时段和原生汇总投影。`decisions.history` 整叶 HOLD，等待历史版本关系／覆盖确认。


## 原始批次范围

L = list，G = get。原始 action 集合保持完整；全操作通过前不将整个 leaf 或 batch 记为 delivered。
成员默认继承批次 `status`；部分完成时，在成员上分别标记 `delivered` 或 `blocked`，
批次保持未完成。工具按完整 leaf 累计 packages/actions，同时显示每批已完成数量。
整批 `delivered` 不得含未完成成员；HOLD 的范围保留在原票及集中 HIL 清单中。
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
| B07 | [#266](https://github.com/proletariat64/dogopencli/issues/266) | `liquidity.risk.anomalies` LG; `liquidity.risk.events` LG; `liquidity.risk.deposit_concentration` L; `liquidity.risk.credit_usage` L; `liquidity.risk.sla` LG | 5/8 | delivered |
| B08 | [#267](https://github.com/proletariat64/dogopencli/issues/267) | `liquidity.operations.asset_trades` LG; `liquidity.operations.forwards` LG; `liquidity.operations.prefunds` LG; `liquidity.operations.demands` LG; `liquidity.operations.transfers` LG; `liquidity.operations.swaps` L | 6/11 | delivered |
| B09 | [#268](https://github.com/proletariat64/dogopencli/issues/268) | `liquidity.investment.rfqs` LG; `liquidity.investment.quotes` LG; `liquidity.investment.quote_groups` G | 3/5 | delivered |
| B10 | [#269](https://github.com/proletariat64/dogopencli/issues/269) | `liquidity.ledger.customers` G; `liquidity.network.account_capabilities` LG | 2/3 | delivered |
| B11 | [#270](https://github.com/proletariat64/dogopencli/issues/270) | `liquidity.network.realtime` LG; `liquidity.network.route_quotas` G | 2/3 | blocked / HOLD |
| B12 | [#271](https://github.com/proletariat64/dogopencli/issues/271) | `liquidity.investment.strategies` G; `liquidity.investment.strategy_results` LG | 2/3 | delivered |
| B13 | [#272](https://github.com/proletariat64/dogopencli/issues/272) | `collection.clearing_system` L; `collection.card_template` L; `collection.account_isolation` L | 3/3 | delivered |
| B14 | [#273](https://github.com/proletariat64/dogopencli/issues/273) | `payment.rules.same_bank_transfer` L; `payment.rules.cost_reduction` L; `payment.rules.retry` L; `payment.rules.bank_switch` L | 4/4 | delivered |
| B15 | [#274](https://github.com/proletariat64/dogopencli/issues/274) | `collection.sla.configs` LG; `collection.va.rules` LG; `collection.va.capacity` L | 3/5 | delivered |
| B16 | [#275](https://github.com/proletariat64/dogopencli/issues/275) | `payment.channel` L; `payment.cost` L | 2/2 | blocked / HOLD |
| B17 | [#276](https://github.com/proletariat64/dogopencli/issues/276) | `payment.ptr.cases` L; `payment.ptr.orders` L | 2/2 | delivered |
| B18 | [#277](https://github.com/proletariat64/dogopencli/issues/277) | `liquidity.reference.blacklist.account` L; `liquidity.reference.blacklist.bank` L; `liquidity.reference.whitelist.entity` L | 3/3 | blocked：2 leaves / 2 actions delivered；bank HOLD |
| B19 | [#278](https://github.com/proletariat64/dogopencli/issues/278) | `liquidity.cash.accounts` L; `liquidity.cash.balances` L | 2/2 | blocked：accounts delivered；balances 待资格化 |
| B20 | [#279](https://github.com/proletariat64/dogopencli/issues/279) | `liquidity.operations.account_strategies` L; `liquidity.risk.account_capacity` L | 2/2 | delivered |
| B21 | [#280](https://github.com/proletariat64/dogopencli/issues/280) | `liquidity.forecast.account_cashflows` L; `liquidity.forecast.account_demands` L | 2/2 | blocked / HOLD |
| B22 | [#281](https://github.com/proletariat64/dogopencli/issues/281) | `liquidity.forecast.account_t3` L; `liquidity.forecast.account_demands_intraday` L | 2/2 | blocked：T3 delivered；intraday HOLD |
| B23 | [#282](https://github.com/proletariat64/dogopencli/issues/282) | `liquidity.forecast.results` L; `liquidity.forecast.cashflows` L; `liquidity.forecast.accuracy` L | 3/3 | blocked：results delivered；cashflows / accuracy HOLD |
| B24 | [#283](https://github.com/proletariat64/dogopencli/issues/283) | `liquidity.investment.interest_rates` LG; `liquidity.investment.products` LG; `liquidity.investment.products.history` L | 3/5 | blocked：products List/Get delivered；rates / history HOLD |
| B25 | [#284](https://github.com/proletariat64/dogopencli/issues/284) | `liquidity.operations.decisions` LG; `liquidity.operations.decisions.history` L; `liquidity.operations.rule_status` L | 3/4 | blocked：decisions List/Get、rule_status List delivered；history HOLD |

## 暂保留的非 SDK WIP

| Branch | 未合并 PR | 处理 |
| --- | --- | --- |
| `feat/b03-issue262` | [#286](https://github.com/proletariat64/dogopencli/pull/286) | 暂保留，最后另行清理 |
| `feat/b05-issue264` | [#289](https://github.com/proletariat64/dogopencli/pull/289) | 暂保留，最后另行清理 |
| `feat/b06-issue265` | [#287](https://github.com/proletariat64/dogopencli/pull/287) | 暂保留，最后另行清理 |

这些分支已有历史开发与验收记录，但不是当前已合并的 SDK 交付，不据此关闭批次。
后续任务以当前 master、对应批次 ticket 和 SDK 手册为起点；当前清单范围与待验收操作分别验收。
