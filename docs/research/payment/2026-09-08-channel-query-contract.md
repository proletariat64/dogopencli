# 付款渠道列表查询契约

Observed: 2026-09-08
Scope: payment
Status: snapshot

## 结论

“流出渠道基础数据管理”当前由付款运营入口嵌入客资运营页面，列表查询是一个明确的 inquiry 操作：

- 外层页面为 [渠道管理](https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/networkConstruction/channelsManagement)。
- 实际页面上下文为 `https://ifundbossportal.alipay.com/payout/allocationCenter/payerCenter/TransfertoProductization`。
- 查询端点为 `POST https://ifundboss-api.alipay.com/payout/api/ability/search.json`，JSON 结果列表位于 `resultObj.payoutAbilityVOList`。
- UI 使用从 1 开始的页码，默认每页 10 条；已验证 `pageNum=0` 被调整为首页、大于 `totalPages` 被调整为末页。因此客户端必须以分页元数据停止，不能依赖“请求到空页”为终止条件；其他非法页码行为未穷尽。
- 九个业务筛选项在 UI 都没有必填标记，服务端也接受空 JSON。表单的“流出场景”初始值是 `EXTERNAL`，但页面首次自动查询没有发送它；用户点击搜索后才发送该默认值。

同日追加每页 50/100 条、前两页验证：第二页分别成功返回 50/100 条，第一页均重复返回业务失败。因此 50 不是已证明的后端硬上限，100 已在第二页被接受，但目前不能保证大页或第一页可用；详见追加验证。

本报告只固定查询契约，不授权详情、同步、导入、下载、推进、编辑、灰度或生效操作。没有调用这些操作，也没有保存生产记录、账户值、ID、Cookie、票据或 token。

本轮主线程复验和记录总数采用显式 `payoutType=EXTERNAL`，与用户点击 Search 后的默认场景一致。建议 CLI 默认也明确发送此值，避免省略字段后悄悄改变查询范围；其他场景是否作为参数开放仍是命令设计问题，不能将它们仅凭名称判为收款或写操作。

## 证据与方法

| 编号 | 一手来源 | 观察内容 | 限制 |
| --- | --- | --- | --- |
| R1 | [生产渠道管理页面](https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/networkConstruction/channelsManagement) | 在用户已登录的 headed Chrome 中，以独立 CDP target 检查外层页面、iframe、表单控件和 React 选项 | 只代表观察时账号、权限和站点版本 |
| R2 | 页面发出的 Network 请求及浏览器内安全重放 | 记录方法、主机、路径、参数名、JSON 类型、分页元数据和响应结构；重放仅调用已由页面确认的查询端点 | 输出先在页面/进程内脱敏，没有保存原始响应 |
| R3 | 页面加载的生产静态 bundle `https://renderoffice-intl.alipayobjects.com/p/yuyan/180020010001284233/umi.df3bfb1c.js` 与 `https://renderoffice-intl.alipayobjects.com/p/yuyan/180020010001284233/9e65757e-async.16f6b9d1.js` | 前者含 API/模型映射，后者含表单、枚举、分页和 `excuteSearch` 请求组装 | 以带构建指纹的完整 URL 和符号片段定位；未计算 SHA-256，文件名后缀不能当作内容校验值 |
| R4 | `~/dev/di/docs/spec/browser-cdp-v1.1.md` | target 所有权、页面就绪、浏览器内 fetch、凭证保护和 target 清理约束 | 参考规范，不是 dogopencli 已实现能力 |
| R5 | `~/dev/di/src/diexporter/browser_cdp.py` | `HttpCdpTransport`、`_await_target_ready`、`_fetch_expression` 和 worker target 清理实现 | 只借鉴 transport 机制，没有运行 DI launcher 或导出流程 |

知识库检索先在 `~/dev/dogpdkb/graphify_flatten_ready/` 执行：

```bash
rtk proxy graphify query "payment product operations channel management payout ability search endpoint filters enums pagination response schema" --budget 3200
```

随后核对源文件 `收付款产品__调拨中心产品化能力建设__运营能力建设__调拨产品化-调拨基础数据人工运营PRD-2026-04-18-[142062444].md` 第 75、85–125、174–191 行。该设计资料说明渠道、账户、币种、地区、清算网络、成本和时效的领域含义；运行态 R1–R3 才是本报告接口契约的依据。设计稿把部分筛选描述为文本或单选，当前页面实际将账户简称、银存账号、清算网络和两个币种实现为多选，不能用历史稿覆盖生产观察。

