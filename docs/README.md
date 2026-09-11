# 文档索引

## 产品规格

- [v0.1.0 付款只读 CLI 规格（GitHub Issue #1）](https://github.com/proletariat64/dogopencli/issues/1)：已发布，标签 `ready-for-agent`；公开 CLI＋假 CDP 为 SIT，生产只读验收为 UAT。

## 研究报告

以下是 2026-09-08 的研究快照；运行态仅代表当时账号可见的页面和已验证请求，不保证后续版本、权限或数据不变。

| 范围 | 报告 | 内容 |
| --- | --- | --- |
| General | [运营平台访问与通用发现](research/general/2026-09-08-platform-access.md) | CDP、登录、聚合应用结构、查询协议、只读约束与技术参考 |
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

## 协作规范

- [仓库目录与命名](agents/documentation.md)：Python 代码、测试及文档的目录约定。
- [领域文档](agents/domain.md)：根目录 `CONTEXT.md` 和 `docs/adr/`，尚不存在时不创建占位文件。
- [需求与规格跟踪](agents/issue-tracker.md)：GitHub Issues 是需求与规格的记录位置。
- [分诊标签](agents/triage-labels.md)

研究报告是观察快照；已接受的架构决策以上方 ADR 为准，其他实现建议不代表已交付行为。
