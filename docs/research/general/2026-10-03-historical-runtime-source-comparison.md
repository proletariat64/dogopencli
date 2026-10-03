# 可按日期查询的运行态数据源对照

Observed: 2026-10-03
Scope: general
Status: snapshot

## 结论

`forecast results list` 符合“后端可按业务日期和记录时刻查询历史运行态数据”的类别。其内容是预测记录，不是已完成的资金交易。最直接的同类命令是 `payment ptr orders list`；实际资金记录方面，现金流水、资产转移订单和投资收益记录更接近历史交易查询。源码声明的 `runtimes` 分类、原生时间筛选以及已有生产验收分别构成不同证据，不能互相代替。

按当前执行注册表计数，Liquidity 有 **21 个 runtime list 路由，其中 12 个带原生日期查询合同**，包含 forecast results 和目前受阻的 ledger balances。另有 Payment PTR orders 一个时间区间查询。排除 forecast results 后，共 **12 个已注册的日期/时间查询路由：11 个可服务，1 个 ledger balances 受阻**。此处 returns 的 accrual/cash 是一个公共路由的两个合同变体，定价和利率记录也计入，但不称为实际交易。来源：[注册入口](../../../src/dogopencli/plugins/__init__.py)、[Liquidity 路由及合同](../../../src/dogopencli/plugins/liquidity/leaves.py)、[新增现金/预测合同](../../../src/dogopencli/plugins/liquidity/cash_forecast.py)、[PTR orders 合同](../../../src/dogopencli/plugins/payment/ptr_orders.py)。

用户接受 forecast 的带告警返回，与当前实现一致：普通 live 返回可用记录及 `INCOMPLETE_RESULT`，保留 `complete=false` 和退出码 1；严格查询拒绝部分数据；解析校验通过但覆盖不完整的 refresh 返回可用数据、`published=false`，保留此前完整缓存。总数变化仍作为 `INVALID_RESPONSE` 拒绝。来源：[live 查询](../../../src/dogopencli/plugins/liquidity/query.py)、[refresh](../../../src/dogopencli/plugins/liquidity/refresh.py)、[forecast 合同说明](../../../src/dogopencli/plugins/liquidity/cash_forecast.py)。本次没有改变产品代码。

## 同类日期查询命令

表内命令省略 `dogopencli` 前缀；Liquidity 日期值均为 `YYYYMMDD`。普通查询默认读匹配范围的本地缓存，直接查后端需 `--live`；`--all` 仅展开该范围的显示结果。旧叶子使用 `--from-date/--to-date`，新增 end-of-day 和 forecast results 使用 `--from/--to`，不能混用。旗标由 [scope option 构造](../../../src/dogopencli/plugins/liquidity/leaves.py) 直接生成。已有 PASS 只代表报告中的选定生产范围，本次未重新执行这些命令。

| 公共路由 | 内容与时间维度 | 公共筛选与原生字段 | 已有证据与限制 |
| --- | --- | --- | --- |
| `payment ptr orders list` | 既有付款试运行订单；按最后修改时间查询 | `--updated-from/--updated-to`，严格 `YYYY-MM-DDTHH:MM:SS+08:00`；映射 `modifiedTimeBegin/modifiedTimeEnd`，返回 `gmtModified` 为 epoch 毫秒 | 已核实原生时间筛选及 UTC+08:00 语义；公共区间左闭右开，最多 31 天，两次稳定读取，单次完整范围最多 500 条；超限拒绝。是 PTR 订单，不是全量付款交易平台 |
| `liquidity cash statements intraday list` | 银行账户交易流水；按业务日期查询，返回交易日期和时刻 | `--account --currency --from-date/--to-date`；`queryDateBegin/queryDateEnd`；保留日期轴 `valueDate` | 原选定历史日 5/5，live/refresh/offline PASS；账户和币种为必需范围 |
| `liquidity cash statements end-of-day list` | 日终银行流水记录；按业务日期查询 | `--entity --account --currency --from/--to`；`queryDateBegin/queryDateEnd`；日期轴 `valueDate` | 选定单日 6/6 三模式 PASS，另有合法空范围；多日及更早保留范围未普遍验证 |
| `liquidity operations asset-trades list` | 资产转移订单；按交易日查询 | `--from-date/--to-date`；`tradingDateBegin/tradingDateEnd`；日期轴 `tradingDate` | 原选定历史日 2/2 三模式 PASS；订单状态不自动证明最终结算，独立 get 仍延期 |
| `liquidity investment returns list --basis accrual` | 投资计提收益记录 | `--from-date/--to-date`；`queryBeginTime/queryEndTime`；日期轴 `transactionDate` | 修复后选定范围 1231/1231 三模式 PASS |
| `liquidity investment returns list --basis cash` | 投资现金收益记录；按结算日查询 | `--from-date/--to-date`；`settlementDateBegin/settlementDateEnd`；日期轴 `settlementDate` | 选定范围 595/662；普通 live/refresh 带告警提供数据，严格拒绝，失败不发布缓存 |
| `liquidity forecast cashflows list` | 预计现金流明细；预计资金时间维度 | `--account --currency --from-date/--to-date`；`beginValueDay/endValueDay`；日期轴 `expectValueDateTime`，原生格式 `YYYYMMDDHHmm` | 原选定历史日 1 条三模式 PASS；单响应无原生 total。是预计流量，不是历史实际流水或预测版本快照 |
| `liquidity investment holdings list` | 原生查询日期范围内的投资持仓快照 | `--date` 映射原生字段 `date`，并参与缓存作用域；行 `valueDate` 不代表请求快照日期，不能用于过滤快照成员 | pageSize=500；2026-10-03 完整 UAT 发现 native live/refresh 各 1078 条，但旧离线日期过滤错误地仅返回 1 条；现改用按采集时间保留的快照历史，保留全部原生行及其日期、隔离不同查询日期。修复后生产三模式复核另记；属于快照而非交易流 |
| `liquidity investment interest-rates list` | 市场基准利率历史 | `--source market --from-date/--to-date`；`beginDate/endDate`；日期轴 `effectiveDate`，原生日期 `YYYY-MM-DD` | 日期格式修复后选定范围 137/137 三模式 PASS；银行报价路由未启用 |
| `liquidity pricing client-prices list` | 客户价格/版本记录 | `--from-date/--to-date`；`startCostDate/endCostDate`；日期轴 `costDate` | 原选定历史日 34/34 三模式 PASS；固定已验证状态为 DEPRECATED/WAIT_FOR_AUDIT/DRAFT，不代表有效成交价格或实际收费 |
| `liquidity pricing cost-prices list` | 成本价格/版本记录 | `--from-date/--to-date`；`costStartDate/costEndDate`；日期轴 `costDate` | 原选定历史日 800/800 三模式 PASS；不是实际扣费流水 |
| `liquidity pricing factor-values list` | 定价因子观测/版本值 | `--from-date/--to-date`；`costStartDate/costEndDate`；日期轴 `costDate` | 原选定历史日 470/470 三模式 PASS；不是交易流水 |
| `liquidity ledger balances list` | 日期化账本余额，INNER/OUTER | `--book-type --from-date/--to-date`；`valueDateStart/valueDateEnd`；日期轴 `valueDate` | 有日期合同，但指定分页位置仍发生原生业务错误 999；完整采集 BLOCKED，尚无安全兼容方案 |

