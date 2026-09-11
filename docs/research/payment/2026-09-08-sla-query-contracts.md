# 产品 SLA 基线查询契约

Observed: 2026-09-08
Scope: payment
Status: snapshot

## 结论与边界

已在已登录 Chrome 的付款运营页面中观察并以浏览器上下文的只读 `fetch` 复验两条产品 SLA 基线查询。它们属于付款产品 SLA 基线，不涵盖同一菜单组的渠道 SLA 规则：

| 动作 | 方法与固定路径 | 已验证结果位置 |
| --- | --- | --- |
| 列表 | `POST https://iglobalfundcontrol.alipay.com/api/fundOutSlaBaseline/queryFundOutSlaBaseline` | 顶层 `resultDataList`、`totalCount` |
| 详情 | `GET https://iglobalfundcontrol.alipay.com/api/fundOutSlaBaseline/getFundOutSlaBaselineDetail?slaBaselineId=…` | 顶层 `resultData` |

入口是 [产品 SLA 基线页面](https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/productSLAManagement/SlaManagement)。该页嵌入 `https://igfc.alipay.com/receivedPayment/sla/fundOutSlaBaseline` iframe；iframe 才发出上述 API 请求。跨应用拓扑、CDP 约束及只读边界见[通用访问报告](../general/2026-09-08-platform-access.md)，菜单范围及早期接口发现见[付款运营报告](2026-09-08-payment-operations.md)。

本报告是一个账号和当日站点版本的运行态快照。字段、空值和字典选项均为观察结果，不能当作后端的穷尽或永久模式声明。未执行新增、编辑、审批、生效、导出或任意其他写操作；没有保存原始响应、业务行、实体 ID、账号、Cookie 或 token。

同日追加验证确认列表支持 `pageSize=5000` 和 `10000`，两次均一次返回当前全部 23 条，唯一 ID 数与后端总数一致。详情仍使用独立的单 ID 查询；列表的大页能力不能代替逐条详情采集。

## 证据与方法

运行态证据来自 `http://127.0.0.1:9222` 的现有已登录 Chrome。探针创建临时页面 target、等待 iframe 页面稳定、在该 origin 内 `fetch` 已验证的查询，然后关闭 target；没有启动、停止或切换 Chrome。CDP websocket 使用 `suppress_origin=True`，因为浏览器拒绝默认 websocket Origin。该选项仅解决 DevTools 附着握手，和业务 API 鉴权无关。

观察的页面初始网络请求、页面控件 `label[for]`、列表/详情响应的结构摘要和静态前端渲染器互相交叉核对。运行态加载的静态资源为 `https://renderoffice-intl.alipayobjects.com/p/yuyan/180020010001284234/146598be-async.6b69f44b.js`（列表、查询序列化和 SLA 显示，SHA-256 `0de6823b96525c467729080dcb664e91e39ede173ce3b3fd132800418a2846e8`）与 `https://renderoffice-intl.alipayobjects.com/p/yuyan/180020010001284234/728bad9d-async.534da215.js`（详情显示，SHA-256 `9e0e0669bb1db68ef91c4f7c9e1ad9a60c0e1437478ad0fe75bd7652d8972aa4`）。前一文件的 `handleSearch` 读取 `form.getFieldsValue()` 并扩展到查询 payload；其 `onTableChange` 写入 `pageNo = current - 1`。两份文件都以 `floor(sla / 3600)` 和 `(sla % 3600) / 60` 显示 SLA；后一文件将时区和节假日原样显示、将服务等级列表以逗号连接。静态代码仅用于解释页面如何序列化和显示已观察字段；响应契约仍以运行态请求为准。

知识库检索遵守先图后源的顺序：在 `~/dev/dogpdkb/graphify_flatten_ready/` 运行 `rtk proxy graphify query 'SLA baseline payment product operation'`（宽匹配、未作为本报告事实依据）和 `rtk proxy graphify query 'fundOutSlaBaseline' --budget 8000`（无匹配节点）。因此没有为本报告引用知识库源文档，也没有重建或写入知识图谱；本报告的接口结论只来自运行态页面和静态资源。

## 列表请求

### 已观察模板与认证形状

页面真实请求为：

```text
POST https://iglobalfundcontrol.alipay.com/api/fundOutSlaBaseline/queryFundOutSlaBaseline?ctoken=<fresh browser value>
Content-Type: application/json
X-Requested-With: XMLHttpRequest
body: {"pageSize": 10}
```

`ctoken` 是查询参数，不在 JSON body。当前浏览器可见名为 `ctoken` 的 Cookie；同一域还观察到 Cookie 名 `sso.global.authtoken`。页面全局变量、`localStorage` 和 `sessionStorage` 中没有 token 命名键。主线程从 Cookie 在内存中读取当前 `ctoken`，构建绝对 API URL 后独立复验列表和详情成功；这证明此构造方式可用，但不证明前端内部的唯一派生方式。值未输出或持久化。

