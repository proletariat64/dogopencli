# 变更记录

## 未发布

规格 #162：`liquidity cash accounts list` 合并现金清单、基线清单与真实基线详情，
`accountType`、`status` 仅取基线；新增默认 `timeZone`、`detail_state` 列。
退出对客 `network bank-baselines list/get` 及其独立 refresh/prune，直接调用引导至现金账户。
原生未知互补字段保留，冲突、来源与详情拒绝证据按账户展示；清单覆盖与详情覆盖分别报告。

只有本次验证成立的现金单空洞可通过清单完整性，原生报数、有效报数及探测证据均保留。
Live 只可保存已验证的操作提示，不写业务槽；显式 refresh 原子替换复合结果，
离线不访问网络。旧现金清单槽需显式 refresh。其他叶子的采集和缓存规则保持不变。
本地合成验证与生产只读 UAT 分别记录；完整原生详情字段范围与生产详情拒绝仍需独立验收。


## v0.4.1（2026-10-13）

合并 PR #158（规格 #157）：所有已启用 list 及 FX trade 默认重放每叶唯一临时结果；
`--live` 不写缓存，非空 refresh 原子替换完整采集，空结果保留旧缓存，
每叶 prune 仅删除自己的结果。移除 `--all`（改用 `--limit 0`）、缓存 getter、
详情 refresh、采集历史／保留规则和 Ledger balances（#144）。首次访问会丢弃旧业务缓存；
配置、认证、profile 和外部 DuckDB 输入保持不变。

Cash 在线默认 ALIPAYGM；`--entity ANY` 从只读 DuckDB 冻结原生 instId。
FX 在线默认前一完整 GMT+08 日。Bootstrap 默认安装 DuckDB 可选依赖。
修复本地过滤错误降低完整性、离线读取要求写权限、FX 采集未持有刷新锁的问题；
完整缓存的声明本地过滤可通过严格模式，部分采集及未覆盖范围仍被拒绝。

验证：3269 tests、28 subtests 通过，Ruff、doc-guard、远端 CI 和 Qoder 通过；
Greptile 在包含三项修复的提交上给出 5/5。生产 smoke 为部分验收：窄范围 ANY、
离线重放、原生 getter、prune 已通过；广范围 Cash 返回 incomplete，
FX 昨日查询仍被后端拒绝（IPAY_RS_520000500），空结果保留的证据来自本地测试。

## v0.3.2（2026-10-13）

新增现金余额日期范围、ALL 与可配置页宽（#147）：无日期保留最新快照；成对日期
读取包含两端的每日原生余额。无显式主体的 `--all` 有意扩大为全部目录 instId；
显式主体加 ALL 仍只展开所选范围。最新在线/refresh 页宽默认 100，支持 1–100；
离线拒绝显式页宽，每日拒绝页宽及 timezone。其他叶子不变。

live 不发布；显式 refresh 原子保存余额与冻结选择，离线不联网或重新发现目录。
沿用 partial/strict、硬失败保留旧缓存及最新/每日独立缓存规则，不推断历史归属或补零。
余额输出改用易读 snake_case 字段；原生缓存不变。最新余额按 balId 采集，
同账户、币种及余额日只展示最后账单：同金额静默，金额变化仅告知正常银行账单更新，
均成功退出。此前 #155 为 CLI 身份误判；完整 latest ALL 尚待重新验证。
兼容旧缓存中主体及账户选择的排列顺序；账单分组前拒绝缺失或畸形的账户／币种字段。
PR #151 已合并，相关 #147–#155（不含 PR #151）已关闭。线上 ALL 资格化缺口不因发布而视为通过。
用法见 [README](README.md)，边界见[规格](docs/design/liquidity-cash-balances-v0.1.0.md)。

## v0.3.1（2026-10-11）

新增按域恢复认证的 `login --domain payment|liquidity`（PR #146，规格 #145），
默认仍为 Payment。Liquidity 使用独立入口和目标域认证验证；等待人工 SSO 时仅观察已有页面，
完成后自动切回 headless 并复验。结果和恢复提示包含目标域，临时验证失败使用有界重试。

独立 profile 和空闲端口的生产认证 UAT 已通过 4/4：人工 SSO 与自动模式切换、
Liquidity 认证检查、重复登录及 Payment 认证检查。共享 OAuth 保持认证的行为由用户接受，
未将其报告为已构造服务端 Liquidity 过期。此前宿主 X11 崩溃造成的退出阻塞在环境修复后消失，
无需修改 Chrome launcher。本次不扩大业务查询范围；逐叶生产 UAT 的既有待办保留。

## v0.3.0（2026-10-07）