上述字段与合同分别由 [Liquidity 原有声明](../../../src/dogopencli/plugins/liquidity/leaves.py)、[日终流水声明](../../../src/dogopencli/plugins/liquidity/cash_forecast.py)、[PTR 源码](../../../src/dogopencli/plugins/payment/ptr_orders.py) 和 [PTR 公共帮助](../../../src/dogopencli/plugins/payment/ptr_orders_reading.py) 直接支持。生产范围和状态来自 [原有叶子 UAT 及定点修复](2026-10-02-liquidity-inherited-cli-uat.md)、[新增现金/预测叶子 UAT](2026-10-02-liquidity-spec76-implementation-uat.md)、[PTR 原生合同调查](../payment/2026-09-27-payment-ptr-orders-contract.md)。本次仅核对源码和既有证据，不扩大这些历史验收结论。

后续完整 UAT 补充（2026-10-03）：holdings 的原生请求字段 `date` 与行 `valueDate` 是不同维度。查询 `20261001` 返回 1078 条完整记录，行 `valueDate` 横跨 `20220815..20261001`；旧实现误将后者当作快照覆盖日期，导致离线只保留匹配日期的 1 条。修复保留所有原生行与字段，不推断 `valueDate` 的其他业务含义。缓存现在用精确请求日期隔离作用域，并依 [ADR 0017](../../adr/0017-liquidity-one-million-record-retention.md) 按实际采集时间保留快照历史。该排序轴不冒充后端业务时间；保留上限裁剪了快照时，普通离线返回保留行及不完整告警，严格查询拒绝。旧缺少请求日期作用域的缓存须显式刷新，不能重新解释为正确快照。

## 有 runtime 或 history 名称，但没有后端日期反查

`liquidity investment transactions list` 当前能完整返回投资交易列表，但已发布合同不提供日期筛选。`transactionDate` 出现在行中，不等于存在可传给后端的时间筛选。其 `PROFILE_HISTORY` 意味着完整当前列表按本地采集时间保留，不保证可查询某个尚未采集的过去日期。`operations forwards`、`operations prefunds`、`investment compound-ledger`、`forecast adjustments`、`risk metrics` 也未发布后端日期旗标；其中 metrics 可返回原生指标序列，仍不能指定历史日期采集。来源：[原有合同和 scope_options](../../../src/dogopencli/plugins/liquidity/leaves.py)、[profile 定义](../../../src/dogopencli/plugins/liquidity/spec.py)。

`cash balances`、`cash group-balances`、`cash waterlevels` 是当前余额/水位来源；行中的时间及本地连续采集可以形成历史观测，但不建立后端按日期回查旧余额的能力。来源：[余额和组余额合同](../../../src/dogopencli/plugins/liquidity/cash_forecast.py)、[水位合同](../../../src/dogopencli/plugins/liquidity/leaves.py)。上述九个非日期 runtime list 与前表的十二个日期 runtime list 合计二十一个。

