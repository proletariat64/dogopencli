# Handoff: FX 后台背景与 dogopencli FX 查询插件目标

Observed: 2026-09-09
Scope: general
Status: snapshot

日期:2026-09-09。读者:接手 dogopencli FX 插件(设置/数据查询)的工程师或 Agent。
这不是已批准配置或操作手册;所有在线操作只读。

## 1. 背景:FX 平台与 weblink

### 1.1 环境入口

| 项 | 值 |
| --- | --- |
| SIM origin(唯一允许) | `https://app-ipay-qk-sim.alipay.com` |
| 认证 | Chrome 人工 SSO,认证保留在浏览器;不导出 cookies/token/headers |
| CDP 端口 | 建议 `9222`;`9330–9340` 全部禁用 |
| 主生产地址 | 不访问 |

归属立场查询页面与应用:

- **Arrow(A+ 外汇)** — `/arr/`,报价方案(QUOTE_SCHEME)的 BCode 定义、报价规则、报价策略所在前端。
  - 源报价查询:`/arr/querySourceRate`
  - 策略获取规则与偏离:`/arr/load-strategy`、`/arr/sourceMonitorAndDeviation`
- **Blade(Book 与交易)** — `/bladeweb/`,如 Trade Profile 查询 `/bladeweb/TradeProfileIdList`。
- **标准发布平台(changemng)** — `sourceFrom: ifxchangemng`,承载迭代/模块的审批与分阶段发布。

### 1.2 后端 API(已在 SIM 观测;Facade hash 后缀是构建产物,会变)

读写配置 POST `/arr/api/function/...`(transport envelope `{"requestData":[payload]}`):
`IfxBcodeDefinitionMngFacade`(create/updateBcodeDefinition)、`IfxQuoteRuleMngFacade`(create/updateQuoteRuleList)、`IfxQuoteStrategyMngFacade`(strategy base/detail/batch + preValidate)。
文档来源:`~/dev/dogfxwizard/docs/fx-quote-scheme/backend-api-map.md`。

生命周期 API POST `/changemng/api/function/...`:
`IterationFacade.queryIterationDetailById`、`IfxConfigGraphFacade.checkEmptyModule`、`IterationFacade.submitApproval`、`IterationFacade.publish`、`ModuleFacade.publish`。
迭代状态机:`EDIT → APPROVAL → TRIAL_EDIT → DEV → SIT → PRE → GREY → PROD → WAIT → FINISH`。

证据与抓包副本(仓库外):`~/dev/dogfamily/fxquote-investigation/`。

### 1.3 领域骨架(引用 dogfxwizard 文档,标注 K/O/G 证据强度)

来源:`~/dev/dogfxwizard/docs/fx-quote-scheme/fx-e2e-architecture.md`(架构基线)与
`fx-e2e-exploration.md`(SIM 跨模块补证执行记录,2026-09-07)。

- 领域链:**机构源报价 → 行情与报价(Arrow/Lego/MP/BCode)→ 对客配置(Profile/合约)→ 代客交易 → Book 与策略(CB→AB→HB)→ 预测虚转实(预测类)→ 平盘配置 → 机构执行 → 资金交割(SSI/银存)→ 损益估值 → 核算对账**。
- 必须保持的边界:报价源 ≠ 报价方案 ≠ 报价结果;Arrow BCode ≠ 所有场景业务 code ≠ ProfileID ≠ 合约号;交易策略 ≠ 平盘策略 ≠ 调度任务;Book ≠ 交割账户 ≠ 核算内部户。
- 证据状态:报价侧和部分 Book/策略有 SIM 查询证据(O);客户绑定→渠道执行→资金交割→核算的同一场景闭环**尚未闭合**(G)。查得到配置 ≠ 业务闭环。

### 1.4 现有工具分工(本 handoff 的决策背景)