本次发布整合 v0.2.8 之后已合并的查询、开发环境、测试和登录改进，
包括此前 v0.2.9 源码中的 list 参数统一（PR #135，规格 #127）。
当前 Liquidity 目录为 **98 supported / 34 unsupported / 132 total**，
延期范围为 12 list 和 22 get；monitoring HOLD 和各叶子的契约／验收门槛保留。
发行附件提供 wheel、源码包及 SHA256SUMS；本次包验证不代替既有逐叶生产 UAT。

修复公司 SSO 等待期间的浏览器闪屏和重复标签页（PR #143）：
轮询复用现有页面的只读用户信息请求，最终仍要求应用返回及认证验证；
切换模式时正常关闭受控 Chrome 以保存 cookies／会话历史，并只在新启动阶段清理重复启动页。
人工输入期间和同模式复用不归一化标签页；无关 profile 不受影响。

pytest 和 doc-guard 已接入独立 CI gate，假浏览器测试等待大幅缩短；
新增 `make bootstrap` 初始化工作树开发环境，复用已有 uv 缓存。

新增三个独立 Liquidity 原生 getter（规格 #136）：`operations demands get --task-id`、
`network realtime get --network-id`、`investment quotes get --quotation-order-id`，
以及对应 `refresh liquidity <resource> detail get`。默认离线，live 不写缓存或回退，
详情刷新独立于列表。需求核对 FUND_REQUIRE 及内外成功标志；网络保留原生版本；
报价使用 form POST 并核对嵌套 quotationId。只公开各自允许字段，保留原生精度及空值，
硬失败不覆盖旧详情。后续资格化范围见 #137。

新增 `investment rfqs get --inquiry-sub-task-id` 和独立
`network route-quotas get --route-id --account-alias`（实施 #139，资格化 #137）。
RFQ 按原生页面将子任务 ID 传入 wire inquiryTaskId，并核对 TARGET_RFQ 与原生成员身份。
路由额度是精确租户/路由/账户别名上下文的单个聚合，保留动态/静态数组及重复空 quotaId；
请求范围与原生缺失回显分开，count 不作数组总数。均复用独立详情缓存、显式 refresh、
live 隔离和失败保留契约。global routes get 继续延期，不能以 route-quotas 代替。

新增资产交易 `operations asset-trades get --order-no` 和报价组
`investment quote-groups get --quotation-group-row-id`（规格 #141）。
两者使用单字段原生 form POST，独立详情缓存、显式 refresh 和非发布 live。
资产只提供已绑定交易根与产品字段，排除未证明归属的日志；报价组按物理版本行身份查询，
保留所选版本及联系人/版本历史组成，不隐式解析最新版本，排除附件和审批动作。
报价组列表与其他二十二项 get 继续延期；失败保留旧 capture。

规范化全部受支持 list 命令的公共参数契约（规格 #127）：主日期区间统一为
`--from-date`/`--to-date`（YYYY-MM-DD 首选，原 YYYYMMDD 继续接受），账户别名统一为
`--account-alias`（原 `--account`/`--alias`/`--bank-account` 保留为弃用别名），
规则状态时间戳首选 ISO `Z` 形式，决策/需求接受无时区 `T` 形式，PTR 单据接受任意有效数字时区偏移并归一为 +08:00，
预测结果时钟接受 `HH:mm:ss` 首选形式。等价旧写法产生逐参数一次的 stderr 弃用提示；
标量的新旧拼写混用一律 INVALID_ARGUMENT/退出码 2。原生请求、缓存键、作用域与结果策略保持不变；
缓存缺失误提示中的 refresh 建议命令以首选拼写和公共格式重建（含 shell 引号），可直接执行。
帮助 JSON 为每个选项新增版本化 `argument_contract`（值类型、首选/接受格式、弃用别名、
cache/live/refresh 各模式可用性/角色/基数与约束），`help_version` 保持 1。
兼容性至少保留一个完整发布周期；生产 UAT 另行验收。

新增 `liquidity operations rule-status list` 与独立 refresh（Batch H，规格 #122）：
必填 `--trigger-from`、`--trigger-to`（YYYY-MM-DD HH:mm:ss，UTC，包含两端，允许同点），
单次页宽 5000 仅一个请求；总数超 5000、行数或唯一原生 ID 与 count 不符、重复 ID、
错租户或越界触发时间均在输出与发布前严格拒绝并提示缩小范围。
原生正整数 id 无损作为身份，保留 executeStatus/createdOrder/orderStatus 原生状态区分与
null realTriggerTime，时间戳为 UTC epoch 毫秒；排除金额、账号别名与自由文本。
按精确 profile/tenant/触发范围隔离缓存，失败保留已有缓存，空范围成功如实发布。
getter 与 queryDetailed 展开记录继续不支持；生产 CLI UAT 仍待串行验收。

