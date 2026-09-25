# 收款菜单只读深度调查

Observed: 2026-09-26
Scope: general
Status: snapshot

## 结论与证据边界

本报告先固定当前账号可见的 22 个 collection 外层菜单及嵌入入口：15 项观察到业务 iframe，7 项未观察到业务 iframe。外层页面是在业务请求受拦截的条件下读取结构；外层可见、iframe 存在、空表或页面未完整渲染，均不能证明查询成功、无权限或没有业务数据。内层复查结果单列，不能把历史验证计数当作本轮结果。

`va-value` 是此前 agent 提议的未证实候选名，不是操作者提供的业务术语。现有证据没有建立其业务对象或查询契约，应撤回将它作为现成能力的推断；不将规则、容量、池、PTR VA 库或费用换名代替。只有新的实际页面证据支持明确对象时，才形成新的设计输入。[H5]

业务数据严格只读。页面明确报告无权限时，记录准确入口、拒绝提示和受阻范围，供操作者后续申请；不绕过权限，不把登录跳转或请求拦截误记为权限不足。记录仅限菜单、控件、表头、origin/path、结构和脱敏状态；不包含账户值、凭证、生产行、原始响应或 HAR。

## 外层菜单清单

来源：2026-09-26 专用浏览器外层 DOM 结构采样（本轮临时摘要 `/tmp/collection_survey_outer.json`）。以下保留全部 22 项及原始大小写；临时摘要不是长期依赖，本表保存其必要入口证据。

外层基址为 `https://ifundcontrol.alipay.com/productOperation/collectionProductManagement/`，表中路径相对此基址。业务 iframe 只记录 origin/path，不含查询参数；公共 `https://tracert.alipay.com/cross.html` 不计为业务入口。“未观察到”不代表页面一定没有嵌入实现。

| # | 菜单原文 | 外层相对路径 | 业务 iframe（origin/path） | 既有证据与限制 |
| --- | --- | --- | --- | --- |
| 1 | Bank Account VA Rule Management | `networkConstruction/bankVARuleManagement` | `https://ifundbossportal.alipay.com/voucher/bankAccountVARuleManage` | 历史已验证 ID 查询；完整扫描第 34 页元数据零化，未得完整快照 [H1]。 |
| 2 | Account Isolation Rule Configuration | `networkConstruction/businessAccount` | 本次未观察到 | 历史仅菜单，未验证查询契约 [H1]。 |
| 3 | VA Rule Management | `networkConstruction/VARuleManagement` | `https://ifundbossportal.alipay.com/voucher/VARuleManage` | 历史列表 907 个唯一规则；三个主详情样本通过；规则不等于单个 VA [H2]。 |
| 4 | VA Capacity Monitoring | `networkConstruction/VACapacityMonitoring` | `https://ifundbossportal.alipay.com/voucher/VACapacityMonitoring` | 历史仅容量/使用量控件与表头；独立池查询未验证 [H3]。 |
| 5 | Spontaneous account balance inquiry | `networkConstruction/accountBalance` | 本次未观察到 | 历史仅菜单，未验证查询契约 [H1]。 |
| 6 | Collection Clearing System Config | `networkConstruction/clearingSystemConfig` | `https://ifundbossportal.alipay.com/voucher/CollectionClearingSystemConfig` | 历史仅菜单，未验证查询契约 [H1]。 |
| 7 | Collection Card Template Config | `networkConstruction/cardTemplateConfig` | `https://ifundbossportal.alipay.com/voucher/CollectionCardTemplateConfig` | 历史仅菜单，未验证查询契约 [H1]。 |
| 8 | Collection PTR Case Library | `productPTRManagement/caseLibrary` | `https://igfc.alipay.com/receivedPayment/receivedPaymentPtr/productTrialRunBase/ptrInCase` | 历史仅菜单，未验证查询契约 [H1]。 |
| 9 | Collection PTR Order Inquiry | `productPTRManagement/orderInquiry` | `https://igfc.alipay.com/receivedPayment/receivedPaymentPtr/productTrialOperationQuery/productTrialOperationIn` | 历史仅菜单，未验证查询契约 [H1]。 |
| 10 | PTR Collection VA Library | `productPTRManagement/VaLibrary` | `https://igfc.alipay.com/receivedPayment/receivedPaymentPtr/virtualAccount` | 历史 PTR 专用 VA 库语义；现行查询契约未验证 [H5]。 |
| 11 | Channel Cost Management | `productPriceManagement/channelCost` | `https://igfc.alipay.com/receivedPayment/fundCost` | 历史交易成本完整性核验；VA 费用曾成功为空，缺非空 schema [H1]。 |
| 12 | Collection Product SLA Management | `productSLAManagement/SlaManagement` | `https://igfc.alipay.com/receivedPayment/sla/fundInSla` | 历史 55 条配置及全部详情；四个单值筛选样本，业务线独立效果证据不足 [H4]。 |
| 13 | Collection Risk Dashboard | `productRiskManagement/dashboard` | 本次未观察到 | 历史仅菜单，未验证查询契约 [H1]。 |
| 14 | Collection Risk Point Management | `productRiskManagement/point` | 本次未观察到 | 历史仅菜单，未验证查询契约 [H1]。 |
| 15 | Index Risk Operation | `productRiskManagement/riskOperation` | `https://ifundbossportal.alipay.com/riskFirewall/indexOrderRiskOpreation` | 历史仅菜单，未验证查询契约 [H1]。 |
| 16 | Collection Risk Event Operation | `productRiskManagement/eventOperation` | `https://ifundbossportal.alipay.com/riskFirewall/fundInOutRiskEvent` | 历史仅菜单，未验证查询契约 [H1]。 |
| 17 | Collection Risk Order Monitoring | `productRiskManagement/orderMonitoring` | `https://ifundbossportal.alipay.com/payout/exceptionMonitoring/RiskOrderFundIn` | 历史仅菜单，未验证查询契约 [H1]。 |
| 18 | PVA&Duplicate Collection | `operationalDisposal/duplicate` | 本次未观察到 | 历史仅菜单，未验证查询契约 [H1]。 |
| 19 | Manual Collection(Batch) | `operationalDisposal/manualBatch` | 本次未观察到 | 历史仅菜单，未验证查询契约 [H1]。 |
| 20 | Manual Collection Inquiry | `operationalDisposal/manualInquiry` | `https://ifundbossportal.alipay.com/voucher/manual1` | 历史仅菜单，未验证查询契约 [H1]。 |
| 21 | Original Road Back | `operationalDisposal/roadBackInquiry` | `https://ifundbossportal.alipay.com/voucher/originalRoadBack` | 历史仅菜单，未验证查询契约 [H1]。 |
| 22 | Active Collection Confirm | `operationalDisposal/activeConfirm` | 本次未观察到 | 历史仅菜单，未验证查询契约 [H1]。 |