`liquidity operations decisions history --id` 能返回指定决策报告的原生版本历史，属于另一种真实历史来源：按对象 ID 查询，不支持时间范围遍历。版本与当前报告经过独立 native detail 验证，修复后的选定对象三模式 PASS。决策 list、执行 list/get 等仍延期，不能视为已可运行的日期交易查询。来源：[history 和延期声明](../../../src/dogopencli/plugins/liquidity/leaves.py)、[history 验证实现](../../../src/dogopencli/plugins/liquidity/decision_history.py)、[定点验收](2026-10-02-liquidity-inherited-cli-uat.md)。

Payment 的 channel/cost/SLA/rules/PTR cases，以及 Collection 的已注册配置、成本、SLA、VA rule/capacity、network 和 account-isolation 查询，没有与 PTR orders 等价的历史交易时间范围接口。配置中的生效时间、行中 raw 时间戳或缓存 `fetched_at` 不能作为已发布的历史交易查询合同。来源：[实际注册入口](../../../src/dogopencli/plugins/__init__.py)、[Collection network 配置](../../../src/dogopencli/plugins/collection/network_config.py)、[account-isolation 帮助](../../../src/dogopencli/plugins/collection/account_isolation_reading.py)、[Payment PTR cases 范围说明](../../../src/dogopencli/plugins/payment/ptr_reading.py)、[Payment rules 帮助](../../../src/dogopencli/plugins/payment/rules_reading.py)。

## Forecast 的历史实证

上一轮完成的十个日期按 **2026 年、全天、pageSize=5000、ordinary live** 查询，后端各页 total 都稳定，所有返回行的 `valueDate` 都匹配所选日期。八个范围因跨页重复带 `INCOMPLETE_RESULT`，两个单页范围完整成功；配置和正式缓存未改动。结果汇总：

| 日期 | 唯一行 / 原生 total | 跨页重复 | 结果 |
| --- | ---: | ---: | --- |
| 2026-09-30 | 24964 / 24969 | 5 | 带告警可用 |
| 2026-09-28 | 25545 / 25556 | 11 | 带告警可用 |
| 2026-08-13 | 25966 / 25971 | 5 | 带告警可用 |
| 2026-07-03 | 25417 / 25421 | 4 | 带告警可用 |
| 2026-06-05 | 25090 / 25098 | 8 | 带告警可用 |
| 2026-05-20 | 26061 / 26070 | 9 | 带告警可用 |
| 2026-04-02 | 24377 / 24383 | 6 | 带告警可用 |
| 2026-03-08 | 1332 / 1332 | 0 | 完整成功 |
| 2026-02-21 | 822 / 822 | 0 | 完整成功 |
| 2026-01-07 | 25757 / 25759 | 2 | 带告警可用 |

原始运行证据保存在忽略且受限访问的 `tmp/forecast-history-batch-20261003T010417Z/verified-results.json`，本报告只保留日期和计数。汇总中 native `gmtCreate` 也落在原历史时段，例如 1 月 7 日记录的创建时间为 UTC 1 月 6 日至 1 月 8 日；这比仅查看 `baseValueDate` 更直接地证明返回了历史创建的记录。本次没有重新执行十个日期查询。

查询语义由 [FORECAST_RESULTS 声明](../../../src/dogopencli/plugins/liquidity/cash_forecast.py) 限定：`--from/--to` 对应 `valueStartDay/valueEndDay`，选择预测业务日期；`--record-from-time/--record-to-time` 对应 `recordStartTime/recordEndTime`，值为 `HHmmss`，来源时区未知。它不是任意 epoch 查询，也没有“截至某时刻”的 as-of 快照参数。日期轴 `valueDate`、预测基准日 `baseValueDate`、记录时刻 `recordCreateTime`、创建时间 `gmtCreate` 各自含义不同，不能互换。

尚未证明历史所有日期连续覆盖、最早保留日、每个日期的全部版本或所有账户完整性。其他有日期合同的命令本次未接受同样的十日期历史跨度验证；推荐后续优先对现金流水和资产转移订单做对应的有界历史探查，再讨论跨数据源关联。

## 方法与证据边界

本次先核对 code-review-graph 的工作树和分支：图指向当前工作树、`feat/sub-cmd-lm`、HEAD `a01562075f31eab50224fb35eea1de0cd27867f8`，覆盖 130 个 Python 文件。结构查询定位注册入口、PTR window 调用方和 Liquidity help 构造。图未覆盖未跟踪的 `cash_forecast.py`、`decision_history.py` 等新增文件，因此针对已知缺口直接读当前工作树源码；枚举实际 `LIST_LEAVES` dataclass 元数据核对二十一个 runtime list 的分类与十二个原生日期合同，未从图缺失推断能力不存在。

研究过程未连接浏览器、执行生产业务查询或写入产品缓存，未改动产品代码。报告中的状态沿用日期明确的既有生产证据；公共路由计数来自当前源码。预测、实际流水、订单、余额快照、利率/价格记录和本地采集历史分别标注，未把名称或字段存在当作已验证的业务语义或历史覆盖保证。
