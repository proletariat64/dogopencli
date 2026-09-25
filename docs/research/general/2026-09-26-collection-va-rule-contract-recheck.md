# 收款 VA 规则查询契约复核

Observed: 2026-09-26
Scope: general
Status: snapshot

## 结论

VA Rule Management 的列表与详情查询契约与 [H2 VA 规则研究](2026-09-23-collection-va-rule-query.md) 一致,endpoint、method、请求体、分页语义、行字段和详情字段均未变化。当前 totalCount 为 911(H2 当时为 907),大页两轮各取得 911 行、911 个唯一非空 `vaRuleId`。本轮复核支持进入 GitHub 规格与工单阶段;筛选参数仍只验证了 `vaRuleId` 单值,其余 UI 控件的请求编码与语义维持 H2 的未验证状态。

## 方法与会话

专用 Chrome headless,CDP 9222,复用既有认证会话(页面正常渲染业务表单,无登录跳转)。新建临时 target 打开 `https://ifundbossportal.alipay.com/voucher/VARuleManage`,观察到原生 Search 请求后,仅重放 H2 已验证的列表/详情端点。未执行 Add、Edit、VA allocation、Offline、Delete、Sync 或任何写操作;未读取生产行内容,仅内存计数与字段名比对。ctoken 等认证参数只记录键名,不记录值;不保存原始响应、账号值、规则 ID 值或截图。复核完成后临时 target 已关闭。

## 原生列表请求

| 项 | 观察值 |
| --- | --- |
| Method / URL | POST `https://ifundboss-api.alipay.com/ivostro/api/virtualAccountRule/list.json` |
| 查询参数 | 仅 `ctoken`(键名) |
| 请求体 | `{"pageNo":1,"pageSize":10}` |
| 原生响应 | success=true,pageNo=1,pageSize=10,totalCount=911,10 行 |

响应顶层键(本轮完整枚举,是 H2 文字描述的完整化,不代表服务端 schema 保证):`data`、`errorCode`、`errorContext`、`errorDescription`、`msg`、`pageNo`、`pageSize`、`resultCode`、`resultCodeType`、`resultDataList`、`resultDescription`、`resultStatus`、`sofaTracerId`、`success`、`totalCount`。

行字段与 H2 完全一致(17 个):`vaRuleId`(str)、`bankRuleId`(int)、`aliasName`、`bankAccountNo`、`financialInst`、`reconInst`、`entity`、`currency`、`memo`、`operator`、`assembleStrategy`、`regionType`、`ruleStatus`(str)、`countries`、`sceneCodes`(str[])、`supportMultiCurrency`(bool)、`gmtCreate`、`gmtModified`(int)。

## 重放验证

均以原生观察到的同一认证 URL 重放,全部 HTTP 200 且 success=true:

| 检查 | 结果 |
| --- | --- |
| pageNo=1, pageSize=10 | 10 行,totalCount=911,页码/容量回显匹配 |
| pageNo=2, pageSize=10 | 10 行,totalCount=911 |
| 越过末页(pageNo=92, pageSize=10) | 0 行,totalCount 仍为 911 |
| pageNo=1, pageSize=1000,两轮 | 各 911 行、911 个唯一非空 `vaRuleId`,totalCount=911 |
| `vaRuleId` 单值筛选(取大页返回的现有 ID) | totalCount=1,返回 ID 完全匹配 |
| 详情 GET `detail.json?vaRuleId=…`(取同一现有 ID) | success=true,resultObj 非空,ID 与列表匹配 |

详情字段与 H2 一致:`assembleStrategy`、`assignInfo`、`bankRuleId`、`clientEntity`、`creditAreas`、`entity`、`memo`、`regionType`、`ruleStatus`、`sceneCodes`、`vaRuleId`、`vaWarningInfo`。`assignInfo` 子键与 H2 一致(assignCount、assignFlows、ruleVaTotal、vaAssignAble、vaAssigned、vaImported、vaRuleId、vaUnused、vaUsed)。本样本 `vaWarningInfo` 为对象;H2 已记录并非所有样本都有可枚举的 warning 键,通知信息仍不得设为必填,联系信息不进入记录或 fixture。

## 与 H2 的差异

- totalCount 907 → 911:业务数据自然增长,非契约变化。
- 响应顶层键本轮做了完整枚举;行字段、详情字段、分页语义、筛选行为无变化。

## 仍未验证(沿用 H2 缺口,不因本轮复核消失)

1. 关联银行账户规则详情(`bankAccountVaRule/detail.json`)本轮未重放,H2 观察为 resultObj=null、原因未定;`get` 的覆盖边界须在规格中明确。
2. `vaRuleId` 以外的筛选控件(别名、机构、账户、地区、币种、主体、场景、状态、local/cross、memo、监控配置、VA 策略)未验证请求编码、枚举、数组/空值/默认语义;不据控件名发布参数。
3. 不存在的 ID、权限拒绝、认证过期、异常 schema、服务端最大容量等失败分支未探测;规格中以合成 SIT 覆盖,不在生产制造故障。
4. 1000 行大页是当前规模下两次验证的经验值,不是服务端上限保证。
5. 详情仅验证一个当前样本,不证明全部 911 个详情可取得;全量详情策略(缓存范围、原子发布)属规格决策点。
