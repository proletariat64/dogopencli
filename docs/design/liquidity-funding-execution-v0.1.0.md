# 资金需求与执行查询 batch 规格 v0.1.0

权威规格：[GitHub Issue #82](https://github.com/proletariat64/dogopencli/issues/82)。本文为可读副本；后续范围调整见 Issue 的用户确认记录。实施状态与生产放行以独立验收报告为准。

## Problem Statement

运营人员需要通过 CLI 查看资金需求、执行记录、swap 订单和可投资资金，并在显式刷新后离线使用可信的记录。目前这四个 `runtimes` 列表仍为 `unsupported`：已有测试日期与范围内查询成功的登记，但结果为空，不能证明非空记录结构、唯一身份、业务语义或采集完整性。用户无法把这些查询作为可靠的数据来源。

本批目标是新增 **4 个可验证的列表查询**。历史空结果不是非空契约或生产 UAT 已通过的证据，公共不完整结果策略也不能替代未验证叶子的启用门槛。

## Solution

### 已确认的范围调整（2026-10-03）

生产原生 swap 默认全范围采集收到 959 行，只有 952 个唯一 `dealId`，有 7 行重复，不能放行无日期查询。用户已明确选择：**允许仅开放必填交易日期范围**。`operations swaps list` 与其根级 refresh 必须同时提供 `--trade-from` 和 `--trade-to`，采用原生包含两端的 YYYYMMDD 交易日期；无日期、单边日期或倒置范围在联网前拒绝。保留公共不完整结果及严格模式语义，不开放无日期默认范围，也不放宽重复容忍。

原生 2026-09-01～10-01 范围已采集 15/15 条、跨 2 页且无重复；单日边界和完整空日期范围已验证。这些原生探测仍需候选代码的 CLI UAT、离线缓存一致性和本地 Kimi CI／复审，才能启用该受限叶子。其余三个叶子的非空证据门槛保持不变，四叶子整体交付不得因单个受限叶子通过而视为完成。

交付「资金需求与执行查询」batch，沿用现有查询、结果策略、SQLite 采集缓存及离线描述架构。以下命令统一省略 `dogopencli liquidity` 前缀。

| 优先级 | 列表命令 | 业务用途 | 必须补齐的证据 |
| --- | --- | --- | --- |
| P1 | `operations demands list` | 查看资金需求 | 非空记录结构、唯一身份、日期及筛选范围、分页完整性 |
| P1 | `operations executions list` | 查看执行记录 | 非空记录结构、唯一身份、状态含义、分页完整性 |
| P2 | `operations swaps list` | 查看 swap 订单 | 订单身份、日期语义、查询范围、分页完整性 |
| P2 | `investment investable-funds list` | 查看可投资资金 | 金额／币种、资金范围、时点语义、记录身份、完整性 |

每个叶子的交付包括 `list`、现有根级 `refresh liquidity …` 入口、`help/describe` 和离线缓存读取。每个叶子只有在原生只读契约、非空样本、完整采集和生产 UAT 单独通过后才启用；证据不足继续保持可发现、不可执行的 `unsupported`，并说明具体缺口。

## User Stories

1. As an 资金运营人员, I want 查询资金需求列表, so that 我能了解指定范围内的资金需求。
2. As an 资金运营人员, I want 查询执行记录列表, so that 我能查看已经记录的执行情况。
3. As an 资金运营人员, I want 查看执行状态的原生值和已验证说明, so that 我不会把不同业务状态误解为同一结果。
4. As an 资金运营人员, I want 查询 swap 订单列表, so that 我能按已验证的订单身份识别每笔订单。
5. As an 投资运营人员, I want 查询可投资资金列表, so that 我能查看已验证范围内的资金数据。
6. As an 投资运营人员, I want 查看资金金额及币种, so that 我不会混合不同币种或丢失金额精度。
7. As an 数据使用者, I want 了解各列表的日期、时区及边界语义, so that 我能选择正确的查询范围。
8. As an 数据使用者, I want 区分业务观测时间和采集时间, so that 我不会把刷新时间当成资金观测时点。
9. As an 数据使用者, I want 使用经非空样本验证的字段说明, so that 我能正确读取和解释返回记录。
10. As an 数据使用者, I want 使用经验证的唯一身份, so that 我不会把不同需求、执行记录、订单或资金记录合并。
11. As an 运营人员, I want 使用已验证的原生筛选条件, so that 返回数据对应我的业务范围。
12. As an 运营人员, I want 显式刷新选定叶子的列表缓存, so that 我能控制数据采集和更新时间。
13. As an 离线使用者, I want 默认 list 只读取本地缓存, so that 断开浏览器后仍能查询已采集记录。
14. As an 离线使用者, I want refresh 与 cached list 的记录、数量和范围一致, so that 我能信任离线结果。
15. As an 离线使用者, I want 完整空结果也能缓存, so that 我能区分已验证的零记录范围和缓存缺失。
16. As an 运营人员, I want 通过 --live 执行只读查询且不写缓存, so that 我能查看源端结果而不替换离线数据。
17. As an 数据使用者, I want 每次输出明确采集完整性、更新时间及缺口, so that 我能判断数据适用性。
18. As an 自动化使用者, I want 沿用 --require-complete 的严格行为, so that 需要完整数据的任务可以拒绝覆盖不足。
19. As an 数据使用者, I want 分页重复、身份冲突和遗漏有明确证据, so that 去重或数量相等不会掩盖错误。
20. As an 运营人员, I want 查询失败时保留原缓存, so that 认证、传输或业务失败不会损坏已采集数据。
21. As an CLI 使用者, I want help 和 describe 离线可用并准确显示支持状态, so that 我能发现可用命令及其限制。
22. As an 维护者, I want 每个叶子有独立生产 UAT 记录, so that 某个叶子的成功不会替其他叶子放行。
23. As an 维护者, I want 使用已有 CLI 测试入口覆盖全链路, so that 验收反映用户可观察行为。
24. As an 维护者, I want 使用本地 Kimi CLI 执行 CI／复审并记录结果, so that 本批遵循用户指定的验证流程。
25. As an 运营人员, I want 证据不足的叶子继续显示 unsupported 和具体阻塞, so that 我不会误用未验证能力。
26. As an 项目维护者, I want 后端异常调查单独登记, so that 本批交付保持在四个列表查询范围内。

## Implementation Decisions

- 四个业务叶子保持 `runtimes` 分类；复用 Liquidity capability 注册、列表契约、领域采集器、投影字段、查询与刷新入口、列表 capture store 和离线描述机制。不新建浏览器、认证、缓存引擎或采集框架。
- 先核对原生页面及查询行为，再取得可用非空样本。已有调查中 demands 与 executions 关联 `riskActionTaskQuery.json`，swaps 关联 `swapOrderQuery.json`，investable-funds 关联 `queryInvestableFundList.json`；这些是核查起点，不能把历史路径直接当作完整的现行生产契约。
- 明确每个查询的来源、端点、方法、编码、允许参数、默认范围、分页方式、包络、total 计数单位和结束条件；只允许经验证的 inquiry。共用端点不等于共用业务范围，demands 与 executions 的任务类型须分别验证并隔离。
- 唯一身份只能来自原生契约与非空记录证据，复合身份须明确组成及作用域。不能用字段名猜测、列表位置或整行哈希替代身份验证。同身份内容冲突为硬失败。
- 字段投影与 describe 使用脱敏非空样本和来源证据；金额／币种采用现有精度安全约定。未知状态保留原生值，未验证说明不得本地推导。
- 日期含义、时区、包含边界、筛选映射及可投资资金的业务观测时间逐叶核验；`fetched_at` 仅表示采集时间。来源没有观测时点时，明确未知，不用采集时间补充业务含义。
- 按验证后的时间与范围语义选择现有 history 或 dated 缓存 profile，不提前假定四个叶子全部按日期采集。列表刷新独立于详情，不触发任何详情抓取。
- 保留既有每叶子 1,000,000 主记录上限、原子发布及 retention 覆盖语义；记录、范围、采集证据和索引一起提交。筛选或展示 limit 不改变源端采集完整性。
- 默认 list 离线读取且不隐式刷新；根级 refresh 显式采集列表；`list --live` 不写缓存。help/describe 不联网并显示字段、身份、日期／时点、筛选、分页、缓存及支持状态。
- 沿用 [Issue #78](https://github.com/proletariat64/dogopencli/issues/78) 与 ADR 0019 的统一结果策略：已启用能力的安全不完整候选默认可返回／发布，`complete=false`，持续告警，真实记录 `published`；严格模式拒绝不完整数据并且 refresh 不发布。认证、权限、包络、范围、身份冲突、固定 total 漂移等硬失败不降级、不发布。
- **本批放行要求仍是取得完整、无重复、无遗漏、无身份冲突的代表性采集证据。** 安全 partial 行为是运行时兼容要求，不能替代首次生产 UAT，也不新增跨页重复容忍规则。数量相等或去重不单独证明完整性；无 total 时依经验证的原生结束协议，不伪造 total。
- 完整零记录采集可以发布；本地筛选为空、覆盖不足或缓存缺失不能被标记为来源完整空结果。失败刷新保留已有缓存；安全 partial 的更新遵循公共策略，不能拼接旧记录补洞。
- 逐叶实施、测试、生产只读 UAT 后放行，不一次性切换四个 supported 标志。登记具体缺口和继续条件；若最终不足四个通过，报告实际数量，本批四个新增目标尚未完全达成。

## Testing Decisions

- 用户已确认沿用现有最高层测试入口：**公共 CLI＋fake CDP＋临时真实 SQLite**。复用既有 Liquidity CLI、partial 回归、describe 和统一结果策略验收经验；不新增测试框架。必要解析／契约负向检查只补在已有 seam。
- 好测试检查请求约束、输出记录／元数据／退出码、缓存发布事实和离线可用性，避免断言内部调用顺序或复制实现分支。合成 fixture 用已验证结构脱敏构造，不将合成成功称为生产验收。
- 必需验收矩阵如下，每项分别覆盖四个叶子及其已声明的查询 variants。

| ID | 场景 | 必须证明 |
| --- | --- | --- |
| T01 | 非空原生查询 | 结构、字段类型、身份、范围及业务语义验证成立 |
| T02 | 代表性多页／原生单响应 | 已验证结束条件与总数语义成立；原始行数、唯一数、重复数可核查；无冲突、重复或遗漏 |
| T03 | refresh → cached list | 同一已提交 capture 下数量、身份、记录内容、范围和采集证据一致；比较全量结果，排除展示窗口影响 |
| T04 | 断开 fake CDP 后 list／help／describe | 离线成功、无网络请求、无隐式刷新，支持状态及说明准确 |
| T05 | 完整零记录 refresh | 空 capture 和覆盖证据真实发布；离线返回完整空结果，不是 CACHE_MISS |
| T06 | 非空或空 --live | 不创建或修改缓存记录、capture、索引及质量；检查缓存前后状态；输出 fetched_at、complete、scope 和缺口 |
| T07 | 日期边界及各原生筛选 | 范围映射正确、错误参数明确拒绝、demands／executions 类型不串用 |
| T08 | 安全 partial，默认／严格模式 | live、refresh、离线质量一致；默认持续告警；strict 不暴露数据且不发布；不伪装 complete |
| T09 | 冲突／重复／遗漏／total 漂移 | 正确区分硬失败和安全覆盖缺口；没有未经声明的重复容忍；缺口未知时不伪造缺失数量 |
| T10 | auth／权限／包络／scope／传输／事务失败 | 真实错误、不降级、无候选发布、原缓存保留 |
| T11 | unsupported 放行门禁 | 缺少任何必需证据时不执行查询；list 未通过时仍可离线发现原因；get 不因 list 放行而启用 |
| T12 | retention 与已有能力回归 | 复用既有上限及覆盖行为；缺失覆盖不成为空结果；相关已有叶子不回退 |

- 实施时执行相关 pytest、Ruff 检查与格式门禁；**使用本地 Kimi CLI 执行 CI／复审**，记录实际命令、结论和未完成项。自动测试、本地 CI／复审与生产 UAT 分开报告，不能互相替代。
- 每叶子独立生产只读 UAT：原生契约核对、可用非空样本、分页完整性、独立 refresh、断开传输离线回读、完整空范围（需源端证据）、live 不写缓存以及描述准确性。数据变化时按各次采集事实核查；refresh 与 cached list 比较同一 capture，不强行把不同时间的 live 与 refresh 认定一致。
- 生产门禁必须证明真实身份及代表性跨页边界；若没有足够非空／多页数据，不能仅以合成 fixture 宣称生产分页通过。单响应查询可依其已验证的全量契约验收。

## Out of Scope

- 不开发或启用任何 `get`，明确排除 `cash accounts get`；不以列表行替代原生详情。
- 不纳入 `forecast accuracy list`、已知分页重叠列表、wallet／pool balance／credit usage，以及其他已知身份、分页或业务语义阻塞项。
- 不执行需求创建、审批、资金执行、swap 交易、投资下单等任何业务变更，不提供任意请求或 JavaScript 入口。
- 不扩展公共 incomplete 策略，不新增全局缩页／重复容忍／无限重采，不更换缓存引擎或重构所有领域。
- 不把后端反复错误修复、repair campaign 或其他叶子故障治理混入交付；阻塞单独登记，受影响叶子继续 unsupported。

## Further Notes

- 依据：用户本次 batch 选择与验收要求、已确认的 CLI 测试 seam，以及本地 Kimi CLI CI 指令。
- 与 [#71](https://github.com/proletariat64/dogopencli/issues/71)、[#72](https://github.com/proletariat64/dogopencli/issues/72)、[#76](https://github.com/proletariat64/dogopencli/issues/76) 的 Liquidity 查询范围衔接；质量与缓存策略沿用 [#78](https://github.com/proletariat64/dogopencli/issues/78)。遵守 ADR 0015–0019，ADR 0019 是本工作树较新的 incomplete 行为依据。
- 当前源码将四个 list 登记为 `empty-scope` 的 deferred runtimes；历史 probe 和近期全 CLI UAT 仍将其列为延期。历史证据证明测试范围内成功空查询，**尚未证明本批四叶子可启用**。
- 实施前核验 Liquidity 独立授权；遵守项目浏览器规范与禁止使用 CDP 9330–9340 的约束。仅保存脱敏字段结构及验收摘要，认证材料与敏感响应不进入 issue、Git 或日志。
- 最终交付逐叶报告契约、非空样本、自动验证、本地 Kimi CLI CI／复审、生产 UAT、支持状态及具体 blocker。进度以已通过全部放行条件的叶子数／4 为准。
- 此 issue 为实施规格；发布规格不表示代码、CI 或生产 UAT 已完成。标记 `ready-for-agent` 表示可开始按门禁实施，不表示四个叶子已有生产使用资格。
