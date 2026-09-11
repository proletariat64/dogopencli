# 付款渠道成本查询契约

Observed: 2026-09-08
Scope: payment
Status: snapshot

## 结论与适用范围

成本列表的实际接口、七个筛选字段名称、已观察响应字段和计费分支已取得生产证据；字典依赖仅部分核验。追加验证已确认：固定付款类型、`pageNo=0`、`pageSize=5000` 可单次取得当前全部 3291 条，唯一 `itemId` 数也为 3291；两次请求集合及记录内容一致。前端 50 条分页选项不是后端当前的硬限制。

每页 10 或 50 条的跨页查询仍有重复，原因未确定。此前据此将能力限制为单页小样本的建议由本次大页证据修正；不能把尚未解决的跨页异常推断为无法取得当前全量。随后 `pageSize=10000` 也成功返回当前全部 3291 条，见追加验证；长期行为和后端最大页大小仍未验证。

付款菜单嵌入的是共享成本页面。初载请求不限制成本类型，字典同时包含收款、付款、流动性和外汇成本。[ADR 0002](../../adr/0002-payment-v010-scope.md) 已确定 `payment cost list` 固定 `costTypeCode=FUND_OUT_CHANNEL_TRANS_FEE`；响应应检查 `itemType`，出现不符时报告契约错误。此限制是 CLI 的付款范围，不是页面已有行为；不推断外汇或流动性成本应全部归入付款。

本报告补充并细化 [付款产品发现](2026-09-08-payment-operations.md) 的成本部分；跨产品接入约束见 [平台访问研究](../general/2026-09-08-platform-access.md)。没有增加 CLI 命令或实现业务代码。

## 证据与只读方法

- C1：已登录 headed Chrome，CDP `127.0.0.1:9222`，独立临时 target。读取付款成本页面 DOM、请求和响应；只点击查询、分页、行展开。
- C2：页面实际发出的成本查询及字典请求；仅复验这些已核实请求。生产实体值只在内存中用于组合筛选，不落盘。
- C3：页面加载的 `7d06402e-async.f92c9dca.js`，重点 `renderSearchForm`、`handleSearch`、`onTableChange`、`expandedRowRender`；SHA-256 为 `ff8cf00cb9a4616395b0d46e55847294ac2888936bf32a2648413d7d3a9afdac`。
- C4：同应用加载的 `umi.5538b17e.js`，重点 `searchFundCost`、`getFundCostDetail` 和全局字典适配器。

这是运行态契约探查，未另行查询知识库。知识库设计不能代替 C1–C4；主线程的 graphify 检索结果由主线程另行综合。没有创建、修改、审批、上下线、同步或导出成本，也未保存 HAR、凭证、真实账号、费率或实体 ID。

## 页面、主机与请求

| 项目 | 已验证值 |
| --- | --- |
| 入口 | [付款渠道成本](https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/productPriceManagement/channelCost) |
| iframe | `https://igfc.alipay.com/receivedPayment/fundCost`；本次只有 `localeType` 查询参数 |
| API | `https://iglobalfundcontrol.alipay.com/api/fundCost/query.json` |
| 方法 | POST，JSON body |
| 认证 | URL 查询参数 `ctoken`，浏览器 Cookie；在 iframe 上下文执行 `credentials: "include"` |
| 页面 Content-Type | `application/json; charset=utf-8` |
| 复验最小显式头 | `Content-Type: application/json`；未添加页面的 `x-requested-with` 仍成功 |
| 初载 body | `{"pageSize":10}`；响应 `pageNo=0` |
| 查询按钮 body | `{"pageSize":10,"pageNo":0}` |

`ctoken` 的值与 iframe `document.cookie` 中同名 Cookie 相等，比较只输出布尔值。使用此来源构建新请求已成功。成本代理未移除 Cookie 或令牌来测试权限，也未证明每个浏览器自动附加头的必要性。主线程随后完成不改变 Cookie 存储的 `credentials: omit` 失败探测，以及同 profile headless 成功复验，见[综合验证](../general/2026-09-08-query-contract-audit.md)；令牌实际过期、401/403 等仍未穷尽。