## 外层已显示的业务结构

只有第 5、22 项在本次外层摘要中显示业务筛选和表头。其他 20 项的外层摘要未提取到业务标签；后续内层和原生复查结果见下文。各页均出现的 `Permission Management` 是按钮标签，不是权限拒绝提示。

| 菜单 | 已观察结构 | 限制 |
| --- | --- | --- |
| Spontaneous account balance inquiry | 筛选：银存 VA 规则 ID、银存主体、VA 规则 ID、业务主体、币种、业务线、预警状态。表头包含账户总数、已使用/未使用账户数、昨日/平均每日申请数、单日峰值、预警天数、剩余可用天数及创建/修改时间。按钮：查询、重置。 | 页面英文标题不证明是金额余额；可见中文结构是账户余量监控。未验证请求、单位、统计口径及结果完整性，不等同单个 VA 库存列表。 |
| Active Collection Confirm | 筛选：Billing Date、PSP Agency、Reconciliation Status、Receipt Processing Status、Bank Deposit Account Name。表头含 Bank Account、Actual Receipt Amount、Manual Receipt Amount、Remaining Amount、Amount Of Sent、Amount Of To Be Sent 及状态；另显示 Check Details 结构。按钮含 Add、Search、Reset、Batch Initiated Account。 | 只记录控件，不操作新增或批量发起；本次结构不能证明详情已打开或查询返回成功。 |

## 内层及原生页面复查

本轮对 15 个已观察 iframe 的 origin/path 新建临时页面逐项复查。14 项显示业务控件；第 17 项仅应用壳。以下是 DOM 标签，不是已验证 CLI 参数或响应字段。未点击 Search、Add、开户、导出或任何行操作，也未据此判断数据为空。IGFC 的六页 document.title 为空，但筛选和表头已显示。

### 1. Bank Account VA Rule Management

页面标题：`Bank Account VA Rule Manage - ifundboss`。

筛选标签：`ID`、`Alias Name`、`Account No.`、`Financial Inst`、`Multi currency`、`Area`、`Currency`、`Recon inst`、`Rule status`、`VA Strategy`。

表头：`ID`、`Alias Name`、`Financial Inst`、`Account No.`、`Multi currency`、`Sub-account`、`Area`、`Currency`、`Recon inst`、`VA strategy`、`Rule status`、`Creation time`、`Modification time`、`Operator`、`Action`。