新增 `liquidity operations demands list` 与独立 refresh：必填
`--execute-from`、`--execute-to`（YYYY-MM-DD HH:mm:ss，包含两端），固定
FUND_REQUIRE 来源及单次页宽 5000；原生总数超过 5000 时拒绝并提示缩小范围。
保留原生任务身份、金额精度和未知状态，按精确
时间范围隔离缓存。原生历史范围 79/79 完整，公共 CLI 生产只读验收 10/10 通过；
宽范围的后端 `099` 失败保留已有缓存。详情由后续 #136 独立实施；其余未验证列表继续延期。
Batch H 完成时 unsupported 为 40 条，其中 list 为 12 条（含 monitoring HOLD）。
证据见 [Batch H 契约](docs/research/general/2026-10-06-batch-h-rule-status-contract.md)
与 [Batch G 报告](docs/research/general/2026-10-06-batch-g-current-probes.md)。
批次验收与后续候选研究见 [Batch H 验收记录](docs/research/general/2026-10-06-batch-h-acceptance.md)、
[剩余清单 PRD 交叉核对](docs/research/general/2026-10-06-remaining-list-prd-crosscheck.md) 与
[剩余清单当前探测](docs/research/general/2026-10-06-remaining-list-current-probes.md)；
quote-groups 覆盖阻塞于 2026-10-06 续证维持不支持（#124）。

## v0.2.8（2026-10-05）

合并 PR #106、#107、#108，新增三个独立 Liquidity 列表：

- `liquidity rules transfer list`：原生转账规则配置和条件字段，固定租户及单响应范围。
- `liquidity network realtime list`：Realtime network 配置，固定分页参数，排除运行指标。
- `liquidity pricing factors list`：定价因子类型定义，保留 code/description/englishName，与每日 factor-values 独立缓存。

三个列表的请求约束、原生身份冲突检查和缓存命名空间独立；相关详情、路由及监控能力维持原有边界。
转账规则 `ruleName`、`title` 中的邮箱和 URL 不进入列表摘要；身份、编号及其他配置原值保持独立。
目录统一为 85 supported / 46 unsupported，共 131 个叶子（34 settings、43 runtimes、8 reference）。
各自生产 UAT 与本地 Kimi、Qoder 审查结果见已合并的契约和 UAT 报告；本次发布验证组合后的源码及包，不新增生产 UAT。
上述隐私修复提交 `8e63575` 已另行通过 Standards/Spec 和本地 Kimi 审查（confidence 4/5）；修复后重新执行生产 CLI UAT，890/890 完整、离线 capture 一致、live 数据库不变且真实 get 缓存保留。最终组合源码的 201 项测试通过。
本版本提供 wheel、源码包及 SHA256SUMS。

## v0.2.7（2026-10-05）

合并 PR #99、#100、#102，发布以下 Liquidity 查询能力；移除 Kimi GitHub review workflow。

记录 #98 的有界原生核验及剩余业务契约门槛，更新延期原因。
新增 `cash pool-balances list` 和显式 refresh：固定 BANK 范围、独立 runtimes
capture；分别保留池/成员账面、可用、原币、银行折算余额，未知成员时间不猜补。
池级金额不以成员求和替换，旧 pools settings/list/get 与缓存不变。
新增 `cash credit-usage list` 和独立 refresh：保留授信/成员原生树与两套金额、
币种、共享标志及显示分组；不执行业务金额、币种或时间校验，不改写来源值。
使用观察时间 unknown，旧 credit-lines settings 字段及缓存不变。
按用户确认移除已停用的 `network product-baselines list/get` 目录项。
新增 `investment quotes list`：仅 QUOTED，`--from-date/--to-date` 必填，
YYYY-MM-DD 映射原生日期；无总数的单响应契约采用 pageSize=5000，不循环分页。
原生百分比、起存金额、期限/日期及未知字段值原样保留，UTC+08:00 仅作为时间解释；
独立 quotes-v1 缓存按完整日期范围隔离。WIN 不启用，quotes get 仍延期。
整合 #97 后目录为 82 supported、49 unsupported，共 131 个查询叶子；
#98 原始四项为三项实现、一项退役；独立生产 CLI UAT 结果另行记录。
生产 CLI UAT 结果在独立验收报告记录。

#97 新增真实策略任务详情（fund/product 两类）和风险事件／告警详情，按原生身份与
类型校验，独立刷新、离线读取，live 不写缓存。新增准确命名的 `pricing fee-orders list`，
支持最多 31 日的有界 Service Date 范围；费用与交易币种分别保留，不作为 valuations 别名。

本批被接受的候选实现 4/4：三个旧 unsupported 已解除，另新增一个费用订单叶子。
国家／地区基础数据按用户决定从需求和目录撤除，不导入、不保留 unsupported 入口；
撤除不计为实现。上述目录已包含 #97 与 #98；valuations 保持 unsupported。
注册公共 CLI 生产 UAT 24/24 通过；本地检查和审查见
[验收报告](docs/research/general/2026-10-04-liquidity-issue97-gates.md)。
#97 已随 PR #99 合并关闭。本版本提供 wheel、源码包及 SHA256SUMS；历史生产 UAT 与本次发布检查分别记录。

