# Cash / Forecast 业务 Probe 结果

Observed: 2026-10-02
Scope: general
Status: snapshot

日期：2026-10-02，Asia/Shanghai。计划：GitHub Issue #74。
基线：`feat/sub-cmd-lm` / `c06551a022ab6e277ea5790490b2efc9690876cf`。

## 结论

18 个延期命令均已形成逐项判定：**8 项可进入实现、2 项需后端修复、5 项需样本/契约、3 项在所查原生入口不对应独立 getter**。
这是生产只读 probe 结果，不是 CLI 业务 UAT 通过。未修改产品代码、未启用命令、未发布缓存、未提交/合并 PR。

四批合计 **57 次显式业务 inquiry**，其中 53 次业务成功、4 次业务拒绝；无传输错误或响应截断。耗时合计约 **202.677 秒**，包含临时目标准备与传输，不是稳定性能基准。
登录检查和前端资源读取单独记录；原生页面初始化请求不计入这 57 次显式 inquiry，也不是分页完整性证据。

## 18 叶子状态树

前缀均为 `dogopencli liquidity`。

```text
cash
├─ accounts get                 需后端修复：原生查看身份返回 errorCode=999
├─ balances list                可进入实现：pageSize=30，12/12 与 1/1
├─ groups list                  可进入实现：配置投影，pageSize=100，1/1
├─ groups get                   不对应独立能力：原生 Detail 仅展开列表成员
├─ group-balances list          可进入实现：余额投影，3 个成员与等值汇总
├─ pools list                   可进入实现：BANK 配置投影，100，43/43
├─ pools get                    可进入实现：独立 POST 详情，两对象各两轮
├─ pool-balances list           需契约：当前余额值时间与折算口径仍不充分
├─ wallets list                 需样本/契约：wallet 标志未建立成员差异
├─ wallets get                  需样本/契约：无已确认的钱包正样本
├─ wallet-balances list          需样本/契约：无已确认钱包及独立余额 caller
├─ credit-lines list            可进入实现：pageSize=100，两轮 84/84
├─ credit-lines get             不对应独立能力：原生 Details 仅展开列表成员
├─ credit-usage list             需契约：有占用字段，缺余额观察时间/汇总约定
└─ statements end-of-day list   可进入实现：1000，6/6 正样本；另两范围为空
forecast
├─ results list                 可进入实现：5000，两轮 4419/4419
├─ results get                  不对应独立能力：图表/实测查询不等于记录详情
└─ accuracy list                需后端修复：1000 跨页 3 重复/3 缺失；另有语义缺口
```

“不对应独立能力”仅指本次复核的当前原生入口，没有声称所有后台都不存在相应 API。
“可进入实现”仅适用于下列已验证范围和明确投影；随后仍需实现、focused SIT 和生产 inquiry UAT。

## PageSize 与覆盖

| 原生业务 | 本轮页宽 | 覆盖与重复读取 | 判定 |
| --- | --- | --- | --- |
| balances | 5000 → 30；10 对照 | 5000 两次明确拒绝；30 两次 12/12，账户过滤两次 1/1；10 两页共 12/12 | 后台明确最大 30。30 可作为该叶子的初始宽度 |
| forecast results | 5000；10 对照 | 当天全范围两次 4419/4419；一个账户两次 1/1；小页相邻两页无重复 | 5000 在该范围生效；不能据此保证多大页范围稳定排序 |
| groups | 100 | 当前全部与一个真实 userGroupCode 范围，各两次 1/1 | 接受 100，但总量仅 1，尚不能证明超过 UI 容量时的行为 |
| pools | 100 | BANK 范围两次 43/43，约 401 KB/次；两个真实详情各两次 | 100 已实际返回超过 UI 10 条并完整覆盖 |
| wallet / ordinary accounts | 100 | wallet=true/false 各两次；四次均返回同一批 100 条，总数 3691 | 页宽接受；仅首批 membership 对照，不是账户全量完整性验证 |
| accuracy | UI 10；1000 | 1000 五页到达 4419，唯一 4416；账户过滤范围两次 1/1 | 1000 不满足全范围完整性。该 endpoint 的 5000 **未测** |
| credit-lines | UI 10；100 | UI 首批约 22.8 秒；100 两次完整 84/84，约 34.2/31.3 秒，约 393 KB | 100 可作为已验证范围初始宽度；90 秒重试未触发 |
| EOD | 1000；UI 10 | 三个已有账户各单日；0、0、6 条。正样本另读两次1000和一次10，均6/6且内容一致 | 1000 在有数据范围响应 echo 正确；仅验证一页，未验证跨页 |