按钮：`Search`、`Reset`、`Add`。

### 3. VA Rule Management

页面标题：`VA Rule Manage - ifundboss`。

筛选标签：`ID`、`Alias Name`、`Financial Inst`、`Account No.`、`Multi currency`、`Area`、`Currency`、`Recon inst`、`Business entity`、`Scene code`、`Rule status`、`Local cross-border`、`Memo`、`Exists monitor config`、`VA Strategy`。

表头：`ID`、`Alias Name`、`Financial Inst`、`Account No.`、`Multi currency`、`Area`、`Currency`、`Recon inst`、`Business entity`、`Scene code`、`VA Strategy`、`Rule status`、`Local cross-border`、`Creation time`、`Modification time`、`Memo`、`Operator`、`Action`。

按钮：`Search`、`Reset`。

### 4. VA Capacity Monitoring

页面标题：`VA Capacity Monitoring - ifundboss`。

筛选标签：`Bank Account VA Rule ID`、`Account No.`、`Bank Account Entity Code`、`Legal entity code`、`VA Rule ID`、`Scene code`、`currency`、`Memo`、`Warning state`。

表头：`Bank account va rule info`、`VA rule info`、`var number monitor`、`Va available days monitor`、`Extra info`、`Operater`、`Bank Account VA Rule ID`、`Account No.`、`Bank Account Entity Code`、`distributable VA`、`VA Rule ID`、`Currency`、`Scene code`、`Legal entity code`、`Memo`、`Total VA`、`Used VA`、`Number of warnings`、`Unused VA`、`Number of applications yesterday`、`Average number of applications`、`Single day peak`、`Warning days`、`Available days remaining`、`Memo`、`Modification time`。

按钮：`Search`、`Reset`。

### 6. Collection Clearing System Config

页面标题：`CollectionClearingSystemConfig - ifundboss`。

筛选标签：`CreditorBankLocation`、`collectionCurrency`、`clearingSystemType`、`clearingSystemName`、`status`。

表头：`ID`、`CreditorBankLocation`、`collectionCurrency`、`clearingSystemType`、`clearingSystemName`、`clearingSystemIdentifierCodeName`、`accountCheckingLength`、`status`、`CostLevel`、`SpeedLevel`、`LastOperator`、`LastModifiedTme`、`RelatedCardTemplate`、`Opera`。

按钮：`Search`、`Reset`、`Batch Export`、`Add`。

### 7. Collection Card Template Config

页面标题：`CollectionCardTemplateConfig - ifundboss`。

筛选标签：`CreditorBankLocation`、`collectionCurrency`、`CollectionBANK`、`CardTemplateName`、`CardTemplateId`、`status`。

表头：`ID`、`CreditorBankLocation`、`collectionCurrency`、`CollectionBANK`、`CardTemplateName`、`status`、`LastOperator`、`LastModifiedTme`、`RelatedBankVaAccountRule`、`Opera`。

按钮：`Search`、`Reset`、`Add`。

### 8. Collection PTR Case Library

页面标题：空（已显示业务控件）。

筛选标签：`测试场景`、`收款币种`、`收款地区`、`交易类型`、`收款行`、`收款银存`、`机构账号`、`业务线`、`清算网络`、`收款能力ID`、`测试用例名称`、`巡检规则`。

表头：`#`、`测试场景`、`测试用例名称`、`收款币种`、`收款地区`、`交易类型`、`收款行`、`收款银存`、`付款金额`、`机构账号`、`业务线`、`清算网络`、`是否支持Recallable`、`是否提供GPI`、`验证清算网络`、`验证收款币种`、`验证Recallable`、`验证GPI`、`收款VA号`、`创建人`、`Created Time`、`巡检规则`、`Operate`。

按钮：`Search`、`Reset`、`巡检设置`、`新增测试用例`。

### 9. Collection PTR Order Inquiry

页面标题：空（已显示业务控件）。

筛选标签：`单据号`、`收款币种`、`收款地区`、`交易类型`、`收款行`、`收款银存`、`业务线`、`单据状态`、`收款VA号`。

表头：`#`、`单据号`、`收款币种`、`收款地区`、`交易类型`、`收款行`、`收款银存`、`业务线`、`清算网络`、`是否支持Recallable`、`是否提供GPI`、`验证收款币种`、`验证Recallable`、`验证GPI`、`收款币种验证结果`、`交易类型验证结果`、`Recallable验证结果`、`GPI验证结果`、`单据状态`、`验证失败原因`、`创建人`、`Created Time`、`Modified Time`、`最后修改人`、`Operate`。

按钮：`Search`、`Reset`。

