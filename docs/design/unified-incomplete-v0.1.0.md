# 统一 incomplete 架构规格 v0.1.0

日期：2026-10-03（Asia/Shanghai）。状态：当前 feature branch 已完成实施与离线验收；Greptile CLI 及 PR 前双轴审查通过，尚未发布或执行新策略的生产 UAT。
规格版本独立于 Python 包版本。实施工作树：`refact-incomplete-unify-process`。
权威规格：[GitHub Issue #78](https://github.com/proletariat64/dogopencli/issues/78)。本文件为仓库阅读副本。

## 目标与业务原则

面向 DI 与 AI 数据分析，经过验证的部分数据仍有使用价值。默认 refresh 可以发布不完整缓存，默认 live 和离线读取可以返回其中的真实数据；每次输出都说明不完整、原因与可量化缺口。完整性是覆盖证明，不能因允许使用而改写为 true。

这项原则适用于已验证能力的安全覆盖缺口，不限定“缺失少于 1%”之类未经选择的阈值。不能从少数历史样例断言所有缺口都很小。严格调用者显式使用 `--require-complete`；格式、scope、身份和业务一致性失效仍属于硬失败。

架构采用：**领域采集器提供完整性证据，公共策略决定使用与发布资格，领域存储原子提交并返回实际发布事实**。保留各能力的分页与必要业务证明；缓存读、live、refresh 使用同一质量语义。

## 对旧规格的明确修订

本规格修订 [ADR 0003](../adr/0003-local-query-snapshots.md) 的“不完整新结果不发布”、[Liquidity v0.2.3](liquidity-v0.2.3.md) 的“partial refresh 保留旧缓存”，以及原[架构研究](../research/general/2026-10-03-acquisition-compatibility-architecture.md)的“允许部分但统一退出 1”建议。

迁移后的正常 partial 是成功取得可用数据，默认 `error=null`、退出 **0**，附 `meta.warnings` 和 stderr 告警。`--require-complete` 不满足时才使用顶层 `INCOMPLETE_RESULT`、退出 **1**、不暴露业务数据；严格 refresh 不发布。[ADR 0010](../adr/0010-collection-va-partial-detail-tolerance.md) 的可容忍详情拒绝与真实性要求保留，默认部分发布后的退出码改为 0，严格模式拒绝在提交前完成。

历史 ADR 与研究报告保留其原始观察；本次取舍见 [ADR 0019](../adr/0019-usable-incomplete-acquisitions.md)。以下定义规格要求，实现状态见首行，不表示发布版本或生产验证已改变。

## 当前源码基线与研究边界

本工作树注册表经实际导入验证为 **46 个 Liquidity list 路由、47 个请求 variant**；holdings 页宽为 **500**。原报告是研究快照，当前 single-response 已同时检查原始行数与唯一行数，不再存在它描述的未修复样例，见 [single collector](../../src/dogopencli/plugins/liquidity/collect.py#L143)。必须保留这项回归。

研究时 code-review-graph 在该 root 返回 0 文件/节点，不能用于推断关系或测试覆盖；只读研究不重建索引，采用报告指向文件的定向源码核查。graphify 已查询内部知识图谱，命中历史分页/报表概念，未提供本 CLI 的直接契约证据，故不据此声称后端语义已验证。源码依据补充见[核查记录](../research/general/2026-10-03-incomplete-source-evidence.md)。研究阶段不调用生产系统、不修改业务代码、不执行生产 UAT；实施阶段已另建源码/测试图并分析影响。

## 完整性与有效性分开

候选只有通过有效性检查，才能进入公共结果策略。

| 类别 | 判定 | 默认行为 |
| --- | --- | --- |
| 完整候选 | 领域覆盖与必要组成证明成立 | 返回；refresh 可发布；退出 0 |
| 安全不完整候选 | 已返回记录合法、scope 正确、身份与内容无冲突，但覆盖不足或无充分证明 | 返回；refresh 可发布；完整性 false、原因告警；退出 0 |
| 硬失败 | 认证/权限、非法包络或字段、scope/身份回显错配、同身份内容冲突、固定 total 变化、必要稳定性失败等 | 不返回候选、不发布；真实错误码及原退出码 |

不可把任意 `CliError` 或 `INCOMPLETE_RESULT` 捕获后转为可发布 partial。只有领域显式产生的安全候选才可降级。网络中断、超时、页预算耗尽、无进展、一般业务拒绝本版继续硬失败；保留已取到的行作为正常缓存需要另行设计可信的中止证据，不在本版自动开放。

硬失败不回退旧缓存伪装 live 成功；已有缓存保持可离线读取。缓存内部损坏与来源采集缺失是两件事：存储行数与声明行数不符、解码失败、非法身份继续拒绝整个缓存，不能当成新的 safe partial。

## 分页重复的判定

去重解决重复，不自行证明覆盖。公共证据记录 `arrivals`（去重前）、`unique_count`、`duplicate_count`、真实 `reported_total` 及总数计数单位。

| 示例 | 判定与理由 |
| --- | --- |
| reported=100，arrivals=100，unique=99 | `complete=false`；少 1 个唯一对象，记录 `COUNT_SHORTFALL` 与 `DUPLICATE_ROWS` |
| reported=100，arrivals=102，unique=100，契约证明 total 计数不同原生身份、同范围遍历结束、内容无冲突、其余证明通过，声明允许同内容重复 | `complete=true`；去重后返回 100，记录 `DUPLICATE_ROWS` 告警 |
| reported=100，unique=100，但固定 total 曾变化、身份冲突或 PTR 双轮不一致 | 硬失败；数量一致不能覆盖域一致性失败 |
| reported=1，single-response 原始两行相同、unique=1，未声明重复容忍 | 保持 `complete=false`；记录 `UNEXPECTED_DUPLICATE_ROWS`，保留现有单响应回归 |
| 未报告 total | `reported_total=null`；完成证明依 single/cursor 等原生契约，不能把本地行数冒充后端 total |
| 无原生身份，合法重复行次 | 保留行次；`unique_count`、`duplicate_count` 为 null，按行次契约判断；禁止整行哈希去重 |
| reported=100，unique=101 | total 单位与契约矛盾，本版硬失败；不伪造负缺失数 |

“complete 带重复告警”必须由能力声明 `duplicate_policy=allow_identical_overlap` 且 `total_semantics=unique_objects`，并通过完整范围结束及所有域证明。未验证能力默认 `duplicate_policy=conservative`，保留现有原始数/唯一数核查；不能仅凭字段名 `id` 或 `totalCount` 开放容忍。

本版先统一处置和证据，既有端点不自动改成容忍重复。后续放行某个能力的重复容忍时，需补该能力契约、代表性多页/单页回归和相应只读 UAT 证据。重复已证实不影响覆盖的候选可以通过严格模式；有缺口的候选即使仅缺一行，也不能通过严格模式。

## 最小公共模型

复用 [CollectedScope 与 execute_bounded](../../src/dogopencli/collect.py#L55)、[collector 注册与分派](../../src/dogopencli/plugins/__init__.py#L157)；新增小型 `result_policy.py`，不另建采集框架，不强行合并 pageNo、offset 与 single-response 循环。

建议模型为实施目标，不是现有 API：

| 字段/接口 | 约束 |
| --- | --- |
| `AcquisitionEvidence` | `scope_complete`、`dataset_complete`、`reported_total`、`total_semantics`、`arrivals`、`collected_total`、nullable unique/duplicate、`reasons`、有界 `attempts` 摘要；先以默认字段兼容旧调用者 |
| `reasons` | 稳定代码＋message＋必要数量/范围；包括 `COUNT_SHORTFALL`、`DUPLICATE_ROWS`、`UNEXPECTED_DUPLICATE_ROWS`、`COVERAGE_UNPROVEN`、`DETAIL_REFUSED`、`RETENTION_GAP`；不解析异常字符串来猜分类 |
| `evaluate_result(evidence, mode, require_complete, contract)` | 纯决策，返回是否可暴露数据、是否有发布资格、warnings、error、exit_code；不联网、不写库、不打印 |
| `contract` | 声明 total 单位、身份、duplicate policy、必要详情/稳定性和已验证恢复计划；覆盖 partial 默认允许，语义与安全硬门槛独立 |
| `PublicationResult` | 来自原子提交的实际 `published`、snapshot/capture ID、实际存储数量和最终 retained quality；不把“可以发布”当作“已经发布” |

`meta.complete` 对应**当前请求范围覆盖**，兼容已有 `backend_complete`；`meta.dataset_complete` 表示**本次要求组成**齐全，列表缺行时为 false，VA 列表完整但详情拒绝时 complete=true、dataset_complete=false。普通 Liquidity list 不因未抓独立详情而 dataset_complete=false；它的组成只包含原生列表记录。`--require-complete` 检查该操作需要的所有完整性维度。

`schema_version` 只表示缓存格式兼容，绝不决定 partial 行为。页宽继续使用已有单一声明；恢复步骤引用它，不新增另一份 initial_page_size 真值。Evidence 不保存 cookies、tokens、真实业务 ID、原始请求或生产响应。

## 对外行为与退出码

| 操作 | 候选/缓存 | data | meta/warnings 与发布 | error / exit |
| --- | --- | --- | --- | --- |
| 默认 live / cache list | 完整 | 正常窗口 | 完整性 true；仅确有质量告警才 warnings | null / 0 |
| 默认 live / cache list | 安全不完整 | 已取到的真实窗口 | complete=false 或 dataset_complete=false；结构化原因＋stderr | null / 0 |
| 严格 live / cache list | 所需维度不完整 | null | 保留可解释证据；拒绝 | INCOMPLETE_RESULT / 1 |
| 默认 refresh | 完整 | 原有刷新摘要 | 原子提交后 published=true；最终保留范围完整性如实输出 | null / 0 |
| 默认 refresh | 安全不完整 | 原有刷新摘要 | 原子提交后 published=true；完整性 false、原因告警 | null / 0 |
| `refresh --require-complete` | 不完整 | null | published=false；旧缓存与 retention 无变化 | INCOMPLETE_RESULT / 1 |
| refresh | 硬失败/提交失败 | null | 未提交时 published=false；旧缓存完整保留 | 原错误码 / 原失败退出码 |
| 默认 get | partial list 中未找到 ID，无完整范围不存在证明 | null | 此次操作没有可用对象；不能报 NOT_FOUND | INCOMPLETE_RESULT / 1 |
| 默认 get | 原生详情存在、验证通过 | 真实详情 | 独立详情缓存依据独立判断；列表 partial 不自动污染详情质量 | null / 0 |
| 默认 get | 已列对象详情明确缺失/拒绝 | null | 标明具体缺失；不以列表行替代详情 | INCOMPLETE_RESULT / 1 |

JSON 保留 `{data, meta, error}`。允许 partial 的 warnings 使用 `code=INCOMPLETE_RESULT`、结构化 `reason_codes`/evidence，warning code 不等于顶层错误。覆盖完整但有允许重复时，单独使用 warning `code=DUPLICATE_ROWS`、`reason_codes=[DUPLICATE_ROWS]` 与重复数量，complete=true、error=null，普通/严格均退出 0；不把完整候选标成 INCOMPLETE_RESULT。table 展示完整性和数量，同步 stderr 告警；格式不改变退出码。默认 exit 0 体现数据可用；自动化要求完整时必须显式传严格参数，帮助、describe、release note 均说明此变化。

首次 partial refresh 可以建立可用缓存。正常 refresh 以最新安全候选替换相同 scope 的 snapshot，即使旧缓存完整、新缓存不完整；不静默保留“最好但更旧”的版本。snapshot 不增加 complete/partial 双缓存、选择开关或旧行补洞；history/dated 沿用原保留机制。

空结果须区分：合法 total=0 且覆盖证明通过，发布零行完整缓存；single/fixed 单响应契约允许正常结束、total>0 且取得零行，发布零行 incomplete 缓存并告警；offset/pageNo 在达到 total 前提前空页、无进展，以及认证/传输/解析失败产生的空候选继续硬失败，不能发布。partial 空集合可以返回 `data=[]`，但告警明确“不能证明后端没有记录”；它不能作为不存在证明。

refresh 增加 `--require-complete`；若已有等价参数，复用其解析机制而不创建别名。所有 refresh 输出增量加入 `meta.published`，保留原 `data.published`；失败上下文只有在确认未提交时才输出 false。live/cache 读取不虚构 published。提交后告警不得再抛普通失败异常而丢失发布事实。

示例为脱敏合成数据，不是当前运行时输出：

```json
{
  "data": {"published": true, "row_count": 3690},
  "meta": {
    "source": "cache",
    "published": true,
    "complete": false,
    "dataset_complete": false,
    "reported_total": 3691,
    "collected_total": 3690,
    "missing_count": 1,
    "coverage_ratio": 0.999729,
    "warnings": [{"code": "INCOMPLETE_RESULT", "reason_codes": ["COUNT_SHORTFALL"], "message": "Published usable incomplete cache: collected 3690 of 3691; missing 1."}]
  },
  "error": null
}
```

missing_count/coverage_ratio 仅在 total 单位可信且分子同单位时计算；total 未报告或不具备可比性时为 null，total=0 不做除法。采集缺口与 details/retention 缺口分别列原因，比例不承诺缺失无偏或代表性。

`collected_total` 在本地筛选前，`matched_total` 在筛选后窗口前，`returned_count` 为实际显示数量。`--limit 1`、fields、offset、排序不能改变质量或消除告警；`has_more` 只描述已取集合的本地展示。partial 排名及聚合基于已取集合，不称为后端全量排名/总额。

多 capture 查询存在范围重叠时，不把各 capture 的 reported_total 直接相加作为查询范围 total；输出逐 capture 证据，无法得到同单位且不重叠的可信总数时，查询级 reported_total/missing_count/coverage_ratio 为 null。

## 缓存证据必须与数据一起保存

只删 refresh 的拒绝分支会产生假完整：当前 [plan_capture_publish](../../src/dogopencli/plugins/liquidity/store.py#L360) 与 trim 元数据写死完整性为 true；[CaptureEntry](../../src/dogopencli/plugins/liquidity/store.py#L37) 尚无采集质量；[select_captures/covers_window](../../src/dogopencli/plugins/liquidity/store.py#L634) 主要依据范围/留存推断完整。必须在同一迁移阶段改造 store 和 read，不可先发布 partial 再补读路径。

1. capture/index 和 snapshot 持久化真实 scope/dataset 完整性、采集原因、原始 total/计数摘要。`row_count` 始终等于实际存储主记录数；后端 total 单独保存。现有 [SnapshotMeta](../../src/dogopencli/cache.py#L56) 已有两个完整性字段，复用它们；新增证据通过窄元数据迁移，所有已迁移域的缓存读取须能取回。
2. 数据、证据、index、trim、deletes、retention 在既有 [publish_many](../../src/dogopencli/cache.py#L269) 事务内原子落库。无法持久化/回读证据的能力，不得先放行 partial 发布。
3. 普通缓存读先验证来源与内部存储完整性，再评估来源质量并告警。保持 [validated_records](../../src/dogopencli/cached_query.py#L58) 的实际行数/身份校验；它检查缓存是否损坏，不应要求实际行数等于后端 total。
4. 历史缓存无新增 evidence 时，复用其已有 backend/dataset flags，不根据“行数相等”升级为完整；false 缺理由则使用 `COVERAGE_UNPROVEN`。旧 Liquidity capture/index 原本只允许完整采集，缺新增字段可按旧格式语义兼容，retention holes 仍必须检查。读时不写库；新增记录不得丢字段后被旧逻辑读成 true。
5. 缓存来源、simulated、fetched_at/stale 与完整性独立。`--require-fresh` 保留原规则，不通过换质量标记更新采集时间或业务观测时间。

## Liquidity dated、history 与 retention

partial dated capture 的业务窗口表达**请求过的范围**，不证明窗口内每天完整。不能把 acquired partial 的 window_from..window_to 直接纳入 `covers_window` 的完整区间。

- 有精确日覆盖证明时记录真实完整日与缺口；只有全窗 total 缺数、无法定位丢在哪天时，整个采集窗口完整性未证明，不编造精确 missing_days。
- 已验证行可以按真实 series time 参与普通离线读取，即使该 capture 不完整；不能沿用“所有 missing_days 的行一律跳过”而隐藏刚允许发布的有效 partial 行。采集未知缺口与 retention 的确切淘汰日分开存储和判断。
- 多 capture 重叠时，按同 scope/来源的最新采集请求窗口确定行与覆盖权威区间，不按业务记录时间猜先后。最新窗口内只采用最新 capture 的已取得行，旧 capture 的该区间行全部排除，即使最新是 partial；窗口外仍可采用旧 capture。最新 partial 未见的 ID 不补旧行，也不推断已删除。完整区间计算先排除被更新 partial 覆盖的旧证明，再使用有效完整证据；不能仅把所有旧 complete 窗口做 union。更新的完整 capture 可以证明其重叠区间，范围内的旧 partial 行不能再带入全量结果，包括新完整采集已证明删除/不存在的旧对象。
- 仅拼出 total 数量或跨 capture unique 数量不能证明完整，也不能将来自不同采集轮次的行冒充一轮原子后端快照。需要聚合的查询返回完整性证明所引用的 capture 范围与质量；history 默认最新 capture 的质量直接沿用。
- snapshot/history/dated 三种留存 profile 和每 leaf 1,000,000 主记录上限保留。trim 必须继承采集不完整性；淘汰不能洗掉 COUNT_SHORTFALL。失去实际行的日/范围增加 RETENTION_GAP，verified-empty 日仅能来自完整采集。
- 严格 refresh 在计划与提交前检查**提交后拟保留结果**是否满足请求范围；若 cap 将淘汰当前请求需要的记录，也拒绝本次提交，旧缓存不变。默认 refresh 可按原 retention 策略提交，输出最终 retained quality 与淘汰告警；不得只输出采集前 complete=true。

原 PR #75 的 exact missing_days / partial-day 过滤回归必须保留，再补 acquired partial 的读取；不能为了返回部分行复活已被更新证据否定的旧记录。

## 能力契约与迁移目录

| 能力 | 保留的契约与本版改变 |
| --- | --- |
| 全部 46 Liquidity list / 47 variants | 接入默认 partial publish/read；去掉 schema_version/路径告警开关；offset 固定推进与 total 稳定性、scope、身份检查保留 |
| Liquidity single-response | 有原生身份保留 raw/unique 证据；无身份保留行次；未报告 total 的完整性来自原生全范围单请求合同 |
| Payment cost / SLA | 保留 5000 与一次 10000 独立重采；恢复后仍安全 partial 则默认可用/可发布；SLA 已取得列表对象仍采真实必需详情，普通失败不伪造详情 |
| Payment channel / 已放行规则列表 | 审计后只把覆盖缺口转成 safe partial；snapshot 替代源仍独立命名空间；不沿用 Cost 页宽或恢复计划 |
| Collection cost | 保留固定 pageNo=0、pageSize=1000；把仅数量不足的 parser 拒绝迁至 evidence/policy，格式/scope 验证保留；不采用 Payment 10000 或添加未知分页 |
| Collection SLA / 网络配置列表等 | 已验证列表的覆盖缺口纳入公共 policy；必要详情与所有结构/共享字段一致性仍为硬门槛，不机械放开所有旧拒绝 |
| Collection VA capacity | 保留 running_total、最后短页/整倍数空页收敛及原生 ruleId；同范围动态 total 规则仅适用于此能力 |
| Collection VA rules | 保留有效 HTTP200/success=false 的特定详情拒绝例外、null detail；允许合法 partial list 中已取得对象的必需详情按原规则采集；默认发布质量分别记录列表与详情，未见 ID 不报 NOT_FOUND |
| PTR cases / orders | 保留双轮稳定、orders 扩大范围证明再裁业务窗口；本版不削弱现有采集放行门槛，现有稳定/覆盖证明失败继续拒绝；若未来支持稳定 partial，须单独修订契约与回归 |
| Liquidity native detail | 独立 list/detail 缓存保留；不拿 list 行冒充详情，不新增未验证 getter |

默认允许覆盖 partial 是业务策略；表中 PTR 例外保留现有语义证明，必须通过具名契约明确列出，不能再靠“某个插件原来 strict”笼统豁免全域。未验证/延期能力保持非执行状态；公共策略不新增端点、权限或业务范围。

分页恢复仍限于已验证能力声明：候选独立重建、共享截止时间与重试预算、不拼接候选、不用旧缓存补洞。总数变化只允许发生在独立候选之间，不能放宽同一固定-total 候选。首次采集质量问题可触发已有一次重采；一般业务失败或身份冲突不能被当作容量问题。

Payment 已有恢复契约区分预计页序列尚未结束的提前空页与遍历结束后的覆盖缺口：前者仍硬失败；后者包括末页为空，可触发已声明的一次 10000 独立重采。该契约不扩展到其他能力。

本版不增加全局缩页阶梯、无限重采、按 total 盲目选页宽、repair campaign 或全新 paginator。holdings 默认 500、Collection cost 固定 1000 与既有各 leaf 页宽保留。

## 分步实施与交付边界

| 阶段 | 实施内容 | 停止条件 |
| --- | --- | --- |
| 0：行为/契约清单 | 导出全部注册能力与 variants；记录分页、total 单位、身份、详情/稳定性、partial 规则；补缺口原因，不把旧 boolean 自动当安全证明 | 46/47 Liquidity 完整映射、全部其他采集入口映射；例外有明确依据 |
| 1：公共 policy＋Liquidity 全链路 | evidence、live/refresh/cache read 同时迁移；存储真实质量；dated/retention 处理；严格 refresh；输出/退出码 | 所有 Liquidity list 的 safe partial 可首次建缓存和持续回读告警；严格无数据/不发布；无假完整 |
| 2：Payment/Collection | 审计 parser/collector 的覆盖拒绝；复用公共策略与持久化证据；SLA/VA 原生详情；PTR 保留具名证明 | 已放行采集入口没有无告警 partial；default/strict 与发布事实一致；硬失败未放宽 |
| 3：证据/有限恢复整理 | 使用既有 collector 注册；恢复原因结构化；预算/候选摘要；只在证据齐全能力放行 duplicate tolerance | 不再由 schema 或路径决定 quality；无候选拼接；域契约与 UAT 对得上 |

实施前按当前工作树构建/核验 code-review-graph 并执行影响分析；本次只读研究未完成的图覆盖不能作为实施已通过依据。实现提交前刷新图，对实际默认分支分析变更；不提交 `.code-review-graph/`。

退出码变更、首次 partial 缓存发布、最新 partial 替换旧 complete、严格刷新及 schema 向前兼容限制进入 release note 与 describe/help。新增 evidence 写法上线前确认旧版本不会将 partial 当完整：不兼容旧读路径时提升相应缓存格式版本并要求旧二进制拒绝，保留其他命名空间。回滚不得仅回退代码并让旧版读取新 partial namespace；应回退该次事务前缓存备份或显式隔离新格式。证据与数据不能半迁移。

研究阶段产物仅研究、规格、ADR 与文档索引。后续实施按本节验收，结果另行记录，不改写研究观察。生产验证保持 inquiry-only，按各能力真实 allowlist、身份与来源范围执行；不沿用 Payment 登录成功作为 Liquidity 授权证明。

## 验收矩阵

实施验收用 fake transport、真实临时 SQLite 和 CLI 边界测试，避免只重复 policy 内部分支。下列为必需条件；实施验收记录见文末，不等于生产 UAT。

| ID | 输入/场景 | 必须证明 |
| --- | --- | --- |
| A01 | 首次默认 partial refresh，有有效少量行及可信 total | 缓存原子建成；published=true；完整性 false；error=null/exit0；可断浏览器离线读且每次告警 |
| A02 | 旧完整缓存＋新安全 partial / 契约允许结束的 single/fixed 零行 partial | 默认以新候选替换，不保留旧行补洞；snapshot/证据/行数一起更新；行内容 hash 相同也持久化新质量；不声称后端无数据 |
| A03 | 严格 partial refresh / 严格 partial live/cache | data=null；INCOMPLETE_RESULT/exit1；refresh published=false；记录、index、trim 与 retention 全部不变 |
| A04 | 完整数据或 complete＋允许重复告警 | exit0；严格可通过；告警不将 complete 改成 false |
| A05 | raw=total、unique 少 1 | 无论缺口大小，保持 incomplete；COUNT_SHORTFALL 与 duplicate 可同时解释 |
| A06 | raw>total=unique，具名容忍合同/保守合同对照 | 仅容忍声明满足全部证明时 complete＋warning；保守及 single raw2/total1/unique1 仍 incomplete |
| A07 | 无原生身份、未报告 total、真实零范围 | 行次保留；nullable 计数真实；零行 namespace 与 index 同时存在；不伪造 total |
| A08 | total 变化、身份冲突、scope 错配、auth/403/解析/超时/预算失败、分页提前空页/无进展 | 原硬失败，不发布、不重采掩盖、不静默退缓存；原缓存完全保留；不得按 A02 零行例外放宽 |
| A09 | partial dated 不能定位缺哪天 | 整窗标覆盖未证明；普通返回有效行＋告警；严格拒绝；不变成 verified-empty 日 |
| A10 | 同日旧 complete={A,B}，新 partial={A'}；以及旧 partial={A}、新 complete={A',B'}；后续新 complete={A''} | 第一组仅返回{A'}且 incomplete；第二组仅返回{A',B'}且 complete；第三组仅返回{A''}不复活B；窗口外旧有效日保留，retention缺口回归保留 |
| A11 | trim/retention＋原采集 partial；严格 refresh 将超 cap | 原缺口原因保留，retention 原因单列；普通输出提交后质量；严格不得提交后才发现不完整 |
| A12 | VA partial list / 特定 detail refusal / 其他 detail error | 默认有效行/真实详情按合同发布，缺详情 null；strict拒绝；403/身份/共享字段冲突保留旧缓存；get不伪装 list |
| A13 | Payment一次重采、Collection固定1000、VA动态total、PTR双轮漂移 | 页宽与各自证明保留；共享预算；后轮完整可exit0；PTR不能由相同count误放行 |
| A14 | partial list 中未知 ID 与 native detail 独立完整 | 未知ID为INCOMPLETE_RESULT，完整scope才NOT_FOUND；独立完整详情可正常用 |
| A15 | 本地filter/limit/offset/fields/json/table | evidence不受展示影响；每次partial告警；两格式同退出码；输出真实published |
| A16 | SQLite 提交故障、锁冲突、缓存损坏、旧格式读取/回滚 | 事务回滚；损坏硬拒绝；partial不被旧版读成complete；读路径不写库/联网 |
| A17 | 注册表遍历全部路由/variant/其他采集入口 | 每个已放行能力声明规则；无schema/path分支；未验证能力继续不可执行；选代表CLI做全链路证明 |

最终交付报告分别报告离线验收、生产只读 UAT、仍未验证的能力及具体阻塞；历史 UAT 不证明新 policy/缓存迁移已验收。

## 实施验收记录

2026-10-03，最终业务代码提交 `c64178eaa89e15f345711886bc6427984e9f2af5`，相对实际默认分支 `master`（`308d5c448abad01478330729555204a05e90d59b`）验证：

- 全套离线 pytest：**1725 passed、1 skipped、28 subtests passed**，914.11 秒。使用既有虚拟环境、fake CDP/transport 与真实临时 SQLite；没有调用生产系统。
- Ruff、格式、编译与 Doc Guard 通过。仓库未配置独立静态类型检查器，不将编译检查记作类型检查。
- 原命令 `greptile review`：**5/5、零评论**，review ID `03d38ea6-bce8-46e9-99af-860200dd5cf1`。
- PR 前双轴审查分别完成：Standards 明文规范违规及未解决建议均为 0；Spec 原 2 项 P1 均已修复，未解决项为 0。修复包括拒绝 Liquidity capture 内损坏的原生身份/存储序号，以及保留 Channel 未验证业务键下的有效行次；损坏缓存 JSON 返回明确错误。
- Payment 末页覆盖缺口的独立重采已补回归：5000、5000、10000 请求，最终缓存仅来自重采候选；遍历未结束的提前空页继续硬失败。
- 注册表实测仍为 **46 个 Liquidity list 路由、47 个 variant**；页宽和 PTR 必需稳定性证明保留。

本记录证明当前分支的实现与离线验收，不代表已发布、已创建 PR 或已执行新策略的生产 UAT。生产逐能力验证及历史延期边界继续以真实 allowlist 和各能力契约为准。
