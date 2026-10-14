# 默认使用可验证的不完整采集并统一质量处置

Status: accepted — implemented on feature branch; not released
Date: 2026-10-03

权威规格：[GitHub Issue #78](https://github.com/proletariat64/dogopencli/issues/78)。

用户选择让 DI/AI 分析继续使用可验证的部分数据：正常 refresh 可发布 incomplete 缓存，正常 live/离线读取返回有效记录并持续告警，严格调用者显式要求完整。保留完整性事实、原生身份、范围和必要业务证明；去重后仍缺对象不能标 complete，只有具名契约证明相同重复不损害覆盖时才允许 complete 带告警。

采用领域采集证据、公共结果策略、领域原子提交三层。默认可用 partial 的 error=null、退出 0，warnings 与 stderr 告警包含原因；严格 partial 为 INCOMPLETE_RESULT/退出 1，不暴露数据、不发布。发布后的质量与实际 published 状态一起返回，采集质量必须持久化并在离线读取、dated 覆盖和 retention 中保留。

这明确重新考虑 [ADR 0003](0003-local-query-snapshots.md) 的“仅完整真实来源快照发布”及 [ADR 0010](0010-collection-va-partial-detail-tolerance.md) 的“部分发布后失败退出”：全有或全无会丢弃可供分析的合法数据，但错误标完整会制造不存在证明和误导统计。选择可用性与真实质量分开；代价是默认退出码不再承担完整性门禁，自动化必须使用 --require-complete。最新安全 partial 可替换旧 complete，不引入优选旧版本或双缓存。

本决定在当前 feature branch 已实施，并完成[新策略生产只读 UAT](../research/general/2026-10-03-unified-incomplete-production-uat.md)：82/83 个目标命令通过，channel EXTERNAL 源端阻塞，ledger balances 按用户要求跳过；尚未发布。历史文档保留当时证据。全部迁移、缓存兼容、PTR稳定性例外与验收条件见[统一规格](../design/unified-incomplete-v0.1.0.md)，对外行为变化见[未发布变更记录](../../CHANGELOG.md)。

## 2026-10-14：现金账户单空洞覆盖例外（#162）

[规格 #162](https://github.com/proletariat64/dogopencli/issues/162) 接受一个受限兼容定义：仅现金账户目录原生报数比唯一实取多一，且本次采集再次验证内部单空洞、相邻位置及覆盖区间身份一致时，可按原生报数减去该已验证位置判断清单完整。保留原生报数、有效预期数、实取数、偏移及当前验证证据，发布 `VERIFIED_BACKEND_HOLE`，不再把已接受差异报告为 `COUNT_SHORTFALL`。

这不是被压制账户无业务意义的证明，也不豁免其他叶子、多个缺口、边界缺口、重复冲突或不稳定数据。历史提示每次必须重验。复合账户的清单覆盖和所需详情覆盖分别报告；基线未匹配或详情拒绝仍使顶层 incomplete，严格调用不返回数据、不替换业务槽。

## 2026-10-15：银行黑名单的最新创建记录选择（#168/#176）

用户明确确认银行以 `bankId` 识别，同银行取原生 `gmtCreate` 较晚的完整记录。
这是银行黑名单的业务选择规则，不声明来源行或版本身份，也不改其他名单的重复策略。
先验证原始分页、全部边界与终止覆盖，再从实取行中选择；原生报数、到达行数和所选银行数分别保留。
完整的来源行采集可以产生较少的银行结果，以具名选择合同解释此差异，告警但不报 COUNT_SHORTFALL。
缺少来源行覆盖证据仍 incomplete，严格拒绝；无效创建时间、同时间不同内容和变化的分页证据仍硬失败。
此记录选择不恢复历史存储或改变 ADR 0020 的 live、refresh、离线和单槽规则。
