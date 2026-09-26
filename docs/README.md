# 文档索引

## 产品规格

- [v0.1.0 付款只读 CLI 规格（GitHub Issue #1）](https://github.com/proletariat64/dogopencli/issues/1)：已发布，标签 `ready-for-agent`；公开 CLI＋假 CDP 为 SIT，生产只读验收为 UAT。
- [DI 风格渐进式 CLI 帮助（GitHub Issue #13）](https://github.com/proletariat64/dogopencli/issues/13)：计划与规格已发布，标签 `ready-for-agent`；无参数导航、JSON/text、完整命令目录及离线帮助验收，尚未实现。

- [Data helper v1（GitHub Issue #16）](https://github.com/proletariat64/dogopencli/issues/16)：四个付款查询叶子的离线 schema、字段证据与读取指引；[可运行命令与版本化机器契约](../README.md#data-helper)。
- [收款交易成本查询规划（GitHub Issue #21）](https://github.com/proletariat64/dogopencli/issues/21)：当前开发分支实现固定类型的交易成本列表、live、刷新及离线描述；VA 费用及池/实体账户等仍排除，VA 规则另见 #31。

- [收款 SLA 配置查询（GitHub Issue #27）](https://github.com/proletariat64/dogopencli/issues/27)：列表、真实详情、原子刷新与四项本地筛选；实施及验收见下方报告。

- [收款 VA 规则查询（GitHub Issue #31）](https://github.com/proletariat64/dogopencli/issues/31)：列表、主详情、原子刷新规格；契约证据见 VA 规则研究与当日契约复核；其中“全量详情方可发布”已由 [ADR 0010](adr/0010-collection-va-partial-detail-tolerance.md) 收窄为仅容忍后端明确拒绝的单个详情。

## 研究报告

以下报告各自记录观察日期；运行态仅代表当时账号可见的页面和已验证请求，不保证后续版本、权限或数据不变。

| 范围 | 报告 | 内容 |
| --- | --- | --- |
| General | [运营平台访问与通用发现](research/general/2026-09-08-platform-access.md) | CDP、登录、聚合应用结构、查询协议、只读约束与技术参考 |
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
| Payment | [付款产品设计与运行态发现](research/payment/2026-09-08-payment-operations.md) | 产品模型、27 个菜单、查询字段、接口证据、权限限制和 CLI 候选范围 |

## 查询契约补充

- [付款渠道列表](research/payment/2026-09-08-channel-query-contract.md)：多选筛选、动态字典、响应及页码回退规则。
- [渠道成本列表](research/payment/2026-09-08-cost-query-contract.md)：共享成本范围、查询字段、计费结构及分页重叠限制。
- [产品 SLA 基线列表与详情](research/payment/2026-09-08-sla-query-contracts.md)：请求、分页、响应和时效语义。
- [四项查询综合验证](research/general/2026-09-08-query-contract-audit.md)：跨查询的接入验证、证据方法及审计结论。
- [Channel 页面交互对照探查](research/payment/2026-09-09-channel-ui-investigation.md)：以正常页面真实请求定位重放差异；本轮登录状态及后续验证范围。
- [Channel 分页 Bug 报告](research/payment/2026-09-09-channel-pagination-bug-report.md)：原生 UI 复现步骤、99 页遍历结果、旧表格保留及跨页重复证据。
- [Channel 每页 10 与 100 条对照](research/payment/2026-09-09-channel-page-size-comparison.md)：两轮全页遍历、实际导出、重复与覆盖交集。

## 领域与架构

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

## 协作规范

- [仓库目录与命名](agents/documentation.md)：Python 代码、测试及文档的目录约定。
- [领域文档](agents/domain.md)：根目录 `CONTEXT.md` 和 `docs/adr/`，尚不存在时不创建占位文件。
- [需求与规格跟踪](agents/issue-tracker.md)：GitHub Issues 是需求与规格的记录位置。
- [分诊标签](agents/triage-labels.md)

研究报告是观察快照；已接受的架构决策以上方 ADR 为准，其他实现建议不代表已交付行为。

- [Collection cost PR review validation](research/general/2026-09-26-collection-cost-review.md)