## 请求契约

### 端点与认证

| 项 | 观察值 |
| --- | --- |
| 方法 | `POST` |
| URL | `https://ifundboss-api.alipay.com/payout/api/ability/search.json` |
| 请求体 | JSON object，正常页面请求发送 `Content-Type: application/json` |
| 页面上下文 | `https://ifundbossportal.alipay.com/payout/allocationCenter/payerCenter/TransfertoProductization` |
| 凭证 | `fetch(..., credentials: "include")` 所代表的浏览器 Cookie 会话 |
| token 名称 | 页面 Cookie 中存在 `ctoken`；正常 UI 请求把同名参数附在 URL query 上 |

认证最小形状的安全探测结果为：

- Cookie 会话和 query `ctoken` 同时存在时，HTTP 200 且内外层业务成功。
- 保留 Cookie 会话、移除 query `ctoken` 时，本次端点仍成功。因此不能把 query 参数描述为服务端绝对必填项。
- 保留 query `ctoken`、移除所有浏览器凭证时，HTTP 仍为 200，但返回 `success=false` 的认证错误对象；其键为 `buserviceErrorCode`、`buserviceErrorMsg`、`redirectUrl`、`success`，没有标准 `resultObj`。

忠实重放应从当前页面内存读取最新 `ctoken`，同时使用 `credentials: "include"`。不得把 token 或 Cookie 复制到配置、日志、fixture 或报告。上述试验只能证明 Cookie 会话整体必要，不能识别其中某一个 Cookie 的独立必要性。

### 筛选与分页字段

| UI 名称 | JSON 字段 | JSON 类型 | 默认与必填 | 取值来源或映射 |
| --- | --- | --- | --- | --- |
| 流出场景 | `payoutType` | string | 可选；表单初始值 `EXTERNAL` | 固定枚举，见下表 |
| 银行简称 | `financialInstId` | string | 可选 | `/api/queryBank.json`；显示 `suggestName`，提交 `suggestValue` |
| 账户简称 | `debitAccountNameList` | string[] | 可选，多选 | `/payout/api/ability/searchDataMap` 的同名 string[]；显示值等于提交值 |
| 银存账号 | `debitAccountNoList` | string[] | 可选，多选 | `/payout/api/ability/searchDataMap` 的同名 string[]；显示值等于提交值 |
| 流出国别 | `debitInstCountryCode` | string | 可选 | `/api/common/queryBankArea.json`；显示 `suggestName`，提交 `suggestValue` |
| 清算网络名称 | `clearingSystemNameList` | string[] | 可选，多选 | `/payout/api/ability/cutoffAndAbilityClearSystems`；提交 `suggestValue || suggestName`，并有静态追加的 `DEFAULT` |
| 付款币种 | `debitCurrencyList` | string[] | 可选，多选 | `/api/common/getCurrency.json`；显示和提交都使用 `suggestName` |
| 收款币种 | `creditCurrencyList` | string[] | 可选，多选 | 同上 |
| 生效状态 | `status` | string | 可选 | 固定枚举，见下表 |
| 页码 | `pageNum` | integer | 可选；UI 初始值 1，API 空 body 默认 1 | UI 从 1 开始 |
| 每页条数 | `pageSize` | integer | 可选；UI 初始值 10，API 空 body 默认 20 | UI 可选 10、20、30、40、50 |

R3 中 `renderSearchForm` 固定了表单字段名和选项映射；`componentDidMount` 首次调用 `excuteSearch({})`；`excuteSearch` 再从分页状态补齐缺失的 `pageNum` 和 `pageSize`。实际 Network 与此一致：首次请求仅含 `pageNum=1`、`pageSize=10`，点击搜索后含 `payoutType=EXTERNAL`、`pageNum=1`、`pageSize=10`。

#### 流出场景

| 显示值 | wire value |
| --- | --- |
| 对客流出 | `EXTERNAL` |
| 流动性调拨 | `LIQUIDITY` |
| 人工调拨 | `MANUAL` |
| 清算调拨 | `SETTLEMENT` |

#### 生效状态

| 显示值 | wire value |
| --- | --- |
| 启用 | `ENABLE` |
| 废弃 | `DISABLE` |
| 灰度 | `GRAY` |
| 待上线 | `TEST` |
| 草稿 | `INIT` |

