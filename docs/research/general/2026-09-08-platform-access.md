# 运营平台访问与通用发现

Observed: 2026-09-08
Scope: general
Status: snapshot

## 结论

通过已登录 Chrome 的 CDP 在页面上下文执行查询是可行的。本次同时验证了原生页面的 GET 查询和嵌入页面的 POST 查询；两者均返回业务成功。付款平台是多个应用的聚合入口，CLI 需要明确区分入口页面、嵌入页面和实际 API。

本报告记录跨产品的访问机制、协议差异和只读边界。付款领域、完整菜单及已观察的接口分别见 [付款产品报告](../payment/2026-09-08-payment-operations.md)。收款产品没有进行运行态探索。

## 证据与方法

| 编号 | 来源 | 本轮做了什么 | 证据限制 |
| --- | --- | --- | --- |
| G1 | [付款运营根](https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/) | 用户在 headed Chrome 手动登录后，通过 CDP 读取 DOM、菜单、iframe 和网络事件 | 仅代表当时账号、权限及站点版本 |
| G2 | 付款页面发出的查询请求 | 观察 URL、方法、参数结构、响应结构和业务结果；对两条已确认查询进行浏览器内重复请求 | 没有穷举参数、错误分支或全部接口 |
| G3 | `~/dev/di/docs/spec/browser-cdp-v1.1.md` | 阅读 headed/headless、profile、就绪检查和 API 查询规范 | 参考实现，不是 dogopencli 已实现能力 |
| G4 | `~/dev/di/src/diexporter/browser_cdp.py` | 阅读 CDP transport、页面就绪、fetch 和 target 清理实现，重点第 110、180、265、357、401 行起 | 未运行 DI 导出或其 Chrome 启动器 |
| G5 | `~/dev/di/scripts/launch_di_chrome.sh` | 阅读 profile 互斥、进程归属和模式切换实现 | 原默认端口位于本项目禁用范围，不可照搬运行 |

证据来自本轮会话的页面与 Network/CDP 输出。报告保存经过筛选的结论和结构信息，不保存原始 HAR、响应数据集、Cookie、登录票据或截图。没有执行新增、编辑、审批、生效、同步、退款、PTR 发起等业务操作。

## CDP 与登录

本轮使用 `http://127.0.0.1:9222` 和独立的临时 Chrome profile。最初导航付款根时进入登录页；用户完成登录后，页面回到付款产品管理。所有探索均使用该 headed 会话。

浏览器扩展连接不可用并不代表直接 CDP 不可用：本轮最终使用 Python 经 CDP 成功访问页面。此前建议寻找 “Settings → Computer use” 不适用于本次接入方式，不应成为项目的安装前置条件。

实际验证的请求链路为：

```text
Python → Chrome CDP → 目标页面或 iframe 的执行上下文
                    → 浏览器内 fetch → 对应应用 API
                    ← HTTP 状态 + 业务结果 + 数据结构
```

查询使用浏览器已有登录态，复验只复用了页面已发出的查询请求。本轮没有实现独立 OAuth 客户端，也没有确认底层认证授权协议的完整细节。

项目目标仍是 headed 完成人工 OAuth/SSO 登录、headless 执行日常查询；本轮没有切换 headless。参考 DI 时应保留以下机制：

- 同一专用 profile 在 headed 与 headless 间复用，同一时刻仅由一个 Chrome 进程占用。
- CLI 查询层连接既有 CDP；登录与浏览器生命周期单独处理。
- 请求前等待页面稳定就绪，识别重定向和登录失效。
- 区分浏览器不可达、登录失效、接口权限不足、传输异常和业务失败。
- 只关闭本次创建的 target，避免影响用户其他标签页。

CDP 端口 9330–9340 在开发、测试和验证中均禁止使用；本轮未连接这些端口。9222 是本次验证端口，尚未确定为 CLI 的固定默认值。

## 聚合页面与实际 API

| 页面载体 | 本轮观察到的后端 | 付款范围内的例子 |
| --- | --- | --- |
| `ifundcontrol.alipay.com` 原生页面 | `ifundcontrolprodops.alipay.com` | 流量、降本、换银存、重试规则和部分风险查询 |
| `intl-fluxnet.alipay.com` iframe | `ifundboss.alipay.com` | 一码通、同行转账规则 |
| `ifundbossportal.alipay.com` iframe | `ifundboss-api.alipay.com` | 渠道、HOLD、风险及人工退票页面 |
| `igfc.alipay.com` iframe | `iglobalfundcontrol.alipay.com` | 已确认的产品 SLA 查询；成本和多个 PTR 页面同样嵌入 igfc，具体 API 未逐一核验 |