追加验证成功的付款全量单页请求模板（当前总数小于 5000）：

```json
{
  "costTypeCode": "FUND_OUT_CHANNEL_TRANS_FEE",
  "pageNo": 0,
  "pageSize": 5000
}
```

## 筛选字段与字典

七个筛选在页面均为可清空的单选框，值为字符串。未设置字段由页面序列化时省略；本轮没有验证空字符串或 `null` 与省略等价。页面没有查询名称、状态、审批状态或渠道能力 ID 的筛选项。

初载成功请求只含 `pageSize`，证明七个筛选和 `pageNo` 可同时省略。建议的付款 CLI 范围另要求固定 `costTypeCode`；这不是后端必填约束。`pageSize` 的省略失败见分页段；未知参数、类型强制转换和更多无效值的行为尚未验证。

| 页面标签 | 请求字段 | 选项值/响应对应 | 证据 |
| --- | --- | --- | --- |
| 成本类型 | `costTypeCode` | 字典 `value`；列表 `itemType` | C2、C3；固定付款类型复验成功 |
| 渠道签约主体 | `legalEntityCode` | `entityCode`；列表 `legalEntity` | C3；组合筛选成功 |
| 渠道名称 | `financialInstCode` | `financialInst` | C3；组合筛选成功 |
| 银存账号 | `bankAccount` | 实际提交 `aliasName`，显示 `captionName`；列表 `bankAccountAliasName` | C3；组合筛选和不匹配条件成功 |
| 交易币种 | `transCurrencyCode` | `currencyCode` | C3；组合筛选成功 |
| 计费承担方式 | `chargeBearer` | 字典 `value` | C2、C3；组合筛选成功 |
| 清算网络名称 | `clearingNetworkName` | `clearingSystemName` | C2、C3；组合筛选成功 |

组合复验使用一条付款记录的六个属性，加固定成本类型和分页参数；响应业务成功，返回记录的六个属性均匹配。它证明组合被接受，不能代替逐字段穷举或证明后端对所有字符串采用精确匹配。

`GET /api/option/getCostTypes.json` 本次返回：

| value | label |
| --- | --- |
| `FUND_OUT_CHANNEL_TRANS_FEE` | 流出渠道成本 |
| `FUND_IN_CHANNEL_TRANS_FEE` | 收款渠道成本 |
| `FUND_IN_VA_FEE` | 收款 VA 功能成本 |
| `LIQUIDITY_FEE` | 流动性成本 |
| `FX_FEE` | 外汇成本 |

`GET /api/option/getCommonSelectOption.json?bizName=chargeBearer` 返回 `CRED`/Creditor、`DEBT`/Debitor、`SHAR`/Shared、`FVT`/FVT。以上两条字典均在 `iglobalfundcontrol.alipay.com`，附带 `ctoken`，结构为 `success`、`resultDataList[{label,value}]`。

清算网络字典 `GET /api/fundOutNetwork/fetchAllClearingSystemNames.json` 在本次加载被观察。其余选项由全局状态供应，静态适配器映射如下；本轮未逐一复验这些可能命中缓存的字典请求，不把其完整请求契约标为已验证：

- 币种：`/api/currency/getAll.json` → `currencyCode`。
- 主体：`/api/entity/getAll.json` → `entityCode`。
- 机构：`/api/financialInst/getAllFinancialInstFromDBExcludeDisabling.json` → `financialInst`。
- 银存：`GET /api/bankAccount/getBankAccountsOfEntity.json`；适配器将 `dataType` 映射为 `accountRole`，输出 `aliasName`、`captionName`；页面实际初始化参数尚未单独复验。

## 分页、重复查询与已知异常