余额明确给出最大 30 后，直接按显式限制缩小，没有继续发送已知越限的 1000/100。此调整仅用于研究脚本，没有实现通用生产回退。
余额30的两轮耗时约2.93/1.92秒；native10两页合计约3.57秒。预测5000两轮约14.19/11.13秒。这些是单次观测，不能外推其他业务或宣称稳定提速比例。

## Native 契约表

host 均为 `iliquidity.alipay.com`；tenant 来源是当前原生页面。GET 通过 URL query 编码，POST 通过 JSON body。每次都走共享 allowlist / CDP transport。

| 对应叶子 | menu / caller | method / endpoint | 原生请求字段 | rows / total / envelope |
| --- | --- | --- | --- | --- |
| balances list | AcctBalanceVime.excuteSearch | POST /latestBalanceQuery.json | rowStart,pageSize,tntInstId,entitys,timeZone；bounded aliasNames | $.data.data / $.data.totalCount / success |
| groups list、group-balances list | GroupManagementVim.excuteSearch | GET /bankAccountGroupQuery.json | tntInstId,bankAccountManageUnitQueryVO；VO含分页、equiCurrency、可选userGroupCode | $.result.data / $.result.count（顶层count一致）/ resultFlag,result.success |
| pools list、pool-balances list | CashPoolMaint.excuteSearch | POST /cashPoolList.json | rowStart,pageSize,tntInstId,cashPoolCategory | $.data.data / $.data.totalCount / success |
| pools get | CashPoolMaint.toggleExpand | POST /cashPoolDetail.json | tntInstId,id,inUse,cashPoolCategory | $.data / 非分页 / success；id echo 已核对 |
| wallets list | QueryWalletAccount.excuteSearch | GET /queryintnalbkactlist.json | tntInstId,bankAccountQueryVO,wallet | $.result.bankAccountPropertyVOList / $.count / resultFlag,result.success |
| accounts get；wallet get候选 | IntNalBankAccount.handleView → View原生queryOne | GET /queryaccountbyid.json | tntInstId,id，来自列表查看动作的route参数 | 本轮失败；resultFlag=false，$.result.errorCode=999 |
| credit-lines list；credit-usage候选投影 | CreditLine.excuteSearch / expandedRowRender | GET /queryBankCreditLineByParams.json | tntInstId,bankCreditLineQuery；VO含rowStart,pageSize | $.result.data / $.count（result.count一致）/ resultFlag,result.success |
| statements end-of-day list | AcctStmtEodView.excuteSearch | POST /bankAccountDetailDayQuery.json | rowStart,pageSize,tntInstId,instIds,bankAccountAliasName,currency,timeZone,queryDateBegin,queryDateEnd | $.data.data / $.data.totalCount / success |
| results list | BankCashForecastRecord.queryList | GET /bankCashForecastRecordQuery.json | tntInstId,bankCashForecastRecordQueryVo；VO含日期、时间、分页、金额区间及可选aliasName | $.result.dataValue / $.result.count / resultFlag,result.success |
| results 的实测值补充（不是results get） | queryList callback → manage/getDataByRow | GET /bankAccountDetailBalanceQuery.json | tntInstId,bankAccountDetailBalanceQueryVo；由实际行的valueDate/accountNo/instId/currency/aliasName构造 | $.result.bankAccountDetailBalanceVo / 非分页 / resultFlag |
| accuracy list 的基础行 | CashFlowForecastAccuracy.queryList | GET /bankCashForecastRecordAccuracyQuery.json | tntInstId,bankCashForecastRecordQueryVo；与原生日期/时间/金额过滤一致 | $.result.dataValue / $.result.count / resultFlag,result.success |
| accuracy 指标补充 | queryList callback → manage/cashFlowDetailDay | GET /cashFlowDetailDay.json | tntInstId,bankAccountDetailCashFlowQueryVO；由实际行绑定date/account/currency/forecastRecordId/forecastBalance/aliasName/bankId | $.result.bankAccountDetailDayVO / 非分页 / resultFlag,result.success |
| groups get、credit-lines get | 各页面toggleExpand | 本地状态与列表成员展开 | 没有独立server getter | 不将已有列表行伪装成原生详情 |
| results get | sendRecord图表与realized enrichment | 原生图表查询返回曲线；实测查询返回账户/日期余额 | 已复核caller语义；本轮未执行图表查询 | 均未证明独立 forecast record getter |
| wallet-balances list | 当前钱包入口、原生源码 | 未确认独立query caller | 不构造猜测请求 | 未取得契约 |