在 iframe origin 内对上述**绝对 `iglobalfundcontrol.alipay.com` URL**执行的 POST，带 `credentials: "include"`、只有 `Content-Type: application/json`、且不带 `ctoken` 与 `X-Requested-With` 也返回 HTTP 200 且 `success=true`；使用列表中仅在内存中保留的 ID 对绝对详情 URL 的 GET 同样成功。因此，前者是用于页面保真重放的已观察模板；后者是此浏览器会话中已证明可工作的最小请求形状。两者都依赖 Chrome 附带的当期 Cookie，不能把任何一次 token 值缓存到配置、日志或 fixture。

供以后 headed 登录后或 headless 同 profile 复验的安全流程为：连接既有 CDP、创建一个 `igfc.alipay.com` 临时 target、等待 origin 和 `document.readyState` 连续稳定、从该上下文向绝对 `iglobalfundcontrol.alipay.com` URL 执行跨 origin 的 `fetch` 并使用 `credentials: "include"`、只保留结构摘要，最后关闭该 target。每次重新登录或浏览器重启后都应让浏览器重新提供当前鉴权状态与页面参数；不要从旧日志或文件恢复任何 Cookie 或 `ctoken` 值。

### 参数、默认值与筛选映射

| JSON 字段 | 默认/必填证据 | 页面控件和含义 |
| --- | --- | --- |
| `pageSize` | 初始请求为 `10`；`{}` 返回 HTTP 200 但 `success=false`、`pageNo=0`、`pageSize=0` 且 `resultDataList=null`。当前观察表明它不可省略；正数约束和最大范围尚未验证。 | 每页条数 |
| `pageNo` | 初始请求省略，响应为 `0`；显式 `0` 与 `1` 均成功。 | 零基页号；见分页段。 |
| `bizCategory` | 初始成功查询省略。 | 业务线 |
| `bizLegalEntity` | 初始成功查询省略。 | 业务主体 |
| `creditorCurrency` | 初始成功查询省略。 | 收款币种 |
| `regionCode` | 初始成功查询省略。 | 收款地区 |
| `status` | 初始成功查询省略。 | 状态 |

五个业务筛选字段由 iframe 中 `<label for>` 的实际值确认。列表静态序列化器的 `handleSearch` 取 `form.getFieldsValue()`，以 `{...formValues, pageSize, pageNo: 0}` 发送；翻页也以 `{...formValues, pageSize, pageNo: current - 1}` 发送。因此标签字段名和实际 POST payload 的映射均有前端证据。初始成功请求只含 `pageSize`，所以它们在未筛选查询中均为可省略字段。尚未枚举字段组合约束或无效值行为。

运行态补充验证了 `bizCategory`、`creditorCurrency`、`regionCode` 和 `status`：分别从一条仅在内存中读取的默认列表记录取值，再以该单字段请求首页；每次 HTTP 200、`success=true`，并且返回行都与选择的同一字段值一致。`bizLegalEntity` 的页面字段名和 serializer 映射已确认，但尚未用单独的业务主体值验证结果行，因为当前列表行不返回该字段。

前端加载的选项来源及已观察结构如下；CLI 不应把当日选项硬编码为固定枚举：

| 筛选 | 已观察选项来源 | 选项响应中的值形状 |
| --- | --- | --- |
| `bizCategory` | `GET /api/fundPlan/getBizCategories.json?ctoken=…` | `resultDataList[].code`、`desc`，可含递归 `children[]`（`code`、`desc`、`parentCategoryCode`） |
| `bizLegalEntity` | `GET /api/entityRole/fetchAll.json?ctoken=…` | `resultDataList[].label`、`value` |
| `creditorCurrency` | `GET /api/currency/getAll.json?ctoken=…` | `resultDataList[].currencyCode`、`currencyLabel`、`currencyValue` |
| `regionCode` | `GET /api/option/getAllRegion.json?ctoken=…` | `resultDataList[].label`、`value` |
| `status` | `GET /api/fundPlanSegment/fetchAllStatusType.json?ctoken=…` | `resultData[].label`、`value` |

本次状态字典返回的完整快照值为 `DRAFT`、`WAIT_FOR_SUBMIT`、`WAIT_FOR_AUDIT`、`AUDITED`、`ACTIVATED`、`DEPRECATED`、`LAUNCHED`、`OFFLINE`、`ONLINE`、`DEV_ENV_TESTING`、`SIT_ENV_TESTING`、`TEST_COMPLETED`、`WAIT_LAUNCHED`、`PRE_LAUNCHED`、`GRAY_LAUNCHED`、`PROD_LAUNCHED`、`PRE_OFFLINE`、`GRAY_OFFLINE`、`PROD_OFFLINE`、`WAIT_OFFLINE`、`OFFLINE_AUDITED`。这是字典响应的 `value`，不表示每个状态都有 SLA 基线记录，也不保证后续权限或版本下的集合不变。

