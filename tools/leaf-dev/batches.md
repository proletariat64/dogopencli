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
- 全局逐 leaf/action 累计为 **79/80 完整 leaves、105/107 actions**；仍有 1 leaf、2 actions 未完成。
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

- B11/#270：`network.route_quotas` Get 完成，以请求中的 routeId、aliasName、tntInstId 为整组原生额度的复合身份。`network.realtime` List 已验证，Get 保留根、历史及条件额度关联，但历史覆盖仍未知，普通 Get 显式 incomplete、strict 拒绝；整叶两项 actions 仍归 #332，未计交付。
- B12/#271：两个 leaf / 三项 actions 完成。`investment.strategies` 仅 Get；`investment.strategy_results` 按显式任务类型查询 List/Get，原生根与嵌套数据保留。
- B13/#272：三个收款配置 List 完成，固定首个 1000 容量按原生 total 与唯一身份验证；卡模板保留原生嵌套数组，不承诺未验证的明细语义。
- B14/#273：四个付款规则 List 完成，原生单响应全量及精确本地筛选；银存切换保留单接口原生层级，嵌套条件须在同一分支成立。
- B15/#274：三个完整 leaf / 五项 actions 完成；`va.capacity` 使用已批准的标准短页策略，独立原生／pinned、live/refresh/offline及HTTP生命周期通过，#339已合并、批次票已关闭。
- B16/#275：两个 List 完成。cost 以 itemId 保留不同计费规格，clearingNetworkName 在完整取源后精确筛选，live/offline 一致。channel 以 abilityId 去重，使用已批准的 short_page 绕行；同 ID 同内容重复为 exit 0 + warning，可发布 refresh；冲突仍失败。total 未知，不声称已证明后端业务全集。
- B17/#276：两个 PTR List 完成，复用 custom 实现两次成功完整稳定读取、字段白名单及填充范围验证后修剪；两项原生／pinned、live/refresh/offline及同ZIP HTTP生命周期通过。
- B18/#277：三个 List 完成。银行黑名单按 bankId+bankSwiftCode 为键，先比较 gmtModified，再比较 gmtCreate 选择；独立保留源到达、原生 total 和选中行数量。
- B19/#278：两个 List 完成。cash.accounts 保留已批准的 failed-detail/incomplete 策略，strict/refresh 拒绝不完整详情。cash.balances 保留 latest/daily、冻结的当前目录标签和账户／日期分块；当前目录不作为历史所有权证明。
- B20/#279：`operations.account_strategies` List 完成，保留原生复合身份、全部版本和状态；旧额外空终页探测由 SDK 标准完整性机制替代。`risk.account_capacity` List 完成，custom 按原1–10显式账户范围逐一校验原生alias回显；原生／pinned、live/refresh/offline及同ZIP HTTP生命周期通过。

B11–B20 累计交付 24 leaves / 27 actions；未完成 1 leaf / 2 actions 归 #332：network.realtime 的历史覆盖。

## B21–B25 迁移