`pageNo`、`pageSize` 为 JSON 整数。C3 将 UI 页码 `current` 转为 `pageNo=current-1`，查询按钮重置为 0；页面第二页实际发送 1。接口分别回显 0、1、2，不能仅凭字段名推断为一基页码。

- `pageNo` 可省略：初载成功且回显 0。
- `pageSize` 应显式提供：在无匹配银存条件下省略它，返回 HTTP 200、`success=false`、`PARAM_ILLEGAL`、`errorSpecific=0400`，分页字段为 0。
- UI 提供 10、20、30、40、50，默认 10；最初分页样本使用 10，后续补验 50 和 5000，见下节。服务器最大值尚未验证。
- 固定付款类型的 0/1/2 页各返回 10 行；`totalCount` 相同。直接查询由总数计算的末页，行数符合余数；下一页成功返回空数组，同时仍保留正的 `totalCount`。
- 相同页 0、页 1 的重复请求分别保持有序 ID 列表一致；页 0 完整记录也一致。
- **相邻页 0/1、1/2 的 `itemId` 集合均存在重叠，重复复验后仍成立。** 这几页各自内部 ID 唯一。
- 小样本 `pageSize=1` 虽被接受，但 0、1 页返回同一完整记录；固定付款类型后仍复现。这是探测值，不是建议 CLI 提供的分页规格。

因此只能确认页面使用的分页协议，不能证明可靠的全量遍历。重叠来源可能涉及后端排序或偏移实现，目前原因未证实。没有观察到服务端排序参数；页面 `sorter` 使用本地比较函数，不能擅自加入 `sortBy`。

此前“默认仅取一页、不提供全量”的建议已由下节追加验证修正。当前可优先单次大页查询，核对业务成功、范围、页码、返回数、唯一 ID 数与 `totalCount`；不完整时不发布缓存。若未来需要跨页遍历，仍应检测重复和无进展。一般结束条件 `(pageNo + 1) * pageSize >= totalCount` 或成功空页只说明遍历应停止，不证明结果完整。

## 每页 50 条与单次 5000 条的追加验证

用户指出手工每页 50 条浏览成功率高，并询问后端能否一次返回全量。2026-09-08 追加只读验证，保持既有 headed Chrome/CDP 9222，使用独立临时 target，不操作用户原有标签页。生产行与 ID 只在浏览器内存中用于计数及集合比较；输出仅含统计，target 随后关闭。

先顺序读取固定付款类型的页 0–65，`pageSize=50`，完整执行两轮：

| 指标 | 第一轮 | 第二轮 |
| --- | ---: | ---: |
| 成功页数 | 66 | 66 |
| 返回行数 / 后端总数 | 3291 / 3291 | 3291 / 3291 |
| 唯一 `itemId` 数 | 2999 | 2999 |
| 重复行数 | 292 | 292 |
| 同 ID 内容冲突 | 0 | 0 |
| 末页行数 | 41 | 41 |

总数、页码和页大小回显均正常，没有缺失 ID 或付款类型不符。两轮 ID 集合和共有记录内容一致；第二轮新增 ID 为 0。首两页各自 ID 唯一，跨页有 12 个共同 ID，分布在页内不同位置。50 条分页能够成功走完，但这不足以把返回行数当作去重后的实体数；292 首先是重复行计数，不能仅由此断言遗漏 292 个实体。

随后对同一个已验证的只读 POST 查询直接发送 `pageNo=0`、`pageSize=5000`，固定付款类型，连续两次得到：

- HTTP 成功且 `success=true`，回显页码 0、页大小 5000。
- `totalCount=3291`，实际返回 3291 行，唯一 `itemId` 数 3291。
- 无重复 ID、缺失 ID 或付款类型不符；两次 ID 集合及记录内容一致。