### 分页

接口使用零基 `pageNo`。前端的 `onTableChange` 将可见页码 `current` 序列化为 `rowStart = current - 1`，Search 重置为 `current=1`、`rowStart=0` 并发出 `pageNo=0`。运行态也确认：

- 默认 `{pageSize: 10}` 回显 `pageNo=0`、`pageSize=10`，返回 10 行，`totalCount=23`（本次观察日 `2026-09-08`）。
- `{pageSize: 1, pageNo: 0}` 与 `{pageSize: 1, pageNo: 1}` 各返回一行，回显对应页号；两页首行的 ID 在探针内比较为不同，未输出 ID。
- `{pageSize: 10, pageNo: 1000000}` 返回 HTTP 200、`success=true`、空 `resultDataList`，仍给出正数 `totalCount`。

安全终止条件是先使用响应 `totalCount`（若其为可信非负数）限制最大页号，并把空 `resultDataList` 作为额外停止条件。主线程另两次复验了合成的不匹配地区字符串 `regionCode=DOGOPENCLI_NONMATCHING_REGION`：HTTP 200、`success=true`、`totalCount=0`、分页回显正常，但 `resultDataList` 键被省略，`errorName=SUCCESS`。这一已观察分支可规范化为正常空列表；不推断任意缺失或 `null` 都表示空。

处理顺序为先判断 HTTP 和业务成功，再检查零总数且列表键省略这一分支，其余成功响应要求列表结构符合契约。若 `success=false`、分页元数据异常或其他无法解释的结构变化，应报查询/契约错误。

### 5000 与 10000 大页追加验证

2026-09-08 在既有 headed Chrome、CDP 9222 的独立 target 中，按同一已验证请求模板，仅将 `pageNo` 设为 0、`pageSize` 分别设为 5000 和 10000，各执行一次无业务筛选的列表查询：

| 请求大小 | HTTP / 业务成功 | 回显大小 | 总数 / 返回行 / 唯一 ID | 响应正文 UTF-8 字节 | 请求耗时 |
| --- | --- | ---: | --- | ---: | ---: |
| 5000 | 200 / true | 5000 | 23 / 23 / 23 | 9882 | 1017 ms |
| 10000 | 200 / true | 10000 | 23 / 23 / 23 | 9883 | 233 ms |

两次回显页码均为 0，无缺失 ID、重复或同 ID 内容冲突；跨大小的 ID 集合和记录内容一致。记录和 ID 仅在内存中比较，主线程核对了统计脚本，临时 target 已关闭。

结果证明当前列表没有强制为小页，可用大页取得当前全量；未证明服务器最大页大小或更多数据时的响应时间。检查的已验证契约没有批量详情接口，未调用任何猜测的批量或导出端点。离线 SLA 详情缓存仍需列表后逐条查询详情，这是正常采集步骤，不是列表失败后的 fallback。

### 列表响应

成功非空响应的已观察顶层形状如下；这些类型不是字段必有或允许空值的完整声明：

```text
{
  success: boolean,
  resultDataList: SlaBaseline[],
  totalCount: number,
  pageNo: number,
  pageSize: number,
  showButton: boolean,
  permissions: array,
  sofaTracerId: string,
  errorContext: { errorStack: ErrorItem[] }
}

ErrorItem = {
  codeLevel: string, codeType: string, errorName: string,
  errorSpecific: string, systemCode: string, systemName: string
}
```

当缺少 `pageSize` 时，本次观察到 `success=false` 响应仍有 `pageNo`、`pageSize`、`totalCount`、`showButton`、`sofaTracerId`、`errorContext` 和 `resultDescription`，但 `resultDataList` 为 `null` 而不是空列表。错误文本和追踪 ID 均不应作为稳定 CLI 协议或记录到日志。

零总数且列表键省略的成功响应，与缺少 `pageSize` 时的业务失败及显式 `null` 不同。字段缺失、显式 `null`、空数组三者必须分别记录和处理。解析器保留未识别的业务字段及嵌套 JSON，不因本轮样本中未出现而丢弃；CLI 必需的 envelope 和标识字段仍需校验。

当前成功行的观察字段形状如下：

```text
SlaBaseline = {
  id: string,
  bizCategory: string,
  creditorCurrency: string,
  regionCode: string,
  status: string,
  timezone: string,
  creditorMinAmount: string,
  creditorMaxAmount: string,
  debitorSuccessSla: string,
  creditorSuccessSla: string,
  holidayLimit: string,
  serviceLevelLimit: array,
  creator: string,
  lastOperator: string,
  gmtCreate: number,
  gmtModified: number
}
```

