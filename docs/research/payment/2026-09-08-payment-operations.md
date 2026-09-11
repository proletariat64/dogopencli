# 付款产品设计与运行态发现

Observed: 2026-09-08
Scope: payment
Status: snapshot

## 结论

付款运营根覆盖网络建设、PTR、价格、SLA、流量、换银存、异常、风险和运营处置。当前账号稳定可见 9 组、27 个子菜单，本轮已逐页读取页面结构，并验证了代表性查询和详情。

已验证的渠道查询和流量规则列表/详情适合作为首批 CLI 候选。付款单据查询入口也位于根内，但当前账号查询被明确拒绝；该能力不能当作已可用功能交付。

本报告将知识库设计与生产事实分开记录。CDP、登录、后端拓扑、错误分类和只读传输约束统一见 [通用报告](../general/2026-09-08-platform-access.md)。

## 证据与方法

- 设计段：优先通过现有 graphify 图的 `query`、`explain` 定位，再阅读源 Markdown；没有重建或更新知识图谱。
- 运行态：从 [付款管理根](https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/) 进入，读取菜单、表单标签、表头、分页、iframe 与查询网络事件。
- 验证：使用页面查询/详情入口，对流量规则 GET 和同行转账规则 POST 做了浏览器内只读重复请求，均返回业务成功。
- 边界：没有执行编辑、审批、推进灰度、启停、生效、同步、PTR 发起、退款、风险关闭或业务重试。未下载原始业务数据。

下面的“页面已观察”仅证明入口和结构可见；“查询成功”才表示本次请求返回业务成功。报告不包含全部接口参数或所有详情分支。

## 设计段：领域对象与运营问题

| 对象 | 产品含义 | CLI 查询应保留的区分 | 设计来源 |
| --- | --- | --- | --- |
| 平台商与付款合约 | 谁签约了哪些付款能力 | 业务主体、业务场景、平台商和签约身份不随意合并 | D1、D8 |
| 付款套餐 | 币种、地区、账户类型、OBO/FVT、服务策略等能力组合 | 套餐不是资金方案；页面业务套餐 ID 与服务使用的组合 ID 不一定相同 | D1、D4 |
| 流出通路 | 某业务主体和场景可用的资金路径 | 业务主体与流出主体、付款币种与收款币种分别保留 | D1 |
| 资金方案 | 具体实现资金路径的步骤和末端银存关联 | 一个通路可关联多个方案 | D1 |
| 渠道、银存、清算网络 | 可实际承担付款的机构账户与网络能力 | 银行名称不是完整主键；一个账户可支持多个网络 | D1、D2 |
| 运营规则与版本 | 按场景限制或选择能力，控制流量与异常处理 | 配置状态、审批状态、灰度状态及版本不能合并 | D2、D3 |
| 付款及关联单据 | 产品、调拨、金融交换、银行处理等层次的运行记录 | 多层单号与状态分别保留 | D5、D6 |
| 路由记录与 GPI | 内部决策依据及外部银行进度 | 已发生的决策记录与重新运行决策不同 | D6、D8 |

运营最有价值的问题包括：某主体和币种地区能否付款、有哪些可用账户和网络、为何选中或排除了某渠道、哪版规则在生效，以及一笔付款在哪个处理阶段发生失败或退票。

## 设计段：容易误读的变化

- D3 明确“已提交”在生产不生效，“灰度完成”也不等于“线上生效”；修改规则时存在新旧版本，未命中灰度的交易仍可能消费旧版。
- D4 将套餐服务策略扩展为多选；页面业务套餐 ID 保持不变，向上游提供的 ID 按业务套餐 ID 和服务策略组合。这是设计演进证据，尚未在本轮套餐运行页面复验。
- D5 将调拨单号、指令单号、End-to-End ID、Bank Ref ID、UETR 分开。其 UETR 查询设计先读取 GPI 中的 End-to-End ID，再定位调拨单。
- D6 区分预咨询付款银存决策与正式流出清算网络决策，保留触发校验、输入、候选范围和排除原因。
- D7 中“超限拆单规则”是新增需求，不能因 PRD 中有原型就认定生产已上线。本轮最终可见菜单中没有该独立入口。
- 源文件名中的 2026 日期不一定代表设计始于 2026：例如 D2 版本记录为 202204，D6 为 202207/202301。字段及生命周期应同时核对文档版本和生产响应。

## 运行态：菜单地图

下表路径均相对于 `/productOperation/paymentProductManagement/`。名称按页面含义译为中文；界面实际存在中英文混排。