外层 DOM 的主内容可能只有面包屑和标题。必须先识别 iframe，再进入对应执行上下文读取字段、列表和请求。仅检查外层表格数量会产生“没有数据”的错误结论。

这些域名是观察到的访问拓扑，不是可以整站放行的接口白名单。每个插件仍需声明具体查询操作及其参数范围。

## 查询协议差异

| 验证对象 | 请求 | 分页 | 响应中的数据位置 |
| --- | --- | --- | --- |
| 流量规则列表 | GET | `pageNo=0`、`pageSize=10` 为本轮首页请求 | `data.businessDataList`，分页信息在 `data` 中 |
| 流量规则详情 | GET | 不分页，按 `ruleId` 查询 | `data.businessData` |
| 同行转账规则列表 | POST JSON | `pageNum=1`、`pageSize=20` 为本轮首页请求 | `resultObj.payoutBookDecisionRuleVOList`，分页信息在 `resultObj` 中 |
| 渠道列表 | POST JSON | 参数为 `pageNum`、`pageSize` | `resultObj.payoutAbilityVOList` |
| 产品 SLA 详情 | GET | 按 `slaBaselineId` 查询 | `resultData` |

表中首页起点只对已复验的两个接口成立，不能推断为整个后端的统一规则。列表组件可能重复渲染列、使用虚拟行或展开子行，DOM 行数不适合直接充当接口记录总数。

已观察请求包含名为 `ctoken` 的参数。这里只记录参数名称，不保存其值；不能假定简单的 `credentials: include` 就能替代站点所有必要的请求参数。实际 CLI 实现仍需验证令牌来源、有效期及失效行为，避免将登录态复制到业务配置或日志中。

## 成功、无数据与权限

付款单据查询的 HTTP 状态为 200，但业务响应为 `success=false`，错误码为 `IPAY_RS_51195250319`，描述为“鉴权失败，用户无权限”。界面当时呈现 “No data”。

因此必须分别处理：

1. HTTP/网络层是否成功。
2. 业务 envelope 是否成功，是否包含权限或认证错误。
3. 成功结果中的列表是否为空。

“页面可见”不保证“查询获授权”；出现权限错误后不换其他入口绕过。页面加载后显示空表，也可能只是尚未点击查询，例如本轮渠道页面在点击 Search 后才返回列表。

## 只读 CLI 的设计建议

以下是基于观察提出的建议，尚未作为 ADR 接受或实现：

- 核心层负责 CDP 会话、站点上下文、超时、错误分类和查询操作允许清单；付款插件负责查询参数、领域字段与响应解析。
- 查询限制按主机、路径、方法以及请求中的动作含义实施，不能单靠禁止 POST 或检查 URL 中是否有 `query`。
- 对外暴露有限的列表、详情、字典和已有记录查询，不提供任意 URL、JavaScript 或原始请求命令。
- 只读取已有路由结果，不通过重新执行路由、PTR 或业务重试来“验证查询”。
- 分页和结果 envelope 由具体适配器转换；保留源字段、状态和版本信息，避免把不同业务状态压成一个成功标志。
- 插件以本机可信代码为前提。接口注册限制不是隔离恶意 Python 插件的安全沙箱。
- 导出按钮可能创建服务端任务，本轮未使用；不能自动认定为纯 inquiry。

## 未验证事项

- headed 登录态切换 headless 后，对所有嵌入应用和 API 是否持续有效。
- 登录超时、令牌过期、区域切换、403、重定向及跨域错误的完整行为。
- 各 API 的全部筛选字段、页码上限、排序、限流和字段权限。
- 成本、PTR 等页面是否在全部场景使用相同后端或相同 envelope。
- 插件发现、配置格式、CLI JSON 协议与自动化测试尚未实现。

生产证据是一次账号视角的快照。后续应复验确切查询契约，再将需要接受的架构决定记录到 ADR；不以历史设计文档替代运行态验证。