主线程检查了两个探针的顺序分页、计数和集合比较逻辑。以上证明当前范围可通过一次大页查询取得与后端总数一致的全部记录，无需调用独立导出任务。没有比较 50 条分页与 5000 条单页之间的完整 ID 集合，未确认跨页异常根因；也未验证服务端事务快照隔离、最大页大小或未来数据增长后的行为。

主线程还重新读取页面加载的 C3/C4 静态资源：分页选项为 `[10,20,30,40,50]`，查询适配器把参数作为 POST data 传给 `fundCost/query.json`。检查的成本页面代码及该路径族中未发现独立全量导出接口；这不证明平台全局不存在导出能力。本轮没有创建或触发任何导出任务。

### 10000 条请求与客户端超时

同日继续验证 `pageNo=0,pageSize=10000`、固定付款类型。首次请求在客户端约 20 秒的 fetch 预算下超时，没有取得 HTTP 或业务响应，不能据此判断后端拒绝大页。只将 fetch 等待延长至 60 秒后再请求一次，约 15.018 秒完成，HTTP 200、`success=true`，回显大小 10000；总数、返回行数和唯一 ID 数均为 3291，无重复、冲突、缺失 ID 或范围不符。响应正文为 4,819,617 UTF-8 字节。

这验证了 10000 的请求容量可用，也说明暂时失败可先重试原请求，不应遇到一次超时就认定需要小页。单次耗时不构成性能保证；业务明细大小也不能仅由顶层行数估计。本轮未继续探测更大上限，没有执行分页 fallback 或制造失败。

## 响应 envelope 与行模型

成功 envelope 的已观察字段如下；除明确记录的缺失分支外，字段是否必有、能否为 `null` 尚未逐项证明。此处是观察模式，不是可直接用于严格拒绝未知字段或空值的完整 schema：

```text
success: boolean
errorContext.errorStack[]: {errorName, errorSpecific, codeLevel, codeType, systemCode, systemName}
pageNo: integer
pageSize: integer
totalCount: integer
resultDataList: array<CostItem>
permissions[]: {permissionCode: string}
showButton: boolean
sofaTracerId: string
```

成功响应也有 `errorContext`，其中 `errorName=SUCCESS`；不能以该字段存在就判断失败。`permissions`、`showButton` 是页面操作权限元数据，不是成本实体字段，也不应据此开放写命令。

| 行字段 | 本轮返回类型与含义 |
| --- | --- |
| `itemId` | string；成本条目标识，行展开按它查询 |
| `itemType` | string；成本类型，本轮付款样本为 `FUND_OUT_CHANNEL_TRANS_FEE` |
| `mappingCode` | string；映射码，生成及唯一性规则未证实 |
| `legalEntity`、`financialInst` | string；渠道签约主体、机构 |
| `bankAccountAliasName` | string；银存别名，不是完整账号 |
| `transCurrencyCode`、`costCurrencyCode` | string；交易币种与计费币种，必须分开 |
| `chargeBearer`、`clearingNetworkName` | string；承担方式与清算网络 |
| `isExistFvtAbility`、`isFvt` | string，已见 `Y`/`N`；前者在部分行缺失，不能把缺失改成 `N` |
| `status` | string；已见 `ACTIVATED`、`OFFLINE`，不是穷尽枚举 |
| `approveProcessStatus` | 页面有此列，已检查的响应行未返回；可缺失，不能从 `status` 推导 |
| `gmtCreate`、`gmtModified` | integer 时间戳；应保留原值，时区约定另核 |
| `lastOperator` | string；敏感操作人信息不用于研究样本 |
| `costRateConfigList` | array；内嵌计费规则，本轮样本长度为 1，不可假定永远只有一条 |

未发现 `abilityId` 或其他能把成本条目一对一绑定渠道能力的主键。成本命令已确定独立放在 `payment cost`，不应要求先查询能力 ID，也不应把 `itemId` 改名为渠道 ID。

## 计费结构与金额语义