| 分组 | 子路径 | 页面内容 |
| --- | --- | --- |
| 网络建设 | `networkConstruction/channelsManagement` | 付款渠道管理 |
| 网络建设 | `networkConstruction/oneCodePassRuleConfig` | 一码通生效规则 |
| 网络建设 | `networkConstruction/sameBankTransferRuleConfig` | 同行转账可用性规则 |
| 网络建设 | `networkConstruction/onHoldRuleConfig` | HOLD 规则 |
| 网络建设 | `networkConstruction/exchangeSettlementRules` | 结汇路由规则 |
| PTR | `productPTRManagement/outflowNetworkView` | 流出网络视图 |
| PTR | `productPTRManagement/caseLibrary` | 测试用例库 |
| PTR | `productPTRManagement/orderInquiry` | PTR 单据查询 |
| PTR | `productPTRManagement/autoFlowManagement` | 自动流程批次管理 |
| PTR | `productPTRManagement/beneficiaryAccountLibrary` | 收款账户库 |
| PTR | `productPTRManagement/patrolRuleLibrary` | 巡检规则库 |
| PTR | `productPTRManagement/patrolBatchLibrary` | 巡检历史批次 |
| 价格 | `productPriceManagement/channelCost` | 渠道成本 |
| SLA | `productSLAManagement/SlaManagement` | 产品 SLA 基线 |
| SLA | `productSLAManagement/sLAruleConfiguration` | 渠道 SLA 规则 |
| 流量 | `channelTrafficOperation/rule` | 流量运营规则 |
| 流量 | `channelTrafficOperation/cost` | 降本运营规则 |
| 换银存 | `bankSwitchOperation/bankSwitchManage` | 银存切换配置 |
| 异常交易 | `abnormalTransactionManagement/retryRule` | 交易重试规则 |
| 风险 | `productRiskManagement/dashboard` | 付款风险大盘 |
| 风险 | `productRiskManagement/point` | 风险点管理 |
| 风险 | `productRiskManagement/riskOperation` | 风险指标运营 |
| 风险 | `productRiskManagement/eventOperation` | 风险事件运营 |
| 风险 | `productRiskManagement/orderMonitoring` | 风险单据监控 |
| 运营处置 | `operationalDisposal/orderOperation` | 付款单据查询与运营 |
| 运营处置 | `operationalDisposal/manualRefund` | 人工退票页面 |
| 运营处置 | `operationalDisposal/outflowRiskManage` | 流出风险管控 |

最终重新展开菜单后仍为 27 个入口。加载过程中曾短暂看到 Payment Card Template Config 文本，但稳定菜单未出现，未将它列为可用入口。

根内未直接出现套餐或签约菜单；顶层导航另有 Global Standard Payment 和 Collection And Payment Product Signing，本轮没有扩展探索这些模块。

## 运行态：主要查询字段

| 页面 | 筛选与结果中的重要内容 | 验证情况 |
| --- | --- | --- |
| 渠道 | 流出场景、银行、账户别名/账号、国别、清算网络、付款/收款币种、生效状态；结果含成本/时效评分、FVT、灰度、集成和通信模式 | 点击 Search 后查询成功；初始空表不能解释为没有渠道 |
| 一码通 | 流出场景、收款国别地区、付款币种、流出渠道；列表含清算网络和规则状态 | 页面、字典请求和列表请求已观察；未单独复验成功结果 |
| 同行转账 | 付款银行简称、规则状态；判断方式、优先级、付款行清算号和收款行匹配条件 | 页面查询及 CDP 重复查询成功 |
| 流量规则 | 名称、业务主体/线、付款/收款币种、地区、账户类型、服务策略、商户、状态 | 列表、详情及 CDP 重复查询成功 |
| 降本规则 | 名称、业务线、法律主体、收款币种/市场、OBO、FVT；结果含状态和切流比例 | 自动列表查询成功 |
| 换银存 | 来源/目标银存及网络、状态；版本、策略、比例和切换阶段 | 自动列表查询成功 |
| 重试规则 | 主体、业务线、机构、币种、地区、账户、网络、状态；交互/集成模式 | 自动列表查询成功；没有执行重试 |
| 成本 | 成本类型、主体、机构、账号、交易币种、费用承担、网络；状态与审批状态 | 列表已显示数据，具体 API 未逐一验证 |
| 产品 SLA | 业务线/主体、收款币种、目的地、状态；付款成功 SLA、到账 SLA、节假日 | 列表与详情请求成功；详情含时区 |
| PTR | 用例、渠道、账户、网络、币种、OBO/FVT、验证状态、批次与巡检规则 | 各页面列表可见；没有发起 PTR 或修改结果 |
| 风险 | 风险场景、风险点、指标、事件、责任人、状态和单据关联 | 大盘和部分列表请求成功；个别辅助查询失败，非全量权限验证 |
| 付款单据 | 多层单号、银行流水、商户、账户、币种金额、时间、OBO/FVT、退票原因 | 页面可见，实际查询因权限不足被拒绝 |