### 字典端点

以下端点的实际主机均为 `https://ifundboss-api.alipay.com`，由页面以 `GET` 调用，在本次登录态下 HTTP 200、外层 `success=true`、`status=true`。已捕获请求只有 URL query 参数名 `ctoken`，没有请求体；未测试省略令牌的字典调用，不能断言其必填。表中不记录参数值或字典内容。

| 路径 | `resultObj` 结构 | 页面用途 |
| --- | --- | --- |
| `/api/queryBank.json` | `errorCode:string`、`errorMessage:string`、`pageNo:integer`、`pageSize:integer`、`success:boolean`、`suggestObjectList:{suggestName:string,suggestValue:string}[]`、`totalCount:integer` | 银行简称；按 `suggestValue` 去重 |
| `/api/common/queryBankArea.json` | 同一 suggestion envelope | 流出国别 |
| `/api/common/getCurrency.json` | 同一 suggestion envelope | 付款/收款币种；页面只使用 `suggestName` |
| `/payout/api/ability/cutoffAndAbilityClearSystems` | 同一 suggestion envelope | 清算网络；映射为单一名称并追加 `DEFAULT` |
| `/payout/api/ability/searchDataMap` | `debitAccountNameList:string[]`、`debitAccountNoList:string[]` | 账户简称和银存账号 |

这些字典是动态生产数据源。表格用于说明字段来源，尚不构成五个独立字典能力的完整契约；参数必填性、动态依赖和权限变化需在将其注册为 CLI 辅助查询前核实。不能把其内容固化为仓库枚举，尤其不能保存账户简称或银存账号列表。

## 分页与空结果

生产安全查询验证了以下语义：

- `pageNum=1` 是首页；响应回显 `resultObj.pageNum=1`。
- `pageNum=0` 不报错，而是被钳制为 1。
- `pageNum` 大于 `totalPages` 不返回空数组，而是被钳制到最后一页，并再次返回最后一页记录。
- 最后一页可以少于 `pageSize`；观察到 `totalPages = ceil(totalCount / pageSize)`。
- 空 JSON body 成功，服务端使用 `pageNum=1`、`pageSize=20`。
- 使用合成的不存在银行标识进行查询时，HTTP 200，内外层成功，返回 `pageNum=0`、`pageSize=10`、`totalCount=0`、`totalPages=0` 和空的 `payoutAbilityVOList`。

分页消费者先识别 `totalCount=0`、`totalPages=0` 和空列表这一正常空结果；此分支的回显 `pageNum=0` 不应被当成分页错误。非空结果在处理 `pageNum == totalPages` 后停止，并核对请求与回显、检测重复页或无进展。若使用“继续请求直到列表为空”，该端点会重复最后一页并造成死循环或重复数据。

## 响应契约

### 大页及每页 50/100 条的追加验证

2026-09-08，使用既有 headed Chrome、CDP 9222、独立临时 target，固定 `payoutType=EXTERNAL`。Channel 代理先以同一正确认证 URL、同一会话、请求头和凭证设置比较 `pageNum=1` 的 `pageSize=5000` 与 10：5000 返回 HTTP 200、外层 `success=false/status=false`、无有效 `resultObj`；10 返回 HTTP 200、内外层成功、10 行、总数 4914。没有把这一失败认定为明确的页大小上限。

用户随后要求只验证 50、100 条各两个页面。主线程按 `pageNum=1,2` 各执行一次，并对这四个请求完整复验一次，两轮结果一致：

| 请求页大小 | 请求页码 | HTTP | 业务结果 | 返回行 / 唯一 ID | 回显页大小 / 页码 | 总数 / 总页数 |
| --- | --- | ---: | --- | --- | --- | --- |
| 50 | 1 | 200 | 外层失败，无有效内层结果 | 不适用 | 不适用 | 不适用 |
| 50 | 2 | 200 | 内外层成功 | 50 / 50 | 50 / 2 | 4914 / 99 |
| 100 | 1 | 200 | 外层失败，无有效内层结果 | 不适用 | 不适用 | 不适用 |
| 100 | 2 | 200 | 内外层成功 | 100 / 100 | 100 / 2 | 4914 / 50 |

两个第一页的失败码均为 `msgCode=IPAY_RS_510090020`、`errorName=SERVICE_RESULT_NOT_TRUE`、`errorSpecific=0020`。这不是成功空结果，不能输出零条配置；错误码也没有直接证明页大小限制、登录失效或具体后端根因。

