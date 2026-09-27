# Dogopencli

把产品运营平台的付款与收款查询带到终端。Dogopencli 面向单人、单机使用，
提供离线缓存查询、显式实时查询，以及适合脚本和 Agent 读取的 JSON 帮助与数据描述。
所有生产业务操作仅查询；登录管理专用本地浏览器，刷新写入本地快照。

## 快速开始

需要 Python 3.10+。实时查询还需要 Google Chrome、运营平台访问权限及人工 SSO 登录；
缓存查询、帮助和数据描述可以离线使用。缓存应存放在本地 Linux 文件系统上，
WSL 用户应使用 Linux 磁盘目录。

### 1. 安装

从 [Releases](https://github.com/proletariat64/dogopencli/releases) 下载 wheel，
在虚拟环境中安装。以下以 v0.1.12 为例，在下载目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./dogopencli-0.1.12-py3-none-any.whl
dogopencli --version
```

也可以在仓库根目录安装源码：

```bash
python -m pip install -e .
```

### 2. 配置一个查询来源

创建 `~/.config/dogopencli/config.toml`，先添加需要使用的能力。例如账户隔离规则：

```toml
[sources.collection_account_isolation]
kind = "cdp"
```

`cdp` 表示通过专用 Chrome 会话执行已验证的查询。其他能力的配置键见下表；
无需一次配置所有来源。

### 3. 登录、刷新、查询

```bash
dogopencli login
dogopencli auth check
dogopencli refresh collection account-isolation
dogopencli collection account-isolation list --require-fresh --require-complete
```

`login` 打开可见 Chrome，等待人工完成 SSO，随后切回无头模式并复验会话。
默认等待 600 秒，可用 `--timeout-seconds` 调整。`auth check` 只检查现有会话，
不会启动或修复浏览器。

之后可直接读取缓存，或明确要求实时查询：

```bash
dogopencli collection account-isolation list --currency GBP --all
dogopencli collection account-isolation list --live --all
```

示例中的币种、业务代码与 ID 应替换为实际返回值；示例筛选结果可以为空。

## 可以查询什么

下表命令均省略 `dogopencli` 前缀。配置键对应 `[sources.<键>]`，
除付款渠道的离线替代源外，使用 `kind = "cdp"`。

| 能力 | 查询命令 | 刷新命令 | 配置键 |
| --- | --- | --- | --- |
| 付款渠道 | `payment channel list` | `refresh payment channel` | `payment_channel` |
| 付款交易成本 | `payment cost list` | `refresh payment cost` | `payment_cost` |
| 付款 SLA 基线 | `payment sla baselines list` / `get --id ID` | `refresh payment sla` | `payment_sla` |
| 同行转账规则 | `payment rules same-bank-transfer list` | `refresh payment rules same-bank-transfer` | `payment_rules_same_bank_transfer` |
| 降本规则 | `payment rules cost-reduction list` | `refresh payment rules cost-reduction` | `payment_rules_cost_reduction` |
| 重试规则 | `payment rules retry list` | `refresh payment rules retry` | `payment_rules_retry` |
| 银存切换规则 | `payment rules bank-switch list` | `refresh payment rules bank-switch` | `payment_rules_bank_switch` |
| 收款交易成本 | `collection cost list` | `refresh collection cost` | `collection_cost` |
| 收款 SLA 配置 | `collection sla configs list` / `get --id ID` | `refresh collection sla` | `collection_sla` |
| 收款 VA 规则 | `collection va rules list` / `get --id ID` | `refresh collection va` | `collection_va` |
| 收款 VA 容量 | `collection va capacity list` | `refresh collection va capacity` | `collection_va_capacity` |
| 收款清算系统 | `collection clearing-system list` | `refresh collection clearing-system` | `collection_clearing_system` |
| 收款卡模板 | `collection card-template list` | `refresh collection card-template` | `collection_card_template` |
| 收款账户隔离规则 | `collection account-isolation list` | `refresh collection account-isolation` | `collection_account_isolation` |

只有表中标注 `get` 的能力提供独立详情。详情 ID 来自对应列表；VA 规则使用
`vaRuleId`，付款 SLA 与收款 SLA 使用 `id`。列表摘要不能代替详情。

付款成本固定查询 `FUND_OUT_CHANNEL_TRANS_FEE`，收款成本固定查询
`FUND_IN_CHANNEL_TRANS_FEE`。这些是成本配置，不是实际交易费用。
SLA 是配置目标，不是观测到账耗时。

银行账户 VA 规则是独立对象，因完整分页验证失败仍未实现，见
[#52 与阻塞证据](docs/research/general/2026-09-27-collection-bank-va-rule-blocker.md)。
VA 费用、VA 池、实体账户、余额及生产变更操作不在当前范围。

付款 flow 规则的真实详情存在身份不一致，#54 暂未交付，也未提供 list-only 替代；
见[复核证据](docs/research/payment/2026-09-27-payment-flow-rule-blocker.md)。PTR 单据查询尚未实现。

## 缓存、实时查询与刷新

| 操作 | 数据来源 | 是否更新本地缓存 |
| --- | --- | --- |
| 普通 `list` / `get` | 已发布的 SQLite 快照；不联网、不启动浏览器 | 否 |
| 查询加 `--live` | 当前 CDP 会话；失败不回退缓存 | 否 |
| `refresh …` | 配置的 CDP 或渠道 snapshot 来源 | 是，原子发布 |
| `help` / `describe` | 随安装包发布的命令与字段说明 | 否，也不读取配置或缓存 |

没有缓存时普通查询返回 `CACHE_MISS`。缓存默认有效期为 72 小时；默认允许读取旧数据，
但会标记 `stale`。需要时加 `--require-fresh` 或 `--require-complete`，不会因此自动刷新。
各能力及来源的快照相互隔离。

刷新通常只在完整校验通过后替换快照，失败保留旧数据。**VA 规则详情拒绝是一个例外**：
若后端明确拒绝单条详情，刷新可以发布真实列表行与 `detail=null` 的部分快照，
标记 `dataset_complete=false`，再以 `INCOMPLETE_RESULT` 失败退出。
此时旧详情可能被替换；`--require-complete` 会拒绝该快照，缺详情的 `get` 也会失败。
其他采集错误仍保留旧快照。详见 [ADR 0010](docs/adr/0010-collection-va-partial-detail-tolerance.md)。

显示分页不等于后端采集分页。收款成本、VA 规则、清算系统、卡模板及账户隔离规则
以及上述四项付款规则使用各自验证过的单页采集契约；超过 1000 条或覆盖校验失败会明确报错，不猜测下一页。
VA 容量采用已验证的多页采集与最终总数校验。`--limit` 不会放宽这些完整性要求。

账户隔离采集拒绝仅在后端筛选场景观察到的 null 列表／全零分页响应，避免把未知状态
发布为空快照；正确回显页码、页大小及零总数的空数组可以接受。见
[账户隔离契约](docs/research/general/2026-09-27-collection-account-isolation-contract.md)。

## 常用查询方式

所有列表默认输出 JSON，显示前 100 行，偏移量为 0。

| 选项 | 用途 |
| --- | --- |
| `--limit N --offset N` | 显示窗口；limit 必须为正整数，offset 为非负整数 |
| `--all` | 显示全部匹配行；与显式 `--limit` / `--offset` 冲突 |
| `--fields id,currency` | 仅保留指定顶层字段，保留选中的完整嵌套值和质量 metadata |
| `--format table` | 以表格阅读；默认 `--format json` |
| `--live` | 显式实时查询，不写缓存 |
| `--require-fresh` | 拒绝超过 TTL 的缓存 |
| `--require-complete` | 要求来源完整；VA 规则还要求详情完整 |

```bash
dogopencli collection sla configs list --currency USD --currency EUR --region US --all
dogopencli collection sla configs get --id CONFIG_ID
dogopencli collection va rules get --id VA_RULE_ID --live
dogopencli collection va capacity list --va-rule-id RULE_ID
dogopencli collection clearing-system list --currency GBP --format table
dogopencli collection card-template list --template-id TEMPLATE_ID --live
dogopencli collection account-isolation list --all --fields id,currency
```

### 收款筛选

以下筛选在缓存与实时查询中均使用本地精确字符串匹配：同字段重复值取 OR，
不同字段取 AND，区分大小写，`*` 按字面值处理。空值或纯空白参数会被拒绝，
有效值不裁剪、不标准化，缺失或 null 字段不会匹配。先筛选、排序，再应用显示窗口和投影。

| 列表 | 筛选参数 |
| --- | --- |
| SLA 配置 | `--business-line`、`--entity`、`--currency`、`--region` |
| VA 容量 | `--va-rule-id`、`--bank-va-rule-id` |
| 清算系统 | `--bank-location`、`--currency`、`--system-type`、`--system-name`、`--status` |
| 卡模板 | `--bank-location`、`--currency`、`--bank`、`--template-name`、`--template-id`、`--status` |
| 账户隔离规则 | `--opening-rule-id`、`--business-line`、`--business-region`、`--customer-group`、`--scene-code`、`--collection-region`、`--currency`、`--transaction-type` |

收款成本与 VA 规则列表没有领域筛选。收款刷新不接受筛选条件。
账户隔离的 `customerTags` 和 `currency` 可以包含逗号，需传入完整字符串，CLI 不拆分成员。
VA 容量的行身份是 `ruleId`；`--bank-va-rule-id` 匹配 `bankAccountVaId`，不是查询银行账户规则详情。
容量预警状态没有已验证的筛选选项。

付款 Channel、Cost 和 SLA 筛选的缓存与实时语义有所不同，以对应 `help` / `describe` 为准。
实时付款 Cost/SLA 每字段只接受单值；付款 SLA 的 `--biz-legal-entity` 仅支持实时透传，
其独立筛选效果未验证，缓存模式拒绝该参数。付款 Channel 默认范围为 `EXTERNAL`，
`--payout-type` 还支持 `LIQUIDITY`、`MANUAL`、`SETTLEMENT`。

### 付款规则筛选

四项规则在缓存和实时模式下都先完整采集，再本地筛选；同字段 OR、跨字段 AND，
区分大小写、保留空格、`*` 按字面匹配，空白参数拒绝。刷新不接受筛选。

| 列表 | 筛选参数 |
| --- | --- |
| 同行转账 | `--bank`、`--status` |
| 降本 | `--name`、`--business-line`、`--currency`、`--market`、`--status`、`--entity`、`--obo`、`--fvt` |
| 重试 | `--name`、`--status`、`--communication-mode`、`--integration-mode`、`--entity`、`--business-line`、`--bank`、`--currency`、`--region`、`--bank-account`、`--clearing-network` |
| 银存切换 | `--source-account`、`--source-network`、`--status`、`--target-account`、`--target-network` |

降本的主体/OBO/FVT、重试的主体/业务线/银行/币种/地区/银行账户/清算网络，
按原始字符串数组的成员精确匹配，不拆分逗号。OBO/FVT 不是布尔开关。
银存切换要求嵌套条件在同一适用条件、同一规则内成立，目标账户和网络必须属于同一目标；
返回整个来源节点，保留未匹配的子规则。降本列表是组摘要，不代表完整历史版本。

```bash
dogopencli refresh payment rules retry
dogopencli payment rules retry list --currency USD --currency EUR --all
dogopencli payment rules bank-switch list --source-account SOURCE_ACCOUNT --all
dogopencli describe payment rules cost-reduction list --format text
```

以上命令需先配置对应 `sources.payment_rules_*` 的 `kind = "cdp"`。
具体字段映射和证据见 `describe` 与[查询契约](docs/research/payment/2026-09-27-payment-rules-contract.md)。

## 帮助与导航

```bash
dogopencli
dogopencli help collection
dogopencli help collection account-isolation list
dogopencli collection account-isolation list --help
dogopencli help collection account-isolation list --format text
dogopencli describe collection account-isolation list --format text
```

无参数入口和分组命令提供逐层导航；叶子命令直接执行操作，需要帮助时加 `--help`
或使用 `help <路径>`。帮助默认 JSON，人工阅读可用 `--format text`。

### Data helper

`describe <查询路径>` 提供 JSON Schema、字段说明、来源证据和读取指引，不查询业务数据。
帮助输出使用 `help_version`；描述输出包含 `describe_version`、`schema_version`、
`capability`、`data_schema`、`read_guide` 和 `query_help`。两者直接返回文档对象，
不使用业务查询的 `data/meta/error` envelope。

Agent 或脚本应先读取 `help` 确认参数，再用 `describe` 判断字段含义。Schema 中
`x-evidence` 区分已验证、仅观察和未知事实；`x-observed-values` 不是封闭枚举。
保留缺失、null、空字符串、空数组及原始数值精度，不推断未验证的金额倍率、时间单位或跨域关联。
更完整的领域区别见 [CONTEXT.md](CONTEXT.md)。

## 读取查询结果

JSON 业务结果使用 `data`、`meta`、`error`。先检查退出码和 `error`，再使用数据。

| Metadata | 如何理解 |
| --- | --- |
| `source` / `backend` | 读取方式 `cache/live` 与来源类型 `snapshot/cdp` 是两个维度 |
| `fetched_at` / `stale` | 采集时间与缓存新鲜度；新鲜不等于完整 |
| `complete` / `dataset_complete` | 来源覆盖与数据集完整性；VA 详情拒绝、渠道替代集需分别解释 |
| `simulated` | 是否属于显式替代数据；不能把替代集当作已验证生产全量 |
| `matched_total` / `returned_count` / `has_more` | 当前可用来源中的匹配数与显示窗口，不证明生产覆盖 |
| `loaded_at` / `source_observed_from` / `source_observed_to` | 导入时间与原始观察时间；重新导入不会让旧观察变新 |

`--fields` 不删除质量 metadata。投影后的数据可能缺少 schema 中的必填字段，
应作为部分记录处理。`seqid` 是本地位置，不是跨快照身份；不同能力的 ID 也不是通用 join key。

业务查询和刷新退出码：`0` 成功、`1` 运行失败、`2` 参数错误、`130` 用户中断。
允许的部分结果也可能退出 `0`，因此需要检查质量字段或指定 `--require-complete`。
认证命令使用独立的 `output_version` envelope，参数和运行错误均退出 `1`。

## 配置与本地会话

| 内容 | 默认位置或值 |
| --- | --- |
| 配置 | `~/.config/dogopencli/config.toml` |
| 缓存 | `~/.local/share/dogopencli/cache.sqlite3` |
| 专用 Chrome profile | `~/.local/share/dogopencli/chrome/` |
| CDP 端口 | `9222` |
| 缓存 TTL | `72` 小时 |

配置路径优先级为：认证命令显式 `--config-dir`、`DOGOPENCLI_CONFIG_DIR`、
`DOGOPENCLI_CONFIG`、默认路径。前两者指定目录，`DOGOPENCLI_CONFIG` 指定文件。

可选缓存配置如下；路径请使用本机的实际绝对路径：

```toml
[cache]
path = "/home/YOUR_USER/.local/share/dogopencli/cache.sqlite3"
ttl_hours = 72
```

缓存依赖 SQLite WAL、共享内存及 POSIX 文件锁，不支持 Windows DrvFS/9p 或网络文件系统。
并发刷新返回 `LOCKED`，不会抢占活跃锁。专用 profile 同一时刻由一个 Chrome 进程持有；
不要与日常浏览器共用 profile，也不要使用 CDP 端口 9330–9340。

```bash
dogopencli logout
```

`logout` 清理并验证专用本地认证，不删除业务缓存，也不撤销公司全局 SSO。
Cookie、令牌、profile、私有快照及生产原始响应不得提交到 Git。

### 付款渠道的离线替代源

付款 Channel 的生产全量验收仍受后端分页问题阻塞，见
[Issue #10](https://github.com/proletariat64/dogopencli/issues/10)。可显式使用已整理的私有数据集：

```toml
[sources.payment_channel]
kind = "snapshot"
path = "/absolute/path/to/channel-dataset"
```

运行 `dogopencli refresh payment channel` 导入后，普通查询只读缓存。
数据集不随仓库分发，仅覆盖 `EXTERNAL`，不支持 `--live`，也不证明生产全量；
完整性标记保留这些限制。切回 `kind = "cdp"` 时移除 snapshot 专用的 `dataset_id`，
显式刷新并验证覆盖，不会自动回退。来源类型、路径或显式数据集身份变化后需重新刷新。
见 [ADR 0005](docs/adr/0005-channel-snapshot-source.md)。

## 故障处理

| 错误码 | 建议操作 |
| --- | --- |
| `CONFIG_ERROR` | 检查配置文件路径、对应 source 节和来源类型 |
| `CACHE_MISS` | 执行该能力的刷新命令；来源身份改变也需要刷新 |
| `CACHE_STALE` | 刷新，或明确允许旧数据后移除 `--require-fresh` |
| `INCOMPLETE_RESULT` | 检查覆盖或详情拒绝；VA 规则刷新可能已发布部分快照 |
| `AUTH_REQUIRED` / `BROWSER_UNAVAILABLE` | 执行 `login` 恢复专用会话；启动失败时检查 Chrome 日志 |
| `LOCKED` | 等待当前刷新或浏览器操作结束后重试 |
| `INVALID_RESPONSE` | 后端响应不符合已验证契约；保留错误信息并排查，勿视为空结果 |
| `SOURCE_SCOPE_UNAVAILABLE` / `LIVE_SOURCE_UNAVAILABLE` | 检查渠道替代集的范围及实时查询限制 |
| `REQUEST_NOT_ALLOWED` | 请求超出已验证查询允许清单，需要核查实现与契约 |
| `CACHE_ERROR` / `IO_ERROR` | 检查本地权限、磁盘和支持的文件系统 |
| `INTERNAL_ERROR` | 保留 stderr 与错误关联号，提交脱敏问题报告 |

## 未完成的外部验收依赖

- 付款 Channel 真实全量 UAT 仍待后端分页故障修复（[#10](https://github.com/proletariat64/dogopencli/issues/10)）；离线替代集不代表生产全量。
- 认证 UAT 的 `logout` 范围仍需单独确认；当前规则查询验收复用已有会话，未执行登出。
- launcher 安全参数变更后的完整生产连接复验仍待完成：用当前默认参数执行 `dogopencli login`，再执行 `dogopencli refresh payment cost`，验证应用会话和采集。此前独立空 profile 的真实 Chrome 检查只证明启用沙箱、未开放通配 Origin 时原生 CDP 可连接，且不可信 Origin 被拒绝；已有会话上的查询成功不能替代该流程。

## 开发与文档

在仓库根目录安装开发依赖并运行检查。仓库开发命令统一使用 `rtk`：

```bash
rtk proxy python -m pip install -e '.[dev]'
rtk pytest -q
rtk proxy ruff check .
rtk proxy ruff format --check .
rtk proxy make doc-guard test-doc-guard
```

业务插件位于 `src/dogopencli/plugins/payment/` 与 `src/dogopencli/plugins/collection/`；
认证、受限传输、缓存和输出由共享模块提供。测试使用公开 CLI、假 CDP 与临时 SQLite。
生产验收保持查询范围，并使用私有缓存。

- [文档索引](docs/README.md)：契约、研究、验收与架构决策。
- [领域词汇](CONTEXT.md)：付款、收款、VA 规则与账户对象的区别。
- [贡献约定](AGENTS.md)：代码、测试、浏览器及研究工作流。
- [GitHub Issues](https://github.com/proletariat64/dogopencli/issues)：需求、规格与缺陷。
- [Releases](https://github.com/proletariat64/dogopencli/releases)：安装包与版本记录。

契约与 UAT 报告记录特定日期、账号权限下的验证结果；生产行为变化后需要重新验证。
