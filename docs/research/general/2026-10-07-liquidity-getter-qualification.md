# Liquidity getter 资格化与本轮实施

Observed: 2026-10-07
Scope: general
Status: snapshot

权威资格化规格为 [#137](https://github.com/proletariat64/dogopencli/issues/137)，
本轮实施票为 [#139](https://github.com/proletariat64/dogopencli/issues/139)。
用户本轮授权实施，并明确选择独立路由额度查询；`network routes get` 继续延期。
原始十四项中的 RFQ 已获得新证据；其余十二项保持 unsupported。
独立路由额度是新增上下文聚合查询，不计作 routes getter 已完成。

## 方法与来源

先使用 `~/dev/dogpdkb/graphify_flatten_ready/` 的 graphify 查询，再核对国际流动性白皮书
197368565 行 735–749、1029–1039，以及页面梳理 323959460 行 42–77。
这些 PRD 说明配置、任务、结果与价格的业务粒度，不证明当前详情接口可用。

代码关系先查询当前 worktree 的 code-review-graph；图基线为 master 合并提交
`da50bce0c6700a7d8ab0f6d76683adf5bcd48cf2`，包含 210 文件、2813 节点。
外部压缩前端属于图覆盖缺口，以下使用零起点 Unicode 字符偏移作有界复核。
原生来源是本机保存的 `umi-current.js`，SHA-256 为
`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`。
它与此前已核对的部署源码相同；有界检查没有找到新接口，不代表后台不存在其他接口。
生产数据只存私有目录；本文不包含真实对象 ID、账户别名或原始响应。

## RFQ 子任务：修正原生身份绑定

原规格将 wire 参数 `inquiryTaskId` 解释为父任务 ID；原生调用证明参数名称不能决定粒度。
Detail 链接偏移 9912866 把行的 `inquirySubTaskId` 放入 URL `inquiryTaskId`，
组件 9949925 读取该参数，调用 9962246 将其传入
GET `/rfq/subInquiryTask/queryInquiryTaskDetail.json`（wrapper 1530533）。
URL 中另有父 `taskId`，该详情调用不使用它。

本轮按上述真实绑定仅做一次修正查询：HTTP 200、success=true，根
`inquiryTaskId` 精确回显所选子任务，`inquiryType=TARGET_RFQ`，
`inquiryOrderListVOList` 包含四个原生成员。此前父 ID 查询的业务 999
不能代表这个正确子任务调用失败。机构级 `inquiryOrderDetail` 是另一粒度，不替代子任务详情。

拟实施 `liquidity investment rfqs get --inquiry-sub-task-id`：独立原生详情缓存，
保留原生根对象及询价成员的允许字段、精度与日期，严格核对子任务身份和类型。
普通 get 离线、显式 detail refresh 发布、live 不写缓存或回退；失败保留旧缓存。

## 独立账户上下文路由额度

原生 wrapper 1501759、selected-network caller 7211216 和 account-route caller 4398031
证明 GET `/queryWhaleRouteDetail.json` 的 `routeId`、`aliasName`、`tntInstId`
绑定所选网络/账户上下文，响应回调消费该上下文的额度聚合。
本轮先读一个原生 realtime 详情并核对 ID，再使用其原生 routeId/debitAliasName
查询额度：HTTP 200，resultFlag=true、result.success=true；dynamicQuotas 一项、staticQuotas 两项。
两次请求均为只读，原有浏览器 target 集合保留。

拟实施 `liquidity network route-quotas get --route-id --alias-name`，固定当前租户 GUAPW3SG。
一个返回对象表示请求上下文的完整原生额度聚合，不将数组成员当作可独立寻址的 quota 对象。
请求上下文仅在 metadata 中记录；本次响应没有 route/alias/tenant 回显，不能声称原生身份已回显。
如果后续响应出现相矛盾的回显则拒绝。

必须保留 dynamicQuotas/staticQuotas 两数组及成员次序、重复项、空 quotaId、嵌套日期和精度。
缺失或畸形组件不能补成空数组并称完整。原生 count=0 与非空数组并存，不能作为额度总数。
缓存按租户、routeId、aliasName 的精确组合隔离；不推断全局路由配置、全账户覆盖或每项独立身份。

## 剩余资格化门槛

| Getter | 本次复核边界 | 恢复所需证据 |
| --- | --- | --- |
| investment interest-rates | wrapper 1514937、映射 1560013 仅 base-rate list/reference | 同粒度独立原生 getter、日期/版本及身份 |
| investment benchmarks | 列表 wrappers 1519108/1519697，modal 9386733 复制行 | 投资 benchmark 独立详情、复合身份，不能借风险 benchmark |
| rules funding | wrappers 1499757，loaders 6478971/6489820 从 URL 取 module/iteration | 原生有效 moduleId+iterationId 父行或可靠映射；不猜旧 id |
| rules action-mapping | modal 4545570 复制字段 | 独立原生 mapping 详情及身份 |
| rules fx-settlement | modal 5665322 复制行 | 同配置粒度 getter；交易/余额不替代 |
| rules forecast | modal 4300126 复制规则 | 规则定义 getter；任务/结果/准确率不替代 |
| pricing factors | wrapper 1500487/1500550 为类型参数及日期值列表 | 区分定义/日期值粒度，独立精确身份 |
| pricing strategies | 5459697 从 pricingStrategyVOList 选行；5467115 读取辅助环境 | 独立策略详情及版本语义 |
| ledger accounts | JSON POST wrapper 1512134、loader 5120744；此前真实请求 404 | 部署路径修正或来源证明的替代调用；不重放 404/猜前缀 |
| reference banks | modal 4342283 复制行；query/select wrappers | 银行对象独立 getter；账户基线/余额不替代 |
| reference calendars | modal 3107808 复制 year/dayInfoList | 日历+年份原生身份、日期组成覆盖 |
| reference entities | modal 5577087 复制行 | 独立对象与 instId/instCode/entityCode 类型绑定 |

这十二项没有发送业务请求，没有创建推测实施票。cash accounts、swaps、client prices
及 monitoring HOLD 不在本轮范围内。

## 实施验收

资格化原生查询已通过；公共 CLI 生产 UAT、本地测试和最终审查将在实现后单独记录。
本轮不自动触发 Greptile，也不发布新版本或合并 PR。