源码 SHA-256：`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`。当前umi资源与先前原生审查副本完全一致，11个已知契约caller片段及8个相关组件完整匹配。额外两个GET仅是页面列表的原生只读补充，不执行预测生成或决策动作。

## 身份、投影、时间与金额

### 可进入实现的明确边界

- **balances**：身份候选 `(entity,aliasName,currency)`；12条非空唯一，两轮及native10内容按身份完全一致。`curBalance/avlBalance/openBalance/openAvlBalance`保留原生意义；`equv*`保留原生等值币种。源时间来自`statementCreateTime/timeZone`与日终/日内嵌套对象的`valueDate/updateTime`，不可用fetch时间替代。样本中部分日内来源很旧，不把“latest”命名解释成新鲜。
- **groups配置**：group.id，成员 `(group.id,member.id)`。配置白名单：id,userGroupCode,groupName,type,memo,version,tntInstId,operator,gmtCreate,gmtModified；成员身份与账户关系。余额字段从settings剔除。
- **group-balances**：三个成员均有`currentBalanceTime`，仅一个有`forecastTime`；空时间须如实保留unknown。原生`equiCurrency=USD`范围中，父级三类汇总分别与成员`equiCurrentBalance/equiForecastBalance/equiLastDayClosingBalance`相加一致。成员原币余额不能跨币直接相加。汇总的valueDate和成员值时间分别保留；gmtModified不是余额时间。
- **pools配置/详情**：范围仅BANK，pool.id；成员 `(pool.id,member.id)`，358个返回成员在各pool内无ID冲突。配置白名单：id,cashPoolName,cashPoolType,cashPoolCategory,mainCurrency,entity,status,haircutRatio,memo,operator,gmtModified，以及明确的成员账户关系/主账户/共享配置。两个详情的父级身份、上述配置与成员数均和列表一致；独立详情各两轮成功。当前余额、开盘余额、可用金额与派生capacity从settings剔除。
- **credit-lines配置**：line.id；667个成员各父级内ID无冲突。白名单包含id,creditLineType,currency,amount（原生Credit Amt）,dateType,startTimestamp,expiryTimestamp,bankId,masterBankId,instId,shareTag,status,manageStatus,memo,version,tntInstId，以及成员额度/账户关系。usedAmount/availableAmount及成员used/available字段从settings剔除。两轮84个ID与按ID内容相同，但记录顺序不同；跨多页时必须严格检测收敛，不能假设稳定排序。
- **EOD**：三账户范围均来自已取得的余额行；日期是这些行真实日终`valueDate=20260930`，在最近7日内。六条正样本bankTransNo均非空且唯一；建议身份限定在 `(instId,bankAccountAliasName,currency,valueDate,bankTransNo)`，仍需实施SIT覆盖空号和重复。`valueDate/transDate/transTime/date`分别保留，不合并；样本含5个Cr、1个Dr。金额为原生十进制字符串，方向独立，不根据正负金额猜方向。
- **forecast results**：record.id 非空唯一，两个当天完整读取内容一致。保留forecastTaskId、forecastBatchNo、forecastRuleId为不同字段；本范围有4419个record ID、4419个task ID、12个batch号，不能互换身份。baseValueDate与valueDate确实不同，base日分布跨历史日期；不得统一改成查询日。`gmtCreate`是整数，`recordCreateTime`是独立字符串。UI过滤标签为GMT Create Date/Time；请求未带时区，具体服务器解释不推断，保留原生日期/时间和时间区未知。可先实现原生预测字段；若声称UI完整展示，另需原生实测查询，不能填零或用fetch时间替代。

原生金额formatter `Ue.sZ`只插入千分位，不除以100；上述返回值按UI原样作为货币金额字符串保留。forecast过滤的预期金额输入由caller乘100，这是**请求过滤编码**，不能据此将全部响应再除100。空串、null与零分别保留；未观测到的金额/null类型在实施时必须拒绝错误结构或显式标注。

### 继续延期的具体缺口