`id` 是列表中的字符串标识；将一个仅在内存中取得的 `resultDataList[].id` 作为详情的 `slaBaselineId` 后，详情成功返回，证明这两个名称之间的对应关系。`gmtCreate` 和 `gmtModified` 是数字，但此轮没有验证 epoch 单位或时区。金额字段在样本中是十进制文本；不要在缺少进一步契约时将其转为二进制浮点数。

## 详情请求与响应

### 参数与空值行为

页面请求使用：

```text
GET https://iglobalfundcontrol.alipay.com/api/fundOutSlaBaseline/getFundOutSlaBaselineDetail?slaBaselineId=<list.id>&ctoken=<fresh browser value>
```

用最小浏览器内 GET（Cookie 凭据、无 `ctoken` 查询参数）也成功返回当前列表中的 ID。`slaBaselineId` 是必填：完全省略时返回 HTTP 200、`success=false`、`resultData=null` 和 `resultDescription`。使用合成、非存在的字符串 ID 时返回 HTTP 200、`success=true`、`resultData=null`，没有把“找不到”表示为 HTTP 错误。本次没有把真实 ID、错误描述或追踪 ID 写入输出。

调用方应把 `success=false` 视为请求失败；把 `success=true` 且 `resultData=null` 表示为不存在的 SLA 基线，而不是构造一条空记录。无论哪种情形，都不应重试为写请求或探测其他端点。

### 成功响应

成功详情的已观察顶层形状为：

```text
{
  success: boolean,
  resultData: SlaBaseline,
  sofaTracerId: string,
  errorContext: { errorStack: ErrorItem[] }
}
```

当前详情的 `resultData` 字段与列表 `SlaBaseline` 形状相同。页面静态详情渲染器还会尝试读取 `creditorBankBicLimit`、`creditorSlaBuffer`、`creditorSlaDecide`、`debtorSlaBuffer`、`debtorSlaDecide`、`riskRuleCode` 及告警相关字段；它们没有出现在本次成功详情响应中。它们只能作为前端可选字段提示，不属于已验证的强类型模型；将来实际返回时，应作为原始扩展字段保留。

在默认首页的 100 条以内记录中，`serviceLevelLimit` 均为空数组；因此其元素的键、元素类型、`null` 行为和是否在其他记录中出现均未验证。解析器应保留空数组并将非空元素视为待确认 JSON，不应猜测其嵌套结构。

## 时效、时区与节假日语义

前端静态列表和详情渲染器给出以下较强证据：

- `debitorSuccessSla` 的显示标签是 `PaymentSucceedSLA`，`creditorSuccessSla` 是 `PaymentArrivalSLA`。
- 两个 SLA 字段均按 `floor(value / 3600)` 显示小时、按 `(value % 3600) / 60` 显示分钟，因此数值文本的基础单位是秒。当前样本也符合“整数字符串”的形状。
- `timezone` 在 `TimeZone` 标签下原样显示；其格式、允许的 IANA/偏移枚举和默认值尚未验证。
- `holidayLimit` 在 `Holiday` 标签下原样显示；其编码、是否为布尔/策略/日期规则以及与 SLA 的计算关系尚未验证。
- `serviceLevelLimit` 在 `serviceLevel` 标签下以逗号连接显示；当前只观察到空数组，元素语义未知。

因此 CLI 应保留两个 SLA 字段的原始字符串，仅当可解析为有效数值时派生秒及小时/分钟显示，不能把未知格式默认成零。保留 `timezone`、`holidayLimit` 和 `serviceLevelLimit` 的原始形状，直到有多种非空记录的独立证据。

## 未验证事项与实现限制

- 除状态外的筛选值全集、字段组合、排序和最大 `pageSize`。
- `totalCount` 在并发变更时的一致性；它是观察到的分页上界，不是快照事务保证。
- 合成不匹配地区值的零总数分支已经主线程复验；不同有效字典值组合导致零结果时是否完全相同，未逐一验证。
- 非空 `serviceLevelLimit` 的嵌套模式，及静态渲染器中其他可选详情字段何时出现。
- `timezone`、`holidayLimit`、创建/修改时间的精确格式和业务语义。
- 权限、会话到期和 SSO 重定向的完整行为；主线程已独立完成同 profile headless 列表/详情成功复验。不带浏览器凭证的列表 fetch 观察到 `TypeError`，具体成因未定，见[综合验证](../general/2026-09-08-query-contract-audit.md)。

在这些缺口关闭前，CLI 契约应限制为固定的两个查询端点、上述已验证参数和保守 JSON 解析，并拒绝所有非 allowlist 的请求。