“运营处置”不能整体等同于写操作：其中存在查询入口；同时，“PTR 管理”也不能整体当作只读工具，其页面提供批量发起、启停巡检、审批和结果修正等写动作。

## 运行态：接口证据

为避免把同名路径误认为同一接口，以下按实际主机分组。只记录参数名，不保存认证参数值和生产实体标识。

### ifundcontrolprodops.alipay.com

| 编号 | 方法与路径 | 关键参数/结构 | 本轮结果 |
| --- | --- | --- | --- |
| P1 | GET `/api/fundOut/flowOperation/rule/query` | `pageNo`、`pageSize`；`data.businessDataList` | 页面查询和浏览器内重复请求成功；首页使用 `pageNo=0` |
| P2 | GET `/api/fundOut/flowOperation/rule/detail` | `ruleId`；`data.businessData` | 点击 Detail 后成功 |
| P3 | GET `/api/fundOut/flowOperation/rule/getClearNetworkByAccountAliasName` | `accountAliasName` | 随详情读取成功，返回网络、通信和集成模式 |
| P4 | GET `/api/fundOut/costCutFlow/query` | `pageNo`、`pageSize`；`data.businessDataList` | 成功 |
| P5 | GET `/api/fundNavigation/nodeSwitch/query` | `pageNo`、`pageSize`；按来源节点组织切换要求列表 | 成功 |
| P6 | GET `/api/fundOut/flowOperation/exceptionRetryRule/page` | `pageNo`、`pageSize` | 成功 |
| P7 | GET `/api/fundOutMainOrder/searchByExplorer` | 本次默认查询含 `pageNo`、`pageSize` | HTTP 200、业务失败；鉴权失败，用户无权限 |
| P8 | GET `/api/fundOut/forexChannel/businessElement/query` | `pageNo`、`pageSize` | HTTP 200、`success=false`；响应含权限字段，未进一步复验 |
| P9 | POST `/api/fundInOut/riskEvent/query`、POST `/api/firewall/summary` | 页面风险查询请求 | 成功；完整筛选契约未确认 |

P1 返回 `ruleId`、`groupRuleId`、`ruleName`、`groupRuleName`、`ruleVersion`、`status`、`auditStatus`、业务与币种地区字段。P2 进一步包含 `channelList`、`strategyType`、`fallBackAction`、收款账号/BIC/清算号的匹配条件及 `serviceLevelList`。这些字段支持查询规则实际配置，不能被压缩成名称加启用开关。

### ifundboss.alipay.com 与 ifundboss-api.alipay.com

| 编号 | 主机 | 方法与路径 | 本轮结果 |
| --- | --- | --- | --- |
| P10 | `ifundboss.alipay.com` | POST `/payout/api/bookDecisionRule/search.json` | 页面查询和浏览器内重复请求成功；请求 `pageNum=1`、`pageSize=20`；数据在 `resultObj.payoutBookDecisionRuleVOList` |
| P11 | `ifundboss-api.alipay.com` | POST `/payout/api/ability/search.json` | Search 查询成功；请求包含 `payoutType`、`pageNum`、`pageSize`；数据在 `resultObj.payoutAbilityVOList` |
| P12 | `ifundboss-api.alipay.com` | POST `/payout/api/firewall/indicatorRule/query` | 风险指标列表查询成功 |
| P13 | `ifundboss-api.alipay.com` | POST `/api/fundInOut/riskEvent/query.json` | 风险事件列表查询成功；完整筛选契约未确认 |

P11 返回的字段包含 `abilityId`、`configVersion`、币种与限额、清算网络、`costLevel`、`noFvtCostLevel`、`efficiencyLevel`、`cutOffTime`、灰度相关字段、`integrationMode` 和 `communicateMode`。报告只记录结构，不保留账户值、金额或生产规则内容。

### iglobalfundcontrol.alipay.com

| 编号 | 方法与路径 | 本轮结果 |
| --- | --- | --- |
| P14 | POST `/api/fundOutSlaBaseline/queryFundOutSlaBaseline` | 产品 SLA 列表查询成功 |
| P15 | GET `/api/fundOutSlaBaseline/getFundOutSlaBaselineDetail` | 按 `slaBaselineId` 读取成功；详情在 `resultData`，包含状态、时区、节假日及成功/到账时效字段 |

接口路径不是开发规格，也不是整段 URL 前缀的授权。后续实现需要逐个固定方法、参数、响应和错误契约；共享收付款 API 还需核对付款范围的筛选条件。

## 权限与范围结论