列表样本返回嵌套费率数据，已覆盖普通计费与 `CA4` 分段分支。以下字段有实际响应证据；其必有性、空值及其他计费分支仍未穷尽：

```text
costRateConfigList[]
  feeItemRateConfigId: string
  feeCalcBasisType: string               # 已见 CA1、CA4
  feeCalcScale: string                   # 已见 TWO_DECIMAL_AFTER_POINTS
  feeRoundingMode: string                # 已见 HALF_UP
  progressType: string                   # 已见 FULL_PROGRESS
  validStartTime / validEndTime: integer
  costRateVO
    feeItemRateConfigId / feeCalcBasisTypeCode / status: string
    gmtCreate / gmtModified: integer
    lastOperator: string
    bottomAmount / fixedAmount / topAmount: Money
    feeRateRatioValue: Ratio
    costRateRangeList[]                  # 实际 CA4 样本存在
      feeRateRangeId / status / lastOperator: string
      gmtCreate / gmtModified: integer
      includeRangeBottom / includeRangeTop: boolean
      rangeBottom / rangeTop: Money
      rangeBottomFeeAmount / rangeTopFeeAmount / rangeFixedAmount: Money
      rangeFeeRateRatioValue: Ratio

Money
  amount: number
  cent / centFactor: integer
  currency / currencyCode / currencyValue: string

Ratio
  amount / value / hundredthValue / thousandthValue / tenThousandthValue: number
  ratioUnit / ratioUnitCode: string
```

JSON 金额和比例为数值，本轮既见整数，也见小数；不是服务端十进制字符串。Python 应以 Decimal 解析精度敏感数值，保留币种与比例单位，不从 `cent` 名称假设所有币种除以 100，也不把 `value` 与 `hundredthValue` 混用。

C3 显示普通计费 UI 使用 `feeRateRatioValue.hundredthValue`、各 Money 的 `amount`；CA4 使用每个区间的比例、固定额和上下限，并用两个布尔字段表达开闭区间。有效期用 `validStartTime`、`validEndTime` 经前端日期库格式化。本轮没有运行计费引擎，不应据这些字段自行宣称算出最终付款费用，也未确认所有计费方法、边界金额和时区的完整业务语义。

## 行展开辅助查询

页面行展开实际发出 `GET https://iglobalfundcontrol.alipay.com/api/fundCost/detail.json`，参数为 `ctoken`、`itemId`，成功数据位于 `resultData`。C4 中名为 `saveFundCostDetail` 的 effect 调用的是该 GET，并保存到前端状态；它不是服务端写操作。

本轮观察的详情和列表具有相同顶层字段及费率结构。列表输出无须自动对每行发详情请求；详情仅是研究中的辅助证据，不新增第五个 CLI 查询契约。不能以一个样本证明所有列表行与详情始终完全相同。

## 空结果、错误与实现限制

- 用合成的不匹配银存别名查询，得到 HTTP 200、`success=true`、`resultDataList=[]`、`totalCount=0`：可作为正常空结果。
- 超末页查询得到成功空数组及正的总数：与筛选无匹配不同，应保留分页元数据。
- 缺少 `pageSize` 得到 HTTP 200、`success=false`、`PARAM_ILLEGAL`：应报参数/业务失败，不能渲染成功空列表。
- 没有故意破坏登录态或越权；权限失败、认证过期、限流和网络错误样本仍未覆盖。
- 主线程在 headed 和 headless 独立复验固定付款类型的两页，均成功且都存在相邻页重叠；模式切换未消除此问题。
- 尚未穷尽筛选组合、动态字典、状态枚举、缺失/空值分支、所有计费类型及多条费率有效期；未知值须保留，不应因不在已见枚举而丢数据。
- 跨页稳定性和排序契约仍未闭合；单次 `pageSize=5000` 已验证可取当前全量。不能把这一成功扩展为任意规模、任意页大小或所有数据分支均“完整无缺口”。
