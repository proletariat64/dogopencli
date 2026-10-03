# Liquidity inquiry specification v0.2.3

权威规格：[GitHub Issue #76](https://github.com/proletariat64/dogopencli/issues/76)。证据：[业务 probe 脱敏报告](../research/general/2026-10-02-cash-forecast-business-probe.md)。本文件是可阅读的规格与完整树副本；原始响应保留在私有目录。

日期：2026-10-02（Asia/Shanghai）。规格冻结时状态：设计更新；当时新增能力尚未实现或通过 CLI UAT。
版本：上一版 spec v0.2.1 + 0.0.2 = **v0.2.3**。这是规格版本，不修改 Python 包或运行时版本。
基线：`feat/sub-cmd-lm` / `c06551a022ab6e277ea5790490b2efc9690876cf`。

后续实施状态（2026-10-02）：八个契约已实现并显式放行；七项通过完整 CLI UAT。用户另行要求预测按 accounts 语义兼容后端缺陷：历史 7504/7502，新全范围 UAT 20135/20129，严格模式及 refresh 拒绝变化的 count，失败不发布且旧缓存保留。本地 CI 与 Greptile apex 复审已通过；放行不表示源端完整或缺陷已修复，见[后端报告与关联建议](../research/general/2026-10-02-forecast-results-backend-count-bug.md)。三个旧 getter 已从活动 CLI 目录移除。以下树和 probe 结论保留规格冻结时基线，不将历史观察改写为实施证据；最新状态见[实施与 UAT 记录](../research/general/2026-10-02-liquidity-spec76-implementation-uat.md)。

## 规格关系与适用范围

本版承接 [原始规格 #71](https://github.com/proletariat64/dogopencli/issues/71)、[实现记录 #72](https://github.com/proletariat64/dogopencli/issues/72) 和 [业务 probe 计划 #74](https://github.com/proletariat64/dogopencli/issues/74)。下面的 cash/forecast 判定、分页表与撤回 getter 清单取代 #71 中相应旧判定；其他八个业务域继承原规格及当前分支契约，未进行新的业务 probe。

所有查询保持 inquiry-only；禁止生成、执行、修改、审批、导出与外部 DI 查询。仍采用同级插件、共享 CDP/auth/transport、默认离线、显式 live 不写缓存、独立 list/native detail 缓存、原子发布、每叶子 1,000,000 主记录上限与既有保留策略。每个业务叶子只有一个 kind：`settings`、`runtimes` 或 `reference`。采集时间与业务观测时间分别表示；未知来源时间不能满足来源新鲜度要求。

规格冻结本次 57 次显式只读请求的结论：53 次业务成功，4 次业务拒绝，无传输失败或截断；覆盖 18 个原延期命令。它们分为 8 项可进入实现、2 项需后端修复、5 项需样本/契约、3 项撤回当前 getter 设计。本次没有重新证明其他日期、主体、pool 类别或多大页范围的完整性，也不代表业务 UAT 已通过。

## 本版 cash / forecast 命令设计

符号：`E` 当前分支已实现（不代表全部 UAT 已通过）；`E!` 已实现但已知后端完整性缺口；`N` 本版接受进入实现；`B` 后端异常阻塞；`D` 样本或契约不足、暂不执行。

```text
dogopencli liquidity
├─ cash
│  ├─ accounts
│  │  ├─ list                    E! reference · pageSize=5000
│  │  └─ get                     B  reference · 原生详情返回999
│  ├─ balances list              N  runtimes  · pageSize=30
│  ├─ statements
│  │  ├─ intraday list           E  runtimes  · pageSize=1000
│  │  └─ end-of-day list         N  runtimes  · pageSize=1000
│  ├─ groups list                N  settings  · pageSize=100
│  ├─ group-balances list        N  runtimes  · pageSize=100
│  ├─ wallets
│  │  ├─ list                    D  reference · 钱包归属未确认
│  │  └─ get                     D  reference · 无已确认钱包身份
│  ├─ wallet-balances list       D  runtimes  · 无原生余额契约
│  ├─ pools
│  │  ├─ list                    N  settings  · BANK，pageSize=100
│  │  └─ get                     N  settings  · BANK，独立原生详情
│  ├─ pool-balances list         D  runtimes  · 观测时间与折算口径缺口
│  ├─ credit-lines list          N  settings  · pageSize=100
│  ├─ credit-usage list          D  runtimes  · 占用时间与共享额度汇总缺口
│  └─ waterlevels list           E  runtimes  · pageSize=1000
├─ forecast
│  ├─ results list               N  runtimes  · pageSize=5000
│  ├─ cashflows list             E  runtimes  · 原生单请求，无分页参数
│  ├─ accuracy list              B  runtimes  · 跨页重复＋指标语义缺口
│  └─ adjustments list           E  runtimes  · pageSize=1000
├─ operations                    沿用当前分支设计和延期状态
├─ investment                    沿用当前分支设计和延期状态
├─ risk                          沿用当前分支设计和延期状态
├─ rules                         沿用当前分支设计和延期状态
├─ network                       沿用当前分支设计和延期状态
├─ ledger                        沿用当前分支设计和延期状态
├─ pricing                       沿用当前分支设计和延期状态
└─ reference                     沿用当前分支设计和延期状态
```

本版 cash/forecast 共 **20 个保留设计叶子**：5 个已有实现（其中账户列表有完整性缺口）、8 个新增实施目标、7 个继续延期。规格冻结时 CLI 仍有 23 个发现路径；当次只改规格，8 项尚未启用，3 项旧 getter 尚未从当时 CLI 目录移除。后续实施已移除这 3 项；当前活动状态以上述实施记录为准。

### 撤回当前 getter 设计的三个路径

| 旧草案路径 | 本次原生证据 | 本版处理 |
| --- | --- | --- |
| `cash groups get` | 原生 Detail 仅展开已取得的 `memberList` | 从新设计树移出；成员配置随 groups list 获取 |
| `cash credit-lines get` | 原生 Details 仅展开 `bankAccountCreditLineList` | 从新设计树移出；成员额度配置随 credit-lines list 获取 |
| `forecast results get` | 图表曲线和账户实测余额查询均不是预测记录的独立 typed getter | 从新设计树移出；results list 仅承诺原生预测字段 |

当前复核入口没有证明上述独立能力，不推断整个后台绝无其他详情 API。未来若取得原生独立契约，可在后续版本重新提出。实施时从活动设计/帮助树移除旧占位项，并保留迁移说明；不得用列表行、当地展开或其它语义的请求伪装 `get`。

## 分页配置及证据

页宽是每个查询契约的配置；原生 UI 页宽只作为发现起点，调整后的值必须有对应 endpoint 的生产只读证据。当前实现仍有未覆盖契约使用统一默认 10，本版没有声称所有查询已按大页探测。

| 叶子 | 本版初始 pageSize | 依据及限制 |
| --- | ---: | --- |
| cash accounts list | 5000 | 既有正式配置；仍存在总数3691、实际唯一3690，不能视为完整成功 |
| cash balances list | 30 | 5000两次拒绝，后端明确最大30；30两轮12/12、限定账户1/1；UI10两页完整对照 |
| cash groups list | 100 | 全范围及真实group范围各两轮1/1；低总量未证明大页上限 |
| cash group-balances list | 100 | 同一原生列表的独立运行态投影；3成员及等值汇总已核对 |
| cash pools list | 100 | BANK范围两轮43/43、358成员；未扩展其它类别 |
| cash credit-lines list | 100 | 两轮84/84、667成员，约34.2/31.3秒；顺序不同但ID/内容相同 |
| cash statements end-of-day list | 1000 | 3个已知账户的单日范围0/0/6；正样本两轮1000与10内容相同；多页未测 |
| cash statements intraday list | 1000 | 继承已实现页宽与既有probe，非本轮重测 |
| cash waterlevels list | 1000 | 继承已实现页宽与既有probe，非本轮重测 |
| forecast results list | 5000 | 两轮当天全范围4419/4419，约11.1/14.2秒；响应约3.36MB；限定账户1/1 |
| forecast adjustments list | 1000 | 继承已实现页宽与既有probe，非本轮重测 |
| forecast cashflows list | 无 | 原生单请求，不添加rowStart/pageSize |

阻塞叶子的页宽只作为研究记录：accuracy 的1000五页不完整，5000在该 endpoint 未测；wallet 的100仅首批成员对照；pool-balances/credit-usage 的100仅来源列表候选值，不构成接受其业务能力的证据。

**通用大页失败缩小回退继续记录为后续工作，本版不实施。** 后续设计须允许每叶子独立初始值、已验证硬上限、明确缩小序列和有界重试；不能把认证过期、业务拒绝、排序重叠或语义错误一概当作页宽过大。缩小重试须重新取得同一完整范围，保持唯一身份/总数/收敛检查与旧缓存保护。当前30/100/1000/5000为固定、已有证据的初始值，不是已实现自动回退的宣称。

## 8 个新增实施目标的原生契约

host：`iliquidity.alipay.com`；tenant 从专用 Liquidity 来源绑定。GET 用 query 编码，POST 用 JSON body。请求只允许下述固定原生契约及已验证过滤结构；禁止用户任意 endpoint、请求字段或 JavaScript。

| 命令 | 原生 caller / endpoint | 请求结构 | 数据与完整性 |
| --- | --- | --- | --- |
| cash balances list | AcctBalanceVime.excuteSearch；POST `/latestBalanceQuery.json` | rowStart,pageSize,tntInstId,entitys,timeZone；可选aliasNames | `$.data.data` / `$.data.totalCount`；success；身份(entity,aliasName,currency) |
| cash groups list | GroupManagementVim.excuteSearch；GET `/bankAccountGroupQuery.json` | tntInstId,bankAccountManageUnitQueryVO；VO是JSON字符串，含rowStart/pageSize/equiCurrency及可选userGroupCode | `$.result.data` / `$.result.count`；顶层count须一致；resultFlag及result.success；group.id |
| cash group-balances list | 同上；独立运行态获取与缓存作用域 | 同上；已验证等值币种USD | 同上；group.id与嵌套(group.id,member.id)分别标识 |
| cash pools list | CashPoolMaint.excuteSearch；POST `/cashPoolList.json` | rowStart,pageSize,tntInstId,cashPoolCategory=BANK | `$.data.data` / `$.data.totalCount`；success；pool.id |
| cash pools get | CashPoolMaint.toggleExpand；POST `/cashPoolDetail.json` | tntInstId,id=pool.id,inUse=Y,cashPoolCategory=BANK | `$.data`独立对象；success；必须回显同一id，不分页 |
| cash credit-lines list | CreditLine.excuteSearch；GET `/queryBankCreditLineByParams.json` | tntInstId,bankCreditLineQuery；JSON字符串VO含rowStart/pageSize | `$.result.data` / `$.count`；result.count一致；resultFlag及result.success；line.id |
| cash statements end-of-day list | AcctStmtEodView.excuteSearch；POST `/bankAccountDetailDayQuery.json` | rowStart,pageSize,tntInstId,instIds,bankAccountAliasName,currency,timeZone,queryDateBegin/queryDateEnd | `$.data.data` / `$.data.totalCount`；success；身份(instId,bankAccountAliasName,currency,valueDate,bankTransNo) |
| forecast results list | BankCashForecastRecord.queryList；GET `/bankCashForecastRecordQuery.json` | tntInstId,bankCashForecastRecordQueryVo（精确小写Vo）；JSON字符串VO含rowStart/pageSize及原生日期/时间/金额范围，可选aliasName数组 | `$.result.dataValue` / `$.result.count`；resultFlag及result.success；record.id |

### CLI 与过滤约束

继续使用既有 `list/get`、显式 `--live`、默认离线、root refresh/describe/help 约定。新增 getter 仅为 `cash pools get --pool-id <pool.id>`；pool-id严格传递到原生id，不接受账户别名或无类型通用ID。该能力只支持已验证BANK类别及inUse=Y，未探测的类别/状态不能作为可用选项。

新列表的CLI scope参数与刷新参数共用声明，不在各插件复制解析逻辑：

- balances：主体、账户别名、时区绑定entitys/aliasNames/timeZone；沿用既有`--entity`、`--account`、`--timezone`命名，数组按原生编码。`--as-of`只选择已保留快照，不冒充后台历史余额过滤。
- groups/group-balances：可选`--group-code`绑定userGroupCode；等值币种必须写入作用域元数据与缓存身份，本轮USD范围获得业务证据，未验证其它币种不自动开放。
- pools：BANK是明确且可发现的固定范围，列表与详情各有独立缓存；get参数不依赖临时列表行替代。
- credit-lines：本轮只接受原生已证明的完整列表范围；不构造后台未验证的搜索过滤。现有通用本地过滤若使用，仅作用于已完整取得且已声明字段的本地数据，不伪装源端过滤。
- EOD：主体/账户/币种/时区与`--from`、`--to`绑定原生字段和YYYYMMDD日期；请求范围必须明确，有效空范围与已证实6条正样本分别保留。instIds采用原生已证实结构，不能把账户别名替换为账户号码。
- forecast results：`--from`/`--to`绑定valueStartDay/valueEndDay，创建时间参数分别绑定recordStartTime/recordEndTime；原生VO还包含expectInflowStart/End、expectOutflowStart/End、expectMin/MaxBalance。金额输入过滤由原生caller乘100，只影响请求编码；具体CLI选项发布前须在focused SIT/UAT逐一验证，不因为字段存在便宣称所有组合已验收。请求不带timezone，不把来源时区未知改成用户时区或GMT确定解释。

作用域必须隔离tenant、kind、endpoint/schema版本、业务过滤、币种和时区；get另绑定原生typed身份及固定类别。不得引入为补全界面字段而默认全量逐行补充的请求。

### 配置投影与运行态语义

- groups settings白名单：id,userGroupCode,groupName,type,memo,version,tntInstId,operator,gmtCreate,gmtModified及成员身份/账户关系。移除所有余额。group-balances单独使用余额投影，不因复用 endpoint 就共用配置缓存。
- group-balances以group.id作为主记录，成员保留嵌套身份；每叶子记录上限按主记录计，成员不另装成重复父记录。保留当前/预测/上日关账的原币及等值币金额、equiCurrency和各自来源时间；三个成员有currentBalanceTime，仅一个有forecastTime，其余为unknown。父级三类等值汇总在USD范围与对应成员等值之和一致，不能跨币相加原币金额或把gmtModified当余额时间。
- pools list/get settings白名单：id,cashPoolName,cashPoolType,cashPoolCategory,mainCurrency,entity,status,haircutRatio,memo,operator,gmtModified及明确成员关系/主账户/共享配置。成员身份为(pool.id,member.id)。移除当前/开盘/可用余额与派生capacity；返回额外新字段不自动进入配置schema。
- credit-lines settings白名单：id,creditLineType,currency,amount（原生Credit Amt）,dateType,startTimestamp,expiryTimestamp,bankId,masterBankId,instId,shareTag,status,manageStatus,memo,version,tntInstId及成员额度/账户关系。成员身份为(line.id,member.id)。usedAmount、availableAmount及成员used/available字段全部排除。
- balances为保留采集快照的运行态；来源时间来自statementCreateTime/timeZone与日终/日内嵌套valueDate/updateTime。curBalance/avlBalance/openBalance/openAvlBalance和equv值保留原义，旧值不因latest命名而满足新鲜度。
- EOD为dated dataset；valueDate、transDate、transTime、date不混用。bankTransNo正样本唯一但不能假设所有日期均有号；空号/重复身份必须显式失败或不完整，不能丢行后报成功。保留Cr/Dr方向，不能根据金额正负猜方向。
- forecast results为dated dataset；record.id、forecastTaskId、forecastBatchNo、forecastRuleId分别表示，baseValueDate与valueDate不合并。gmtCreate整数与recordCreateTime字符串分别保留，服务器时区未证实则为unknown。只承诺预测字段；`bankAccountDetailBalanceQuery.json`为账户日期实测补充，不是results get，不默认为4419条全量发起补充。
- 金额保留原生精度和十进制表达；响应formatter仅加千分位、不除100。请求过滤乘100不能作为全体响应单位缩放依据。零、空串、null分别处理；未观测类型必须拒绝错误结构或显式标记。

## 7 个保留延期叶子的具体条件

| 命令 | 当前阻塞 | 解除条件 |
| --- | --- | --- |
| cash accounts get | 原生row.id查看两次HTTP200但resultFlag/result.success=false、errorCode999；首100账户共用同一id | 后台修复查看身份及详情失败，核对独立typed身份与详情回显；不以alias/currency猜造id |
| cash wallets list | wallet=true/false各两次首100行及count3691相同，未建立钱包归属 | 可用钱包正样本与过滤差异、完整列表及身份契约 |
| cash wallets get | 无已确认的钱包身份，复用账户queryOne候选不足以证明归属 | 钱包正样本及真实独立详情；账户详情修复不自动证明钱包能力 |
| cash wallet-balances list | 未确认钱包成员，也未找到独立余额caller | 原生钱包余额caller、样本、金额与观测时间契约 |
| cash pool-balances list | valueDate不够证明当前值时间，父级UI币种写死USD；折算/汇总契约不足 | 真实余额观测时间及主/原/折算币与汇总契约；gmtModified/billingTime不可替代 |
| cash credit-usage list | 有used/available字段，但mergeFlag合并、共享额度币种汇总及观测时间未证实 | 验证共享/合并口径及占用来源时间；配置修改和额度有效期不充当占用时间 |
| forecast accuracy list | 1000五页报告4419条、唯一4416，3跨页重复；基础行无指标，逐行cashFlowDetailDay补充仅零流量样本 | 先修复分页并全范围唯一收敛，再验证非零/误差/分母边界、公式与日界线；5000需单独探测 |

账户列表既有缺口另行处理：正式pageSize=5000；实际3690与总数3691不一致时输出明确`INCOMPLETE_RESULT`告警、`meta.complete=false`、非零退出。允许的partial live保留真实行；`--require-complete`拒绝partial；refresh不得发布不完整结果，`meta.published=false`并保留旧有效缓存。账户列表少1与详情999分别跟踪，未确定共同根因。

准确率五页到达1000/1000/1000/1000/419不代表完整：唯一ID必须与总数一致；去掉重复后也不能报成功。相同范围预测结果5000两轮4419个唯一ID，仅作跨接口对照，不把它当准确率完整期望集的独立证明。

### 后端复现摘要

- 账户详情：进入`GUAPW3SG/menu/IntNalBankAccount`，Network核对列表row.id，点击原生View，检查`queryaccountbyid.json`的tntInstId/id与HTTP200业务999；比较另一账户是否同id。点击步骤由当前caller推导，本轮未逐项点击UI。
- 准确率：进入`GUAPW3SG/menu/CashFlowForecastAccuracy`，查询有记录当天及全天创建时间；Network只读重发`bankCashForecastRecordAccuracyQuery.json`原生VO，pageSize1000、rowStart=0/1000/2000/3000/4000；汇总record.id、检查总数与唯一数。重复在1页999→2页2、2页1000→3页5、3页999→4页1；页内位置从1起算。UI原生10页宽未证明复现同样边界，准确率5000未测；不猜后台根因。

## 实施与验收条件

下一轮只实施8个N叶子以及必要的目录迁移；实施基线仍为`feat/sub-cmd-lm`，相关PR目标为此worktree根分支。当前任务到设计/spec更新结束，不修改命令注册、查询代码、包版本或缓存。

实施前完成影响分析；复用现有ListSpec/DetailSpec、page_size、解析/transport/store机制。新增投影在插件层定义字段白名单，身份/币种/作用域与mandatory kind明确，不复制浏览器栈或存储框架。

进入正式可用状态须满足：

1. focused SIT验证精确method/path/VO大小写/encoding/原生字段、成功和业务错误、auth expiry、typed身份回显、字段白名单、金额精度/null/时间unknown、kind/scope缓存隔离。
2. 分页检测总数改变、跨页重复、短页、空页不收敛、身份缺失/冲突；允许partial保持非零退出与真实覆盖，refresh失败保留旧缓存。信用额度两轮排序不同，要覆盖多页不稳定排序的拒绝行为。
3. pool独立list/get获取和缓存分别验证；list不触发全详情，detail失败不使另一次成功列表失效。预测列表不默认逐行抓实测值/准确率，成员展开不是get。
4. 生产inquiry UAT逐叶子验证声明范围、正样本与有效空范围、当前分页宽度、全部发布选项及离线browser-disconnected行为。多页EOD/credit-lines/更大预测范围未验证时不得外推完整性。
5. 按repo要求完成必要gates并报告逐叶子状态。N未完成上述步骤前保持非执行发现状态；B/D不启用、不输出伪零。旧3 getter的目录迁移具有明确原因，不能标为业务已成功。

后续通用分页回退另行设计与实施，不属于本版8叶子的放行条件。其记录与每叶子固定页宽不可混为一个已交付能力。

## 完整业务命令树

以下从规格冻结时分支136个唯一发现路径派生：保留此前增加的`network realtime list/get`，撤回3个getter后，共**133个设计叶子**。其中60个已有实现、8个新增实施目标、65个延期；已有实现仅表示代码注册，不表示全部生产UAT已通过。现金/预测以外状态来自当前注册/延期目录，未重新probe；具体旧原因继续以#71/#72及源契约为准。

root login/auth check/logout、refresh、describe及help属于共享控制命令，不计入业务叶子数；同一命令的内部契约variant只计一个路径。

```text
dogopencli liquidity
├─ cash
│  ├─ accounts
│  │  ├─ list  [E! · reference]
│  │  └─ get  [B · reference]
│  ├─ balances
│  │  └─ list  [N · runtimes]
│  ├─ statements
│  │  ├─ intraday
│  │  │  └─ list  [E · runtimes]
│  │  └─ end-of-day
│  │     └─ list  [N · runtimes]
│  ├─ groups
│  │  └─ list  [N · settings]
│  ├─ group-balances
│  │  └─ list  [N · runtimes]
│  ├─ wallets
│  │  ├─ list  [D · reference]
│  │  └─ get  [D · reference]
│  ├─ wallet-balances
│  │  └─ list  [D · runtimes]
│  ├─ pools
│  │  ├─ list  [N · settings]
│  │  └─ get  [N · settings]
│  ├─ pool-balances
│  │  └─ list  [D · runtimes]
│  ├─ credit-lines
│  │  └─ list  [N · settings]
│  ├─ credit-usage
│  │  └─ list  [D · runtimes]
│  └─ waterlevels
│     └─ list  [E · runtimes]
├─ forecast
│  ├─ results
│  │  └─ list  [N · runtimes]
│  ├─ cashflows
│  │  └─ list  [E · runtimes]
│  ├─ accuracy
│  │  └─ list  [B · runtimes]
│  └─ adjustments
│     └─ list  [E · runtimes]
├─ operations
│  ├─ demands
│  │  ├─ list  [D · runtimes]
│  │  └─ get  [D · runtimes]
│  ├─ decisions
│  │  ├─ list  [D · runtimes]
│  │  ├─ get  [E · runtimes]
│  │  └─ history  [E · runtimes]
│  ├─ executions
│  │  ├─ list  [D · runtimes]
│  │  └─ get  [D · runtimes]
│  ├─ rule-status
│  │  └─ list  [D · runtimes]
│  ├─ transfers
│  │  ├─ list  [D · runtimes]
│  │  └─ get  [E · runtimes]
│  ├─ swaps
│  │  ├─ list  [D · runtimes]
│  │  └─ get  [D · runtimes]
│  ├─ forwards
│  │  ├─ list  [E · runtimes]
│  │  └─ get  [E · runtimes]
│  ├─ asset-trades
│  │  ├─ list  [E · runtimes]
│  │  └─ get  [D · runtimes]
│  └─ prefunds
│     ├─ list  [E · runtimes]
│     └─ get  [E · runtimes]
├─ investment
│  ├─ products
│  │  ├─ list  [E · settings]
│  │  ├─ get  [E · settings]
│  │  └─ history  [E · settings]
│  ├─ offers
│  │  └─ list  [D · runtimes]
│  ├─ holdings
│  │  ├─ list  [E · runtimes]
│  │  └─ get  [E · runtimes]
│  ├─ transactions
│  │  ├─ list  [E · runtimes]
│  │  └─ get  [E · runtimes]
│  ├─ investable-funds
│  │  └─ list  [D · runtimes]
│  ├─ interest-rates
│  │  ├─ list  [E · runtimes]
│  │  └─ get  [D · runtimes]
│  ├─ rfqs
│  │  ├─ list  [D · runtimes]
│  │  └─ get  [D · runtimes]
│  ├─ quotes
│  │  ├─ list  [D · runtimes]
│  │  └─ get  [D · runtimes]
│  ├─ quote-groups
│  │  ├─ list  [D · settings]
│  │  └─ get  [D · settings]
│  ├─ quote-sessions
│  │  └─ list  [D · runtimes]
│  ├─ strategies
│  │  ├─ list  [E · settings]
│  │  └─ get  [E · settings]
│  ├─ benchmarks
│  │  ├─ list  [E · settings]
│  │  └─ get  [D · settings]
│  ├─ benchmark-values
│  │  └─ list  [D · runtimes]
│  ├─ strategy-results
│  │  ├─ list  [D · runtimes]
│  │  └─ get  [D · runtimes]
│  ├─ compound-ledger
│  │  ├─ list  [E · runtimes]
│  │  └─ get  [E · runtimes]
│  └─ returns
│     └─ list  [E · runtimes]
├─ risk
│  ├─ events
│  │  ├─ list  [D · runtimes]
│  │  └─ get  [D · runtimes]
│  ├─ metrics
│  │  └─ list  [E · runtimes]
│  ├─ anomalies
│  │  ├─ list  [D · runtimes]
│  │  └─ get  [D · runtimes]
│  ├─ account-capacity
│  │  └─ list  [D · runtimes]
│  ├─ thresholds
│  │  ├─ list  [E · settings]
│  │  └─ get  [E · settings]
│  └─ sla
│     ├─ list  [D · settings]
│     └─ get  [E · settings]
├─ rules
│  ├─ transfer
│  │  ├─ list  [D · settings]
│  │  └─ get  [E · settings]
│  ├─ treasury-transfer
│  │  ├─ list  [D · settings]
│  │  └─ get  [D · settings]
│  ├─ funding
│  │  ├─ list  [E · settings]
│  │  └─ get  [D · settings]
│  ├─ operation
│  │  ├─ list  [E · settings]
│  │  └─ get  [E · settings]
│  ├─ realtime
│  │  ├─ list  [E · settings]
│  │  └─ get  [E · settings]
│  ├─ action-mapping
│  │  ├─ list  [E · settings]
│  │  └─ get  [D · settings]
│  ├─ fx-settlement
│  │  ├─ list  [E · settings]
│  │  └─ get  [D · settings]
│  ├─ notification
│  │  ├─ list  [E · settings]
│  │  └─ get  [E · settings]
│  ├─ forecast
│  │  ├─ list  [E · settings]
│  │  └─ get  [D · settings]
│  ├─ waterlevel
│  │  ├─ list  [E · settings]
│  │  └─ get  [E · settings]
│  └─ monitoring
│     ├─ list  [D · settings]
│     └─ get  [D · settings]
├─ network
│  ├─ routes
│  │  ├─ list  [D · settings]
│  │  └─ get  [D · settings]
│  ├─ realtime
│  │  ├─ list  [D · settings]
│  │  └─ get  [D · settings]
│  ├─ bank-baselines
│  │  ├─ list  [E · settings]
│  │  └─ get  [E · settings]
│  ├─ product-baselines
│  │  ├─ list  [D · settings]
│  │  └─ get  [D · settings]
│  └─ account-capabilities
│     ├─ list  [E · settings]
│     └─ get  [E · settings]
├─ ledger
│  ├─ customers
│  │  ├─ list  [E · reference]
│  │  └─ get  [E · reference]
│  ├─ accounts
│  │  ├─ list  [E · reference]
│  │  └─ get  [D · reference]
│  └─ balances
│     └─ list  [E · runtimes]
├─ pricing
│  ├─ client-prices
│  │  ├─ list  [E · runtimes]
│  │  └─ get  [D · runtimes]
│  ├─ cost-prices
│  │  └─ list  [E · runtimes]
│  ├─ factors
│  │  ├─ list  [D · settings]
│  │  └─ get  [D · settings]
│  ├─ factor-values
│  │  └─ list  [E · runtimes]
│  ├─ strategies
│  │  ├─ list  [E · settings]
│  │  └─ get  [D · settings]
│  ├─ valuations
│  │  ├─ list  [D · runtimes]
│  │  └─ get  [D · runtimes]
│  └─ bills
│     ├─ list  [D · runtimes]
│     └─ get  [D · runtimes]
└─ reference
   ├─ entities
   │  ├─ list  [E · settings]
   │  └─ get  [D · settings]
   ├─ banks
   │  ├─ list  [E · reference]
   │  └─ get  [D · reference]
   ├─ areas
   │  └─ list  [D · reference]
   ├─ business-lines
   │  └─ list  [E · reference]
   └─ calendars
      ├─ list  [E · reference]
      └─ get  [D · reference]
```
