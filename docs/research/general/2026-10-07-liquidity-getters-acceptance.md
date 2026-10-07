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

## 独立生产 CLI UAT

生产 getter 验收当前 **0/3，认证阻塞**。9222 专用 headless Chrome 的 CDP 元数据可达，
原生 Liquidity 启动页进入登录页，公开 auth check 返回 auth_required，
公开 demand refresh 返回 AUTH_REQUIRED。
未发送业务查询；已有 target 清单及生产缓存 SHA-256 保持不变。
前两次 sandbox 尝试发生 websocket 超时，环境外的相同有界调用进一步确认登录状态；
超时不计作业务契约失败或成功验收。首次尝试未保留初始 target 清单而报告不一致，
原因未确认；第二次及最终尝试保留清单并证明完全一致，未发现遗留临时 target。
在上述验收尝试中未启动、切换或修复 Chrome，未隐式登录。

人工 SSO 完成后须逐叶执行独立 refresh，并把每个投影值与同次原生响应核对；
随后断开传输验证离线同 capture，验证真实 live 的同次原生值及缓存字节不变，
并记录各叶子实际覆盖。规格阶段的成功 probe 不替代上述实施后 UAT。
Issue #136 在这些门槛完成前保持开放；本地测试及审查结果不代表生产验收。
