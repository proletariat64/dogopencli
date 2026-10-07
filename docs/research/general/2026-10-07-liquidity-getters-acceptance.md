# Liquidity 三项原生 getter 实施与验收

Observed: 2026-10-07
Scope: general
Status: snapshot

权威规格：[Issue #136](https://github.com/proletariat64/dogopencli/issues/136)。
本批只实施 demands、realtime、quotes；其余十四项由
[Issue #137](https://github.com/proletariat64/dogopencli/issues/137)保留资格门槛。
没有版本变更、默认分支合并或包发布。

## 原生契约与公开边界

| Getter | 必填字符串身份 | 原生请求 | 输出边界 |
| --- | --- | --- | --- |
| operations demands get | --task-id | GET /riskActionTaskQueryDetail.json；taskId、固定 tntInstId=GUAPW3SG | FUND_REQUIRE 需求核心；内外成功标志、精确 typed taskId；15 个允许字段 |
| network realtime get | --network-id | JSON POST /api/ai/decision/network/detail.json；仅 id | 26 个已交付网络 settings 字段；原生版本，不提供版本固定查询 |
| investment quotes get | --quotation-order-id | form POST /queryQuotationOrder.json；仅 quotationOrderId | quotationDetail 与 productDetail 分别投影；嵌套 quotationId 精确绑定 |

需求根 tntInstId 的原生空值保持空；请求租户另列 request_scope。
网络 version 持久化于原生详情并作为 source_version 暴露，独立于列表版本/采集时间。
报价保留嵌套原生命名、百分比、O/N 和 UTC+08:00 领域解释，不推算金额或日期。
人员、自由文本、附件及关联业务动作排除于首版投影。

默认 get 只读独立详情缓存。显式
`refresh liquidity <resource> detail get <identity>` 只采集选定对象；
列表不代替详情，也不自动爬取详情。Live 不写缓存且失败不回退。
身份冲突、错误成功标志、认证/传输/业务失败不会发布新详情或覆盖旧有效缓存。
复用 ADR 0015、0016、0018、0019 及既有共享允许清单、CDP/OAuth、SQLite、结果策略。

## 本地验证

测试通过公共 CLI、fake CDP 和临时真实 SQLite，验证请求方法/编码/精确字段、
类型/身份/租户/来源拒绝、嵌套投影、原生十进制精度、空值和未知状态，
以及独立对象/列表缓存、live 不写入/不回退、失败刷新保护、版本隔离及帮助/描述。
实施提交为 `022b8f3`。210 项相关测试通过，覆盖公共详情、风险/策略详情、报价、
snapshot 和 capability 的共享回归；Ruff check 与 format check 通过。
Graph 已刷新，并针对实际默认分支 origin/master 分析变化；图的间接 CLI 测试边不能
完整表示这些行为覆盖，人工审查继续核对公共测试。最终审查与远程 CI 单独记录。

Standards 审查没有规范违例；一项重复元数据组装的维护建议不属于正确性缺陷。
Spec 审查初次指出列表/详情及 schema 隔离验收未充分覆盖，随后新增三个叶子的
公共 CLI 用例：已存在列表时 get 仍 CACHE_MISS，两个方向刷新互不破坏 capture，
schema 切换必须显式刷新且旧 schema capture 保留。Getter 与父列表相关 150 项测试通过；
独立 Spec 复验确认这些门槛及生产 UAT 均已完成，没有剩余规格发现。

初次远程全量测试为 2871 passed、28 subtests passed、2 failed：旧 network get
延期断言已修正，字段证据缺失在 `4d17754` 修复：注册三个真实 getter 的15/26/17字段，
quote schema 保留两个原生层次、必填 quotationId 与可缺失/null 的产品段。
新增公共 describe 用例验证字段边界及零传输，相关 128 项测试通过，Ruff/format 通过。
两轴复审此修复均没有物质性发现。最终远程门禁及本地 Kimi 输出记录于
[PR #138](https://github.com/proletariat64/dogopencli/pull/138)，不以初次失败作为最终通过证据。
远程 Qoder review 未产出代码结论（日志：no valid model config found）；用户明确说明
本月额度用尽并要求忽略其失败，不修改 workflow，也不把失败记为通过。

## 独立生产 CLI UAT

首次 getter 验收 **0/3，认证阻塞**。9222 专用 headless Chrome 的 CDP 元数据可达，
原生 Liquidity 启动页进入登录页，公开 auth check 返回 auth_required，
公开 demand refresh 返回 AUTH_REQUIRED。
未发送业务查询；已有 target 清单及生产缓存 SHA-256 保持不变。
前两次 sandbox 尝试发生 websocket 超时，环境外的相同有界调用进一步确认登录状态；
超时不计作业务契约失败或成功验收。首次尝试未保留初始 target 清单而报告不一致，
原因未确认；第二次及最终尝试保留清单并证明完全一致，未发现遗留临时 target。
在上述验收尝试中未启动、切换或修复 Chrome，未隐式登录。

用户明确要求打开登录页面并完成人工 SSO。复用现有登录生命周期和专用 9222 profile；
公共 login 没有 domain 参数，本次向原有生命周期显式传入 Liquidity 启动页，
没有更改应用源码或另建认证栈。Headed 验证后切回 headless，公共
`auth check --domain liquidity` 再次确认 authenticated。

集成源码 `022b8f3`（文档提交 `be56c34`）独立生产 CLI UAT **3/3 PASS**：

| Getter | 同次原生值核对 | 独立 refresh / 断开传输 offline / live | 结果 |
| --- | --- | --- | --- |
| demands | 15 个需求核心字段，FUND_REQUIRE、typed taskId、空 tenant 原样；request_scope 与原生回显分离 | 全部通过 | PASS |
| realtime | 26 个网络配置字段，typed id；原生 version 与 refresh/cache/live 的 source_version 一致 | 全部通过 | PASS |
| quotes | 17 个 quotationDetail/productDetail 字段，原生 form 编码及嵌套 quotationId | 全部通过 | PASS |

每次 refresh 只发一条真实详情请求；记录外部 CDP 返回但不替换响应，按规格允许字段
独立计算期望对象并逐值比较。离线把 CDP 指向不可达的允许端口，完整数据与该 capture
一致且未调用 CDP；live 与自身同次原生响应一致，私有缓存 SHA-256 字节不变。
断开传输的 live 返回失败且 data=null，随后离线旧 capture 保持可读；没有回退。
每个 getter 的 help/describe 通过。共发出 6 次 inquiry-only 详情请求（3 refresh、3 live）。
最终 UAT 原有 target 清单完全一致，生产缓存 SHA-256 保持不变。
这证明每叶一个已知正向对象的验收，未爬取全部对象或恢复其余十四个 getter。
规格阶段的成功 probe 与本次实施后 UAT 分开记录；Issue #136 由 PR #138 合并后关闭。