### 10. PTR Collection VA Library

页面标题：空（已显示业务控件）。

筛选标签：`收款能力ID`、`收款币种`、`开户机构`、`银存账号`。

表头：`#`、`银存账号`、`开户机构`、`VA号`、`场景码`、`收款币种`、`VA开户规则ID`、`业务身份标识`、`Created Time`。

按钮：`Search`、`Reset`、`PTR收款VA开户`。

### 11. Channel Cost Management

页面标题：空（已显示业务控件）。

筛选标签：`Cost Type`、`Entity`、`Institution`、`Bank Account`、`Transaction Currency`、`Charge Bearer`、`Clearing NetworkName`。

表头：`#`、`Cost Type`、`Entity`、`Institution`、`Bank Account`、`Transaction Currency`、`Charge Type`、`Payment Method`、`是否有全额到账能力`、`FVT`、`Charge Currency`、`Status`、`Approval Status`、`Last Operator`、`Operate`。

按钮：`Search`、`Reset`、`批量新增`、`新增价格`。

### 12. Collection Product SLA Management

页面标题：空（已显示业务控件）。

筛选标签：`Business Line`、`Business entity`、`Collection Area`、`Receipt Currency`。

表头：`#`、`Business Line`、`Business entity`、`Collection Area`、`Receipt Currency`、`End-to-End SLA`、`IPAY Internal SLA`、`Holiday`、`Last Operator`、`Modified Time`、`Status`、`Operate`。

按钮：`Search`、`Reset`、`Add SLA Rule`。

### 15. Index Risk Operation

页面标题：`Index risk operation - ifundboss`。

筛选标签：`业务风险场景`、`异常规则`、`风险指标ID`、`状态`。

表头：`风险场景`、`指标名称`、`异常规则ID`、`异常规则名称`、`指标统计维度`、`指标统计周期`、`状态`、`Operation`。

按钮：`Search`、`Reset`、`新增风险指标`。

### 16. Collection Risk Event Operation

页面标题：`collection&payment risk operation - ifundboss`。

筛选标签：`Risk case Creation Date`、`Business scene`、`Potential Risk Event ID`、`risk point`、`Phases of the business`、`Owner`、`Operation Scenario`、`Review Status`。

表头：`Risk case Creation Date`、`Business scene`、`Potential Risk Event ID`、`risk point`、`Phases of the business`、`fund plan`、`Operation Scenario`、`Channel`、`Recon inst`、`Bank Account Number`、`Time of first discovery`、`Time of last discovery`、`Risk Cause`、`人工打标原因`、`Number of transactions`、`Amount of transactions`、`USD amount`、`Owner`、`Review Status`、`Estimated Time Of Completion`、`Operation`。

按钮：`Expand`、`Search`、`Reset`。

### 17. Collection Risk Order Monitoring

页面标题：`ifundboss`。

筛选标签：未显示。

表头：未显示。

按钮：未显示。

### 20. Manual Collection Inquiry

页面标题：`New Manual - Adjustment List - ifundboss`。

筛选标签：`voucherNo`、`VA Number`、`Bank Account Number`、`Institution`、`Bank Reference Number`、`Currency`、`Status`、`Business Unit`、`Fund Received Time`、`Entity`、`File Batch No`。

表头：`Collection Voucher No`、`Bank Account Number`、`Bank Reference Number`、`Currency`、`Amount`、`Status`、`VA Strategy`、`Reverse Status`、`Fund Received Time`、`Action`。

按钮：`Search`、`Reset`。

### 21. Original Road Back

页面标题：`Original Road Back - ifundboss`。

筛选标签：`Collection Voucher No`、`VA Number`、`Bank Account Number`、`Inst`、`Bank Reference Number`、`Currency`、`Business entity`、`Business Line Type`、`Fund Received Time`、`Status`、`Back Apply Time`、`Trans Amount`。

表头：`Business entity`、`Business Line Type`、`Collection Voucher No`、`Bank Reference Number`、`Back Apply Time`、`Status`、`VA Number`、`Amount`、`Inst`、`Bank Account Number`、`Currency`、`Fund Received Time`、`Last Operator`、`Last Time`、`Operation`。

按钮：`Reset`、`Search`。

### 请求观察与安全边界

浏览器通过 CDP Fetch 拦截未核实的业务 XHR/Fetch 和非 GET 请求。放行页面文档、静态资源、既有认证页面引导，以及经前端源码核对的 ifundboss 初始化元数据：`GET /api/user/getUserInfo.json`、`GET /api/multiLanguage/queryAllLanguageConfig.json`、`GET /api/getReconInst.json`；`POST /api/user/getPermission.json` 仅允许 JSON 字段集合恰为 `userId`、`codes`。这些读取不构成业务查询验证。另允许浏览器原生自动 SSO 表单向 `pubbuservice.alipay.com/auth.htm` 发送 Document POST；未输入凭证或自动执行人工登录。

