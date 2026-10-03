# 默认使用可验证的不完整采集并统一质量处置

Status: accepted — implemented on feature branch; not released
Date: 2026-10-03

权威规格：[GitHub Issue #78](https://github.com/proletariat64/dogopencli/issues/78)。

用户选择让 DI/AI 分析继续使用可验证的部分数据：正常 refresh 可发布 incomplete 缓存，正常 live/离线读取返回有效记录并持续告警，严格调用者显式要求完整。保留完整性事实、原生身份、范围和必要业务证明；去重后仍缺对象不能标 complete，只有具名契约证明相同重复不损害覆盖时才允许 complete 带告警。

采用领域采集证据、公共结果策略、领域原子提交三层。默认可用 partial 的 error=null、退出 0，warnings 与 stderr 告警包含原因；严格 partial 为 INCOMPLETE_RESULT/退出 1，不暴露数据、不发布。发布后的质量与实际 published 状态一起返回，采集质量必须持久化并在离线读取、dated 覆盖和 retention 中保留。

这明确重新考虑 [ADR 0003](0003-local-query-snapshots.md) 的“仅完整真实来源快照发布”及 [ADR 0010](0010-collection-va-partial-detail-tolerance.md) 的“部分发布后失败退出”：全有或全无会丢弃可供分析的合法数据，但错误标完整会制造不存在证明和误导统计。选择可用性与真实质量分开；代价是默认退出码不再承担完整性门禁，自动化必须使用 --require-complete。最新安全 partial 可替换旧 complete，不引入优选旧版本或双缓存。

本决定在当前 feature branch 实施，尚未发布或执行新策略的生产 UAT；历史文档保留当时证据。全部迁移、缓存兼容、PTR稳定性例外与验收条件见[统一规格](../design/unified-incomplete-v0.1.0.md)，对外行为变化见[未发布变更记录](../../CHANGELOG.md)。