本范围全部 leaf 已完成；业务模型和 HIL 决定见 [#333](https://github.com/proletariat64/dogopencli/issues/333)，原票操作范围保持不变。

- B21/#280：两个账户 List 完成。alias 和日期必填，保留显式上下文约束及 Duckdog→cache→live 补齐顺序、来源质量与 provenance，不默认 ANY 全库查询。
- B22/#281：两个 List 完成。T3 保留原生八字段身份；intraday 沿用账户解析，单账户单日，非空需 96 个原生 15 分钟时隙标签，不补零。
- B23/#282：三个 List 完成。results 保留原生查询范围；cashflows 以包括 gmtCreate 的 13 字段组合作内部身份，空 gmtCreate 点保留且不推定已有有效预测；accuracy 按每条基础记录的原生请求绑定取得指标，所需查询失败整次失败，保留确认的 legacy 字段投影。
- B24/#283：三个 leaf / 五项 actions 完成。products List/Get 保留原生身份；interest_rates 保留 market、bank、expectation-rule、expection 四来源及 expection Get，银行以报价日期组分页而非行数；products.history 仅返回同产品的原生历史版本数组。
- B25/#284：三个 leaf / 四项 actions 完成。decisions List/Get、rule_status List 保留原契约；decisions.history 核对当前查询和 report/group/tenant 关系，仅返回原生历史数组。


产品／决策 history 的完成边界是原生接口成功返回的整个历史数组，原生 total 保持未知，不拼当前记录、不推定后台未返回版本。该边界不替代 realtime Get 独立的历史覆盖限制。

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
| B11 | [#270](https://github.com/proletariat64/dogopencli/issues/270) | `liquidity.network.realtime` LG; `liquidity.network.route_quotas` G | 2/3 | partial：route_quotas delivered；realtime HOLD |
| B12 | [#271](https://github.com/proletariat64/dogopencli/issues/271) | `liquidity.investment.strategies` G; `liquidity.investment.strategy_results` LG | 2/3 | delivered |
| B13 | [#272](https://github.com/proletariat64/dogopencli/issues/272) | `collection.clearing_system` L; `collection.card_template` L; `collection.account_isolation` L | 3/3 | delivered |
| B14 | [#273](https://github.com/proletariat64/dogopencli/issues/273) | `payment.rules.same_bank_transfer` L; `payment.rules.cost_reduction` L; `payment.rules.retry` L; `payment.rules.bank_switch` L | 4/4 | delivered |
| B15 | [#274](https://github.com/proletariat64/dogopencli/issues/274) | `collection.sla.configs` LG; `collection.va.rules` LG; `collection.va.capacity` L | 3/5 | delivered |
| B16 | [#275](https://github.com/proletariat64/dogopencli/issues/275) | `payment.channel` L; `payment.cost` L | 2/2 | delivered |
| B17 | [#276](https://github.com/proletariat64/dogopencli/issues/276) | `payment.ptr.cases` L; `payment.ptr.orders` L | 2/2 | delivered |
| B18 | [#277](https://github.com/proletariat64/dogopencli/issues/277) | `liquidity.reference.blacklist.account` L; `liquidity.reference.blacklist.bank` L; `liquidity.reference.whitelist.entity` L | 3/3 | delivered |
| B19 | [#278](https://github.com/proletariat64/dogopencli/issues/278) | `liquidity.cash.accounts` L; `liquidity.cash.balances` L | 2/2 | delivered |
| B20 | [#279](https://github.com/proletariat64/dogopencli/issues/279) | `liquidity.operations.account_strategies` L; `liquidity.risk.account_capacity` L | 2/2 | delivered |
| B21 | [#280](https://github.com/proletariat64/dogopencli/issues/280) | `liquidity.forecast.account_cashflows` L; `liquidity.forecast.account_demands` L | 2/2 | delivered |
| B22 | [#281](https://github.com/proletariat64/dogopencli/issues/281) | `liquidity.forecast.account_t3` L; `liquidity.forecast.account_demands_intraday` L | 2/2 | delivered |
| B23 | [#282](https://github.com/proletariat64/dogopencli/issues/282) | `liquidity.forecast.results` L; `liquidity.forecast.cashflows` L; `liquidity.forecast.accuracy` L | 3/3 | delivered |
| B24 | [#283](https://github.com/proletariat64/dogopencli/issues/283) | `liquidity.investment.interest_rates` LG; `liquidity.investment.products` LG; `liquidity.investment.products.history` L | 3/5 | delivered |
| B25 | [#284](https://github.com/proletariat64/dogopencli/issues/284) | `liquidity.operations.decisions` LG; `liquidity.operations.decisions.history` L; `liquidity.operations.rule_status` L | 3/4 | delivered |

## 暂保留的非 SDK WIP

| Branch | 未合并 PR | 处理 |
| --- | --- | --- |
| `feat/b03-issue262` | [#286](https://github.com/proletariat64/dogopencli/pull/286) | 暂保留，最后另行清理 |
| `feat/b05-issue264` | [#289](https://github.com/proletariat64/dogopencli/pull/289) | 暂保留，最后另行清理 |
| `feat/b06-issue265` | [#287](https://github.com/proletariat64/dogopencli/pull/287) | 暂保留，最后另行清理 |

这些分支已有历史开发与验收记录，但不是当前已合并的 SDK 交付，不据此关闭批次。
后续任务以当前 master、对应批次 ticket 和 SDK 手册为起点；当前清单范围与待验收操作分别验收。