核对源码来自页面实际加载的 `renderoffice-intl.alipayobjects.com/p/yuyan/180020010001284167/umi.bfbf5fa6.js`，仅提取上述调用结构，不保存源码或用户信息。静态资源及必要认证通信不等于业务 API allowlist；本轮未修改 CLI transport。

一次较早的 PTR VA 库页面初始化曾观察到 `POST https://iglobalfundcontrol.alipay.com/api/ptr/virtualAccount/pageQuery.json`，已在发送前拦截；没有响应、参数语义、业务成功条件或分页验证。后续逐页复查只显示控件，未稳定重现该列表请求。它只是待验证线索，不能用于实现。规则、容量、风险和人工查询页面也出现下拉选项初始化请求，均未据名称放行。

所有表格均未读取生产行。没有新增详情验证；筛选枚举、隐藏/展开项、行级动作、默认查询范围、权限码与 API 契约仍有缺口。

### 受限页面记录

本轮对以下七项原生入口逐一复查，均最终到达 `https://ipaybuservice.alipay.com/login.htm`（标题“登录”），未显示业务控件，也未提取到明确权限拒绝文本：

| 菜单 | 本轮结果 |
| --- | --- |
| Account Isolation Rule Configuration | 认证跳转；尚不能判断业务权限 |
| Spontaneous account balance inquiry | 认证跳转；尚不能判断业务权限 |
| Collection Risk Dashboard | 认证跳转；尚不能判断业务权限 |
| Collection Risk Point Management | 认证跳转；尚不能判断业务权限 |
| PVA&Duplicate Collection | 认证跳转；尚不能判断业务权限 |
| Manual Collection(Batch) | 认证跳转；尚不能判断业务权限 |
| Active Collection Confirm | 认证跳转；尚不能判断业务权限 |

调查拦截同时阻断了部分认证初始化及跨站嵌入请求，因而不能断言账号会话已经失效，也不能把结果认定为平台无权限。未继续扩展认证放行或自动执行人工 SSO。第 5、22 项在较早外层采样已显示控件，与本次重新打开后停在登录页属于不同观察时点；保留两者，不用较早控件推断当前查询可用。

已确认的权限拒绝清单：本轮没有明确证据可登记。待恢复正常页面加载后，如出现明确拒绝，按上述菜单和准确路径补录提示及受阻范围，供操作者申请权限。当前可以登记认证/加载缺口，但不应据此申请猜测的权限码。

15 个内层页面均未观察到明确的“无权限 / Access denied / Permission denied / 403”等拒绝文本；此结果不代表具有查询权限。第 17 项没有业务控件，且静态配置/初始化读取被拦截，归为加载受限，不能列为权限申请的已确认依据。

## 历史查询证据索引

下列研究均是既有快照；本报告未重放它们的业务请求。其来源和核验方法见对应文档。

- [H1 收款发现（2026-09-23）](2026-09-23-collection-discovery.md)：22 菜单、成本查询和银行账户 VA 规则分页异常。330 条部分结果不能替代当时总数 450 的完整数据。
- [H2 VA 规则研究（2026-09-23）](2026-09-23-collection-va-rule-query.md)：907 个唯一规则、单 ID 筛选与三个详情样本；大页容量和样本结果不保证未来全量详情。
- [H3 VA 池调查（2026-09-23）](2026-09-23-collection-va-pool-query.md)：容量页面、关联详情失败及搜索范围；未建立独立池或物理/实体 VA 账户契约。历史登录跳转不证明无权限。
- [H4 SLA 研究（2026-09-23）](2026-09-23-collection-sla-query.md)：55 条配置及全部详情、四个单值筛选样本；配置目标不等于实际订单表现。
- [H5 VA value 术语核验（2026-09-26）](2026-09-26-collection-va-value-terminology.md)：历史文档和有限页面观察均未建立该候选名；PTR 库仅是线索，不代表生产客户 VA 全量查询。

## 设计与验收门槛

本轮菜单调查不新增 CLI 或允许端点。对明确识别的单一能力，先验证原生只读请求的 endpoint/method/action、参数、响应、标识、分页及完整性，再形成 GitHub 规格。每个公开参数均须具备对应证据和生产只读 UAT；沿用公开 CLI + fake CDP + 真实本地缓存的既有 SIT 边界。无权限页面只记录缺口，不通过猜测接口或更换业务对象补齐。
