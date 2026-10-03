# Liquidity v0.2.3 完整 CLI UAT

Observed: 2026-10-03
Scope: general
Status: snapshot

## 结论与范围

本轮重新执行全部 **68 个可执行叶子（46 list、22 detail/history）**：**62 PASS，1 EMPTY，4 PARTIAL，1 BLOCKED，0 NOT_ATTEMPTED**。另对全部 **65 个 DEFERRED** 叶子验证帮助和断开浏览器后的非执行拒绝。设计总数为 **133**。
按用户认可的带告警返回口径，所选真实范围的普通 live 有 **67 个可服务叶子**；未通过普通 live 服务的可执行叶子为 **1**，加上 65 个延期叶子，当前设计中未能提供已验服务的项目为 **66**。服务可用不等于完整采集、缓存发布或所有生产范围通过。
规格依据 [Issue #76](https://github.com/proletariat64/dogopencli/issues/76) 和 [v0.2.3 规格](../../design/liquidity-v0.2.3.md)。源码包版本为 **0.2.3**；本轮验收不是已发布版本或已合并 PR 的证明。
PR 比较基线：`master` / `9acb60a1ad47dd0abee302a2b665906dce68cd79`；验收时 feature HEAD：`a01562075f31eab50224fb35eea1de0cd27867f8`，另含未提交实现。HEAD 不是全部验收源码身份；私有 source manifest 记录实际源文件指纹，最终 PR 提交在文档生成后另行记录。
真实业务观测窗口（UTC）：`2026-10-03T02:20:43.617345+00:00` 至 `2026-10-03T03:22:09.434805+00:00`。范围日期来自已验证的原生查询，不由报告日期推断。本轮共 **53 个 list 范围、23 个 detail/history 范围**，每个范围均有 live、refresh、断开浏览器的 offline 结果。

## 方法与保护边界

复用实际 Liquidity CDP 9222 登录会话和未经替换的产品只读传输，预检确认 authenticated/healthy。未启动、切换或修复 Chrome。独立配置仅改变本地缓存路径；真实业务请求未使用假响应、伪造身份、任意 JavaScript 或非白名单端点。
普通 list 验收使用 `--live --all`，然后显式 refresh 和匹配的断开浏览器 `--all`；发生 INCOMPLETE_RESULT 的普通 live 另执行 `--require-complete`。详情使用真实原生身份、独立详情 refresh 和 offline；详情前置 CACHE_MISS 证明没有用 list 行冒充 native detail。
审计重新解析每个私有 CLI 原始 envelope，与 state 对照退出码、complete/source/CDP/non-simulated 元数据、数量、错误码、缓存保护、refresh/offline snapshot 一致性。snapshot 身份相同不要求前一独立 live 观测与 refresh 内容完全相同。
正式配置 unchanged：**True**；正式缓存及数据库 sidecars unchanged：**True**；原浏览器/来源环境 unchanged：**True**。所有 offline 与延期拒绝均记录 0 次浏览器工厂调用；失败 refresh 保持私有逻辑缓存不变。首次 cash accounts offline 的新 SQLite 从不存在变为两个空表，只初始化 schema；原始 cache_unchanged=false 如实保留，独立原生 Cache 初始化指纹与其 after 完全一致、records/snapshots 均为 0，仅此一处允许 schema 初始化，不能推广为业务缓存修改豁免。其他 live、offline、strict 查询均保持私有逻辑缓存不变。真实业务操作均为 inquiry-only；refresh 只写独立本地缓存。

本轮主路径顺序验收 list；`details-worker` 验收全部 22 个 native detail/history。两者使用产品 CLI 和真实只读源，只隔离本地配置中的 cache.path；没有替换产品响应。若在本轮发现并修正持仓缓存问题，最终持仓结果来自单独的 `holdings-worker` 复验，源码变化和该第三路径另述。
详情路径开始时，通过 SQLite 只读 source backup 复制已完成的真实 list 缓存：17 snapshots、1048 records。这是当时已完成 list 范围的真实缓存，不宣称全部详情 identity 都存在对应 list 行。前置 CACHE_MISS 仅证明详情 namespace 独立。
最终私有缓存表计数：主路径 {"records": 18834, "snapshots": 92}；详情路径 {"records": 1071, "snapshots": 39}。详情 raw CLI 在主路径全部 list 完成后按原文件复制合并；审计核对与详情 worker 原文件逐字节一致。主路径缓存只持有 list，详情缓存保留其真实种子加独立详情。
产品源码 manifest 覆盖 80 个文件；details bootstrap manifest 指纹 `7138af2e1d64ca3d949a1f43d26151f872803569e0dc4b377f2acb098dcb1769`，最终 manifest 指纹 `9b3627b1eecc19e0786c6ced1144cc39bf87adab2df7d6dca673d051a3e007e6`。bootstrap 至审计 unchanged=False；发生变更时必须逐文件核对 source-transition 的准确 before/after 哈希及限定影响，不能把旧源码执行当作所有新源码都已运行。
验收脚本的 schema 初始化和 history 文档计数误报只作证据支持的归一化；原始 CLI 及退出码保留，不修改产品行为。归一化日志：`tmp/full-liquidity-cli-uat-20261003T021011Z/audit-normalizations.json`, `tmp/full-liquidity-cli-uat-20261003T021011Z/details-worker/detail-audit-corrections.json`。

### 持仓缓存修正与独立复验

完整 UAT 暴露 investment holdings 原先 DATE/valueDate 缓存过滤语义错误：native 按 --date 获取的持仓完整记录，与行 valueDate 过滤后离线保留的数量不一致。原始失败结果保留，没有改写为成功。
修正前原始数量：live: returned_count=1078, reported_total=1078, code=0; offline: returned_count=1, reported_total=1078, code=0; refresh: returned_count=1078, reported_total=1078, code=0。CLI 原始成功退出不能替代 refresh/offline 数量一致性验收。
本轮仅将 holdings 使用现有 PROFILE_HISTORY，并把 --date 保留为原生请求与缓存 scope key；不再用行 valueDate 对该日期快照二次过滤。原生 pageSize 仍为 500，返回数量、原生身份及完整性检查保持原有要求。该改动修正缓存服务语义，不能由前述脚本误报归一化代替。
限定源变化：`src/dogopencli/plugins/liquidity/leaves.py`。准确 bootstrap/final 哈希核对通过：True；详情路径影响说明：Only the holdings list descriptor changed; detail contracts and transports are identical.。其他当前叶子的 source contract 不因本次持仓 scope 修正变化，详情路径结果保留其实际执行源码证据。
独立源码边界证明记录：反向还原唯一持仓 descriptor 可重现 bootstrap SHA；descriptor 外 AST 与两份 detail declarations 相等，另 79 个产品源文件逐字节相同。该证明不替代持仓真实复验。
第三路径 `tmp/full-liquidity-cli-uat-20261003T021011Z/holdings-worker` 使用全新空缓存与独立配置，按同一真实 native scope 执行 live、refresh、disconnected offline；最终状态 **PASS**。缓存最终计数 {"records": 1079, "snapshots": 2}；最终 raw 与该 worker 原文件逐字节一致。原失败 record/raw 位于 `tmp/full-liquidity-cli-uat-20261003T021011Z/pre-fix-holdings`，主路径旧缓存包含修正前持仓 capture，最终持仓验收依据第三路径缓存，不将两者混同。

### Credit-lines 来源波动与限定重试

credit-lines 首次普通 live 为 83/84、INCOMPLETE_RESULT，之后独立 strict live 为 84/84、complete=true；首次 refresh BUSINESS_QUERY_FAILED，随后 offline CACHE_MISS。各次原生观测反映来源波动，既不把第一次可用警告改成成功，也不归一化后端 total。
仅重试失败 refresh 及依赖的 offline；复用同一主路径配置、缓存和未经改变的产品源码。普通 live 与 strict 原始文件、结果不变，原失败 refresh/offline 和 record 单独保留。该重试没有增加缓存 worker 路径，也不构成整轮重做。
最终路由状态 **PARTIAL**。私有限定重试证据 `tmp/full-liquidity-cli-uat-20261003T021011Z/retry-evidence.json` 核对原/新 raw SHA、相同参数、严格时间先后、相同配置/缓存和源文件指纹。

- refresh: 原 BUSINESS_QUERY_FAILED，exit=1，时间 `2026-10-03T03:14:27.603219+00:00`；重试 OK，exit=0，returned=84/reported=84，时间 `2026-10-03T03:22:05.428913+00:00`。
- offline: 原 CACHE_MISS，exit=1，时间 `2026-10-03T03:14:30.134158+00:00`；重试 OK，exit=0，returned=84/reported=84，时间 `2026-10-03T03:22:09.434805+00:00`。

完整重试 refresh 可以发布自身 capture，offline 仅服务该完整 snapshot；若重试继续硬失败，保留 BLOCKED 和原缓存。普通 live 最早的 83/84 警告继续保留，因此后来成功不把这一路由全模式涂绿。

## 模式汇总

| 模式 | 按实际范围统计的结果 |
| --- | --- |
| live | BUSINESS_QUERY_FAILED: 2; INCOMPLETE_RESULT: 4; OK: 70 |
| refresh | BUSINESS_QUERY_FAILED: 2; INCOMPLETE_RESULT: 3; OK: 71 |
| offline | CACHE_MISS: 5; OK: 71 |

额外 strict 验收 **4** 次：`liquidity cash accounts list`: INCOMPLETE_RESULT, exit=1, data=withheld；`liquidity investment returns list`: INCOMPLETE_RESULT, exit=1, data=withheld；`liquidity cash credit-lines list`: OK, exit=0, data=present；`liquidity forecast results list`: INCOMPLETE_RESULT, exit=1, data=withheld

## 逐项三模式结果

数量是 CLI 实际返回数量和该次源端 total，未统一或修正后端 count。日期、变体和参数名可公开；原生账号与 detail identity 只保留私有证据。多范围叶子取最严格状态。

| 叶子 | 范围 / 原生 pageSize | live | refresh | offline | 状态 |
| --- | --- | --- | --- | --- | --- |
| `liquidity cash accounts list` | scope 1: default native scope; pageSize=5000 | WARN 3690/3691 | WARN 3690/3691 | CACHE_MISS | PARTIAL |
| `liquidity cash balances list` | scope 1: --entity=<native>, --timezone=GMT+08; pageSize=30 | OK 12/12 | OK 12/12 | OK 12/12 | PASS |
| `liquidity cash credit-lines list` | scope 1: default native scope; pageSize=100 | WARN 83/84 | OK 84/84 | OK 84/84 | PARTIAL |
| `liquidity cash group-balances list` | scope 1: --equi-currency=<native>; pageSize=100 | OK 1/1 | OK 1/1 | OK 1/1 | PASS |
| `liquidity cash groups list` | scope 1: --equi-currency=<native>; pageSize=100 | OK 1/1 | OK 1/1 | OK 1/1 | PASS |
| `liquidity cash pools get` | scope 1: --pool-id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity cash pools get` | scope 2: --pool-id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity cash pools list` | scope 1: default native scope; pageSize=100 | OK 43/43 | OK 43/43 | OK 43/43 | PASS |
| `liquidity cash statements end-of-day list` | scope 1: --entity=<native>, --account=<native>, --currency=<native>, --timezone=GMT+08, --from=20260930, --to=20260930; pageSize=1000 | OK 6/6 | OK 6/6 | OK 6/6 | PASS |
| `liquidity cash statements end-of-day list` | scope 2: --entity=<native>, --account=<native>, --currency=<native>, --timezone=GMT+08, --from=20260930, --to=20260930; pageSize=1000 | OK 0/0 | OK 0/0 | OK 0/0 | PASS |
| `liquidity cash statements intraday list` | scope 1: --account=<native>, --currency=<native>, --inst-id=<native>, --timezone=GMT+08, --from-date=20260930, --to-date=20260930; pageSize=1000 | OK 5/5 | OK 5/5 | OK 5/5 | PASS |
| `liquidity cash waterlevels list` | scope 1: --account=<native>; pageSize=1000 | OK 1/1 | OK 1/1 | OK 1/1 | PASS |
| `liquidity forecast adjustments list` | scope 1: default native scope; pageSize=1000 | OK 13/13 | OK 13/13 | OK 13/13 | PASS |
| `liquidity forecast cashflows list` | scope 1: --inst-id=<native>, --account=<native>, --currency=<native>, --from-date=20260930, --to-date=20260930; pageSize=10 | OK 1/1 | OK 1/1 | OK 1/1 | PASS |
| `liquidity forecast results list` | scope 1: --from=20261002, --to=20261002, --record-from-time=000000, --record-to-time=235959, --account=<native>; pageSize=5000 | OK 6/6 | OK 6/6 | OK 6/6 | PARTIAL |
| `liquidity forecast results list` | scope 2: --from=20261001, --to=20261001, --record-from-time=000000, --record-to-time=235959; pageSize=5000 | WARN 22273/22276 | WARN 22273/22276 | CACHE_MISS | PARTIAL |
| `liquidity investment benchmarks list` | scope 1: default native scope; pageSize=5000 | OK 50/50 | OK 50/50 | OK 50/50 | PASS |
| `liquidity investment compound-ledger get` | scope 1: --order-no=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity investment compound-ledger list` | scope 1: default native scope; pageSize=10 | OK 16/16 | OK 16/16 | OK 16/16 | PASS |
| `liquidity investment holdings get` | scope 1: --investment-no=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity investment holdings list` | scope 1: --date=20261001; pageSize=500 | OK 1078/1078 | OK 1078/1078 | OK 1078/1078 | PASS |
| `liquidity investment interest-rates list` | scope 1: --source=market, --timezone=GMT+08, --from-date=20261001, --to-date=20261001; pageSize=10 | OK 139/139 | OK 139/139 | OK 139/139 | PASS |
| `liquidity investment products get` | scope 1: --product-id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity investment products history` | scope 1: --product-code=<native> | OK 1 | OK 1 | OK 1 | EMPTY |
| `liquidity investment products list` | scope 1: default native scope; pageSize=10 | OK 908/908 | OK 908/908 | OK 908/908 | PASS |
| `liquidity investment returns list` | scope 1: --basis=accrual, --timezone=GMT+08, --from-date=20260930, --to-date=20260930; pageSize=5000 | OK 1232/1232 | OK 1232/1232 | OK 1232/1232 | PARTIAL |
| `liquidity investment returns list` | scope 2: --basis=cash, --timezone=GMT+08, --from-date=20260930, --to-date=20260930; pageSize=5000 | WARN 595/662 | WARN 595/662 | CACHE_MISS | PARTIAL |
| `liquidity investment strategies get` | scope 1: --strategy-rule-code=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity investment strategies list` | scope 1: default native scope; pageSize=10 | OK 2/2 | OK 2/2 | OK 2/2 | PASS |
| `liquidity investment transactions get` | scope 1: --order-id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity investment transactions list` | scope 1: default native scope; pageSize=5000 | OK 2241/2241 | OK 2241/2241 | OK 2241/2241 | PASS |
| `liquidity ledger accounts list` | scope 1: --book-type=<native>; pageSize=5000 | OK 105/105 | OK 105/105 | OK 105/105 | PASS |
| `liquidity ledger accounts list` | scope 2: --book-type=<native>; pageSize=5000 | OK 2620/2620 | OK 2620/2620 | OK 2620/2620 | PASS |
| `liquidity ledger balances list` | scope 1: --book-type=<native>, --timezone=GMT+08, --from-date=20260929, --to-date=20260929; pageSize=10 | BUSINESS_QUERY_FAILED | BUSINESS_QUERY_FAILED | CACHE_MISS | BLOCKED |
| `liquidity ledger balances list` | scope 2: --book-type=<native>, --timezone=GMT+08, --from-date=20260929, --to-date=20260929; pageSize=10 | BUSINESS_QUERY_FAILED | BUSINESS_QUERY_FAILED | CACHE_MISS | BLOCKED |
| `liquidity ledger customers get` | scope 1: --customer-no=<native>, --version=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity ledger customers list` | scope 1: default native scope; pageSize=10 | OK 8/8 | OK 8/8 | OK 8/8 | PASS |
| `liquidity network account-capabilities get` | scope 1: --id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity network account-capabilities list` | scope 1: default native scope; pageSize=10 | OK 29/29 | OK 29/29 | OK 29/29 | PASS |
| `liquidity network bank-baselines get` | scope 1: --account=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity network bank-baselines list` | scope 1: default native scope; pageSize=10 | OK 3690/3690 | OK 3690/3690 | OK 3690/3690 | PASS |
| `liquidity operations asset-trades list` | scope 1: --timezone=GMT+08, --from-date=20260930, --to-date=20260930; pageSize=10 | OK 2/2 | OK 2/2 | OK 2/2 | PASS |
| `liquidity operations decisions get` | scope 1: --id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity operations decisions history` | scope 1: --id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity operations forwards get` | scope 1: --order-no=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity operations forwards list` | scope 1: default native scope; pageSize=10 | OK 17/17 | OK 17/17 | OK 17/17 | PASS |
| `liquidity operations prefunds get` | scope 1: --id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity operations prefunds list` | scope 1: --status=APPROVED, --status=CLOSED; pageSize=10 | OK 70/70 | OK 70/70 | OK 70/70 | PASS |
| `liquidity operations prefunds list` | scope 2: --status=SUBMITTED, --status=REJECTED, --status=CLOSED_SUBMITTED; pageSize=10 | OK 22/22 | OK 22/22 | OK 22/22 | PASS |
| `liquidity operations transfers get` | scope 1: --order-no=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity pricing client-prices list` | scope 1: --from-date=20260930, --to-date=20260930; pageSize=10 | OK 39/39 | OK 39/39 | OK 39/39 | PASS |
| `liquidity pricing cost-prices list` | scope 1: --from-date=20260930, --to-date=20260930; pageSize=10 | OK 800/800 | OK 800/800 | OK 800/800 | PASS |
| `liquidity pricing factor-values list` | scope 1: --from-date=20260930, --to-date=20260930; pageSize=10 | OK 1431/1431 | OK 1431/1431 | OK 1431/1431 | PASS |
| `liquidity pricing strategies list` | scope 1: default native scope; pageSize=10 | OK 78/78 | OK 78/78 | OK 78/78 | PASS |
| `liquidity reference banks list` | scope 1: default native scope; pageSize=5000 | OK 928/928 | OK 928/928 | OK 928/928 | PASS |
| `liquidity reference business-lines list` | scope 1: default native scope; pageSize=5000 | OK 335/335 | OK 335/335 | OK 335/335 | PASS |
| `liquidity reference calendars list` | scope 1: default native scope; pageSize=10 | OK 270/270 | OK 270/270 | OK 270/270 | PASS |
| `liquidity reference entities list` | scope 1: default native scope; pageSize=5000 | OK 71/71 | OK 71/71 | OK 71/71 | PASS |
| `liquidity risk metrics list` | scope 1: --metric=CONCENTRATION_RATE; pageSize=10 | OK 96/96 | OK 96/96 | OK 96/96 | PASS |
| `liquidity risk metrics list` | scope 2: --metric=CREDIT_USAGE_RATE; pageSize=10 | OK 92/92 | OK 92/92 | OK 92/92 | PASS |
| `liquidity risk sla get` | scope 1: --sla-config-id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity risk thresholds get` | scope 1: --benchmark-id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity risk thresholds list` | scope 1: default native scope; pageSize=10 | OK 21/21 | OK 21/21 | OK 21/21 | PASS |
| `liquidity rules action-mapping list` | scope 1: default native scope; pageSize=10 | OK 225/225 | OK 225/225 | OK 225/225 | PASS |
| `liquidity rules forecast list` | scope 1: default native scope; pageSize=10 | OK 4/4 | OK 4/4 | OK 4/4 | PASS |
| `liquidity rules funding list` | scope 1: default native scope; pageSize=5000 | OK 123/123 | OK 123/123 | OK 123/123 | PASS |
| `liquidity rules fx-settlement list` | scope 1: default native scope; pageSize=5000 | OK 1071/1071 | OK 1071/1071 | OK 1071/1071 | PASS |
| `liquidity rules notification get` | scope 1: --id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity rules notification list` | scope 1: default native scope; pageSize=10 | OK 17/17 | OK 17/17 | OK 17/17 | PASS |
| `liquidity rules operation get` | scope 1: --rule-id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity rules operation list` | scope 1: default native scope; pageSize=10 | OK 235/235 | OK 235/235 | OK 235/235 | PASS |
| `liquidity rules realtime get` | scope 1: --id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity rules realtime list` | scope 1: default native scope; pageSize=10 | OK 15/15 | OK 15/15 | OK 15/15 | PASS |
| `liquidity rules transfer get` | scope 1: --rule-id=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity rules waterlevel get` | scope 1: --account=<native> | OK 1 | OK 1 | OK 1 | PASS |
| `liquidity rules waterlevel list` | scope 1: default native scope; pageSize=5000 | OK 533/533 | OK 533/533 | OK 533/533 | PASS |

## 原生详情与历史文档

22 个 detail/history 路由分别证明独立缓存前置 CACHE_MISS；普通详情数量代表一个原生文档，不能把嵌套数组长度当成详情文档数量。native history=[] 或 detail={} 在三模式完整读取时标 EMPTY，文档数量仍为 1。历史版本内容和谱系由真实原生合同解析，不由当前 list 行拼装。refresh envelope 仅显示发布文档数量；未暴露的内部数组数量不推断。

| 历史路由 | live 文档内部数组数量 | refresh 文档内部数组数量 | offline 文档内部数组数量 |
| --- | --- | --- | --- |
| `liquidity operations decisions history` | 1 | no top-level arrays | 1 |
| `liquidity investment products history` | 0 | no top-level arrays | 0 |

## 不完整与阻塞的实际边界

INCOMPLETE_RESULT 的 ordinary live 保留可用 data、complete=false 和退出码 1；严格查询不暴露不完整 data。不完整 refresh 返回可用证据并保留旧缓存，不发布新的完整 capture；相应新范围 offline 可出现 CACHE_MISS，不能当成业务无数据。后续独立 refresh 若完整通过，则可以发布该次完整 capture；不能把一次 incomplete 延伸为永久无法发布。PARTIAL 仍用黄色标注。
INVALID_RESPONSE（例如跨页 total 变化或冲突身份）继续拒绝返回 data；带告警兼容不绕过结构或身份不一致。
已知 ledger balances 原生 errorCode 999 和特定分页偏移的调查见 [先前验收](2026-10-02-liquidity-inherited-cli-uat.md)；本轮下面逐项记录实际结果，未把历史结论代替本轮验收。

- `liquidity cash accounts list`: **PARTIAL**；scope 1 live=WARN 3690/3691, refresh=WARN 3690/3691, offline=CACHE_MISS。
- `liquidity cash credit-lines list`: **PARTIAL**；scope 1 live=WARN 83/84, refresh=OK 84/84, offline=OK 84/84。
- `liquidity forecast results list`: **PARTIAL**；scope 1 live=OK 6/6, refresh=OK 6/6, offline=OK 6/6; scope 2 live=WARN 22273/22276, refresh=WARN 22273/22276, offline=CACHE_MISS。
- `liquidity investment returns list`: **PARTIAL**；scope 1 live=OK 1232/1232, refresh=OK 1232/1232, offline=OK 1232/1232; scope 2 live=WARN 595/662, refresh=WARN 595/662, offline=CACHE_MISS。
- `liquidity ledger balances list`: **BLOCKED**；scope 1 live=BUSINESS_QUERY_FAILED, refresh=BUSINESS_QUERY_FAILED, offline=CACHE_MISS; scope 2 live=BUSINESS_QUERY_FAILED, refresh=BUSINESS_QUERY_FAILED, offline=CACHE_MISS。

## 延期能力的非执行验证

65 个 DEFERRED 叶子均帮助可发现、执行返回 UNSUPPORTED_CAPABILITY，断开浏览器工厂调用为 0，缓存未改变。这是保护边界验证，不能算生产查询通过。

| 域 | DEFERRED 路由 |
| --- | --- |
| cash | `accounts get`, `credit-usage list`, `pool-balances list`, `wallet-balances list`, `wallets get`, `wallets list` |
| forecast | `accuracy list` |
| investment | `benchmark-values list`, `benchmarks get`, `interest-rates get`, `investable-funds list`, `offers list`, `quote-groups get`, `quote-groups list`, `quote-sessions list`, `quotes get`, `quotes list`, `rfqs get`, `rfqs list`, `strategy-results get`, `strategy-results list` |
| ledger | `accounts get` |
| network | `product-baselines get`, `product-baselines list`, `realtime get`, `realtime list`, `routes get`, `routes list` |
| operations | `asset-trades get`, `decisions list`, `demands get`, `demands list`, `executions get`, `executions list`, `rule-status list`, `swaps get`, `swaps list`, `transfers list` |
| pricing | `bills get`, `bills list`, `client-prices get`, `factors get`, `factors list`, `strategies get`, `valuations get`, `valuations list` |
| reference | `areas list`, `banks get`, `calendars get`, `entities get` |
| risk | `account-capacity list`, `anomalies get`, `anomalies list`, `events get`, `events list`, `sla list` |
| rules | `action-mapping get`, `forecast get`, `funding get`, `fx-settlement get`, `monitoring get`, `monitoring list`, `transfer list`, `treasury-transfer get`, `treasury-transfer list` |

## 先前历史探查与当前验收

用户先前指定的十个 2026 年历史日期（09-30、09-28、08-13、07-03、06-05、05-20、04-02、03-08、02-21、01-07）forecast 查询是独立历史证据，不计入本轮 fresh UAT 数量。先前全部查询日期匹配 valueDate，跨页 total 稳定；8 天因跨页重复带告警，2 天单页完整成功。不能据此证明连续历史覆盖或最早保留日期。
完整地图包含全部 133 项：[本轮地图](../../assets/general/2026-10-03-liquidity-full-cli-uat-roadmap.svg)。用户原来的地图入口也更新为本轮完整结果：[原地图入口](../../assets/general/2026-10-02-liquidity-inherited-cli-uat-roadmap.svg)。[10 月 2 日报告](2026-10-02-liquidity-inherited-cli-uat.md)保留历史口径，不改写成 fresh 本轮结果。

## 本地验证与证据

- Full-suite baseline phase: PASS；1600 passed, 28 subtests passed; phase evidence only, source/test changes during execution: 7; final affected behavior checked separately。
- Final source-stable focused gates: PASS；325 passed; all source/test hashes unchanged and match current worktree。
- ruff-check: PASS；All checks passed!。
- ruff-format-check: PASS；234 files already formatted。
- version: PASS；dogopencli 0.2.3。
- Independent v0.2.3 wheel verification: PASS；Built wheel version, CLI discovery, 46/22/65 catalog and holdings history/page500 verified; no installation or downloads。
- Documentation guard: PASS；91 Markdown files passed。
- SVG and rendered roadmap review: PASS；133 leaf rows, valid SVG, identical original map alias; all status colors and readable rows checked。

私有原始 CLI、state、配置/缓存指纹和审计位于 `tmp/full-liquidity-cli-uat-20261003T021011Z/`；受保护原始业务响应和身份未进入本文或 Git。`acceptance-audit.json` 是重新解析原始 CLI 后的脱敏汇总。
本轮完整指全部当前可执行叶子及其选定范围均实际尝试；不是所有账号、日期、生产分区或未来来源稳定性的全覆盖。DEFERRED 和 BLOCKED 保持明确，空结果只证明所选范围为空。
