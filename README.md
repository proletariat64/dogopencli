# Dogopencli

将产品运营网站的查询能力转为 Python CLI，供单机单人使用。v0.1.0 的既定范围聚焦付款产品；v0.1.4 增加收款交易成本，v0.1.6 增加收款 SLA 配置，v0.1.7 增加收款 VA 规则查询，v0.1.8 增加收款 VA 容量监控。所有业务操作仅查询，不创建、修改或审批任何生产配置。

Channel 后端故障期间使用显式离线替代源推进工程；正式 CDP 架构保持，真实 Channel 全量验收在后端修复后进行（见[规格 Issue #1](https://github.com/proletariat64/dogopencli/issues/1)、[ADR 0005](docs/adr/0005-channel-snapshot-source.md)）。Cost/SLA/VA 规则查询走真实 CDP 路径。

## 安装

需要 Python 3.10+：

```bash
pip install -e .
```

配置默认位于 `~/.config/dogopencli/config.toml`（认证与查询共用：显式 `--config-dir`〔认证命令〕优先，其次 `DOGOPENCLI_CONFIG_DIR`、`DOGOPENCLI_CONFIG`；文件变量可指定自定义文件名），缓存默认 `~/.local/share/dogopencli/cache.sqlite3`（可用配置键 `cache.path`、`cache.ttl_hours` 调整，新鲜度默认 72 小时）。最小配置：

```toml
[sources.payment_channel]
kind = "snapshot"
path = "/path/to/dataset"    # 显式离线整理集；后端修复后改为 kind = "cdp"

[sources.payment_cost]
kind = "cdp"

[sources.payment_sla]
kind = "cdp"

[sources.collection_cost]
kind = "cdp"

[sources.collection_sla]
kind = "cdp"

[sources.collection_va]
kind = "cdp"

[sources.collection_va_capacity]
kind = "cdp"
```

配置示例见被 Git 忽略的 `tmp/channel-2026-09-11/source.toml`；整理集为私有数据，不随 Git 分发。

## 帮助与导航

帮助为 DI 风格的渐进式导航（[规格 Issue #13](https://github.com/proletariat64/dogopencli/issues/13)），已替代旧的 argparse 文本默认帮助。无参数、`--help`/`-h`、`help` 均返回同一份 `help_version=1` JSON 文档并退出 0；每层只列直属子命令，叶子给出完整调用契约（必填项、默认值、choices、约束、操作影响、输出、错误码、示例与下一步）。帮助全程离线：不读取配置、缓存、浏览器或网络。

```bash
dogopencli                                   # Agent：根 JSON 导航（children：payment/collection/refresh/describe/auth/login/logout）
dogopencli help payment channel list         # 逐层钻取到叶子契约
dogopencli payment sla baselines get --help  # PATH --help 等价于 help PATH
dogopencli --format text                     # 人工：同一份文档的可读文本（任意节点可加 --format text）
```

裸叶子保持执行语义：`dogopencli payment channel list` 仍执行缓存查询，`login`/`logout`/`auth check` 仍执行认证动作；只有无 handler 的命令路径才自动显示帮助。帮助 `--format` 只接受 `json|text`（业务执行格式不变，查询仍 `json|table`）。错误归属不变：根/业务导航参数错误为业务 JSON `INVALID_ARGUMENT` 退出 2，认证路径参数错误为认证 `invalid_arguments` 退出 1。

`cache.path` 仅支持具备可靠 SQLite WAL/共享内存与 POSIX `flock` 语义的本地 Linux 文件系统，推荐 WSL Linux 磁盘上的默认目录。Windows DrvFS/9p 挂载及网络文件系统不在缓存支持范围；无法启用 WAL 时明确失败，不降级为回滚日志。升级前若缓存位于这些挂载上，请改到支持的本地路径并重新刷新；旧库的来源路径列会自动迁移。

## Data helper

Data helper v1 提供随程序发布的 schema、字段说明和读取指引（[规格 #16](https://github.com/proletariat64/dogopencli/issues/16)）。无需配置、缓存或登录；不读取业务数据、不联网、不启动浏览器、不初始化或迁移 SQLite。同一安装版本、同一目标的输出确定，不随本机快照变化。

先从查询帮助的 `next` 找到描述入口，再读取描述、核对参数，最后执行已有查询：

```bash
dogopencli describe                          # 支持的描述路径导航
dogopencli describe payment channel list
dogopencli describe payment cost list
dogopencli describe payment cost list --format text  # 人工阅读 schema、字段说明和读取指引
dogopencli describe payment sla baselines list
dogopencli describe payment sla baselines get
dogopencli describe collection cost list
dogopencli describe collection sla configs get
dogopencli describe collection va rules get
dogopencli describe collection va capacity list
dogopencli help payment cost list            # 参数的权威契约
dogopencli payment cost list --all --fields itemId,costRateConfigList
dogopencli payment sla baselines list --all --fields id
dogopencli payment sla baselines get --id BASELINE_ID
```

`BASELINE_ID` 是合成占位符，替换为列表实际返回的 `id`。SLA 列表和详情分别是数组与对象；详情须独立读取，不能以列表行代替。缓存列表与详情由一次 SLA refresh 一起发布，live 详情是独立查询。

成功描述直接返回 JSON 对象，固定键如下；它本身不使用业务 `data/meta/error` envelope：

| 键 | v1 类型与含义 |
| --- | --- |
| `describe_version` | 整数 `1`，helper 文档协议版本 |
| `capability` | 字符串：`payment.channel.list`、`payment.cost.list`、`payment.sla.baselines.list`、`payment.sla.baselines.get`、`collection.cost.list`、`collection.sla.configs.list`、`collection.sla.configs.get`、`collection.va.rules.list`、`collection.va.rules.get` 或 `collection.va.capacity.list` |
| `schema_version` | 整数 `1`，该查询能力的数据描述版本 |
| `data_schema` | JSON Schema 对象，`$schema` 为 `https://json-schema.org/draft/2020-12/schema`；描述成功且未投影的业务 `data`，不是数据库表或整个 envelope |
| `read_guide` | 对象，包含下面的读取规则及证据词汇 |
| `query_help` | 对应 `dogopencli help <查询路径>` 字符串，参数以此帮助为准 |

各领域 schema 与读取指引由对应插件提供，随查询命令一起注册；核心只组装描述文档与通用输出说明。schema 和读取指引的注解词汇共用一份定义，分别以 `dimensions` 映射和 `aspects` 列表呈现同一组证据维度。

付款 `read_guide` 的领域键与公共键为：`parameter_contract`、`options`（直接复用查询帮助）、`filters`、`filter_semantics`、`envelope`、`metadata`、`access_modes`、`quality`、`projection`、`pagination`、`identifiers`、`interpretation`、`annotations`、`errors`、`exit_codes`、`examples`、`evolution`、`filter_notes`；SLA 另有 `list_to_detail`（`steps` 与 `meaning`）。每个 `filters` 条目有 `flag`、`request_field`、`record_field`；无法映射的记录字段为 JSON `null`。`metadata` 按实际 `meta` 字段名解释语义，`exit_codes` 使用字符串键。

兼容演进可在同一版本增加字段或注解，消费者须允许未知键；不兼容 helper 形状变更提升 `describe_version`，不兼容能力 schema 变更提升 `schema_version`。这两个版本不改变业务 envelope 或 `help_version`。描述执行默认输出 JSON（也可显式 `--format json`）；`--format text` 将同一份完整文档渲染为缩进文本，保留嵌套字段、注解和读取指引。描述帮助仍支持 JSON/text。未知目标、认证/refresh 目标或查询参数（如描述后的 `--live`）返回业务 JSON `INVALID_ARGUMENT`，退出 2；不会执行目标查询或认证。

字段说明位于 schema 的 `description`、`properties`、`items` 和 `$defs`，嵌套 Money/Ratio 通过 `$ref` 引用。只对已验证事实施加类型、必填或枚举约束；未知扩展保持开放。以下注解不是 JSON Schema 验证断言：

| 注解 | 解释 |
| --- | --- |
| `x-evidence` | 独立给出 `type`、`presence`、`nullability`、`unit`、`meaning` 的证据状态 |
| 状态值 | `verified` 已验证；`observed` 仅观察到、不作保证；`unknown` 未解决；`not_applicable` 该维度不适用 |
| `x-observed-type` | 观察到的 JSON 类型，不限制其他类型或 null |
| `x-observed-values` | 非穷尽观察值，不是封闭 enum；查询参数 choices 仍以帮助为准 |
| `x-unit` | 仅明确验证时给出单位名；不执行转换 |
| `x-annotation-vocabulary` | schema 内的注解词汇定义；`read_guide.annotations` 同时提供解释 |

缺失、null、空字符串和空数组须分别保留，不能据此推断 false、零或能力不支持；只观察到空数组不能推定元素结构。保留数值精度及金额字符串，区分交易币种与成本币种，不能仅凭 `cent` 除以 100。未验证比例缩放、时间单位和枚举含义保持未知；SLA 两个成功时效字段明确标注已验证的 `seconds`，仍保留原始字符串。渠道成本配置不是实际收费/总支出，产品 SLA 基线不是观测到账耗时。

`seqid` 是本地位置，不跨快照稳定；Channel `abilityId` 不保证全局唯一，Cost `itemId` 不是渠道 ID；没有通用跨域 join key 或已验证的一对一关系。账户别名和账号分别解释，Cost 的 `--bank-account` 映射 `bankAccountAliasName`，不接受“全账号”的语义替换。

列表默认只显示 100 行；`--all` 读取全部匹配行，与显式 `--limit`/`--offset` 冲突。`--fields` 选择顶层字段并保留选中的完整嵌套值，可能删除标识字段；应按部分数据解释，不能仅因不满足未投影 schema 的必填项而拒绝。投影保留全部质量 metadata。缓存同字段多值 OR、不同字段 AND；live Cost/SLA 每字段单值，Channel 标量筛选单值、已验证数组筛选允许重复。SLA `--biz-legal-entity` 仅列表 live 透传，其独立筛选效果未验证、无对应列表字段，缓存使用报参数错误。

查询时检查退出码与 `error`，再解释 `meta`：`source`（cache/live）和 `backend`（snapshot/cdp）独立；`snapshot_id`/`dataset_id` 标识内容，不提供历史查询或跨域同步快照。`fetched_at`、`loaded_at`、`source_observed_from/to` 区分观察、采集和导入时间，导入不使旧观测变新。`stale` 与 `complete` 独立；`matched_total`/`returned_count`/`has_more` 仅说明当前可用来源的匹配与显示窗口。`complete` 是来源覆盖，`dataset_complete` 可以只表示整理集完整；Channel snapshot 的 `simulated=true`、EXTERNAL 范围不能证明生产全量，即使 `has_more=false` 或返回空列表。`--require-fresh` 拒绝过期缓存，`--require-complete` 检查来源覆盖；VA 规则查询还拒绝 `dataset_complete=false` 的详情拒绝快照。默认缓存读不会隐式刷新，显式 refresh 才发布快照，`--live` 不更新缓存；describe 不执行其中任何操作。

## 登录与认证

认证命令移植自 DI（基线 commit `8eb163c6d140554ca167bd50349a85ca224ac342`），独立运行不依赖已安装 DI；使用专用 Chrome profile（`~/.local/share/dogopencli/chrome/`）与 CDP 端口 9222，输出 `output_version` envelope，详见 [ADR 0004](docs/adr/0004-cli-runtime-boundaries.md)：

```bash
dogopencli login                # 人工 SSO（headed，默认等待 600 秒，--timeout-seconds 覆盖），完成后切回 headless 复验
dogopencli auth check           # 只读检查现有会话，不启动或修复浏览器
dogopencli logout               # 仅清理并验证专用本地认证；不撤销公司全局 SSO，不删业务缓存
```

## 刷新与查询

普通查询只读本地 SQLite 缓存，不隐式联网、不启动浏览器；缓存缺失明确失败。显式 refresh 才访问来源并原子发布缓存；VA 规则详情被后端明确拒绝时可发布不完整快照并返回 `INCOMPLETE_RESULT`，其余失败保留旧快照。snapshot 查询不读取源 manifest 或数据文件，导入后源文件暂时不可用也能查缓存。缓存记录导入来源路径和 dataset_id；改路径或显式身份后必须刷新，同路径文件内容的变化在显式刷新时校验。旧缓存缺少来源路径时需要刷新一次：

```bash
dogopencli refresh payment channel    # snapshot：导入配置指向的整理集；cdp：真实采集
dogopencli refresh payment cost
dogopencli refresh payment sla        # 全列表 + 逐条详情一起原子发布
dogopencli refresh collection cost
dogopencli refresh collection sla
dogopencli refresh collection va          # VA 规则
dogopencli refresh collection va capacity # VA 容量

dogopencli payment channel list       # 默认场景 EXTERNAL，--payout-type 可选 LIQUIDITY/MANUAL/SETTLEMENT
dogopencli payment cost list          # 固定 FUND_OUT_CHANNEL_TRANS_FEE
dogopencli payment sla baselines list
dogopencli payment sla baselines get --id ID
dogopencli collection cost list
dogopencli collection sla configs list
dogopencli collection va rules list
dogopencli collection va capacity list
```

Channel 的 live 查询还会按已验证字段进行本地精确筛选，避免后端忽略条件时透出不匹配行；Cost/SLA 保持已验证的后端筛选语义。实时 SLA 详情的 complete 指所请求 ID 的详情，`meta.query` 标明 ID，成功获取时满足 freshness/completeness 要求。refresh 的 `meta.source=cache` 表示刚发布的本地快照。

Channel 单轮 CDP 采集中，同 `abilityId` 不同内容会阻止发布完整缓存；live 保留各版本但标记 `complete=false`。离线整理集仍可保留跨轮版本：manifest 的 `source_pages_complete` 独立校验各轮源分页，失败页使其为 false，不影响整理集自身的 `dataset_complete`，也不把 `backend_complete` 提升为 true。

公共查询参数：`--format json|table`、`--fields`、`--limit`/`--offset`/`--all`、`--live`、`--require-fresh`、`--require-complete`。默认 JSON envelope 为 `data`/`meta`/`error`；`meta` 始终携带 source、backend、simulated、complete、dataset_complete、stale、fetched_at/loaded_at、来源观察时间等质量标记，`--fields` 只裁剪数据不删质量信息。完整参数与契约见[规格 Issue #1](https://github.com/proletariat64/dogopencli/issues/1)。

## 来源切换与恢复

- Channel 后端修复后：把 `[sources.payment_channel]` 改为 `kind = "cdp"`，显式 `refresh payment channel` 验证当前全量后再使用；验证不通过则显式改回 `"snapshot"`。切换到 cdp 时删除仅适用于 snapshot 的 `dataset_id`，否则返回配置错误。不会自动切换。
- snapshot 与 cdp 缓存按命名空间隔离，切换来源不会读到另一来源的旧缓存；配置 `dataset_id` 与缓存不一致时明确失败并要求刷新。
- 并发刷新冲突返回 LOCKED，稍后重试即可。刷新使用进程持有的文件锁，崩溃或重启后自动释放，磁盘上的锁文件可保留；不按年龄抢占活跃锁。读者始终只见完整旧快照或新快照。

## 常见错误码与处置

| 错误码 | 含义与处置 |
| --- | --- |
| CACHE_MISS | 无缓存或来源身份不一致；运行对应 `refresh payment …` |
| CACHE_STALE | 快照超过 TTL；刷新，或去掉 `--require-fresh` 显式使用过期数据 |
| INCOMPLETE_RESULT | 来源覆盖或详情完整性不足；VA 规则部分刷新可能已发布快照，需检查返回计数和 `dataset_complete`。VA 规则缺详情的 `get` 不返回列表行 |
| AUTH_REQUIRED | 会话失效；运行 `dogopencli login` |
| BROWSER_UNAVAILABLE | 专用浏览器不可达；运行 `dogopencli login` 恢复。连接的 Chrome 必须属于专用 profile；无法证明归属时拒绝复用或退出。Chrome 默认启用沙箱，不开放通配 WebSocket Origin，CLI 原生连接不发送 Origin 头；启动失败时检查 Chrome 日志，不自动关闭沙箱 |
| LOCKED | 另一刷新、SQLite 锁竞争或浏览器生命周期操作进行中；稍后重试 |
| CACHE_ERROR / IO_ERROR | 缓存数据库或本地文件操作失败；检查文件权限、磁盘和数据库，不按锁竞争处理 |
| INTERNAL_ERROR | 未预期的业务命令异常；错误关联号同时出现在 envelope 与 stderr，stderr 附异常类型及函数/行号。排查时保留 stderr；不输出异常文本、源代码行或局部变量 |
| SOURCE_SCOPE_UNAVAILABLE | 替代集仅覆盖 EXTERNAL；其他场景无数据，不伪造空列表 |
| LIVE_SOURCE_UNAVAILABLE | snapshot 来源不支持 `--live`；切换到 cdp 或改用缓存 |
| REQUEST_NOT_ALLOWED | 请求不在只读允许清单；属于防护行为，不开放任意请求入口 |

业务查询与 refresh 退出码：0 成功（含允许的部分/空列表）、1 运行失败、2 参数错误、130 用户中断；认证命令：0 成功/帮助/版本、1 参数或运行失败、130 中断。

## 收款交易成本查询

[Issue #21](https://github.com/proletariat64/dogopencli/issues/21) 在 [ADR 0002](docs/adr/0002-payment-v010-scope.md) 的付款版本范围之外增加独立后续里程碑；不修改历史 v0.1.0 范围。配置 `[sources.collection_cost] kind = "cdp"` 后使用：

```bash
dogopencli help collection cost list
dogopencli describe collection cost list
dogopencli refresh collection cost
dogopencli collection cost list --require-fresh --require-complete
dogopencli collection cost list --live --all
```

固定 `FUND_IN_CHANNEL_TRANS_FEE`，无领域筛选、任意类型、详情或计算费用参数。默认只读独立缓存；`--live` 不写缓存、不回退旧数据。`refresh` 仅在结果完整时原子替换本地快照，生产业务始终只读。JSON/table、顶层字段投影和展示分页沿用公共约定。

采集只发送已验证的 `pageNo=0,pageSize=1000`。总数超过容量、重复 ID、截断或元数据异常都明确失败并保留旧缓存；`INCOMPLETE_RESULT` 不能通过去掉 `--require-complete` 绕过，不切换小页或扩大容量。成功且总数为零时允许省略列表，null 或非零总数缺列表则失败。1000 不是服务端上限保证。

收款 schema 独立标注观察证据与未知含义；保留原始嵌套费率、精确小数、单位、业务时间和未知扩展，不推导实际交易费用。VA 费用、VA 池/实体账户、签约及单据不在此次实现范围；VA 规则由下文独立能力提供。

## 未完成的外部验收依赖

安全参数变更后已用独立空 profile、CDP 9228 的真实 Chrome 验证：启用沙箱、不添加 `--remote-allow-origins` 时，无 Origin 的原生 CDP 连接成功执行 `1+1`；携带不可信 Origin 的连接被 HTTP 403 拒绝。本地证据目录为 `tmp/chrome-secure-smoke-tiwgh41d/` 与 `tmp/chrome-origin-check-gwlhhvs6/`（不随 Git 分发）。该检查仅覆盖连接通路。

- Channel 真实全量 UAT：待后端故障修复后执行（Issue #10），当前替代集明确标记 backend_complete=false，不代表生产全量。
- 认证 UAT 的 logout 范围仍需单独确认；Cost、SLA 和 VA 规则的生产只读 UAT 已分别记录在 [Cost 验收](docs/research/general/2026-09-26-collection-cost-argument-uat.md)、[SLA 验收](docs/research/general/2026-09-26-collection-sla-implementation-uat.md)和 [VA 规则验收](docs/research/general/2026-09-26-collection-va-rule-implementation-uat.md)。
- launcher 安全参数变更后的生产连接复验仍待完成：使用当前默认参数执行 `dogopencli login`，随后执行 `dogopencli refresh payment cost`，验证应用会话与采集；上述空 profile 检查不替代此项 UAT。

## 文档入口

- [文档索引](docs/README.md)：通用发现、付款产品发现及协作约定。
- [仓库目录与命名规范](docs/agents/documentation.md)：新增代码、测试或文档时遵循。
- [贡献指南](AGENTS.md)：只读边界、技术参考与开发约束。
- [数据准备状态](docs/research/payment/2026-09-11-channel-snapshot-preparation.md)：3834 行真实派生 Channel 替代集的整理与审计；配套[离线数据整理工具](scripts/prepare_channel_snapshot.py)。

## 校验

从仓库根目录运行，命令中的 RTK 前缀遵循本机协作约定：

```bash
rtk proxy .venv/bin/python -m pytest -q
rtk proxy ruff check .
rtk proxy ruff format --check .
rtk proxy make doc-guard
rtk proxy make test-doc-guard
```

Make 目标分别为 `make doc-guard`、`make test-doc-guard`；doc-guard 使用 Python 3.10+ 标准库，无需安装项目依赖。校验不连接生产、浏览器或知识库，也不改写文档。

### Collection SLA configurations

[Issue #27](https://github.com/proletariat64/dogopencli/issues/27) adds a separate
collection SLA configuration scope:

```bash
dogopencli help collection sla configs list
dogopencli describe collection sla configs get
dogopencli refresh collection sla
dogopencli collection sla configs list --all --require-complete
dogopencli collection sla configs get --id CONFIG_ID
dogopencli collection sla configs get --id CONFIG_ID --live
```

Replace `CONFIG_ID` with a returned string `slaConfigId`. Default reads are
entirely offline; live inquiries never publish or silently fall back. Refresh
validates the full list and every actual detail before replacing the isolated
`collection.sla.configs.list:configs:cdp` snapshot. Any failure preserves the old
snapshot. `endToEndSla` and `ipayInnerSla` remain seconds; `holidayLimit` retains
both complete arrays. Raw business timestamps and unknown extensions are kept.
These are configuration targets, not measured transaction performance.

The acquisition uses verified `pageNo=0,pageSize=1000`; overflow, duplicates,
invalid metadata and incomplete detail fail without speculative paging. Null
live details are errors, not proof of missing records. Backend snapshot isolation
is not guaranteed; shared list/detail fields must agree. List and detail are
separate raw objects.

List accepts repeatable `--business-line` (`businessCategory`), `--entity`
(`legalEntityCode`), `--currency` (`creditorCurrency`) and `--region`
(`creditorRegion`). Both cached and live queries match exact case-sensitive
literal values locally: repeated values of one field use OR, different fields
use AND. Values are not trimmed or normalized; empty/whitespace-only values
are rejected. A literal `*` is not a wildcard; missing/null fields do not match.
Live always acquires the complete unfiltered list, then filters, sorts by ID and
applies the display window. Filtering does not change source completeness or
freshness. No independent backend business-category filtering is claimed.
Refresh stays unfiltered; get selects only by ID.

```bash
dogopencli collection sla configs list --currency USD --currency EUR --region US --all
dogopencli collection sla configs list --entity ENTITY_CODE --business-line BUSINESS_CODE --live
```

Use actual returned entity/business codes in place of the example values.

### Collection VA rules

[Issue #31](https://github.com/proletariat64/dogopencli/issues/31) specifies a
separate collection VA rule scope, implemented under
[Issue #32](https://github.com/proletariat64/dogopencli/issues/32). Configure
`[sources.collection_va] kind = "cdp"`, then:

```bash
dogopencli help collection va rules list
dogopencli describe collection va rules get
dogopencli refresh collection va
dogopencli collection va rules list --all --require-complete
dogopencli collection va rules get --id VA_RULE_ID
dogopencli collection va rules get --id VA_RULE_ID --live
```

Replace `VA_RULE_ID` with a returned string `vaRuleId`. Default reads are
entirely offline; live inquiries never publish or silently fall back. Refresh
validates the complete list and every true detail — the requested ID and all
eight shared business fields must agree — before atomically replacing the
isolated `collection.va.rules.list:rules:cdp` snapshot. Any failure except one
preserves the old snapshot: when the backend explicitly refuses a single detail
(`success=false`), that rule still publishes with its real list row and a null
`detail`, the snapshot is marked `dataset_complete=false`, and the command then
fails with `INCOMPLETE_RESULT` naming how many details were refused instead of
reporting success ([ADR 0010](docs/adr/0010-collection-va-partial-detail-tolerance.md)).
`vaRuleId` is the VA rule identity; `bankRuleId` references a
distinct bank-account VA rule object and is never accepted as a VA rule ID. The
related bank-account rule detail (`bankAccountVaRule`) is out of scope and
never queried or merged.

The acquisition is one verified one-based `pageNo=1,pageSize=1000` request;
overflow, duplicates, invalid metadata or truncation fail with
`INCOMPLETE_RESULT` instead of speculative paging. 1000 rows is an observed
capacity at the current scale, not a server-side guarantee; no historical count
is hardcoded. A null or invalid live detail (`resultObj=null`) is
`INVALID_RESPONSE`, not proof of a missing record; only a confirmed absent ID
in a complete local snapshot is `NOT_FOUND`. `--require-complete` additionally
rejects a snapshot with refused details, and `get` on such a rule is
`INCOMPLETE_RESULT` — the rule exists, so its list row is never returned in
place of the detail.

List rows and true details stay distinct raw objects. List `countries` and
detail `creditAreas` keep their different names and are never merged or
equated. `vaWarningInfo` is optional; its contact details never enter fixtures,
logs or docs. The list exposes no filters; get selects only by ID. Stable-ID
sorting precedes display windows: ASCII digit IDs sort numerically with the
original string as tie-breaker, other IDs lexically afterward; stored string
IDs never change.

### Collection VA capacity

[Issue #36](https://github.com/proletariat64/dogopencli/issues/36) specifies the
collection VA capacity monitoring scope, implemented under
[Issue #38](https://github.com/proletariat64/dogopencli/issues/38) after the
contract verification in
[Issue #37](https://github.com/proletariat64/dogopencli/issues/37). Configure
`[sources.collection_va_capacity] kind = "cdp"`, then:

```bash
dogopencli help collection va capacity list
dogopencli describe collection va capacity list
dogopencli refresh collection va capacity
dogopencli collection va capacity list --all --require-complete
dogopencli collection va capacity list --va-rule-id RULE_ID
dogopencli collection va capacity list --bank-va-rule-id BANK_RULE_ID --live
```

Each row is one VA rule's capacity/warning projection; `ruleId` is the row
identity. `id`, `bankAccountVaId` and `accountNo` are not unique and are never
accepted as the identity; `--bank-va-rule-id` matches the `bankAccountVaId`
field. Filters are local exact matches over the acquired scope. The UI warning
state is not exposed: rows carry no warning-state field and the server
classification is volatile and not derivable from row counters.

Refresh pages the verified endpoint at `pageSize=1000` until the first short
page and publishes atomically only after the final converged `totalCount`, the
collected row count and unique `ruleId`s agree; interim page totals are
backend running estimates and are never trusted. Duplicate or drifting
identities, changed totals, malformed pages and every other failure preserve
the previous snapshot. Bare `refresh collection va` still refreshes VA rules.
Capacity counters are live values: check `meta.fetched_at`/`stale` and refresh
or use `--live` before acting on them. See
[ADR 0011](docs/adr/0011-collection-va-capacity.md).
