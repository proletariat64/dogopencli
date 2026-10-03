# 文档索引

## 产品规格

- [Liquidity v0.2.3 inquiry specification (GitHub Issue #76)](https://github.com/proletariat64/dogopencli/issues/76)：spec 从 v0.2.1 增加 0.0.2；依据新 cash/forecast probe 接受 8 项实施目标、保留 7 项延期、撤回 3 项 getter 设计。[新版完整命令树与本地规格](design/liquidity-v0.2.3.md)；[实施与 CLI UAT](research/general/2026-10-02-liquidity-spec76-implementation-uat.md)：8 项已实施放行：7 项完整 UAT，预测按 accounts 语义兼容已知后端缺陷；新全范围 UAT 20135/20129、跨页重复与 count 变化均保留非零失败/缓存保护。[后端报告与关联建议](research/general/2026-10-02-forecast-results-backend-count-bug.md)。

- [Liquidity v0.2.1 inquiry specification (GitHub Issue #71)](https://github.com/proletariat64/dogopencli/issues/71): every business leaf has a kind; bounded live evidence, unresolved contracts and release gates. Verified inquiry slice implemented on the current source branch (#72); deferred leaves remain unsupported, and per-leaf production UAT/release are pending.

- [v0.1.0 付款只读 CLI 规格（GitHub Issue #1）](https://github.com/proletariat64/dogopencli/issues/1)：已发布，标签 `ready-for-agent`；公开 CLI＋假 CDP 为 SIT，生产只读验收为 UAT。
- [DI 风格渐进式 CLI 帮助（GitHub Issue #13）](https://github.com/proletariat64/dogopencli/issues/13)：计划与规格已发布，标签 `ready-for-agent`；无参数导航、JSON/text、完整命令目录及离线帮助验收，尚未实现。

- [Data helper v1（GitHub Issue #16）](https://github.com/proletariat64/dogopencli/issues/16)：四个付款查询叶子的离线 schema、字段证据与读取指引；[可运行命令与版本化机器契约](../README.md#data-helper)。
- [收款交易成本查询规划（GitHub Issue #21）](https://github.com/proletariat64/dogopencli/issues/21)：当前开发分支实现固定类型的交易成本列表、live、刷新及离线描述；VA 费用及池/实体账户等仍排除，VA 规则另见 #31。

- [收款 SLA 配置查询（GitHub Issue #27）](https://github.com/proletariat64/dogopencli/issues/27)：列表、真实详情、原子刷新与四项本地筛选；实施及验收见下方报告。

- [收款 VA 容量监控（GitHub Issue #36）](https://github.com/proletariat64/dogopencli/issues/36)：容量列表、原子刷新与两项本地筛选规格；契约证据见容量契约验证报告，实施与验收分别见 #38/#39。
- [收款 VA 规则查询（GitHub Issue #31）](https://github.com/proletariat64/dogopencli/issues/31)：列表、主详情、原子刷新规格；契约证据见 VA 规则研究与当日契约复核；其中“全量详情方可发布”已由 [ADR 0010](adr/0010-collection-va-partial-detail-tolerance.md) 收窄为仅容忍后端明确拒绝的单个详情。#31/#32 已随 PR #35 合并关闭；#33 筛选切片未实施、延期。

- [收款清算系统规格 #41](https://github.com/proletariat64/dogopencli/issues/41)：独立列表、五项本地筛选、原子刷新。
- [收款卡模板规格 #45](https://github.com/proletariat64/dogopencli/issues/45)：独立列表、六项本地筛选、原子刷新。

- [付款规则总规格 #59](https://github.com/proletariat64/dogopencli/issues/59)：#55–#58 四项列表实施；#54 流量规则详情身份不一致，仍阻塞。
- [付款 PTR 总规格 #61](https://github.com/proletariat64/dogopencli/issues/61)：七类独立查询子规格；用例 #63 与有界单据 #64 已冻结，其他资源仍保留生产契约缺口。

## 研究报告

以下报告各自记录观察日期；运行态仅代表当时账号可见的页面和已验证请求，不保证后续版本、权限或数据不变。

| 范围 | 报告 | 内容 |
| --- | --- | --- |
| General | [Liquidity v0.2.3 完整 CLI UAT](research/general/2026-10-03-liquidity-full-cli-uat.md) | 68 个可执行叶子的本轮 native live、独立 refresh、断开传输 offline 验收，以及 65 个延期叶子的非执行检查；[完整彩色地图](assets/general/2026-10-03-liquidity-full-cli-uat-roadmap.svg) |
| General | [可按时间查询历史的运行数据源对照](research/general/2026-10-03-historical-runtime-source-comparison.md) | Forecast 十个历史日期查询证据；对照已执行命令的源端日期/时间过滤、运行数据类型与本地历史缓存边界 |
| General | [采集兼容与完整性处理的整体架构研究](research/general/2026-10-03-acquisition-compatibility-architecture.md) | 统一结果证据、live/refresh 策略与退出码；保留域分页、VA 详情发布和 PTR 稳定校验；分步迁移与验收矩阵，尚未实施 |
| General | [运营平台访问与通用发现](research/general/2026-09-08-platform-access.md) | CDP、登录、聚合应用结构、查询协议、只读约束与技术参考 |
| General | [Liquidity v0.2.1 live probes](research/general/2026-10-01-liquidity-live-probes.md) | All 134 draft leaves audited; scoped timings, decoded payload sizes, sampled schemas, pagination defects, permission gaps and actual SQLite measurements |
| General | [Liquidity inherited CLI UAT](research/general/2026-10-02-liquidity-inherited-cli-uat.md) | 60 个 inherited 叶子的累计验收：55 PASS、1 EMPTY、3 PARTIAL、1 BLOCKED；利率/决策历史修复通过，returns accrual 通过、cash 不完整，ledger 后端 999；holdings 采用用户已验证的 500 页宽，保留历史 UAT；附彩色地图 |
| General | [Forecast results 后端收敛性缺陷](research/general/2026-10-02-forecast-results-backend-count-bug.md) | 历史 7504/7502；新 UAT 20135/20129、跨页重复与 count 变化；accounts 式兼容及关联排查建议，不宣称同根因 |
| General | [Liquidity v0.2.3 实施与 UAT](research/general/2026-10-02-liquidity-spec76-implementation-uat.md) | 8 个契约实现、7 项 UAT 通过、3 个 getter 目录迁移；本地 CI 与 apex 复审通过；8 项放行（7 完整、1 后端兼容），缓存与源端完整性不混同 |
| General | [Liquidity v0.2.3 投影字段证据](research/general/2026-10-02-liquidity-spec76-field-evidence.md) | 仅字段名及类型、独立 pool detail 嵌套白名单；可复现 describe 生成输入 |
| General | [Cash / Forecast 业务 probe](research/general/2026-10-02-cash-forecast-business-probe.md) | 18延期叶子、57次只读请求；8项可进入实现，后端异常及语义/样本缺口分别记录，支撑spec v0.2.3 |
| General | [账户原生详情后台异常](research/general/2026-10-02-cash-accounts-detail-backend-bug.md) | 原生View身份返回业务999，界面复现步骤与证据限制 |
| General | [准确率跨页重复后台异常](research/general/2026-10-02-forecast-accuracy-pagination-backend-bug.md) | pageSize1000到达4419但唯一4416；Network只读复现及5000未测边界 |
| General | [Liquidity UAT 执行记录](research/general/2026-10-01-liquidity-uat.md) | 6,328 CASE；原始失败 1,062 条，区分脚本误判、前置阻塞及实际异常；验收未通过 |
| General | [银行账户列表后端数量异常](research/general/2026-10-01-cash-accounts-backend-count-bug.md) | count 3691、实际 3690；界面短页定位与单页 5000 复现证据 |
| General | [Cash 与 Forecast 分页配置验证](research/general/2026-10-01-cash-forecast-page-sizes.md) | accounts 5000；waterlevels、intraday、adjustments 1000；cashflows 不带分页参数 |
| General | [分页能力后续事项](research/general/2026-10-01-pagination-followups.md) | 大页失败后缩小分页待实现；各查询独立页宽已按后续要求配置 |
| General | [FX 查询插件交接背景](research/general/2026-09-09-fx-handoff.md) | SIM 历史观察、FX 领域边界、查询插件候选范围与未验证事项；尚未实施 |
| General | [DI 渐进式帮助参考](research/general/2026-09-12-cli-help-reference.md) | 无参数入口、JSON/text、逐层导航与 dogopencli 帮助差距 |
| General | [CLI 帮助验收矩阵](research/general/2026-09-12-cli-help-acceptance-matrix.md) | 全部 20 条命令路径的验收规范、20 次探针 before 基线与 Task 4 覆盖清单 |
| General | [收款成本全参数 UAT](research/general/2026-09-26-collection-cost-argument-uat.md) | 84 个 CLI 验收用例；全部选项、帮助/描述、边界与错误组合，区分生产查询和本地状态检查 |
| General | [收款成本实现验证](research/general/2026-09-26-collection-cost-verification.md) | Issue #21 实现清单、只读边界、页面就绪故障及验证结果 |
| General | [收款生产发现与首批范围](research/general/2026-09-23-collection-discovery.md) | 22 个菜单、交易/VA 成本契约、银行账户 VA 规则分页异常及成本优先的实施计划 |
| General | [收款 VA 规则列表与详情](research/general/2026-09-23-collection-va-rule-query.md) | 独立于银行账户规则；两次 907 条完整列表、三个详情样本、ID 筛选与下一步设计缺口 |
| General | [收款 SLA 配置列表与详情](research/general/2026-09-23-collection-sla-query.md) | 55 条列表与全部详情、单值筛选、秒单位/节假日结构及下一步设计缺口 |
| General | [收款 VA 池查询](research/general/2026-09-23-collection-va-pool-query.md) | 登录恢复；容量/凭证/规则详情与池的区别，已查导航及失败证据；用户要求停止入口搜索；池/实体账户保持未验证并排除 |
| General | [收款 VA value 术语核验](research/general/2026-09-26-collection-va-value-terminology.md) | 更正未经证实的命令建议，区分 VA 规则、费用与账户对象 |
| General | [收款菜单只读探查计划](research/general/2026-09-26-collection-menu-readonly-plan.md) | 逐菜单检查范围、只读边界和完成记录 |
| General | [收款菜单深度探查](research/general/2026-09-26-collection-menu-deep-survey.md) | 页面、实际查询入口与权限受限项目；作为后续规格输入 |
| General | [收款 SLA 实施与 UAT](research/general/2026-09-26-collection-sla-implementation-uat.md) | 全参数矩阵、151 项生产只读与本地验收、SIT 和修复后的门禁记录 |
| General | [收款 SLA PR 审查处理](research/general/2026-09-26-collection-sla-review.md) | Kimi 与 GitHub 审查逐项核验、修复及回归证据 |
| General | [收款 VA 规则契约复核](research/general/2026-09-26-collection-va-rule-contract-recheck.md) | 当前 911 条列表/详情契约与 H2 一致;分页、ID 筛选、字段重验及未验证缺口 |
| General | [收款 VA 规则实现与验收](research/general/2026-09-26-collection-va-rule-implementation-uat.md) | 911 条生产只读 UAT、71 条详情拒绝的定位与容错发布验证、门限结果与证据边界 |
| General | [收款 VA 容量查询契约验证](research/general/2026-09-26-collection-va-capacity-contract.md) | warningUseCount 契约、行身份与漂移、运行估算 totalCount、筛选决策及剩余缺口（#37） |
| General | [收款 VA 容量全参数 UAT](research/general/2026-09-26-collection-va-capacity-argument-uat.md) | 全部参数的逐项验收、生产只读刷新与本地状态检查、SIT 分工及门禁记录（#39） |
| General | [清算系统契约](research/general/2026-09-27-collection-clearing-system-contract.md) | 原生请求、分页覆盖、字段与筛选决策（#42） |
| General | [卡模板契约](research/general/2026-09-27-collection-card-template-contract.md) | 原生请求、分页覆盖、字段与筛选决策（#46） |
| General | [清算系统与卡模板全参数 UAT](research/general/2026-09-27-collection-network-config-uat.md) | 27 项参数、595 项生产及私有缓存断言、SIT 分工（#44/#48） |
| General | [Collection architecture refactor UAT](research/general/2026-09-27-collection-architecture-refactor-uat.md) | Six collection capabilities, 2,010 assertions, all cached SLA/VA details, expected VA refusal behavior and cache isolation |
| General | [清算系统与卡模板审查核验](research/general/2026-09-27-collection-network-config-review.md) | Qoder 六项建议逐项处理、Greptile 状态和刷新流程去重验证（PR #49） |
| Payment | [付款产品设计与运行态发现](research/payment/2026-09-08-payment-operations.md) | 产品模型、27 个菜单、查询字段、接口证据、权限限制和 CLI 候选范围 |

- [付款规则查询契约](research/payment/2026-09-27-payment-rules-contract.md)：四项独立采集、全部筛选、嵌套关联和证据边界。
- [付款规则实施与验收](research/payment/2026-09-27-payment-rules-implementation-uat.md)：424 项生产／私有缓存断言、全部参数与合成失败覆盖。
- [已发布 v0.1.13 付款规则 UAT](research/payment/2026-09-27-payment-rules-v0113-uat.md)：隔离安装的发布产物、424 项断言与缓存不变证明。
- [Issues 52–59 发布验收状态](research/general/2026-09-27-issues-52-59-uat.md)：547 项成功断言、延期能力拒绝检查与历史阻塞的证据边界。
- [付款流量规则阻塞](research/payment/2026-09-27-payment-flow-rule-blocker.md)：真实详情身份不一致的重复验证（#54）。
- [付款 PTR 研究与 Graphify/wiki 交叉核验](research/payment/2026-09-27-payment-ptr-research.md)：七类查询对象、术语与状态纠正、候选命令及生产契约验证缺口；初始研究阶段浏览器不可用，后续证据见下方。
- [付款 PTR 原生契约发现与实施阻塞](research/payment/2026-09-27-payment-ptr-contract-discovery.md)：七个列表接口及首屏结构已观察；后续导航 reset/timeout 阻止分页、详情及完整范围验证。
- [PTR 用例与账户库契约](research/payment/2026-09-27-payment-ptr-cases-accounts-contract.md)：用例完整采集、字段投影、筛选；账户库方向隔离仍待证明。
- [PTR 有界单据契约](research/payment/2026-09-27-payment-ptr-orders-contract.md)：UTC+8 更新时间、两端各多取一秒与精确本地区间、完整首批采集。
- [PTR 用例实施与验证](research/payment/2026-09-27-payment-ptr-implementation-validation.md)：公共参数 SIT/UAT 映射、独立审查及网络恢复后的私有缓存验收。
- [PTR 网络总览缺口](research/payment/2026-09-27-payment-ptr-networks-contract-gap.md)：嵌套子记录计数及完整采集超时。
- [PTR 巡检契约调查](research/payment/2026-09-27-payment-ptr-patrol-contract.md)：规则/批次证据、方向与日期边界限制。
- [PTR 自动化批次调查](research/payment/2026-09-27-payment-ptr-automation-contract.md)：有界分页、详情边界、方向与时区缺口。


## 查询契约补充

- [Account-isolation contract](research/general/2026-09-27-collection-account-isolation-contract.md): verified complete acquisition and eight local whole-string filters (#51).
- [Account-isolation acceptance](research/general/2026-09-27-collection-account-isolation-uat.md): 16 options, 315 production/private-cache assertions and synthetic failure coverage.
- [Account-isolation review](research/general/2026-09-27-collection-account-isolation-review.md): review decisions, conservative empty handling and regression checks.
- [Bank-account VA rule blocker](research/general/2026-09-27-collection-bank-va-rule-blocker.md): pagination failure reproduced at multiple supported sizes; #52 remains blocked.

- [付款渠道列表](research/payment/2026-09-08-channel-query-contract.md)：多选筛选、动态字典、响应及页码回退规则。
- [渠道成本列表](research/payment/2026-09-08-cost-query-contract.md)：共享成本范围、查询字段、计费结构及分页重叠限制。
- [产品 SLA 基线列表与详情](research/payment/2026-09-08-sla-query-contracts.md)：请求、分页、响应和时效语义。
- [四项查询综合验证](research/general/2026-09-08-query-contract-audit.md)：跨查询的接入验证、证据方法及审计结论。
- [Channel 页面交互对照探查](research/payment/2026-09-09-channel-ui-investigation.md)：以正常页面真实请求定位重放差异；本轮登录状态及后续验证范围。
- [Channel 分页 Bug 报告](research/payment/2026-09-09-channel-pagination-bug-report.md)：原生 UI 复现步骤、99 页遍历结果、旧表格保留及跨页重复证据。
- [Channel 每页 10 与 100 条对照](research/payment/2026-09-09-channel-page-size-comparison.md)：两轮全页遍历、实际导出、重复与覆盖交集。

## 领域与架构

- [统一 incomplete 规格 v0.1.0](design/unified-incomplete-v0.1.0.md)：默认可发布/读取安全 partial，持续告警；严格模式拒绝；完整性证据、去重、dated/retention 与 17 项验收条件。当前 feature branch 已实施并完成离线验收；[新策略生产 UAT](research/general/2026-10-03-unified-incomplete-production-uat.md) 为 82/83 个目标命令通过，channel EXTERNAL 源端阻塞，ledger balances 按用户要求跳过；尚未发布；[未发布变更记录](../CHANGELOG.md)。
- [统一 incomplete 源码核查](research/general/2026-10-03-incomplete-source-evidence.md)：当前采集器、缓存和必要域证明；单响应重复回归已修复的证据。
- [ADR 0019：可用不完整采集](adr/0019-usable-incomplete-acquisitions.md)：accepted；在当前 feature branch 实施默认可用 partial，修订仅完整发布与 partial 默认失败退出的旧规则。

- [ADR 0005：Channel 离线替代源](adr/0005-channel-snapshot-source.md)：故障期替代传输、数据整理、缓存隔离和切回验收。
- [Channel 替代数据准备状态](research/payment/2026-09-11-channel-snapshot-preparation.md)：崩溃后重新采集，3834 行替代集及仓库 tmp 私有存储。

- [付款运营领域术语](../CONTEXT.md)
- [ADR 0001：按选定查询能力建模](adr/0001-query-capability-model.md)：已选择 B。
- [ADR 0002：v0.1.0 付款范围](adr/0002-payment-v010-scope.md)：渠道、SLA 基线和成本查询；规则类移至下一版本。
- [ADR 0003：本地查询快照](adr/0003-local-query-snapshots.md)：默认只读 SQLite 缓存、72 小时有效期、仅发布完整快照；重试边界待定。
- [ADR 0004：CLI 与登录流程](adr/0004-cli-runtime-boundaries.md)：JSON 输出、三个内置领域插件、`dogopencli login` 管理并校验专用 Chrome。

- [ADR 0008：收款 SLA 配置查询](adr/0008-collection-sla-configurations.md)：独立对象、完整列表与详情、离线快照、本地筛选及完整性边界。
- [ADR 0009：收款 VA 规则查询](adr/0009-collection-va-rules.md)：一页大页采集与失败保留、列表/详情共享字段一致性、稳定 ID 排序、错误分类及银行账户 VA 规则排除。
- [ADR 0010：收款 VA 规则详情容错](adr/0010-collection-va-partial-detail-tolerance.md)：修订 ADR 0009 的全量发布约束，仅容忍后端明确拒绝的单个详情，发布 `detail=null` 且 `dataset_complete=false` 的部分快照并以 `INCOMPLETE_RESULT` 结束；其余失败仍保留旧快照。
- [ADR 0011：收款 VA 容量监控](adr/0011-collection-va-capacity.md)：多页采集与收敛 totalCount、ruleId 行身份、两项本地筛选、预警状态不暴露及空范围/失败包络边界。

- [ADR 0012：收款网络配置快照](adr/0012-collection-network-configurations.md)：独立缓存、单页完整采集、本地筛选与范围边界。
- [ADR 0013: Account isolation](adr/0013-collection-account-isolation.md): independent source, verified envelope and whole-string filtering.

- [ADR 0014：付款规则列表边界](adr/0014-payment-rule-list-boundaries.md)：完整首批采集、银存切换来源节点与关联筛选、flow 阻塞。

- [ADR 0015: Peer domain plugins and shared auth](adr/0015-peer-domain-plugins-and-shared-auth.md): payment, collection and liquidity share core CDP/OAuth while declaring independent origins.
- [ADR 0016: Liquidity list and detail caches](adr/0016-liquidity-independent-list-and-detail-caches.md): independent explicit acquisition; genuine native details and existing incomplete-result policy.
- [ADR 0017: Liquidity retention cap](adr/0017-liquidity-one-million-record-retention.md): 1,000,000 records per leaf; oldest-first time-series eviction with warning and truthful retained coverage.

- [ADR 0018: Liquidity capture store and retention implementation](adr/0018-liquidity-capture-store-and-retention.md): index/capture namespaces, snapshot/history/dated profiles and atomic eviction.

## 协作规范

- [仓库目录与命名](agents/documentation.md)：Python 代码、测试及文档的目录约定。
- [领域文档](agents/domain.md)：根目录 `CONTEXT.md` 和 `docs/adr/`，尚不存在时不创建占位文件。
- [需求与规格跟踪](agents/issue-tracker.md)：GitHub Issues 是需求与规格的记录位置。
- [分诊标签](agents/triage-labels.md)

研究报告是观察快照；已接受的架构决策以上方 ADR 为准，其他实现建议不代表已交付行为。

- [Collection cost PR review validation](research/general/2026-09-26-collection-cost-review.md)