成功的第二页内无重复 ID，所有行均为 EXTERNAL，`abilityId` 均为安全整数。由于第一页失败，无法比较相邻两页的重叠或证明跨页完整性。100 条第二页成功说明后端至少在这一请求中支持超过 UI 50 条的容量；5000 首页失败还不能归因于容量，因为 UI 支持的 50 条首页也失败。10000、1000 及其他场景的大页请求没有执行，不宣称其支持或拒绝。

初次主线程探针以 URL 对象调用当前页面的 `fetch`，未取得可用统计；改为与既有成功探针一致的 URL 字符串后取得以上业务结果，未确认前一调用失败的具体原因，不把它计作后端页大小证据。所有业务记录、ID 和凭证只用于内存中的请求或比较，未落盘。临时 target 均已关闭，用户原页面保留。

### 每页 10 条的完整遍历尝试

用户提出：若每页 10 条能够完整运行，则改用 10 条。2026-09-08 主线程在同一既有会话的两个独立临时 target 中分别尝试顺序遍历 EXTERNAL，从 `pageNum=1,pageSize=10` 开始；每页检查内外层业务成功、页码/大小/总数、记录标识和场景，遇到失败停止，不跳过失败页。

两次均只完成第 1–3 页，每页 10 行，累计 30 行、25 个唯一 `abilityId`、5 个重复行，同 ID 内容冲突为 0。成功页报告 `totalCount=4914,totalPages=492`。第 4 页均返回 HTTP 200、外层 `success=false/status=false`，没有有效内层结果；错误仍为 `IPAY_RS_510090020 / SERVICE_RESULT_NOT_TRUE`，`errorSpecific=0020`。随后停止，没有执行剩余 488 页。

因此“第一页成功”仍成立，但“每页 10 条可完整运行”的条件未满足。没有取得完整快照，也没有证明缩小页大小能修复此问题。根因仍未知，不能将重复行或失败直接归为后端排序、特定坏记录或容量限制。两次只保存统计，业务数据与 ID 留在内存，临时 target 均已关闭。

### 外层 envelope

成功响应样本观察到的顶层键和类型如下；不表示所有响应分支都有这些字段：

| 字段 | 类型 |
| --- | --- |
| `success`、`status` | boolean |
| `data` | null |
| `msg`、`msgCode`、`resultCode`、`resultCodeType`、`resultDescription`、`resultStatus`、`sofaTracerId` | string |
| `errorContext` | object |
| `errorContext.errorStack` | object[]；元素含 `codeLevel`、`codeType`、`description`、`errorName`、`errorSpecific`、`systemCode`、`systemName`，均为 string |
| `errorContext.thirdPartyError` | string |
| `resultObj` | object |

成功不能只看 HTTP 200。先处理 HTTP/传输失败，再检查外层 `success` 及存在时的 `status`。`success=false` 即业务失败，即使没有 `resultObj`；已观察的无凭证分支另外包含认证跳转元数据，但不能把所有业务失败都归类为认证失败。外层成功后，必须验证 `resultObj` 对象、`resultObj.success` 及分页/列表结构；成功响应缺少必要字段应报契约错误。

### `resultObj`

| 字段 | 类型 |
| --- | --- |
| `success` | boolean |
| `code`、`description`、`errorMessage`、`accountingEntityCode`、`legalEntityCode`、`tntInstId` | string |
| `errorContext` | null（成功样本） |
| `pageNum`、`pageSize`、`totalCount`、`totalPages` | integer |
| `payoutAbilityVOList` | object[] |

成功样本中 `resultObj.code` 为 `IPAY_RS_100000200`。生产记录值没有保存；这里只记录 contract 字段与业务成功码。

### `payoutAbilityVOList[]`

下面是四个 `payoutType` 各取首页 10 条、共 40 条只读样本的字段并集和 JSON 类型。40 条样本中这些字段都存在；这只能说明当前样本形状，不能证明所有历史记录永不为 null。

