# 收款生产发现与首批查询范围

Observed: 2026-09-23
Scope: general
Status: snapshot

## 结论

已完成本轮收款菜单发现和首批候选 API 核验。建议第一阶段只交付 `collection cost list` 与 `refresh collection cost`，固定收款交易费用 `FUND_IN_CHANNEL_TRANS_FEE`；生产单次查询取得 556 条、556 个唯一 `itemId`，与 `totalCount` 一致。收款 VA 功能成本查询成功但当前为空，尚无非空记录 schema 证据，延期。

银行账户 VA 规则查询、ID 筛选和正常分页已验证，但完整扫描在第 34 页失败：HTTP 200、`success=true`，却返回 `pageNo=0,pageSize=0,totalCount=0`，无记录。单独重试同样失败。不能将此前 330 条当成完整的 450 条；渠道/VA 规则能力留作独立后续工作，不为本轮注册占位命令，也不自动采用付款离线替代源。

用户要求的是规划与发现，不是收款实现。本报告区分生产事实、历史设计和建议；正式范围与验收见 [Issue #21](https://github.com/proletariat64/dogopencli/issues/21)。[ADR 0002](../../adr/0002-payment-v010-scope.md) 继续限定付款 v0.1.0；收款是独立后续里程碑，未指定版本号，也未将付款验收票据 #9/#10 视为完成。

同日后续：用户要求先逐项研究并留存设计参考。已另记 [VA 规则列表与详情](2026-09-23-collection-va-rule-query.md)（907 条完整列表、三个详情样本）与 [SLA 配置列表与详情](2026-09-23-collection-sla-query.md)（55 条完整列表及全部详情）。下表“仅菜单”和成本优先建议保留为初轮观察；后续证据以两份独立记录为准。VA 规则与本报告失败的银行账户 VA 规则是不同对象。新增研究不自动扩张 Issue #21 的成本实现范围。

## 证据来源与方法

先对 `/home/ubuntu/dev/dogpdkb/graphify_flatten_ready/` 执行 `graphify query`，再读取命中文档原文；未重建图谱或保存查询结果。以下路径均相对于该目录。仅保存结构性摘要，不保存生产记录、认证信息或历史资料中的带票据链接。

| 编号 | 历史来源 | 可支持的结论及限制 |
| --- | --- | --- |
| H1 | `收付款产品__收款产品__产品建设PRD__门户建设__收款产品-门户建设一期-2023-05-23-[229045558].md`，140–150、185–216 行 | 渠道能力与面向签约的产品套餐分开；曾设计渠道筛选及套餐列表/详情。不是当前运营菜单或接口证明。 |
| H2 | `收付款产品__收款产品__产品建设PRD__自助运营__管控运营__收款产品套餐运营能力建设PRD-V1-2026-04-18-[149323704].md`，5–18、23–41、63–65 行 | 套餐基线与某法律主体已签约能力不同；设计包含单/多币种、审批与查询权限。 |
| H3 | `收付款产品__收款产品__产品建设PRD__自助运营__成本运营__收款产品成本报表运营-2026-04-19-[152865220].md`，27–53、70–83 行 | 区分收款交易费用与 VA 维护费用；历史设计列表已含完整内容。不是实际交易成本报表或已验证详情接口。 |
| H4 | `收付款产品__收款产品__产品介绍文档__全球收款产品说明书-2026-04-19-[216566174].md`，263–290、598–623 行 | 基线、套餐、VA、成本、入账单据及 SLA 是不同对象，不宜按付款结构直接复制。 |
| R1 | [付款成本契约](../payment/2026-09-08-cost-query-contract.md) | 2026-09-08 共享字典曾出现 `FUND_IN_CHANNEL_TRANS_FEE` 和 `FUND_IN_VA_FEE`；不证明当前收款请求、权限、覆盖或字段契约。 |

## 登录与方法

初次 `auth check` 显示 CDP 9222 不可达；正常 login 启动 Chrome 后，归属检查误拒绝。只读进程核验确认监听者的专用 profile 正确，但 Chrome 将 argv 展平为单个字符串，原实现按独立 argv 元素比较。修正只在单字符串时解析参数，仍核对实际监听 socket 的唯一进程及精确 profile；42 项浏览器测试、完整 528 项测试及 23 subtests 通过，Ruff 检查通过。

用户随后完成人工 SSO。`dogopencli login` 返回退出码 0、`authenticated=true`、`healthy=true`、`mode=headless`，专用 profile 为 `/home/ubuntu/.local/share/dogopencli/chrome`，CDP 为 `http://127.0.0.1:9222`。没有连接禁用端口 9330–9340。

Browser 连接器未提供会话；本轮经项目原生 CDP 创建独立研究 target，读取菜单与 iframe，观察原生 Search 请求，然后仅重放已确认的查询。没有新增、保存、审批、生效、试算、试跑或导出任务。原始业务行只用于进程/页面内结构、计数与标识校验，未保存数据集、HAR、截图或凭证；报告不包含账户值、ID 值或 token 值。生产响应经筛选后仅记录 schema、协议、计数和状态。API 的存在不授权整站或任意参数访问。

## 当前菜单地图

从 [付款入口](https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/) 的实际导航发现收款根 `/productOperation/collectionProductManagement`，展开六组得到 22 条菜单。下表路径均相对此根；拼写保留页面含义。菜单可见不表示其中每项查询已验证。

| 分组 | 菜单与相对路径 | 本轮核验 |
| --- | --- | --- |
| Network Construction | Bank Account VA Rule Management — `networkConstruction/bankVARuleManagement` | 页面、Search、ID、分页及完整性失败 |
| Network Construction | Account Isolation Rule Configuration — `networkConstruction/businessAccount` | 仅菜单 |
| Network Construction | VA Rule Management — `networkConstruction/VARuleManagement` | 仅菜单；不能与银行账户 VA 规则混同 |
| Network Construction | VA Capacity Monitoring — `networkConstruction/VACapacityMonitoring` | 仅菜单 |
| Network Construction | Spontaneous account balance inquiry — `networkConstruction/accountBalance` | 仅菜单；未触发查询 |
| Network Construction | Collection Clearing System Config — `networkConstruction/clearingSystemConfig` | 仅菜单 |
| Network Construction | Collection Card Template Config — `networkConstruction/cardTemplateConfig` | 仅菜单 |
| PTR Management | Collection PTR Case Library — `productPTRManagement/caseLibrary` | 仅菜单 |
| PTR Management | Collection PTR Order Inquiry — `productPTRManagement/orderInquiry` | 仅菜单 |
| PTR Management | PTR Collection VA Library — `productPTRManagement/VaLibrary` | 仅菜单 |
| Price Management | Channel Cost Management — `productPriceManagement/channelCost` | 页面、类型字典、两类收款 Search、分页及完整性 |
| SLA Management | Collection Product SLA Management — `productSLAManagement/SlaManagement` | 仅菜单 |
| Risk Management | Collection Risk Dashboard — `productRiskManagement/dashboard` | 仅菜单 |
| Risk Management | Collection Risk Point Management — `productRiskManagement/point` | 仅菜单 |
| Risk Management | Index Risk Operation — `productRiskManagement/riskOperation` | 仅菜单 |
| Risk Management | Collection Risk Event Operation — `productRiskManagement/eventOperation` | 仅菜单 |
| Risk Management | Collection Risk Order Monitoring — `productRiskManagement/orderMonitoring` | 仅菜单 |
| Operational Disposal | PVA&Duplicate Collection — `operationalDisposal/duplicate` | 仅菜单；未操作 |
| Operational Disposal | Manual Collection(Batch) — `operationalDisposal/manualBatch` | 仅菜单；未操作 |
| Operational Disposal | Manual Collection Inquiry — `operationalDisposal/manualInquiry` | 仅菜单 |
| Operational Disposal | Original Road Back — `operationalDisposal/roadBackInquiry` | 仅菜单；未操作 |
| Operational Disposal | Active Collection Confirm — `operationalDisposal/activeConfirm` | 仅菜单；未操作 |

本轮收款根下未出现通用 Channel List 或 Package 菜单。历史门户的渠道能力/套餐模型不能直接当作当前运营页。首批范围从历史候选“渠道＋成本”收缩为已充分核验的交易成本，不将 `bankAccountVARule` 擅自命名为所有收款渠道。

## 收款成本查询契约

入口：[Channel Cost Management](https://ifundcontrol.alipay.com/productOperation/collectionProductManagement/productPriceManagement/channelCost)。iframe 为 `https://igfc.alipay.com/receivedPayment/fundCost`；业务 API 为 `https://iglobalfundcontrol.alipay.com/api/fundCost/query.json`。

原生 Search 发出 POST JSON，URL 含 `ctoken` 参数；凭证由既有浏览器会话/传输机制提供，不进入业务配置或日志。页面初载和无条件 Search **不限制成本类型**：本轮返回总数 3847，不能用于收款专用缓存。

类型字典的已观察 GET 查询为 `/api/option/getCostTypes.json`，业务成功且包含付款、收款交易、收款 VA、流动性、外汇五类。通过页面下拉框选择两类收款并点击 Search，分别捕获以下请求：

```json
{"costTypeCode":"FUND_IN_CHANNEL_TRANS_FEE","pageSize":10,"pageNo":0}
{"costTypeCode":"FUND_IN_VA_FEE","pageSize":10,"pageNo":0}
```

类型不由 CLI 用户传递任意字符串。建议首批固定 `FUND_IN_CHANNEL_TRANS_FEE`，并逐行验证 `itemType` 与其一致；VA 类型延期，不自动混合共享页面的其他类别。

| 核验 | 结果 |
| --- | --- |
| 交易成本 pageNo=0/pageSize=10 | HTTP 200、success=true、totalCount=556、10 条/10 个唯一 ID |
| 交易成本 pageNo=1/pageSize=10 | 同上；与第 0 页有 3 个重叠 ID |
| 交易成本 pageNo=0/pageSize=1000 | 556 条/556 个唯一且非空 itemId，totalCount=556，所有 itemType 匹配 |
| VA 成本 pageNo=0/pageSize=10 | HTTP 200、success=true、totalCount=0，省略 resultDataList；重放同样成功为空 |

分页从 0 开始。小页去重不能补回遗漏；首批采用已验证的 1000 大页并严格核对范围与总数。若增长、截断、重复、元数据异常或业务失败导致不完整，应明确失败并保留旧缓存，不能静默回退到已知有重叠的小页。1000 是本轮通过的请求容量，不是服务端上限或长期保证。

业务 envelope 包含 `success`、`totalCount`、`pageNo`、`pageSize`、`resultDataList`、`errorContext`；行以字符串 `itemId` 标识。必须先判断业务成功，再判断是否为空；只允许在成功且总数为 0 时将省略的列表解释为空，非零总数缺列表视为契约错误。

观察到的行字段包括 `bankAccountAliasName`、`chargeBearer`、`clearingNetworkName`、`costCurrencyCode`、`costRateConfigList`、`financialInst`、`gmtCreate`、`gmtModified`、`isExistFvtAbility`、`isFvt`、`itemId`、`itemType`、`lastOperator`、`legalEntity`、`mappingCode`、`status`、`transCurrencyCode`，部分行还含 `validStartTime/validEndTime`。不按名称、银行或账户合并不同记录。

`costRateConfigList` 包含费用基准、阶梯、精度、舍入、有效期及 `costRateVO`；后者可含 `bottomAmount`、`topAmount`、`fixedAmount`、`feeRateRatioValue` 和 `costRateRangeList` 等。应保持嵌套字段、未知扩展、原单位及精确数值，不把配置当作实际交易成本。

页面还显示 Entity、Institution、Bank Account、Transaction Currency、Charge Bearer、Clearing NetworkName 筛选。这里只确认 UI 控件；未核验这些筛选的后端字段映射与效果，首批不暴露相应 live 参数。历史付款映射不能自动成为收款参数证据。金额、状态和有效期的进一步业务语义仍以原字段输出，不新增推导结论。

## 银行账户 VA 规则契约及阻塞

入口：[Bank Account VA Rule Management](https://ifundcontrol.alipay.com/productOperation/collectionProductManagement/networkConstruction/bankVARuleManagement)。iframe 为 `https://ifundbossportal.alipay.com/voucher/bankAccountVARuleManage`。

原生 Search 发出 POST JSON 至 `https://ifundboss-api.alipay.com/ivostro/api/bankAccountVaRule/pageList.json`，URL 含 `ctoken`，无筛选请求为：

```json
{"bankVaRuleId":"","pageNo":1,"pageSize":10}
```

顶层 `resultDataList`，数字 `id`，总数 450。行字段包括账户/别名、机构、地区、币种、多币种支持、VA 组装策略、状态、创建/修改时间、临存标志、卡模板、校验规则及 VA 类别/类型；不将其解释为全部收款能力。

| 核验 | 结果 |
| --- | --- |
| pageNo=1、2、45；pageSize=10 | 各返回 10 条、元数据与请求一致，totalCount=450 |
| pageNo=46；pageSize=10 | 无行、页码 46、pageSize=10、totalCount=450；越过末页不等于全局无数据 |
| 以已返回 ID 的字符串作为 bankVaRuleId | 成功返回 1 条，totalCount=1，ID 完全匹配 |
| pageNo=1、pageSize=1000 | success=true，但 pageNo/pageSize/totalCount 全为 0，无行；不能接受为空快照 |
| 按 10 条完整扫描 | 前 33 页得到 330 个唯一 ID，各页总数 450；第 34 页返回零化元数据后立即停止 |
| 单独重试第 34 页 | HTTP 200、success=true、errorNames=[SUCCESS]，仍 pageNo/pageSize/totalCount 全 0 |

这是当前查询契约/后端返回异常的证据，不是后端内部根因结论。完整性检查必须验证页码、容量、稳定总数、ID 与行数，不能只看 HTTP 或 success。没有继续扫剩余页以拼装“全量”，没有保存部分替代集。

页面的其他筛选控件为 aliasName、accountNo、financialInst、supportMultiCurrency、country、currency、reconInst、ruleStatus、assembleStrategy；这些仅记录 UI 标识，未验证后端筛选语义。未来可单独评估精确 ID 查询，但本轮不将其包装为具备完整缓存的渠道能力。

## 首批范围与实施计划建议

首批命令：`dogopencli collection cost list`、`dogopencli refresh collection cost`，以及它们的离线帮助与 describe。固定交易成本类型；复用现有 JSON/table、字段投影、展示分页、显式 live、新鲜度和完整性约定。默认只读缓存，live 不写缓存，refresh 只有完整时原子发布；收款与付款使用不同能力/类型命名空间。

1. 在 Issue #21 冻结上述端点、固定范围、结果完整性、输出和延期项，不引入全后端运行时模型。
2. 后续另行授权实现：按现有领域能力注册方式接入成本查询、独立缓存范围、help/describe 和合成响应。
3. 公开 CLI SIT 验证范围隔离、错误拒绝、零总数、省略/异常列表、重复与截断、缓存保留和质量信息；生产 UAT 只查询并发布本地缓存，校验当前总数，不硬编码本轮 556。
4. VA 规则独立跟进第 34 页与大页异常，未通过完整性验证前不发布缓存；VA 成本待非空 schema，套餐待实际入口/契约。规则、SLA、PTR、VA 库、签约、单据、费用试算和所有业务写操作延期或排除。

没有故意制造权限/认证错误。缺少权限、会话过期及错误 schema 的实际收款样本需在实现中明确证据等级，以合成 SIT 覆盖防护行为；不通过真实越权、修改认证或业务写入获取样本。研究完成不等于实现、完整 UAT 或所有菜单契约核验完成。