- **pool-balances**：父级有valueDate，UI父级CCY写死USD；成员有原币currency、equv金额、timeZone及billingTime配置，但没有余额实际更新时间。不能拿gmtModified、billingTimeValue当余额值时间；主币种/原币/折算币和现值的计算边界尚缺可靠契约。可以记录日期快照，暂不宣称当前实时余额能力已满足。
- **credit-usage**：原生列表确实含usedAmount、availableAmount；成员含usedCreditAmount、usedAmount、creditCurrency、currency、mergeFlag。UI按mergeFlag合并行显示Credit Used Amt，不能直接将所有行相加。没有可靠占用观察时间；成员start/expiry是额度有效期，gmtModified是配置修改时间。仍需明确shared额度/折算与观察时间契约；没有单独执行新endpoint。
- **wallet三叶子**：wallet=true/false各两轮的首100条身份、内容完全相同，总数都3691。只能证明此对照没有成员差异；不能推断所有账户都是钱包，或全局不存在钱包功能。无已确认正样本，因此不继续钱包详情/余额请求。当前钱包View候选复用账户queryOne，不足以建立钱包归属。
- **accuracy**：基础列表没有准确率字段，指标来自cashFlowDetailDay的逐行补充。两对象各两轮获得11个原生字段，包括inflowAccuracy/outflowAccuracy/flowAccuracy/cashFlowAccuracy。样本均为流入流出零且比率1；非零、误差、分母为零且预测非零等分支未覆盖。UI把比率乘100展示%；Account Estimated Accuracy是三项比率平均再按4位舍入后展示。历史《匡算介绍》提供公式背景，本轮不把它当当前后台公式。当前backend公式的分子分母、日界线/时区仍未充分验证；此外全范围分页已发现3个重复ID。
- **accounts get**：普通账户首100条有100个账户身份组合，但只有1个共享列表id。该id正是原生handleView传给route/queryOne的参数；两次均返回未知异常999。不是传输超时，亦不能据此判为权限不足。不能以alias/currency猜造queryOne的id。详情失败与既有3690/3691 count/list差异分别跟踪。

## 新异常报告

- [账户原生详情返回999](2026-10-02-cash-accounts-detail-backend-bug.md)：原生查看动作参数与失败envelope；UI复现说明。
- [准确率跨页重复与遗漏](2026-10-02-forecast-accuracy-pagination-backend-bug.md)：1000页宽边界、总数/唯一数与源码过滤；UI/Network复现说明。

既有账户count/list差一个报告仍在：`docs/research/general/2026-10-01-cash-accounts-backend-count-bug.md`。本轮没有重跑该全量账户问题，也没有推断它与详情失败共用根因。

## 执行与证据边界

- A/B/C/D分别16/10/16/15次，均低于60/40/40/40上限；主动请求合计低于60分钟。最大单次业务响应约3.36MB，流式10MiB上限未触发。
- 普通超时45秒；授信成功所以没有90秒重试。EOD只用了3账户×1个已有数据日期，没有扩大历史扫描。
- 当前Liquidity登录经专用profile与9222验证；未用9330–9340。default login只证明Payment，随后按Liquidity入口恢复并验证，不混用授权证据。
- 原始参数/账户标识/响应仅留Git忽略的私有probe目录（tmp/cash-forecast-business-probe-20261001T231353Z），目录0700、文件0600；本报告为可发布的脱敏副本，仅写字段、计数和范围信息。
- 临时CDP目标由共享transport/session的关闭流程释放。未访问外部DI、未运行导出/生成/提交/审批/修改动作；未运行与本次probe无关的测试。
- `progress.json`逐请求记录状态/大小/耗时；`request-NNN.json`留真实参数及失败原文；各scope JSON留rows/identity/content，仅私有查看。`current-source.json`留当前源码证明；`leaf-results.json`留18项机器可读结论。
- 这些是显式probe的完整性结论，不能外推其他日期、主体、pool类别、大于一页的范围或所有后台页宽。

## 下一步实施清单

只建议下一轮进入以下8项实现：`cash balances list`、`cash groups list`、`cash group-balances list`、`cash pools list`、`cash pools get`、`cash credit-lines list`、`cash statements end-of-day list`、`forecast results list`。
先实现明确白名单与原生时间/不完整状态，再做focused SIT和生产只读UAT；后端异常及五项契约缺口保留。所有后续实现继续以`feat/sub-cmd-lm`为基线。