- **~/dev/dogfxwizard**(fxwizard CLI):review-first **写入**工具,仅针对标准发布平台进入的 QUOTE_SCHEME 模块(BCode + 报价规则 + 报价策略)。dry-run 默认;写需要 `--execute` + `--confirm` 指纹;一次只做一次生命周期迁移。已有子命令 `init/validate/report/plan/status/options/apply/activate/snapshot-review`。
- **~/dev/dogopencli**:只读查询 CLI(payment/collection 插件),已有 login/auth、专用 Chrome CDP 会话、本地缓存 + `refresh`、`--require-fresh/--require-complete`、`--live`、catalog/describe/helptree(JSON 帮助)。
- **已定决策**:FX 的设置/数据**查询**做在 dogopencli 里(新 `fx` 插件),不往 dogfxwizard 添加运营查询子命令;dogfxwizard 保留 apply 流程自带的 `status`/`options` 前置只读检查。dogopencli 缓存的 FX 快照未来可被 dogfxwizard review/plan 复用做只读对照。

## 2. 目标:dogopencli FX 插件(设置/数据查询)

### 2.1 形态

仿照现有 `plugins/payment`、`plugins/collection` 新增 `plugins/fx`;`~/.config/dogopencli/config.toml` 按能力声明来源(如 `[sources.fx_quote_scheme] kind = "cdp"`)。

建议命令骨架(最终命名实现时定):

```
dogopencli fx bcode list [--live]
dogopencli fx quote-rule list --module-code ...
dogopencli fx strategy list ...
dogopencli fx source-rate list ...      # /arr/querySourceRate
dogopencli fx trade-profile list ...    # /bladeweb/TradeProfileIdList
dogopencli fx iteration show <id>       # IterationFacade.queryIterationDetailById(只读)
```

### 2.2 硬性边界

1. **只查询**:不推进业务状态,不发审批/发布/启用。上下文里的 ARR 写接口仅作字段参考,绝不调用。
2. **只打 SIM**:`https://app-ipay-qk-sim.alipay.com`,不碰主生产;CDP 端口禁用整个 9330–9340 范围。
3. **认证不出浏览器**:复用 dogopencli login/auth 基建;不导出 cookies/token/headers。
4. **保留后端原生字段名**和原生键(iterationId/moduleId/BCode 等),不做同名字段自动合并(领域边界 #1)。
5. 查询录缓存;穿透查询须显式 `--live`;失败/过期/不完整由 `--require-fresh/--require-complete` 报错,不静默降级。
6. 结果对 Agent 友好:走 catalog/describe 约定,键、类型、状态原样输出。

### 2.3 建议迭代范围

- **第一批(证据已足)**:BCode 定义、报价规则、报价策略(QUOTE_SCHEME 域,iteration/module 关联);迭代详情叠加只读查询(`queryIterationDetailById` 有的放矢);源报价(`querySourceRate`)。
- **第二批**(沿用 fx-e2e-exploration 的 P2 补证):LP/渠道、trade profile、获取规则与偏离监控(`load-strategy`/`sourceMonitorAndDeviation`)。
- **暂缓**:资金交割/核算/损益链(KPf 缺口未闭合,先推进探索记录,不做查询接口)。

### 2.4 起点材料

| 材料 | 路径 |
| --- | --- |
| 后端 API 图(ARR+changemng,含 payload) | `~/dev/dogfxwizard/docs/fx-quote-scheme/backend-api-map.md` |
| 架构基线与领域边界 | `~/dev/dogfxwizard/docs/fx-quote-scheme/fx-e2e-architecture.md` |
| SIM 跨模块查询入口记录 | `~/dev/dogfxwizard/docs/fx-quote-scheme/fx-e2e-exploration.md` |
| 配置字段语义(QUOTE_SCHEME profile) | `~/dev/dogfxwizard/docs/fx-quote-scheme/configuration-reference.md` |
| 只读快照约定 | `~/dev/dogfxwizard/docs/fx-quote-scheme/readonly-snapshot.md` |
| 原始抓包/前端源码 | `~/dev/dogfamily/fxquote-investigation/` |
| dogopencli 能力模型 ADR | `~/dev/dogopencli/docs/adr/0001-query-capability-model.md` |

2026-10-01 整理说明:按仓库规范补齐快照元数据和文件位置,并将历史 CDP 建议修正为
`9222`,明确禁用 `9330–9340`。本次未重新验证 2026-09-09 的 SIM 观察或接口契约。