[付款单据查询](https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/operationalDisposal/orderOperation) P7 的业务错误码为 `IPAY_RS_51195250319`，描述为“鉴权失败，用户无权限”。页面当时显示 “No data”；该结果不能解释为付款记录为零。本轮未申请角色、修改权限或换后端绕过。

运行态修正了设计研究中的一个范围判断：历史培训资料的逐笔查询链接位于其他路径，但今天付款根内确实有 `operationalDisposal/orderOperation`。同时，根外的套餐、签约和历史基线页面仍不能默认为本轮已验证范围。

## CLI 候选顺序

以下是建议，不是已接受的版本规格：

1. 先实现 [渠道列表](https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/networkConstruction/channelsManagement) 和 [流量规则列表/详情](https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/channelTrafficOperation/rule)，覆盖核心网络能力与规则运营。
2. 再扩展同行转账规则、降本、重试配置和 [产品 SLA](https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/productSLAManagement/SlaManagement) 等已验证查询。
3. PTR 与风险先限定为已有记录查询；涉及批量执行、修正、关闭和处置的入口不进入 CLI。
4. 付款单据查询保留为待权限满足后复验的能力，当前不可宣称支持。

## 未验证事项

- 各列表的全部筛选、排序、分页边界以及其字段权限；本轮不是完整 API 逆向或权限审计。
- 渠道、HOLD、一码通、风险等页面的全部详情分支；人工退票与流出风险页仅检查结构，没有执行业务处置。
- PTR、渠道成本等页面的完整 API 对应关系，以及多个业务状态的确切枚举语义。
- 套餐、签约、卡模板、超限拆单和 GPI 的当前独立页面/接口；部分仅有设计资料。
- 共享收付款风险接口的完整付款过滤条件；不能因位于付款菜单就假定默认数据范围恒为付款。
- headless 模式下的登录态和查询兼容性，见通用报告。

## 知识库来源

知识库根为 `~/dev/dogpdkb/graphify_flatten_ready/`；现有图为其下 `graphify-out/graph.json`。检索示例：

```bash
rtk proxy graphify query '流出套餐' --graph ~/dev/dogpdkb/graphify_flatten_ready/graphify-out/graph.json --budget 2400
rtk proxy graphify explain '规则状态推进流程操作说明书' --graph ~/dev/dogpdkb/graphify_flatten_ready/graphify-out/graph.json
rtk proxy graphify explain '路由决策状态查询' --graph ~/dev/dogpdkb/graphify_flatten_ready/graphify-out/graph.json
```

图查询存在截断、推断关系及缺失行号，因此以下结论以源文档相应段落为准。编号是本报告的引用编号，不是生产实体 ID。

| 编号 | 源文件（相对知识库根） | 核对段落 |
| --- | --- | --- |
| D1 | `Planning-and-progress-of-key-projects__Key-business-line-s-project__B__B类产品化__全球付款资金网络产品化__全球资金付款网络产品化PRD-2021-08-13-[81756835].md` | 第 144、240、349、470、570、616 行起：术语、套餐、签约、通路和网络 |
| D2 | `收付款产品__调拨中心产品化能力建设__运营能力建设__调拨产品化-调拨基础数据人工运营PRD-2026-04-18-[142062444].md` | 第 26、85、163 行起：能力职责、字段和运营页面 |
| D3 | `收付款产品__调拨中心产品化能力建设__新调拨中心产品化PRD__调拨流量运营能力灰度建设__规则状态推进流程操作说明书-2026-04-19-[221158376].md` | 第 8、26、36、52 行起：状态、生效和灰度多版本 |
| D4 | `Planning-and-progress-of-key-projects__Key-business-line-s-project__B__B类产品化__收付款产品降本专题__付款产品降本一期需求-2023-02-23-[231580456].md` | 第 387–390 行：套餐多策略与 ID |
| D5 | `收付款产品__调拨中心产品化能力建设__运营能力建设__调拨单查询运营能力优化-03-2023-03-06-[233763597].md` | 第 4、11、19、30 行起：多 ID、退票金额和 UETR |
| D6 | `收付款产品__调拨中心产品化能力建设__运营能力建设__运营透明度提升-路由决策状态查询-2026-04-19-[168871821].md` | 第 63、83、143、165 行起：决策字段与两阶段视图 |
| D7 | `Planning-and-progress-of-key-projects__Key-business-line-s-project__Antom__GSA__Antom__CY26__付款产品-渠道超限-产品能力升级-2026-05-20-[542083062].md` | 第 65–105 行：流量菜单、拟新增拆单规则与审批状态 |
| D8 | `收付款产品__收付款培训文档__PC-Product-Introduce-2026-08-05-[277777749].md` | 第 22–40 行：路由核心能力和历史门户入口 |