| 分组 | 字段与观察类型 |
| --- | --- |
| 标识与版本 | `abilityId:integer`；`configVersion:string`；`payoutType:string`；`status:string`；`financialInstCode:string`；`gmtModified:integer`；`operateTime:string`；`lastOperator:string`；`discardReason:string` |
| 账户与网络 | `debitAccountName:string`；`debitAccountNo:string`；`debitInstBic:string`；`debitInstCountryCode:string`；`debitInstMemberId:string`；`clearingSystemName:string`；`clearingSystemType:string`；`creditRegion:string`；`integrationMode:string`；`communicateMode:string` |
| 币种与金额 | `debitCurrency:string`；`creditCurrency:string`；`debitMinAmount:Money`；`debitMaxAmount:Money`；`creditMinAmount:Money`；`creditMaxAmount:Money`；`chargeAmount:Money` |
| 成本与收费 | `costLevel:integer`；`noFvtCostLevel:integer`；`chargeBearer:string`；`chargeDescription:string`；`chargeMode:string`；`chargePercent:integer`；`fvtChargeType:string` |
| 时效 | `efficiencyLevel:integer`；`averageProcessingTime:string`；`businessAcceptStartTime:string`；`businessAcceptEndTime:string`；`cutOffTime:string`；`overCutOffTime:string`；`overLimitTime:string`；`payoutEfficiency:string`；`valueDateEfficiency:string`；`timeZone:string` |
| 能力属性 | `holidayPayoutSolution:string`；`insufficientBalanceSolution:string`；`regulatoryRequiredObo:string`；`supportMultiCurrency:string`；`supportPayoutReverse:string`；`supportedDisplayNonUd:string`；`supportedFvt:string`；`supportedObo:string` |
| 灰度与范围 | `grayOrderCount:integer`；`exceptedGrayOrderCount:integer`；`grayOrderBizNos:array`；`supportCreditInstIdList:array`；`transferTypeList:string[]` |

`Money` 的观察形状为：

| 字段 | 类型 |
| --- | --- |
| `amount` | JSON number；样本中既有整数表现也有非整数表现 |
| `cent`、`centFactor` | integer |
| `currency`、`currencyCode`、`currencyValue` | string |

`grayOrderBizNos` 和 `supportCreditInstIdList` 在这 40 条样本中都是空数组，因此元素类型仍未验证。`transferTypeList` 同时观察到空数组和 string 元素。

金额数值应在 JSON 解码时保留十进制精度，例如使用 Decimal，保留币种及原始金额字段；不能先转二进制浮点再声称精确恢复，也不能从 `cent` 名称假定统一除以 100。比例、时间和评分单位未确认时保留原值。解析器保留未知业务字段、枚举值及嵌套 JSON；两种未知数组元素也应保留，不能因不在本轮字段并集中而丢弃。

## 可复验的脱敏探测

headless 复验应复用同一专用 profile，但只在唯一 Chrome 进程持有该 profile 时运行：

1. 创建自己拥有的临时 target，加载付款根页面并定位上述 `ifundbossportal` iframe 上下文。
2. 要求 `document.readyState` 稳定，且 origin/path 与本报告的页面上下文完全相同。
3. 在页面内存读取最新 `ctoken`，构造绝对 allowlist URL；使用 `credentials: "include"`、JSON body `{"payoutType":"EXTERNAL","pageNum":1,"pageSize":1}` 调用唯一查询端点。
4. 仅返回 HTTP 状态、origin/path、业务成功布尔值、分页字段类型、envelope/result 键、行字段类型和列表长度；不得返回 token、header 值或行值。
5. 关闭 websocket 和本次 target，不切换、不关闭其他 target。

渠道代理完成 headed 探查后，主线程独立复验了 headed 和同 profile 的 headless 查询，均为 HTTP 200、内外层业务成功；EXTERNAL 范围 `totalCount=4914`。浏览器随后恢复 headed。具体模式切换及其限制见[综合验证](../general/2026-09-08-query-contract-audit.md)。

## 未验证事项

- 登录态有效期、认证跳转的稳定错误码，以及各 Cookie 的独立必要性。
- 服务端最大页大小、非法类型校验及首页失败原因。UI 外的 100 条第二页已成功，不能继续把 UI 的 50 当作后端硬上限；也不能因第二页成功而承诺该大小可完整采集。
- 40 条样本之外字段的 nullability，以及两个始终为空数组的元素结构。
- suggestion 字典随权限、租户和时间变化时的稳定性；报告没有保存生产字典值。
- 除认证失败之外的业务错误码及其 `resultObj` 形状。
- headless 长时间运行、登录过期及重复登录后的兼容性；本轮仅完成一次成功切换和查询。
