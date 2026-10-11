# Dogopencli

把产品运营平台的付款、收款与流动性查询带到终端。Dogopencli 面向单人、单机使用，
提供离线缓存查询、显式实时查询，以及适合脚本和 Agent 读取的 JSON 帮助与数据描述。
所有生产业务操作仅查询；登录管理专用本地浏览器，刷新写入本地快照。

## 快速开始

需要 Python 3.10+。实时查询还需要 Google Chrome、运营平台访问权限及人工 SSO 登录；
缓存查询、帮助和数据描述可以离线使用。缓存应存放在本地 Linux 文件系统上，
WSL 用户应使用 Linux 磁盘目录。

### 1. 安装

从 [Releases](https://github.com/proletariat64/dogopencli/releases) 下载 wheel，
在虚拟环境中安装。以下以已发布的 v0.2.4 为例，在下载目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./dogopencli-0.2.4-py3-none-any.whl
dogopencli --version
```

也可以在仓库根目录安装源码：

```bash
python -m pip install -e .
```

### 2. 配置一个查询来源

创建 `~/.config/dogopencli/config.toml`，先添加需要使用的能力。例如账户隔离规则：

```toml
[sources.collection_account_isolation]
kind = "cdp"
```

`cdp` 表示通过专用 Chrome 会话执行已验证的查询。其他能力的配置键见下表；
无需一次配置所有来源。

### 3. 登录、刷新、查询

```bash
dogopencli login
dogopencli auth check
dogopencli refresh collection account-isolation
dogopencli collection account-isolation list --require-fresh --require-complete
```

`login` 默认检查 Payment；`login --domain liquidity` 检查并恢复 Liquidity。
两者使用同一套已配置的专用 Chrome profile，普通浏览器登录不能恢复此 profile。
目标域已有有效的无头会话时直接成功；需要登录时打开可见 Chrome，等待人工
完成 SSO，随后切回无头模式并复验目标域会话。结果明确标识实际检查的 `domain`。
每次新启动 Chrome 都复用并整理初始页面，只保留一个入口页，不再额外追加
入口标签页；模式切换通过正常关闭 Chrome 持久化 cookie 和已关闭标签页记录。
页面整理仅发生在新启动阶段，不在人工输入期间执行；同模式复用不会整理页面。
Payment 人工等待期间仅在现有页面里 fetch 已核实的只读用户初始化接口，不新建/关闭
标签页、不导航表单，也不跟随重定向创建新的 SSO 页面。HTTP 200 本身不代表
成功：用户初始化响应仅作为完成信号，仍需原有域入口导航验证及无头复验；
网络/CORS/响应解析失败会继续
等待并在超时后报不确定状态，不退回会打扰输入的导航轮询。
Liquidity 人工等待只观察现有入口页面的稳定回归和就绪状态，不调用 Payment
用户信息接口；此观察仅是完成候选，成功仍需 Liquidity 入口验证和无头复验。
默认等待 600 秒，可用 `--timeout-seconds` 调整。`auth check` 只检查现有会话，
不会启动或修复浏览器。

之后可直接读取缓存，或明确要求实时查询：

```bash
dogopencli collection account-isolation list --currency GBP --all
dogopencli collection account-isolation list --live --all
```

示例中的币种、业务代码与 ID 应替换为实际返回值；示例筛选结果可以为空。

当前版本默认允许使用已验证的 incomplete 列表：live、离线读取和 refresh
退出 0，`error=null`，每次通过 `meta.warnings` 和 stderr 告警。最新 partial refresh
可替换旧完整缓存；需要完整结果时，查询和刷新都使用 `--require-complete`，
严格刷新会在提交前拒绝。身份、范围、格式及 PTR 稳定性失败继续拒绝。
行为变化与缓存回滚要求见[变更记录](CHANGELOG.md)。

## 可以查询什么

### 离线命令与缓存概览

`snapshot` 按 [#80](https://github.com/proletariat64/dogopencli/issues/80)
提供已安装命令树与本地缓存的元数据概览，默认显示文本树：

```bash
dogopencli snapshot
dogopencli snapshot liquidity cash
dogopencli snapshot liquidity cash balances list --format json
dogopencli snapshot --format table
dogopencli snapshot --format json > snapshot.json
```

路径与 `help` 一致，可选择组或叶子；未知路径与格式退出 2。参数说明和可选值
继续查看 `help` / `describe`。`availability` 的 supported/unsupported 表示当前版本
是否实现该命令；延期叶子和原有原因仍可发现，不表示认证、后端或缓存状态。

缓存概览一起显示存在情况、新鲜度与完整性；JSON 保留各采集的质量、范围与缺口。
缺失缓存的 `rows` 为 null，已验证空采集为 0。`rows` 统计实际保留的业务记录或
原生详情文档，不计内部索引，也不展开详情成员；重叠范围与多次采集可能重复计数，
不是去重查询结果或生产总量。完整性只对声明的保留范围成立。

`updated` 为最新成功采集时间，JSON 同时保留最早时间与逐采集时间；报告时间
`generated_at` 与源观察时间分别保存。新鲜度沿用已有能力/配置策略；时间或策略
缺失时保持未知，多采集质量不同会显示 mixed，最新采集不代表全部缓存。
帮助、描述、认证和 snapshot 控制项没有业务缓存；刷新控制项引用其目标查询缓存。

检查只读配置与 SQLite 的一致视图，不创建文件、不迁移或修复缓存，不启动浏览器、
探测认证、执行查询或刷新。输出只含元数据，范围/采集 ID 是不透明报告标识，
不能作为业务查询参数。缺失、过期、不完整和延期状态退出 0；配置/读取失败退出 1，
保留可读取的树并标记检查错误，JSON 仍可解析。诊断写 stderr。

下表命令均省略 `dogopencli` 前缀。配置键对应 `[sources.<键>]`，
除付款渠道的离线替代源外，使用 `kind = "cdp"`。

| 能力 | 查询命令 | 刷新命令 | 配置键 |
| --- | --- | --- | --- |
| 付款渠道 | `payment channel list` | `refresh payment channel` | `payment_channel` |
| 付款交易成本 | `payment cost list` | `refresh payment cost` | `payment_cost` |
| 付款 SLA 基线 | `payment sla baselines list` / `get --id ID` | `refresh payment sla` | `payment_sla` |
| 同行转账规则 | `payment rules same-bank-transfer list` | `refresh payment rules same-bank-transfer` | `payment_rules_same_bank_transfer` |
| 降本规则 | `payment rules cost-reduction list` | `refresh payment rules cost-reduction` | `payment_rules_cost_reduction` |
| 重试规则 | `payment rules retry list` | `refresh payment rules retry` | `payment_rules_retry` |
| 银存切换规则 | `payment rules bank-switch list` | `refresh payment rules bank-switch` | `payment_rules_bank_switch` |
| PTR 用例 | `payment ptr cases list` | `refresh payment ptr cases` | `payment_ptr_cases` |
| PTR 单据 | `payment ptr orders list`（必填更新时间范围） | `refresh payment ptr orders`（同范围） | `payment_ptr_orders` |
| 收款交易成本 | `collection cost list` | `refresh collection cost` | `collection_cost` |
| 收款 SLA 配置 | `collection sla configs list` / `get --id ID` | `refresh collection sla` | `collection_sla` |
| 收款 VA 规则 | `collection va rules list` / `get --id ID` | `refresh collection va` | `collection_va` |
| 收款 VA 容量 | `collection va capacity list` | `refresh collection va capacity` | `collection_va_capacity` |
| 收款清算系统 | `collection clearing-system list` | `refresh collection clearing-system` | `collection_clearing_system` |
| 收款卡模板 | `collection card-template list` | `refresh collection card-template` | `collection_card_template` |
| 收款账户隔离规则 | `collection account-isolation list` | `refresh collection account-isolation` | `collection_account_isolation` |

只有表中标注 `get` 的能力提供独立详情。详情 ID 来自对应列表；VA 规则使用
`vaRuleId`，付款 SLA 与收款 SLA 使用 `id`。列表摘要不能代替详情。

付款成本固定查询 `FUND_OUT_CHANNEL_TRANS_FEE`，收款成本固定查询
`FUND_IN_CHANNEL_TRANS_FEE`。这些是成本配置，不是实际交易费用。
SLA 是配置目标，不是观测到账耗时。

银行账户 VA 规则是独立对象，因完整分页验证失败仍未实现，见
[#52 与阻塞证据](docs/research/general/2026-09-27-collection-bank-va-rule-blocker.md)。
收款 VA 费用、VA 池、实体账户、余额及生产变更操作不在当前范围。

付款 flow 规则的真实详情存在身份不一致，#54 暂未交付，也未提供 list-only 替代；
见[复核证据](docs/research/payment/2026-09-27-payment-flow-rule-blocker.md)。PTR 当前实现流出用例库和有界单据查询；
网络总览、账户库、巡检规则及两类批次尚未通过各自契约门槛，未注册命令。

## 流动性查询（当前源码分支）

当前发布版本为 **v0.3.0**，依据 [#72](https://github.com/proletariat64/dogopencli/issues/72)、
[#76](https://github.com/proletariat64/dogopencli/issues/76) 和
[PR #83](https://github.com/proletariat64/dogopencli/pull/83) 和
[#87](https://github.com/proletariat64/dogopencli/issues/87) 和
[#88](https://github.com/proletariat64/dogopencli/issues/88) 和
[#89](https://github.com/proletariat64/dogopencli/issues/89) 和
[#97](https://github.com/proletariat64/dogopencli/issues/97) 和
[#98](https://github.com/proletariat64/dogopencli/issues/98) 和
[#103](https://github.com/proletariat64/dogopencli/issues/103) 和
[#104](https://github.com/proletariat64/dogopencli/issues/104) 和
[#105](https://github.com/proletariat64/dogopencli/issues/105)，以及 Batch F
[#109](https://github.com/proletariat64/dogopencli/issues/109)–
[#112](https://github.com/proletariat64/dogopencli/issues/112)，以及
[PR #121](https://github.com/proletariat64/dogopencli/pull/121) 和
[PR #126](https://github.com/proletariat64/dogopencli/pull/126)，以及
[PR #138](https://github.com/proletariat64/dogopencli/pull/138)、
[PR #140](https://github.com/proletariat64/dogopencli/pull/140)、
[PR #142](https://github.com/proletariat64/dogopencli/pull/142) 的实现共支持 98 个查询叶子；
共 132 个查询叶子，其中 34 个延期叶子（12 list、22 get）可通过帮助发现，
执行返回 `UNSUPPORTED_CAPABILITY`，不会返回占位数据。源码可使用本节命令；
v0.2.8 包含 #97/#98 及 #103/#104/#105 的新增能力（85 supported / 46 unsupported）；
v0.3.0 还包含 [PR #135](https://github.com/proletariat64/dogopencli/pull/135) 的 list 参数契约统一，
以及 [PR #143](https://github.com/proletariat64/dogopencli/pull/143) 的登录闪屏和重复标签页修复。
具体支持范围与生产验收结果见下文。
#105 因子类型定义目录属于 reference，CLI 生产 UAT 状态见[独立契约](docs/research/general/2026-10-05-factor-definitions-contract.md)。
已实现命令的完整性、告警和后端阻塞须分别判断，
验收范围见[完整 UAT](docs/research/general/2026-10-03-liquidity-full-cli-uat.md)。

[#88](https://github.com/proletariat64/dogopencli/issues/88) batch B 的三个列表
`risk events list`、`risk anomalies list`（runtimes）和 `rules monitoring list`
（settings）当前放行 **2/3**。events/anomalies 分别固定原生
`RISK_EVENT` / `RISK_ALERT`，使用字符串 `id`，不做本地异常分类。
两者必须同时提供 `--from-date YYYYMMDD --to-date YYYYMMDD`，后者恰好比前者晚一天；
请求发送原生 `YYYY-MM-DD`，缓存按命令、原生范围和采集时刻隔离。
源端 `GMT+08` 时间原样保留，不能把显示日期或 `fetched_at` 当作服务端筛选边界。
监控规则仍 unsupported：当前查询为空，监控规则类型筛选、非空结构和身份尚未验证。
离线 help/describe/snapshot 说明实际支持范围和 blocker，详见
[batch B 证据与继续条件](docs/research/general/2026-10-04-liquidity-issue88-release-gates.md)。

```bash
dogopencli refresh liquidity risk events --from-date 20260925 --to-date 20260926 --require-complete
dogopencli liquidity risk events list --from-date 20260925 --to-date 20260926 --all
dogopencli refresh liquidity risk anomalies --from-date 20260925 --to-date 20260926 --require-complete
dogopencli liquidity risk anomalies list --from-date 20260925 --to-date 20260926 --all
```

```toml
[sources.liquidity]
kind = "cdp"
```

```bash
dogopencli help liquidity --format text
dogopencli login --domain liquidity
dogopencli auth check --domain liquidity
dogopencli refresh liquidity investment holdings --date 20261001
dogopencli liquidity investment holdings list --date 20261001
dogopencli refresh liquidity investment holdings detail get --investment-no HOLDING_ID
dogopencli liquidity investment holdings get --investment-no HOLDING_ID
dogopencli liquidity investment returns list --basis cash \
  --from-date 20260930 --to-date 20260930
dogopencli describe liquidity investment returns list
dogopencli liquidity forecast results list --from 20261001 --to 20261001 \
  --record-from-time 000000 --record-to-time 235959 --live --all
```

日期与身份须替换为实际查询范围和原生 ID；查询默认离线，`--live` 不写缓存。
列表刷新与详情刷新独立：`refresh liquidity <资源>` 仅刷新列表，
`refresh liquidity <资源> detail get|history` 仅刷新指定原生详情；后者必填身份见叶子帮助。
缺失或被驱逐的缓存给出明确错误/刷新提示；不会用列表摘要代替详情或推断源对象不存在。
每个叶子跨范围/采集保留最多 1,000,000 条主记录；时序驱逐会警告并报告保留范围，
非时序超限拒绝刷新。新鲜度按所读采集/详情自己的时间判断，不证明源业务数据年龄。

以下省略 `dogopencli liquidity` 前缀；`returns list` 包含 accrual/cash 两个来源，
参数和逐变体契约以 `help` / `describe` 为准。

| 资源 | 已实现动作 |
| --- | --- |
| `cash accounts` | `list` |
| `cash balances` | `list` |
| `cash groups` | `list` |
| `cash group-balances` | `list` |
| `cash pool-balances` | `list` |
| `cash credit-usage` | `list` |
| `cash pools` | `list`, `get` |
| `cash credit-lines` | `list` |
| `cash statements intraday` | `list` |
| `cash statements end-of-day` | `list` |
| `cash waterlevels` | `list` |
| `forecast adjustments` | `list` |
| `forecast cashflows` | `list` |
| `forecast results` | `list` |
| `investment benchmarks` | `list` |
| `investment benchmark-values` | `list`（必填生效日期范围） |
| `investment quotes` | `list`（仅 QUOTED，必填起息日期范围） |
| `investment strategy-results` | `list` |
| `investment compound-ledger` | `list`, `get` |
| `investment holdings` | `list`, `get` |
| `investment interest-rates` | `list` |
| `investment products` | `list`, `get`, `history` |
| `investment returns` | `list` |
| `investment strategies` | `list`, `get` |
| `investment transactions` | `list`, `get` |
| `ledger accounts` | `list` |
| `ledger balances` | `list` |
| `ledger customers` | `list`, `get` |
| `network account-capabilities` | `list`, `get` |
| `network bank-baselines` | `list`, `get` |
| `operations asset-trades` | `list` |
| `operations decisions` | `list`（必填启动与创建时间范围）, `get`, `history` |
| `operations forwards` | `list`, `get` |
| `operations prefunds` | `list`, `get` |
| `operations swaps` | `list`（必填交易日期范围） |
| `operations transfers` | `list`（必填交易日期范围）, `get` |
| `pricing client-prices` | `list` |
| `pricing cost-prices` | `list` |
| `pricing factor-values` | `list` |
| `pricing strategies` | `list` |
| `reference banks` | `list` |
| `reference business-lines` | `list` |
| `reference calendars` | `list` |
| `reference entities` | `list` |
| `risk metrics` | `list` |
| `risk sla` | `get` |
| `risk thresholds` | `list`, `get` |
| `rules action-mapping` | `list` |
| `rules forecast` | `list` |
| `rules funding` | `list` |
| `rules fx-settlement` | `list` |
| `rules notification` | `list`, `get` |
| `rules operation` | `list`, `get` |
| `rules realtime` | `list`, `get` |
| `rules transfer` | `list`, `get` |
| `rules waterlevel` | `list`, `get` |

### Swap 订单列表

`operations swaps list` 与对应 refresh 必须同时提供 `--trade-from` 和
`--trade-to`，格式为 `YYYYMMDD`，包含两端交易日期。缺失、单边或倒置范围在访问
传输前拒绝；原生无日期全范围有重复记录，未开放。每个精确日期范围独立缓存，
不跨范围拼接记录。`get` 继续返回 `UNSUPPORTED_CAPABILITY`。

```bash
dogopencli refresh liquidity operations swaps --trade-from 20260901 --trade-to 20261001
dogopencli liquidity operations swaps list --trade-from 20260901 --trade-to 20261001 --all
dogopencli describe liquidity operations swaps list
```

正式注册 CLI 的生产只读 UAT 已通过 21/21；代表范围为 15 条订单、两页、无重复或
缺失，refresh 与离线全量记录一致，live 不写缓存。见
[验收记录](docs/research/general/2026-10-04-funding-execution-batch-acceptance.md)。
四列表 batch 当前交付 **1/4**：`operations demands list`、`operations executions list`
和 `investment investable-funds list` 因缺少非空原生结构、身份及业务语义证据，
继续 unsupported；[#82](https://github.com/proletariat64/dogopencli/issues/82) 及其
实施、验收 issues 保持开放。

普通 live 对已验证的不完整采集返回有效数据、完整性 false、`INCOMPLETE_RESULT`
告警，顶层 `error=null`、退出码 0；`--require-complete` 拒绝部分数据。
默认 incomplete refresh 原子替换旧缓存并告警；严格刷新保留旧缓存。
固定-total 合同内的后端 total 变化仍返回 `INVALID_RESPONSE`。
`ledger balances list` 已有查询实现，但后端业务错误 999 仍阻塞完整采集。
`cash pool-balances list` 提供固定 BANK 范围的现金池余额快照；
`refresh liquidity cash pool-balances` 显式采集，默认 list 离线读取，`--live` 不写缓存。
账面余额 `currentBalance` 与可支付余额 `currentAviBalance` 分开保留。
成员原币余额对应 `currency`，`equv` 折算余额对应 `bankCurrency`；
池汇总遵循原生 UI 的 USD 显示口径，不能用配置 `mainCurrency` 替换。
池余额/valueDate 独立于成员金额和成员时间，不强制与成员求和相等；
成员观察时间及空币种保持 unknown，不把采集时间当余额时间。
保留负数、空字符串和 null；不提供业务日期查询、历史命令或资金归集操作。
详见 [现金池余额契约](docs/design/liquidity-pool-balances-v0.1.0.md)。

`cash credit-usage list` 原样读取授信及其 `bankAccountCreditLineList` 成员树；
`refresh liquidity cash credit-usage` 显式采集到独立 runtimes 缓存，默认离线，
`--live` 不写缓存。保留共享/非共享标志、两套原生金额、币种及 `mergeFlag`，
不合并成员、不计算总额或汇率，也不以额度大小、求和或已用/可用关系拒绝数据。
带逗号的金额字符串、空值、负数及未知业务值原样保留；使用观察时间明确 unknown，
不从有效期、配置修改时间或采集时间推算。已有 `credit-lines` settings 缓存不变。
详见 [授信使用读取契约](docs/design/liquidity-credit-usage-v0.1.0.md)。

用户确认 `network product-baselines` 已停用，其 `list`/`get` 已从目录移除；
银行基线和付款 SLA 基线不受影响。#98 原始四项中，池余额、授信使用和报价三项已实现，
产品基线一项退役；各项生产验收状态单独记录。

`investment quotes list --from-date YYYY-MM-DD --to-date YYYY-MM-DD` 仅查询 QUOTED。
起息日起止边界必填，原生 `rowStart=0/pageSize=5000` 单次响应无总数字段；
`refresh liquidity investment quotes --from-date ... --to-date ...` 发布独立缓存，
默认离线，`--live` 不写缓存。缓存按完整请求日期范围隔离，不跨范围拼接或推定完整性。
`quote` 为原生百分比，`ticketSize` 为起存金额，O/N 为隔夜；时间按用户确认的
UTC+08:00 解释，仍保留原生字符串，请求 `timeZone=null` 不变。
金额、利率、期限、日期和值均不做业务运算或改写；`curMaxLimitAvailable` 含义仍未确认。
WIN 后台未实现，首版不提供。报价列表契约详见
[报价读取契约](docs/design/liquidity-quotes-v0.1.0.md)。

### 三项原生详情（#136）

以下 getter 默认读取独立详情缓存；先显式刷新一个对象，或使用 `--live`
直接查询而不写缓存。列表刷新不采集详情，已有列表也不能替代缺失的详情缓存。

```bash
dogopencli refresh liquidity operations demands detail get --task-id <TASK_ID>
dogopencli liquidity operations demands get --task-id <TASK_ID>
dogopencli refresh liquidity network realtime detail get --network-id <NETWORK_ID>
dogopencli liquidity network realtime get --network-id <NETWORK_ID>
dogopencli refresh liquidity investment quotes detail get --quotation-order-id <QUOTATION_ORDER_ID>
dogopencli liquidity investment quotes get --quotation-order-id <QUOTATION_ORDER_ID> --live
```

三种身份均为非空原生字符串，不接受通用 `--id` 或列表分页/日期参数。
需求详情只公开 FUND_REQUIRE 核心字段，原生空租户回显保持空值；请求租户另列元数据。
Realtime 详情公开网络配置及返回的版本，不提供指定版本查询，也不推断路由或执行结果。
报价详情使用原生 form POST，并以 `quotationDetail.quotationId` 核对请求身份；
保留 `quotationDetail`、`productDetail` 原生层次及金额/百分比精度。
人员、附件、自由文本及无关业务动作不进入首版投影。
身份冲突、认证或业务失败均保留旧详情缓存，`--live` 失败不回退。
剩余 getter 的资格门槛见 [#137](https://github.com/proletariat64/dogopencli/issues/137)；
本批权威规格为 [#136](https://github.com/proletariat64/dogopencli/issues/136)。
实施后独立生产 UAT 已通过 3/3，详见
[验收记录](docs/research/general/2026-10-07-liquidity-getters-acceptance.md)。

没有已验证查询合同的叶子继续延期，如 wallets、quote-groups；
独立验证过的详情不受此影响。
[#98 本轮核验](docs/research/general/2026-10-04-liquidity-issue98-gates.md)记录池余额、
授信使用、产品基线和报价的逐项门槛；调查记录不等于新增能力或生产 CLI UAT。
[证据与未验证事项](docs/research/general/2026-10-01-liquidity-live-probes.md)，
[缓存决策](docs/adr/0016-liquidity-independent-list-and-detail-caches.md)。

### RFQ 子任务详情与账户上下文路由额度（#139）

```bash
dogopencli refresh liquidity investment rfqs detail get --inquiry-sub-task-id <SUBTASK_ID>
dogopencli liquidity investment rfqs get --inquiry-sub-task-id <SUBTASK_ID>
dogopencli refresh liquidity network route-quotas detail get --route-id <ROUTE_ID> --account-alias <ACCOUNT_ALIAS>
dogopencli liquidity network route-quotas get --route-id <ROUTE_ID> --account-alias <ACCOUNT_ALIAS> --live
```

RFQ 使用列表的子任务 `inquirySubTaskId`，原生请求与详情回显虽然名为
`inquiryTaskId`，仍表示该子任务；父任务引用不能替代。只接受 TARGET_RFQ，
保留原生询价成员、状态、日期与金额精度，排除自由文本及内部流程 ID。

`route-quotas` 是指定 route/account alias/固定租户上下文的额度聚合，
保留动态和静态额度数组的顺序、重复项及空 quotaId。
请求范围另列 metadata；缺少原生身份回显时不会添加虚构身份。
原生 count 不用作数组总数。`network routes get` 仍延期。
两者默认读取独立详情缓存，refresh 发布一个对象，live 不写缓存或回退；
硬失败保留已有 capture。资格化及独立验收见
[本轮报告](docs/research/general/2026-10-07-liquidity-getter-qualification.md)。

### 资产交易根与报价组版本详情（#141）

```bash
dogopencli refresh liquidity operations asset-trades detail get --order-no <ORDER_NO>
dogopencli liquidity operations asset-trades get --order-no <ORDER_NO>
dogopencli refresh liquidity investment quote-groups detail get --quotation-group-row-id <PHYSICAL_ROW_ID>
dogopencli liquidity investment quote-groups get --quotation-group-row-id <PHYSICAL_ROW_ID> --live
```

资产交易按根 `orderNo` 读取独立原生交易和产品字段；不包含归属尚未证明的日志。
产品保留原生 `assertProductCategory` 等拼写，金额、日期和未知状态保持来源值。
认证租户另列 metadata，不制造缺失的原生租户回显。

报价组使用原生 UI/历史链接选中的物理版本行 `id`，不是业务 `quotationGroupId`。
wire 字段虽然名为 `quotationGroupId`，仍传入物理行 ID；不接受隐式最新版本解析或额外版本参数。
所选根版本不会被历史中的较新版本替换，不同物理行保持独立缓存。
联系人和版本历史保持原生对象数组；附件下载和审批动作排除。
`quote-groups list` 继续 unsupported，不因详情成功启用全列表。

两者默认离线，显式 detail refresh 只发布验证通过的对象，live 不写缓存或回退；
硬失败保留已有 capture。详见 [#141 规格](https://github.com/proletariat64/dogopencli/issues/141)
及[独立验收记录](docs/research/general/2026-10-07-liquidity-asset-quote-group-getters.md)。

### 四项有界列表（Batch F，#109–#112）

`risk sla list` 读取风险 SLA 配置摘要，固定一次 5000 大页，按原生总数和
`slaConfigId` 核对覆盖。列表不包含尚未证明 populated 的规则数组，也不爬取详情。
`forecast accuracy list` 必填单个 `--account-alias` 和 `--record-date YYYY-MM-DD`，
一次最多 100 条基础记录，每条关联原生准确率指标；创建查询日与 `valueDate` 分开，
不计算本地百分比。`risk account-capacity list` 必填 1–10 个不同 `--account-alias`，
只查询明确集合；没有原生全账户总数，也不自动发现账户。`availableResource`
与 `outFlowCapacity` 分开保留。`investment rfqs list` 仅支持 TARGET_RFQ，
必填 `--from-date/--to-date YYYY-MM-DD`；子任务 `inquirySubTaskId` 与父引用
`inquiryTaskId` 分开，同父不同子任务均保留，FULL_RANGE_RFQ 不启用。

```bash
dogopencli refresh liquidity risk sla --require-complete
dogopencli liquidity risk sla list --all
dogopencli refresh liquidity forecast accuracy --account-alias ACCOUNT_ALIAS --record-date 2026-10-05 --require-complete
dogopencli liquidity forecast accuracy list --account-alias ACCOUNT_ALIAS --record-date 2026-10-05 --all
dogopencli refresh liquidity risk account-capacity --account-alias ACCOUNT_ALIAS_A --account-alias ACCOUNT_ALIAS_B --require-complete
dogopencli liquidity risk account-capacity list --account-alias ACCOUNT_ALIAS_B --account-alias ACCOUNT_ALIAS_A --all
dogopencli refresh liquidity investment rfqs --from-date 2026-01-01 --to-date 2026-10-05 --require-complete
dogopencli liquidity investment rfqs list --from-date 2026-01-01 --to-date 2026-10-05 --all
```

默认离线、显式 refresh 原子发布，`--live` 不写库、不回退。SLA 使用 settings
snapshot；其余三项使用按 capture 时间保留的 runtimes history，精确 scope 不混合。
原生金额、计数、状态和时间保持原值，未证明的来源时区保持 unknown。
rules monitoring 继续 HOLD。详见
[四项读取契约](docs/design/liquidity-batch-f-v0.1.0.md)和
[逐叶验收记录](docs/research/general/2026-10-05-liquidity-batch-f-acceptance.md)。

决策列表的启动时间与创建时间分别使用原生 `YYYY-MM-DD HH:mm:ss` 闭区间；
四个边界均必填。转账列表使用原生交易日期 `YYYYMMDD` 闭区间；
保留原始 `gmtCreate`，不据此转换时区、筛选或按展示日期分区。
列表缓存独立于原生详情和历史缓存。以下刷新仅更新配置的本地缓存：

```bash
dogopencli refresh liquidity operations decisions \
  --start-from "2026-09-30 00:00:00" --start-to "2026-09-30 23:59:59" \
  --created-from "2026-09-30 00:00:00" --created-to "2026-09-30 23:59:59" \
  --require-complete
dogopencli refresh liquidity operations transfers \
  --transaction-from 20260930 --transaction-to 20260930 --require-complete
dogopencli liquidity operations transfers list \
  --transaction-from 20260930 --transaction-to 20260930 --all
```

### 投资基准、策略结果与计价账单（batch C）

[#89](https://github.com/proletariat64/dogopencli/issues/89) 四列表当前交付 **2/4**：
`investment benchmark-values list` 查询某一天、某类资金性质（红黄绿）、某种
投资策略（被动活期利息或定期利息）及币种的市场利息基准。必填
`--from-date` / `--to-date`（`YYYYMMDD`，包含两端，固定原生 GMT+08）。
用户确认业务身份为 `effectiveDate + strategyBenchmarkType + currency + colorType`；
原生 `id` 为空，保留原值但不用于合并。利率 `value` 单位为百分数，保留原始字符串
精度，不参与身份。同次采集同键不同值拒绝；后续刷新可以修订该基准。

新增本地派生 `primaryId`，便于单字段引用：
`bmv1:GUAPW3SG:20261002:passiveInterestBenchmark:USD:GREEN`。
固定顺序为版本前缀、租户、生效日期、策略类型、币种、资金颜色；各段使用 UTF-8
百分号编码，仅保留 RFC 3986 非保留字符。利率修订、刷新时间和查询范围不改变 ID；
原生 `id` 和四字段业务身份保留。新字段进入输出、表格及缓存，支持
`--fields primaryId`。缓存契约升级到 v2，已有 v1 缓存保留，先 refresh 再离线读取。

`investment strategy-results list` 支持 `FUND_DECISION_TASK` 与
`PRODUCT_DECISION_TASK`，必须显式提供 `--task-type`、`--trigger-from` 和
`--trigger-to`（`YYYYMMDD`，原生 GMT+08，包含两端）。两个变体与精确触发日期范围
独立缓存；原生 `id` 是任务身份，策略 ID 是独立引用。任务状态不代表投资执行成功。

```bash
dogopencli refresh liquidity investment benchmark-values --from-date 20260928 --to-date 20261004 --require-complete
dogopencli liquidity investment benchmark-values list --from-date 20260928 --to-date 20261004 --all
dogopencli describe liquidity investment benchmark-values list
dogopencli refresh liquidity investment strategy-results --task-type FUND_DECISION_TASK --trigger-from 20260706 --trigger-to 20261004
dogopencli liquidity investment strategy-results list --task-type FUND_DECISION_TASK --trigger-from 20260706 --trigger-to 20261004 --all
dogopencli describe liquidity investment strategy-results list
```

CDP 9223 正式注册 CLI 生产只读 UAT：基准值 **165/165、17 页**，
单日 **33/33**，完整空范围刷新和离线读取通过；资金任务 **50/50**、产品任务 **7/7**，
独立完整采集；离线读取同一 capture 一致，live 不写缓存。金额保留原生字符串与精度；
`investmentAmount` 来源标签为等值 USD，不做本地换算；`triggerDate` / `resultTime`
为 epoch 毫秒，业务日期与 `fetched_at` 分开。用户与自由文本字段不进入输出及缓存。

Batch C 的其余两叶子继续 unsupported：`valuations` 非空来源实际为 fee-order，
由下述 #97 新命令独立表达；DEPOSIT / LOAN 账单查询仍为空，不能据此放行。
Batch C 本身没有新增 get/history；其余目标由 #72 继续追踪。
见[逐叶证据与继续条件](docs/research/general/2026-10-04-liquidity-batch-c-gates.md)。

### #97：真实详情与费用订单

新增 `investment strategy-results get`、`risk events get`、`risk anomalies get`
三个真实详情，以及独立命名的 `pricing fee-orders list`。策略详情必填任务 ID 与
`--task-type`，资金/产品两类分别验证；风险详情按命令验证 `RISK_EVENT` / `RISK_ALERT`。
详情独立 refresh，离线缺失提示刷新；列表刷新不会爬取详情，live 不写缓存。
风险子事件分页和被排除的处理历史不在单对象详情的完整性声明中。

```bash
dogopencli refresh liquidity investment strategy-results detail get --task-id TASK_ID --task-type FUND_DECISION_TASK
dogopencli liquidity investment strategy-results get --task-id TASK_ID --task-type FUND_DECISION_TASK
dogopencli refresh liquidity risk events detail get --risk-event-id EVENT_ID
dogopencli liquidity risk events get --risk-event-id EVENT_ID
dogopencli refresh liquidity risk anomalies detail get --risk-event-id ALERT_ID
dogopencli liquidity risk anomalies get --risk-event-id ALERT_ID
dogopencli refresh liquidity pricing fee-orders --from-date 20260801 --to-date 20260831 --require-complete
dogopencli liquidity pricing fee-orders list --from-date 20260801 --to-date 20260831 --all
```

费用订单按包含两端的 Service Date 查询，每次最多 31 个日历日，固定发送原生
GMT+08 查询设置。费用使用 `pricingCurrency`，交易金额使用 `currency`；金额原样保留，
不计算投资估值。源端无时区的时间字符串不推断 UTC 偏移；旧 valuations 命令和缓存
保持独立，不提供别名或迁移。

本批被接受的四个候选已实现 **4/4**：解除三个旧 unsupported，新增一个费用订单叶子。
原第五项国家／地区基础数据已按用户决定从需求和目录撤除，不导入，也不保留
unsupported 入口；撤除不计为实现。整合 #97/#98 后目录共 131 项
（85 supported / 46 unsupported）。四个详情变体和费用订单注册 CLI 生产 UAT
共 **24/24** 通过，详见[本次证据与验证](docs/research/general/2026-10-04-liquidity-issue97-gates.md)。
#97 已随 PR #99 合并关闭；#98 等待 PR #100 合并，尚未发布新版本。

## 缓存、实时查询与刷新

| 操作 | 数据来源 | 是否更新本地缓存 |
| --- | --- | --- |
| 普通 `list` / `get` | 已发布的 SQLite 快照；不联网、不启动浏览器 | 否 |
| 查询加 `--live` | 当前 CDP 会话；失败不回退缓存 | 否 |
| `refresh …` | 配置的 CDP 或渠道 snapshot 来源 | 是，原子发布 |
| `help` / `describe` | 随安装包发布的命令与字段说明 | 否，也不读取配置或缓存 |

没有缓存时普通查询返回 `CACHE_MISS`。缓存默认有效期为 72 小时；默认允许读取旧数据，
但会标记 `stale`。需要时加 `--require-fresh` 或 `--require-complete`，不会因此自动刷新。
各能力及来源的快照相互隔离。

刷新通过有效性校验后可替换快照；完整或安全 partial 均默认退出 0，硬失败保留旧数据。
若后端明确拒绝单条详情，刷新可以发布真实列表行与 `detail=null` 的部分快照，
标记 `dataset_complete=false` 并持续告警。此时旧详情可能被替换；
`refresh --require-complete` 在提交前拒绝，严格读取也拒绝该快照，缺详情的 `get` 失败。
详情拒绝条件见 [ADR 0010](docs/adr/0010-collection-va-partial-detail-tolerance.md)，
默认结果处置由 [ADR 0019](docs/adr/0019-usable-incomplete-acquisitions.md) 修订。

显示分页不等于后端采集分页。收款成本、VA 规则、清算系统、卡模板及账户隔离规则
以及上述四项付款规则使用各自验证过的单页采集契约；安全数量缺口会标 incomplete 并告警，
不猜测下一页。VA 容量采用已验证的多页采集与最终动态总数校验。
`--limit` 只控制本地展示，不改变完整性证据。

账户隔离采集拒绝仅在后端筛选场景观察到的 null 列表／全零分页响应，避免把未知状态
发布为空快照；正确回显页码、页大小及零总数的空数组可以接受。见
[账户隔离契约](docs/research/general/2026-09-27-collection-account-isolation-contract.md)。

## 常用查询方式

所有列表默认输出 JSON，显示前 100 行，偏移量为 0。

| 选项 | 用途 |
| --- | --- |
| `--limit N --offset N` | 显示窗口；limit 必须为正整数，offset 为非负整数 |
| `--all` | 显示全部匹配行；与显式 `--limit` / `--offset` 冲突 |
| `--fields id,currency` | 仅保留指定顶层字段，保留选中的完整嵌套值和质量 metadata |
| `--format table` | 以表格阅读；默认 `--format json` |
| `--live` | 显式实时查询，不写缓存 |
| `--require-fresh` | 拒绝超过 TTL 的缓存 |
| `--require-complete` | 要求来源完整；VA 规则还要求详情完整 |

```bash
dogopencli collection sla configs list --currency USD --currency EUR --region US --all
dogopencli collection sla configs get --id CONFIG_ID
dogopencli collection va rules get --id VA_RULE_ID --live
dogopencli collection va capacity list --va-rule-id RULE_ID
dogopencli collection clearing-system list --currency GBP --format table
dogopencli collection card-template list --template-id TEMPLATE_ID --live
dogopencli collection account-isolation list --all --fields id,currency
```

### 收款筛选

以下筛选在缓存与实时查询中均使用本地精确字符串匹配：同字段重复值取 OR，
不同字段取 AND，区分大小写，`*` 按字面值处理。空值或纯空白参数会被拒绝，
有效值不裁剪、不标准化，缺失或 null 字段不会匹配。先筛选、排序，再应用显示窗口和投影。

| 列表 | 筛选参数 |
| --- | --- |
| SLA 配置 | `--business-line`、`--entity`、`--currency`、`--region` |
| VA 容量 | `--va-rule-id`、`--bank-va-rule-id` |
| 清算系统 | `--bank-location`、`--currency`、`--system-type`、`--system-name`、`--status` |
| 卡模板 | `--bank-location`、`--currency`、`--bank`、`--template-name`、`--template-id`、`--status` |
| 账户隔离规则 | `--opening-rule-id`、`--business-line`、`--business-region`、`--customer-group`、`--scene-code`、`--collection-region`、`--currency`、`--transaction-type` |

收款成本与 VA 规则列表没有领域筛选。收款刷新不接受筛选条件。
账户隔离的 `customerTags` 和 `currency` 可以包含逗号，需传入完整字符串，CLI 不拆分成员。
VA 容量的行身份是 `ruleId`；`--bank-va-rule-id` 匹配 `bankAccountVaId`，不是查询银行账户规则详情。
容量预警状态没有已验证的筛选选项。

付款 Channel、Cost 和 SLA 筛选的缓存与实时语义有所不同，以对应 `help` / `describe` 为准。
实时付款 Cost/SLA 每字段只接受单值；付款 SLA 的 `--biz-legal-entity` 仅支持实时透传，
其独立筛选效果未验证，缓存模式拒绝该参数。付款 Channel 默认范围为 `EXTERNAL`，
`--payout-type` 还支持 `LIQUIDITY`、`MANUAL`、`SETTLEMENT`。

### PTR 用例

PTR 指生产仿真验证。本命令只读已有流出用例，不发起试跑或修改结果。

```toml
[sources.payment_ptr_cases]
kind = "cdp"
```

```bash
dogopencli refresh payment ptr cases
dogopencli payment ptr cases list --case-type NEGATIVE --all
dogopencli payment ptr cases list --channel CHANNEL --debtor-currency USD --live
dogopencli describe payment ptr cases list --format text
```

支持用例 ID/名称/类型、渠道、付款账户别名、付款/收款币种、清算网络、
OBO/FVT 输入、能力基线 ID、收款账户别名的精确本地筛选。
同项重复 OR、不同项 AND；字符串大小写敏感，空值不匹配，不展开通配符。
默认离线，`--live` 不发布缓存且不回退。

每次采集固定读取两次 5,000 条容量的首批结果；两次必须完整、身份唯一且保留字段一致。
总量超过容量、截断、重复或漂移均报错，刷新失败保留旧缓存。
范围为当前接口可见流出用例库，不保证删除记录或版本历史；`--all` 仅展开该范围。
默认 72h TTL 是缓存策略，不表示验证摘要能保持 72h 最新。

只保留[契约字段清单](docs/research/payment/2026-09-27-payment-ptr-cases-accounts-contract.md)，
省略个人信息、IBAN/BIC、操作人、自由文本及未知字段；详情 `get` 暂缓。
`verifyResult` 表示测试验证结果，预期拒绝也可能通过，不等于付款成功。

### PTR 单据

配置 `sources.payment_ptr_orders` 的 `kind = "cdp"`。刷新与查询都必须提供
`--updated-from`、`--updated-to`，格式严格为 `YYYY-MM-DDTHH:MM:SS+08:00`。
范围按 `gmtModified` 毫秒时间戳计算，包含起点、排除终点，最多 31 天，终点不得晚于当前时间。

```bash
dogopencli refresh payment ptr orders \
  --updated-from 2026-09-01T00:00:00+08:00 --updated-to 2026-09-02T00:00:00+08:00
dogopencli payment ptr orders list \
  --updated-from 2026-09-01T00:00:00+08:00 --updated-to 2026-09-02T00:00:00+08:00 \
  --verify-status VERIFIED --all
```

不同时间范围使用独立缓存；`--all` 不扩大范围。采集会在两端各多查询一秒，
要求两次完整首批结果一致、总量不超过 500 条，再精确排除多取的记录。
超过容量请缩小时间范围，不回退到已发现不可靠的服务端分页。
仅保存每个范围最近一次成功快照，不自动删除历史范围；72h TTL 不保证动态单据保持最新。

支持 PTR ID、用例 ID、渠道、付款账户别名、付款/收款币种、清算网络、
支付状态、验证状态和最终结果的精确本地筛选。三种状态分别保留，不推导 PASS/FAIL。
已知个人信息字段省略，但 `failureReason` 是保留的原始运营失败文本，不能保证其中不含个人信息。
真实详情 `get` 暂缓；[完整契约](docs/research/payment/2026-09-27-payment-ptr-orders-contract.md)。

### 付款规则筛选

四项规则在缓存和实时模式下都先完整采集，再本地筛选；同字段 OR、跨字段 AND，
区分大小写、保留空格、`*` 按字面匹配，空白参数拒绝。刷新不接受筛选。

| 列表 | 筛选参数 |
| --- | --- |
| 同行转账 | `--bank`、`--status` |
| 降本 | `--name`、`--business-line`、`--currency`、`--market`、`--status`、`--entity`、`--obo`、`--fvt` |
| 重试 | `--name`、`--status`、`--communication-mode`、`--integration-mode`、`--entity`、`--business-line`、`--bank`、`--currency`、`--region`、`--bank-account`、`--clearing-network` |
| 银存切换 | `--source-account`、`--source-network`、`--status`、`--target-account`、`--target-network` |

降本的主体/OBO/FVT、重试的主体/业务线/银行/币种/地区/银行账户/清算网络，
按原始字符串数组的成员精确匹配，不拆分逗号。OBO/FVT 不是布尔开关。
银存切换要求嵌套条件在同一适用条件、同一规则内成立，目标账户和网络必须属于同一目标；
返回整个来源节点，保留未匹配的子规则。降本列表是组摘要，不代表完整历史版本。

```bash
dogopencli refresh payment rules retry
dogopencli payment rules retry list --currency USD --currency EUR --all
dogopencli payment rules bank-switch list --source-account SOURCE_ACCOUNT --all
dogopencli describe payment rules cost-reduction list --format text
```

以上命令需先配置对应 `sources.payment_rules_*` 的 `kind = "cdp"`。
具体字段映射和证据见 `describe` 与[查询契约](docs/research/payment/2026-09-27-payment-rules-contract.md)。

## 帮助与导航

```bash
dogopencli
dogopencli help collection
dogopencli help collection account-isolation list
dogopencli collection account-isolation list --help
dogopencli help collection account-isolation list --format text
dogopencli describe collection account-isolation list --format text
```

无参数入口和分组命令提供逐层导航；叶子命令直接执行操作，需要帮助时加 `--help`
或使用 `help <路径>`。帮助默认 JSON，人工阅读可用 `--format text`。

### Data helper

`describe <查询路径>` 提供 JSON Schema、字段说明、来源证据和读取指引，不查询业务数据。
帮助输出使用 `help_version`；描述输出包含 `describe_version`、`schema_version`、
`capability`、`data_schema`、`read_guide` 和 `query_help`。两者直接返回文档对象，
不使用业务查询的 `data/meta/error` envelope。

Agent 或脚本应先读取 `help` 确认参数，再用 `describe` 判断字段含义。Schema 中
`x-evidence` 区分已验证、仅观察和未知事实；`x-observed-values` 不是封闭枚举。
保留缺失、null、空字符串、空数组及原始数值精度，不推断未验证的金额倍率、时间单位或跨域关联。
更完整的领域区别见 [CONTEXT.md](CONTEXT.md)。

## 读取查询结果

JSON 业务结果使用 `data`、`meta`、`error`。先检查退出码和 `error`，再使用数据。

| Metadata | 如何理解 |
| --- | --- |
| `source` / `backend` | 读取方式 `cache/live` 与来源类型 `snapshot/cdp` 是两个维度 |
| `fetched_at` / `stale` | 采集时间与缓存新鲜度；新鲜不等于完整 |
| `complete` / `dataset_complete` | 来源覆盖与数据集完整性；VA 详情拒绝、渠道替代集需分别解释 |
| `simulated` | 是否属于显式替代数据；不能把替代集当作已验证生产全量 |
| `matched_total` / `returned_count` / `has_more` | 当前可用来源中的匹配数与显示窗口，不证明生产覆盖 |
| `loaded_at` / `source_observed_from` / `source_observed_to` | 导入时间与原始观察时间；重新导入不会让旧观察变新 |

`--fields` 不删除质量 metadata。投影后的数据可能缺少 schema 中的必填字段，
应作为部分记录处理。`seqid` 是本地位置，不是跨快照身份；不同能力的 ID 也不是通用 join key。

业务查询和刷新退出码：`0` 成功、`1` 运行失败、`2` 参数错误、`130` 用户中断。
允许的部分结果也可能退出 `0`，因此需要检查质量字段或指定 `--require-complete`。
认证命令使用独立的 `output_version` envelope，参数和运行错误均退出 `1`。

## 配置与本地会话

| 内容 | 默认位置或值 |
| --- | --- |
| 配置 | `~/.config/dogopencli/config.toml` |
| 缓存 | `~/.local/share/dogopencli/cache.sqlite3` |
| 专用 Chrome profile | `~/.local/share/dogopencli/chrome/` |
| CDP 端口 | `9222` |
| 缓存 TTL | `72` 小时 |

配置路径优先级为：认证命令显式 `--config-dir`、`DOGOPENCLI_CONFIG_DIR`、
`DOGOPENCLI_CONFIG`、默认路径。前两者指定目录，`DOGOPENCLI_CONFIG` 指定文件。

可选缓存配置如下；路径请使用本机的实际绝对路径：

```toml
[cache]
path = "/home/YOUR_USER/.local/share/dogopencli/cache.sqlite3"
ttl_hours = 72
```

缓存依赖 SQLite WAL、共享内存及 POSIX 文件锁，不支持 Windows DrvFS/9p 或网络文件系统。
并发刷新返回 `LOCKED`，不会抢占活跃锁。专用 profile 同一时刻由一个 Chrome 进程持有；
不要与日常浏览器共用 profile，也不要使用 CDP 端口 9330–9340。

```bash
dogopencli logout
```

`logout` 清理并验证专用本地认证，不删除业务缓存，也不撤销公司全局 SSO。
Cookie、令牌、profile、私有快照及生产原始响应不得提交到 Git。

### 付款渠道的离线替代源

付款 Channel 的生产全量验收仍受后端分页问题阻塞，见
[Issue #10](https://github.com/proletariat64/dogopencli/issues/10)。可显式使用已整理的私有数据集：

```toml
[sources.payment_channel]
kind = "snapshot"
path = "/absolute/path/to/channel-dataset"
```

运行 `dogopencli refresh payment channel` 导入后，普通查询只读缓存。
数据集不随仓库分发，仅覆盖 `EXTERNAL`，不支持 `--live`，也不证明生产全量；
完整性标记保留这些限制。切回 `kind = "cdp"` 时移除 snapshot 专用的 `dataset_id`，
显式刷新并验证覆盖，不会自动回退。来源类型、路径或显式数据集身份变化后需重新刷新。
见 [ADR 0005](docs/adr/0005-channel-snapshot-source.md)。

## 故障处理

| 错误码 | 建议操作 |
| --- | --- |
| `CONFIG_ERROR` | 检查配置文件路径、对应 source 节和来源类型 |
| `CACHE_MISS` | 执行该能力的刷新命令；来源身份改变也需要刷新 |
| `CACHE_STALE` | 刷新，或明确允许旧数据后移除 `--require-fresh` |
| `INCOMPLETE_RESULT` | 检查覆盖或详情拒绝；VA 规则刷新可能已发布部分快照 |
| `AUTH_REQUIRED` / `BROWSER_UNAVAILABLE` | 执行 `login` 恢复专用会话；Liquidity 使用 `login --domain liquidity`；启动失败时检查 Chrome 日志 |
| `LOCKED` | 等待当前刷新或浏览器操作结束后重试 |
| `INVALID_RESPONSE` | 后端响应不符合已验证契约；保留错误信息并排查，勿视为空结果 |
| `SOURCE_SCOPE_UNAVAILABLE` / `LIVE_SOURCE_UNAVAILABLE` | 检查渠道替代集的范围及实时查询限制 |
| `REQUEST_NOT_ALLOWED` | 请求超出已验证查询允许清单，需要核查实现与契约 |
| `CACHE_ERROR` / `IO_ERROR` | 检查本地权限、磁盘和支持的文件系统 |
| `INTERNAL_ERROR` | 保留 stderr 与错误关联号，提交脱敏问题报告 |

## 未完成的外部验收依赖

- Liquidity 专用登录（[#145](https://github.com/proletariat64/dogopencli/issues/145)）的独立生产认证 UAT 于 2026-10-11 通过 4/4：人工 SSO 与自动 headless 切换、认证检查、重复登录及 Payment 认证检查。共享 OAuth 保持认证的实际行为由用户接受，未人为构造服务端 Liquidity 过期。UAT 使用独立 Chrome/profile 和未占用端口，禁止 9222、9223、9330–9340 及任何活跃会话端口；不得复制生产 cookies/profile。
- 付款 Channel 真实全量 UAT 仍待后端分页故障修复（[#1](https://github.com/proletariat64/dogopencli/issues/1)）；离线替代集不代表生产全量。
- 认证 UAT 的 `logout` 范围仍需单独确认；当前规则查询验收复用已有会话，未执行登出。
- 安静登录轮询已在独立 profile 验证未登录态及连续 fetch 不改变标签页/文档/测试输入，并完成真实人工 SSO、原有认证复验及 headed → headless 持久化闭环；用户确认闪屏消失。另一次全新 profile 验证只有一个可见入口页，登录后 payment/liquidity 认证检查及 payment cost、collection cost、liquidity cash balances 代表性只读查询成功。代表性查询不等于所有命令或全量 refresh 已验收。
- launcher 安全参数变更后的完整生产连接复验仍待完成：用当前默认参数执行 `dogopencli login`，再执行 `dogopencli refresh payment cost`，验证应用会话和采集。此前独立空 profile 的真实 Chrome 检查只证明启用沙箱、未开放通配 Origin 时原生 CDP 可连接，且不可信 Origin 被拒绝；已有会话上的查询成功不能替代该流程。

## 开发与文档

每个新工作树先在其根目录执行 `make bootstrap`。需要已安装的 Python
（3.10 或以上）和 uv；bootstrap 不下载 Python。依赖版本由 `uv.lock` 固定，
使用 uv 共享缓存和硬链接。首次创建环境时，也复用主工作树 `.venv` 中
Python 版本一致且符合锁文件的依赖，避免重复下载已有包。各工作树拥有
独立 `.venv` 和源码绑定，并在结束时验证导入路径。重复运行可补齐依赖。
缓存与工作树须在同一文件系统；可用 `UV_CACHE_DIR` 指定共享缓存目录。
已有环境中的额外包保留。仓库开发命令统一使用 `rtk`：

```bash
rtk proxy make bootstrap
rtk proxy make test
rtk proxy make lint
rtk proxy make doc-guard test-doc-guard
```

测试使用缩短的浏览器轮询间隔，生产探测仍使用 0.25 秒间隔；
验证稳定窗口的测试显式设置其窗口和时钟。`make test` 与 CI 输出最慢的
20 项测试，便于定位新的耗时。CI 对 PR 的合并结果、master 推送和标签推送
运行完整检查；功能分支通过 PR 验证，避免同一 PR 再运行一次分支 push CI。
同一 PR 或引用的新运行会取消过期运行。

业务插件位于 `src/dogopencli/plugins/payment/`、`src/dogopencli/plugins/collection/`
与 `src/dogopencli/plugins/liquidity/`；
认证、受限传输、缓存和输出由共享模块提供。测试使用公开 CLI、假 CDP 与临时 SQLite。
生产验收保持查询范围，并使用私有缓存。

- [文档索引](docs/README.md)：契约、研究、验收与架构决策。
- [领域词汇](CONTEXT.md)：付款、收款、VA 规则与账户对象的区别。
- [贡献约定](AGENTS.md)：代码、测试、浏览器及研究工作流。
- [GitHub Issues](https://github.com/proletariat64/dogopencli/issues)：需求、规格与缺陷。
- [Releases](https://github.com/proletariat64/dogopencli/releases)：安装包与版本记录。

契约与 UAT 报告记录特定日期、账号权限下的验证结果；生产行为变化后需要重新验证。

Batch A ([#87](https://github.com/proletariat64/dogopencli/issues/87)) 两个必需列表的注册生产 CLI UAT 已通过 **2/2**，报价组调查 **1/1**，可选列表放行 **0/1**。当前源码支持数为 **71/133**；报价组继续 unsupported。决策与转账完整刷新分别为 264 与 4,954 条，本地 Kimi 两轴复审均通过。见[本批验收证据](docs/research/general/2026-10-04-liquidity-batch-a-acceptance.md)。

转账规则配置列表（[#103](https://github.com/proletariat64/dogopencli/issues/103)）使用固定租户及默认 entity 范围的一次 GET 大页（5000）。原生 ruleCount、到达数和唯一 ruleId 数一致才 complete；没有自动分页或详情爬取。`refresh liquidity rules transfer` 显式发布 settings capture，普通 `liquidity rules transfer list` 离线读取，`--live` 不写缓存。配置摘要排除动作载荷、人员及运行调度信息；已有 `get --rule-id` 保持独立。生产 CLI UAT 已通过，见[独立验收报告](docs/research/general/2026-10-05-liquidity-transfer-rules-uat.md)；用户已授权本地 Kimi/API 源码与规格审查；[b622caf](https://github.com/proletariat64/dogopencli/commit/b622cafc8ffa06295e4dab8e37e9533963eac8c3) 的静态审查通过，confidence 4/5，测试与生产 UAT 由 root 独立完成。后续纯文档提交未宣称经过 Kimi 复审。

#105 因子类型定义的生产 UAT 与已授权 Kimi 静态审查已通过（confidence 4/5）；审查源码为 [fe33524](https://github.com/proletariat64/dogopencli/commit/fe335248961838db52a0a263f10eff61abe7de1c)，测试与生产 UAT 由 root 独立完成，见[验收报告](docs/research/general/2026-10-05-factor-definitions-uat.md)。后续纯文档提交未宣称经过 Kimi 复审。

### Realtime network 配置列表（#104）

`liquidity network realtime list` 查询原生 decision network settings；先运行
`refresh liquidity network realtime`，默认离线读取；`--live` 不写缓存。只发一次
`rowStart=0/pageSize=5000` 原生请求，缺覆盖持续报告 incomplete；`--require-complete`
拒绝 partial。原生 id 与 routeId 分开，状态不代表实际执行成功。动态性能指标及
私有字段不公开；routes/rules monitoring 不随本列表启用；独立 get 见上方 #136。
v0.2.8 发布时目录为
85 supported / 46 unsupported / 131 total；生产 CLI UAT 204/204 完整及全部 5,304 个投影值对照通过；已随 v0.2.8 发布。

审查修复后独立生产 UAT 再次通过，见[契约与验收报告](docs/research/general/2026-10-05-realtime-network-contract.md)；用户已授权本地 Kimi/API 源码与规格审查；[9488a7f](https://github.com/proletariat64/dogopencli/commit/9488a7f55f604559285572940a36afe2a46e093c) 的静态审查通过，confidence 4/5，测试与生产 UAT 由 root 独立完成。后续纯文档提交未宣称经过 Kimi 复审。
