# 收款 VA 规则列表与详情研究

Observed: 2026-09-23
Scope: general
Status: snapshot

## 结论与下一步设计输入

本轮按用户要求逐项研究，先完成 VA Rule Management，再进入 SLA。已验证 VA 规则列表、单 ID 筛选、列表分页及三个详情样本。两次 `pageNo=1,pageSize=1000` 均取得 907 条、907 个唯一非空 `vaRuleId`，与总数和页元数据一致。当前具备设计 `collection va-rule list` 与 `collection va-rule get --id ID` 的证据，但这些仍是候选命令，尚未实现或纳入已接受范围。

VA 规则不是银行账户 VA 规则，也不是已分配的 VA 账户。此前银行账户规则第 34 页异常不应扩散为“VA 规则全部不可用”。反过来，本轮 VA 列表完整也不能证明银行账户规则问题已解决。已有 [收款总览](2026-09-23-collection-discovery.md) 和 [成本规格 Issue #21](https://github.com/proletariat64/dogopencli/issues/21) 保持各自范围。

建议下一步先设计列表及 ID 查询；详情是否全部缓存需单独决定。本轮只验证三个详情，未证明全部 907 个详情都可取得。列表与详情字段不一致，不应以其中一个冒充另一个；不能默认把详情页关联查询合并成一个“完整对象”。

## 方法与证据

在现有专用 Chrome 上先运行只读 `auth check`，返回 authenticated/healthy，模式 headless；CDP 9222。新建独立研究 target，打开前轮实际发现的菜单。观察原生 Search 和 Details 发出的请求后，只重放确认的查询。未执行 Edit、VA allocation、Offline、Delete 或 Sync DEV/SIT。

生产行仅在内存中用于计数、字段类型、去重与身份比对；不输出账号、规则 ID 值、联系信息或 token 值，不保存原始响应、HAR、数据集或截图。以下计数只代表当前账号、时间和版本。

历史研究先 graphify query，再核对原文；未重建图谱或保存查询结果。所有历史来源相对于 `/home/ubuntu/dev/dogpdkb/graphify_flatten_ready/`：

| 来源 | 已核对位置 | 仅作为历史语义证据 |
| --- | --- | --- |
| `收付款产品__收款产品__产品建设PRD__自助运营__ifundboss运营__VA基础规则管理及VA导入-资金平台PRD-2023-02-22-[85456191].md` | 109、142、148、390 行 | 银行账户 VA 规则、VA 导入、VA 规则和 VA 分配分开；VA 规则增加业务维度 |
| 同上 | 459–466、672–674 行 | 业务主体、场景、地区与 local/cross 维度；查询/详情权限与新增、编辑、审批等分别授权 |
| `收付款产品__收款产品__产品建设PRD__自助运营__ifundboss运营__VA基础规则管理及VA导入-资金平台PRD__VA规则及导入管理-优化-2026-04-19-[120652638].md` | 45–47、65–76、124–125 行 | 地区多选、旧 local/cross 空值，银行能力与面向主体/场景的产品能力不同 |
| `收付款产品__收款需求PRD__资金PRD账户风险隔离12月迭代-2026-03-13-[504472087].md` | 89–100、185–188、263–265、318–320 行 | 另有业务开户规则管理与新的业务维度；不能把其模糊筛选语义直接应用到本页面 |

旧 PRD 截图包含后续被删除的字段；旧截图、`*`/ALL/EU 或 LOCAL/CROSS/ALL 设计不自动成为当前接口枚举与匹配规则。

## 入口与查询边界

外层：[VA Rule Management](https://ifundcontrol.alipay.com/productOperation/collectionProductManagement/networkConstruction/VARuleManagement)。iframe：`https://ifundbossportal.alipay.com/voucher/VARuleManage`。

| 操作 | 已观察请求 | 只读证据 |
| --- | --- | --- |
| 列表 | POST `https://ifundboss-api.alipay.com/ivostro/api/virtualAccountRule/list.json` | 原生 Search；重复查询返回相同范围的规则列表 |
| 详情 | GET `https://ifundboss-api.alipay.com/ivostro/api/virtualAccountRule/detail.json`，`vaRuleId` 查询参数 | 只点击 Details 后观察；三个现有 ID 的查询返回匹配对象 |
| 相关银行账户规则详情 | GET `https://ifundboss-api.alipay.com/ivostro/api/bankAccountVaRule/detail.json`，`bankAccountNo`、`bankVaRuleId` 参数 | Details 页面自动查询；本次 success=true 但 resultObj=null，未证明非空关联对象 |

三者均有 `ctoken` 查询参数；具体值仅由认证页面请求携带，不进入业务配置或日志。没有整站放行或任意请求入口。Details 页面路径也使用 `/voucher/VARuleManage/edit`，并有 `operation`、`vaRuleId`、`bankAccountNo`、`ruleStatus`、`bankVaRuleId` URL 参数；只读性依据实际点击的 Details 和观察请求，不依据路径是否含 edit。

## 列表契约

原生无条件 Search 请求：

```json
{"pageNo":1,"pageSize":10}
```

请求为 POST JSON。响应顶层含 `success`、`pageNo`、`pageSize`、`totalCount`、`resultDataList` 及错误/状态字段；本轮成功时 HTTP 200，`success=true`。业务行的 `vaRuleId` 是字符串，`bankRuleId` 是数字。它们表示不同对象，不能互换。

| 字段 | 本轮观察类型/含义边界 |
| --- | --- |
| `vaRuleId` | string，规则标识；本轮全量唯一且非空 |
| `bankRuleId` | number，关联银行账户 VA 规则，不是当前 VA 规则主键 |
| `aliasName`, `bankAccountNo`, `financialInst`, `reconInst` | string，银行账户/机构维度；未验证别名等价于唯一账户 |
| `entity`, `currency` | string，业务主体与币种原值 |
| `countries`, `sceneCodes` | string[]，保留数组；不拆成多条或压成单值 |
| `supportMultiCurrency` | boolean |
| `assembleStrategy`, `regionType`, `ruleStatus` | string；本轮未穷举枚举和空值语义 |
| `gmtCreate`, `gmtModified` | number，原时间字段；不擅自改变单位或时区 |
| `memo`, `operator` | string；保留业务含义，研究不记录实际内容 |

表述为观察类型，不是完整的可空性约束或服务端 schema 保证；未来解析应保持未知字段，不从这 907 行推断所有版本。

### 分页与覆盖

| 请求/检验 | 实际结果 |
| --- | --- |
| pageNo=1, pageSize=10 | 10 条，totalCount=907，页码/容量回显匹配 |
| pageNo=2, pageSize=10 | 10 条，与第 1 页无 ID 重叠，totalCount=907 |
| pageNo=91, pageSize=10 | 7 条，totalCount=907，页码/容量匹配 |
| pageNo=92, pageSize=10 | 0 条，仍 totalCount=907、pageNo=92、pageSize=10 |
| pageNo=1, pageSize=1000，第一轮 | 907 条、907 唯一非空 ID，totalCount=907，页元数据匹配 |
| 同样大页，第二轮 | 907 条、907 唯一 ID，totalCount=907，页元数据匹配 |
| `vaRuleId` 设为已返回 ID，pageNo=1/pageSize=10 | totalCount=1、1 条，返回 ID 完全匹配 |

分页从 1 开始。越过末页的空行保留全局 totalCount，不可解释为整个查询范围不存在。1000 已通过两次当前规模验证，不是服务端最大容量保证。未遍历所有 91 个小页，因此不宣称小页全程无遗漏或重复；大页完整性应每次独立核对。

### 筛选证据等级

`vaRuleId` 单值筛选已重放验证。以下是 UI 的 label/for 标识，尚未验证请求编码、筛选效果或 cache/live 等价性：

| UI 标签 | 控件标识 |
| --- | --- |
| Alias Name / Financial Inst / Account No. | `aliasName` / `financialInst` / `bankAccountNo` |
| Multi currency / Area / Currency | `supportMultiCurrency` / `countries` / `currency` |
| Recon inst / Business entity / Scene code | `reconInst` / `entity` / `sceneCodes` |
| Rule status / Local cross-border / Memo | `ruleStatus` / `regionType` / `memo` |
| Exists monitor config / VA Strategy | `hasConfigMonitor` / `assembleStrategy` |

不能据控件名称直接发布参数。尤其数组多值 OR/AND、ALL/星号、空值、模糊匹配与状态默认范围仍需针对性研究。

## 详情契约

Details 触发 GET 查询，响应顶层 `success=true,status=true`，对象在 `resultObj`。从全列表头部、中部、尾部各取一个现有 ID：三个样本 HTTP 200、业务成功、对象非空，`vaRuleId` 及 `bankRuleId` 均与对应列表匹配。

详情字段包括 `assembleStrategy`、`assignInfo`、`bankRuleId`、`clientEntity`、`creditAreas`、`entity`、`memo`、`regionType`、`ruleStatus`、`sceneCodes`、`vaRuleId`、`vaWarningInfo`。

- `assignInfo` 包含 assignCount、assignFlows、ruleVaTotal、vaAssignAble、vaAssigned、vaImported、vaRuleId、vaUnused、vaUsed；读取已有计数不是执行分配。空 assignFlows 不证明历史始终为空。
- 非空 `vaWarningInfo` 样本包含 email、memo、monitorHistoryList、notifyByDd、notifyByMail、notifyUrl、ruleId、warningCount、warningDays。另两个样本未返回可枚举的 warning 对象键；不能把通知信息设为必填，也不能把联系信息放入研究记录或 fixture。
- 列表中 aliasName、bankAccountNo、countries、currency、financialInst、gmtCreate、gmtModified、operator、reconInst、supportMultiCurrency 不在这三个主详情对象中。
- 列表 `countries` 与详情 `creditAreas` 名称不同；未对全部记录核验等价关系，不在 parser 中静默重命名/合并。

原生 Details 还发出相关银行账户规则查询。参数不是空字符串、undefined 或 null 字面量，但这次 resultObj=null；原因未确定。它不否定主 VA 规则存在，也不能视为完整关联详情。未来 `get` 若仅返回主详情，应明确覆盖边界；若承诺完整页面组合，则该依赖仍需验证。

## 未验证事项与设计检查清单

1. 决定列表与详情是否使用独立数据模型；主详情返回还是完整页面组合，不能含糊。
2. 决定刷新是否只缓存列表，或还要求所有详情原子发布。只验证三条详情不能证明全量详情可用；不能复制付款 SLA 的刷新策略就宣称通过。
3. 保留规则/银行规则/实际 VA 三类标识。没有业务账号或银行规则全量联接的证明，不提供隐式跨对象关联。
4. 若开放 ID 以外筛选，逐个补齐请求编码、枚举、数组/空值/默认语义与本地匹配依据。
5. 完整性需核对 success、页元数据、总数、唯一 ID 和范围；无效/不完整结果不得替换旧缓存。大页容量增长后的策略待设计，不能照搬其他端点行为。
6. 未探测不存在的 ID、实际权限失败、认证过期、冲突版本、全量详情、异常 schema 或最大容量；设计时明确这些证据缺口，用合成 SIT 验证防护，不在生产制造故障。

以上是下一步设计参考，不是实现规格或新增能力交付声明。未修改收款 CLI、生产配置、根领域词汇或已接受 ADR。
