# 收款产品 SLA 配置列表与详情研究

Observed: 2026-09-23
Scope: general
Status: snapshot

## 结论与下一步设计输入

在完成并保存 [VA 规则研究](2026-09-23-collection-va-rule-query.md) 后，单独核验收款产品 SLA。已观察原生 Search/Details，验证零基分页、55 条完整列表、全部 55 条详情及四个单值筛选样本。列表和详情以字符串 `slaConfigId` 关联，55 个详情均成功且 ID 匹配。

这是配置目标，不是订单实际耗时、违约率或渠道/清算网络 SLA。命令可考虑 `collection sla configs list/get`；是否沿用付款的 `baselines` 命名需下一步设计明确，不能只因页面都叫 SLA 就复用付款字段模型。

本轮为研究记录，不实施命令，也不自动扩张 [成本规格 Issue #21](https://github.com/proletariat64/dogopencli/issues/21)。下一步具备设计列表、详情和列表＋详情缓存的证据，但仍需定义状态/空值、无数据/不存在、错误分支及完整性策略。

## 来源与方法

生产入口：[Collection Product SLA Management](https://ifundcontrol.alipay.com/productOperation/collectionProductManagement/productSLAManagement/SlaManagement)。实际 iframe：`https://igfc.alipay.com/receivedPayment/sla/fundInSla`。

复用已验证的专用 headless Chrome（CDP 9222），在本轮研究 target 中读页面、观察请求、点击 Search 与 Details，随后只重放这两种已确认的查询。未点击 Add SLA Rule、One-Key Sync、More 下的业务动作，未保存、审批或变更配置。没有连接 9330–9340，没有保存账号、实体值、ID 值、token、原始业务响应、HAR 或截图。

历史研究先 graphify query，再核对原文；未重建图谱或保存查询结果。路径相对于 `/home/ubuntu/dev/dogpdkb/graphify_flatten_ready/`：

| 来源 | 位置 | 历史语义与限制 |
| --- | --- | --- |
| `收付款产品__Firewall__项目及需求__付款产品流出SLA运营---风险平台PRD__收款产品流入SLA运营---风险平台PRD-2023-02-22-[197667583].md` | 105–111 行 | SLA1 从付款行汇出到收款产品通知业务；SLA2 从资金网络收单到通知业务，二者不同 |
| 同上 | 189–213 行 | 业务线、主体、收款币种/地区、两个目标时长、节假日；配置表单必填不等于查询条件必填 |
| 同上 | 128–131、148、244、316 行 | 退款/撤回、账户级 fallback、订单实际表现和保障率有各自边界；fallback 被标为待确认，不应实现为既定规则 |
| `收付款产品__Firewall__体验优化__清算网络SLA配置-2023-11-16-[287269949].md` | 3–5 行 | 按渠道/币种/清算网络配置的另一类 SLA，不能混同本页面 |

历史 SLA1/SLA2 给出领域背景；当前 API 名称、类型、标识、分页及显示单位以下述运行态和实际加载的前端资源为准。

## 已验证请求

| 查询 | 方法与固定 URL | 响应位置 |
| --- | --- | --- |
| 列表 | POST `https://iglobalfundcontrol.alipay.com/api/fundInSlaConfig/search.json` | `resultDataList`、`totalCount` |
| 详情 | GET `https://iglobalfundcontrol.alipay.com/api/fundInSlaConfig/getDetailBySlaConfigId.json`，参数 `slaConfigId` | `resultData` |

观察到请求 URL 含 `ctoken`；认证由浏览器和共享传输负责，值不进入业务配置、输出或 fixture。没有尝试无认证访问，不能从当前成功推断 token 可省略或永久有效。

初载列表 POST JSON 为 `{"pageSize":10}`；原生 Search 为：

```json
{"pageSize":10,"pageNo":0}
```

当前未筛选查询没有业务必填字段。未测试省略 pageSize 或非法页号，不能把付款端的失败行为直接套用到这里。

## 列表 schema 与分页

成功 envelope 含 `success`、`pageNo`、`pageSize`、`totalCount`、`resultDataList`、权限/按钮及错误上下文等字段。本轮 HTTP 200、success=true。CLI 应分开判断 HTTP、业务成功与覆盖完整性，不依据页面空表或按钮权限推断查询结果。

| 字段 | 本轮观察类型与边界 |
| --- | --- |
| `slaConfigId` | string；55 行唯一、非空，详情入参使用同一值 |
| `businessCategory`, `legalEntityCode` | string；业务线、业务主体 |
| `creditorCurrency`, `creditorRegion` | string；收款币种、收款地区 |
| `endToEndSla`, `ipayInnerSla` | number；秒，显示转换证据见下文 |
| `holidayLimit` | object，含 `currencyCodes: string[]`、`regionCodes: string[]`；不是付款 schema 的字符串 |
| `slaConfigStatus` | string；枚举全集和状态默认可见性未穷举 |
| `gmtCreate`, `gmtModified` | number；原业务时间，未核验 epoch 单位/时区 |
| `creator`, `lastOperator` | string；不记录实际值 |
| `viewProcessInstanceRequired` | boolean；列表附加字段，不在本轮详情中 |

保留未知扩展字段；观察类型不是完整可空性或跨版本保证。没有 timezone 字段证据，不添加付款字段来补齐。

| 请求 | 返回页/容量 | 总数 / 行数 / 唯一 ID |
| --- | --- | --- |
| pageSize=10，省略 pageNo | 0 / 10 | 55 / 10 / 10 |
| pageNo=0,pageSize=10 | 0 / 10 | 55 / 10 / 10 |
| pageNo=1,pageSize=10 | 1 / 10 | 55 / 10 / 10 |
| pageNo=5,pageSize=10 | 5 / 10 | 55 / 5 / 5 |
| pageNo=6,pageSize=10 | 6 / 10 | 55 / 0 / 0 |
| pageNo=0,pageSize=1000 | 0 / 1000 | 55 / 55 / 55 |

页码从 0 开始，省略时当前默认 0。末页外空列表仍报告全局总数 55；不能当作整个范围的成功零总数。1000 在当前规模通过，不是服务器最大容量保证。未遍历每个小页，不宣称全小页路径无重叠；全量证明来自大页数量与唯一 ID 核对。

## 筛选验证

表单 label/for 与以下四个字段一致。每次从本轮完整列表取一个非空且非 `*` 的现有值，作为 JSON 字符串单值发往已验证列表端点，保留 `pageNo=0,pageSize=1000`；原始值仅在内存中使用。

| 字段 / 标签 | HTTP / 业务 | 返回总数与行数 | 证据限制 |
| --- | --- | --- | --- |
| `businessCategory` / Business Line | 200 / true | 55 / 55，全部匹配选定值，包含取样行 | 数据本就同值，没有证明此字段独立缩小范围；不能据此保证后端不会忽略它 |
| `legalEntityCode` / Business entity | 200 / true | 7 / 7，全部匹配且包含取样行 | 单值样本支持实际过滤；未验证全部值或多条件组合 |
| `creditorRegion` / Collection Area | 200 / true | 4 / 4，全部匹配且包含取样行 | 同上 |
| `creditorCurrency` / Receipt Currency | 200 / true | 4 / 4，全部匹配且包含取样行 | 同上 |

没有验证数组、多值 OR、字段组合 AND、模糊匹配、星号/ALL、空字符串、非法枚举或不匹配值。因此下一步不应把单值验证扩展成这些承诺。若要提供 businessCategory live 筛选，需补强证据或明确以本地精确校验保证返回范围。

## 详情与离线设计边界

原生 Details 触发 `getDetailBySlaConfigId.json?slaConfigId=…`。随后对大页返回的全部 55 个 ID 顺序调用同一 GET 查询，结果为：

- 尝试 55、成功 55、非空 resultData 55、ID 不匹配 0。
- 详情的业务字段与对应列表行一致；唯一观察到的差异是列表的 `viewProcessInstanceRequired` 未出现在详情。
- 详情没有单独分页，不能以页号读取；没有批量详情接口证据。

这支持设计“完整列表＋逐条详情校验后原子发布”的离线方案，但不是已实现行为或后端事务快照证明。采集过程中配置可能变化；设计应定义 ID/字段一致性与失败时保留旧缓存的规则，不按本轮结果假定以后永不变化。

未测试不存在 ID、缺少 ID、详情 null、无权限、认证失效或其他业务失败。本轮 all-details 成功不能证明这些分支可按付款端错误语义处理。

## SLA 单位与节假日显示证据

读取的是页面实际加载的静态资源，只用于核对渲染，不执行其业务动作。资源基址为 `https://renderoffice-intl.alipayobjects.com/p/yuyan/180020010001284234/`：

| 资源 | SHA-256 | 用途 |
| --- | --- | --- |
| `2ea8903f-async.b4d05430.js` | `df193f1bee610fe871dd23b6f1aa41d91b5ddf2b375d07069662a7160ed11200` | 列表将两个 SLA 字段传给 formatFundInSla |
| `618b59fd-async.6d1cf7eb.js` | `b8da7b24582fb3596de9c8f8bcce1b7c379cdb68195f1fdbce869b59d09c2e43` | 详情使用同一 formatter 和 getHolidayLimitText |
| `shared_6hWy7vOV-async.8103dd67.js` | `ac140a841f69b56e8a299c4909567d0799d45f84311d39fb50f811a1489edf63` | 两个 formatter 的实际定义 |

`formatFundInSla` 将数值除以 3600 得小时，将余数除以 60 得分钟，显示“小时/分钟”。因此当前 endToEndSla 和 ipayInnerSla 的基础单位是秒。页面对非数字回退零的显示逻辑不应变成 CLI 的数据规则；未知或异常值不能被无声改为零 SLA。

`getHolidayLimitText` 只显示 regionCodes 和 currencyCodes 的首个元素。CLI 应保留原数组，不能按页面摘要截断。此渲染器不证明节假日计算优先级、日历查询、时区或数组多元素的业务组合语义；本轮没有计算实际到账时间或 SLA 违约。

## 后续设计检查清单

1. 确定 `configs` 与 `baselines` 命名及与付款能力的边界；不要把 slaConfigId 改称付款 slaBaselineId。
2. 定义列表/详情输出、秒单位展示、原始 holidayLimit 数组及未知字段保留。配置目标与实际表现分开。
3. 决定是否支持全部四个单值筛选；businessCategory 的独立后端效果待补证。其他组合语义不扩张。
4. 若缓存详情，采集完整列表后校验全部 ID；任一失败、重复/冲突、scope 或总数不符均不得发布半快照。
5. 不硬编码 55 或当前容量保证。未来超过 1000 的取数策略、排序和并发变化处理需明确设计并验证。
6. 空范围、省略/空/null 列表、不存在详情、权限/认证/业务错误、状态/版本语义仍有缺口。用合成 SIT 保证拒绝错误数据，真实错误证据自然出现时另记，不在生产故意制造。

本记录可作为下一步规格输入；没有新增命令、修改业务配置、关闭设计问题或声称完成实现 UAT。