## v0.2.6（2026-10-04）

合并 PR #94、#95、#96，新增有界 decisions、transfers、risk events、risk anomalies、
investment benchmark-values 和 strategy-results 列表。默认离线读取，显式 refresh
更新缓存，live 不写缓存；沿用原生范围、独立缓存与 partial／strict 规则。
当前 Liquidity 查询叶子为 75 supported、58 unsupported。

基准值以业务日期、策略、币种、资金性质构成身份，并提供稳定可逆的本地 `primaryId`。
基准值 v2 缓存必须显式 refresh，原有 v1 captures 保留，不自动迁移或读取为 v2。
策略结果分别支持 FUND_DECISION_TASK 和 PRODUCT_DECISION_TASK。
Batch C 仅交付 2/4，valuations 与 bills 保持 unsupported，#89 继续开放。

修复 Batch C 研究报告元数据与文档索引。PR #96 独立审查的 246 个聚焦测试通过；
文档修复后 doc-guard 通过。发布检查与历史生产 UAT 分别记录。
本次 GitHub Release 同时打包此前源码 v0.2.5 的有界 swaps 查询，附 wheel、源码包与 SHA256SUMS。

## v0.2.5（2026-10-04）

合并 PR #83，新增 `liquidity operations swaps list` 与对应 refresh，必填
`--trade-from`、`--trade-to`（YYYYMMDD，包含两端）。默认离线读取精确范围缓存，
显式 live 不写缓存；无日期、单边、倒置范围拒绝，get 继续 unsupported。
正式注册 CLI 生产只读 UAT 21/21 通过。

四列表 batch 交付 1/4；demands、executions、investable-funds 仍缺少非空原生
证据，#82、#84、#85、#86 尚未完成。查询叶子为 69 supported、64 unsupported。
同步 README 与 snapshot 回归测试的支持状态；源码版本由 0.2.4 增加至 0.2.5。
此记录不表示安装包或 GitHub Release 已发布。

## v0.2.4（2026-10-03）

新增 `dogopencli snapshot`，离线查看当前命令树及本地缓存元数据，支持 JSON、
文本树和表格。报告命令 supported/unsupported、记录数、采集时间、完整性、
新鲜度与留存范围；保留延期叶子及原因，不读取业务行、不启动浏览器或刷新缓存。
支持子树和叶子选择，详情缓存独立统计。规格 #80，实现 PR #81。

本次发布同时包含此前合并的 Liquidity v0.2.3 查询能力及以下统一 incomplete
结果策略。版本由 0.2.3 增加至 0.2.4；wheel 与源码分发包随 GitHub Release 提供。

### 统一 incomplete 结果策略

默认 live、离线列表及 refresh 可以使用经过验证的 incomplete 数据：返回
`error=null`、退出 0，JSON `meta.warnings` 与 stderr 每次告警，完整性仍为 false。
首次 partial refresh 可建缓存，最新 partial 可以替换旧完整缓存；不从旧缓存补行。
需要完整结果的脚本应使用 `--require-complete`，刷新也支持该参数；严格拒绝退出 1，
`data=null`、`INCOMPLETE_RESULT`，并在提交前保留原缓存。

完整性证据随数据原子保存，区分后端总数、原始行次、唯一记录、重复与留存缺口。
没有原生身份时保留行次，不以整行哈希去重；去重本身不证明完整。
格式、身份、范围、权限、超时及稳定性失败继续拒绝整个候选。PTR 的双轮稳定校验保留，
Collection cost 仍为固定单页 1000，holdings 仍为 500。

Liquidity dated 按最新同范围请求窗口确定有效行与覆盖证明；最新 partial 不复用
旧窗口内的行补洞。默认刷新报告实际 `meta.published` 和提交后的留存质量。
新 Liquidity 索引带 acquisition 格式标记，旧读取器会拒绝该格式。
回滚应恢复迁移前的缓存备份，或隔离新格式缓存后重新刷新；不能只回退二进制。
离线缓存读取不建库或迁移库。

规格与边界见[统一 incomplete 规格](docs/design/unified-incomplete-v0.1.0.md)及
[ADR 0019](docs/adr/0019-usable-incomplete-acquisitions.md)。离线回归及新策略的
[生产只读 UAT](docs/research/general/2026-10-03-unified-incomplete-production-uat.md) 已完成：
82/83 个目标命令通过，Payment channel EXTERNAL 源端阻塞，ledger balances 按用户要求跳过。
后端阻塞与跳过项仍按原报告保留，不因发布版本而视为通过。
