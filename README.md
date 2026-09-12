# Dogopencli

将产品运营网站的查询能力转为 Python CLI，供单机单人使用。v0.1.0 聚焦付款产品，收款产品不在本版本范围。所有业务操作仅查询，不创建、修改或审批任何生产配置。

Channel 后端故障期间使用显式离线替代源推进工程；正式 CDP 架构保持，真实 Channel 全量验收在后端修复后进行（见[规格 Issue #1](https://github.com/proletariat64/dogopencli/issues/1)、[ADR 0005](docs/adr/0005-channel-snapshot-source.md)）。Cost/SLA 始终走真实 CDP 路径。

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
```

配置示例见被 Git 忽略的 `tmp/channel-2026-09-11/source.toml`；整理集为私有数据，不随 Git 分发。

`cache.path` 仅支持具备可靠 SQLite WAL/共享内存与 POSIX `flock` 语义的本地 Linux 文件系统，推荐 WSL Linux 磁盘上的默认目录。Windows DrvFS/9p 挂载及网络文件系统不在缓存支持范围；无法启用 WAL 时明确失败，不降级为回滚日志。升级前若缓存位于这些挂载上，请改到支持的本地路径并重新刷新；旧库的来源路径列会自动迁移。

## 登录与认证

认证命令移植自 DI（基线 commit `8eb163c6d140554ca167bd50349a85ca224ac342`），独立运行不依赖已安装 DI；使用专用 Chrome profile（`~/.local/share/dogopencli/chrome/`）与 CDP 端口 9222，输出 `output_version` envelope，详见 [ADR 0004](docs/adr/0004-cli-runtime-boundaries.md)：

```bash
dogopencli login                # 人工 SSO（headed，默认等待 600 秒，--timeout-seconds 覆盖），完成后切回 headless 复验
dogopencli auth check           # 只读检查现有会话，不启动或修复浏览器
dogopencli logout               # 仅清理并验证专用本地认证；不撤销公司全局 SSO，不删业务缓存
```

## 刷新与查询

普通查询只读本地 SQLite 缓存，不隐式联网、不启动浏览器；缓存缺失明确失败。显式 refresh 才访问来源并原子发布缓存；失败或不完整保留旧快照。snapshot 查询不读取源 manifest 或数据文件，导入后源文件暂时不可用也能查缓存。缓存记录导入来源路径和 dataset_id；改路径或显式身份后必须刷新，同路径文件内容的变化在显式刷新时校验。旧缓存缺少来源路径时需要刷新一次：

```bash
dogopencli refresh payment channel    # snapshot：导入配置指向的整理集；cdp：真实采集
dogopencli refresh payment cost
dogopencli refresh payment sla        # 全列表 + 逐条详情一起原子发布

dogopencli payment channel list       # 默认场景 EXTERNAL，--payout-type 可选 LIQUIDITY/MANUAL/SETTLEMENT
dogopencli payment cost list          # 固定 FUND_OUT_CHANNEL_TRANS_FEE
dogopencli payment sla baselines list
dogopencli payment sla baselines get --id ID
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
| INCOMPLETE_RESULT | 替代集不覆盖后端全量；`--require-complete` 下不可用，去掉该标记可显式使用部分数据 |
| AUTH_REQUIRED | 会话失效；运行 `dogopencli login` |
| BROWSER_UNAVAILABLE | 专用浏览器不可达；运行 `dogopencli login` 恢复。连接的 Chrome 必须属于专用 profile；无法证明归属时拒绝复用或退出。Chrome 默认启用沙箱，不开放通配 WebSocket Origin，CLI 原生连接不发送 Origin 头；启动失败时检查 Chrome 日志，不自动关闭沙箱 |
| LOCKED | 另一刷新、SQLite 锁竞争或浏览器生命周期操作进行中；稍后重试 |
| CACHE_ERROR / IO_ERROR | 缓存数据库或本地文件操作失败；检查文件权限、磁盘和数据库，不按锁竞争处理 |
| INTERNAL_ERROR | 未预期的业务命令异常；错误关联号同时出现在 envelope 与 stderr，stderr 附异常类型及函数/行号。排查时保留 stderr；不输出异常文本、源代码行或局部变量 |
| SOURCE_SCOPE_UNAVAILABLE | 替代集仅覆盖 EXTERNAL；其他场景无数据，不伪造空列表 |
| LIVE_SOURCE_UNAVAILABLE | snapshot 来源不支持 `--live`；切换到 cdp 或改用缓存 |
| REQUEST_NOT_ALLOWED | 请求不在只读允许清单；属于防护行为，不开放任意请求入口 |

业务查询与 refresh 退出码：0 成功（含允许的部分/空列表）、1 运行失败、2 参数错误、130 用户中断；认证命令：0 成功/帮助/版本、1 参数或运行失败、130 中断。

## 未完成的外部验收依赖

安全参数变更后已用独立空 profile、CDP 9228 的真实 Chrome 验证：启用沙箱、不添加 `--remote-allow-origins` 时，无 Origin 的原生 CDP 连接成功执行 `1+1`；携带不可信 Origin 的连接被 HTTP 403 拒绝。本地证据目录为 `tmp/chrome-secure-smoke-tiwgh41d/` 与 `tmp/chrome-origin-check-gwlhhvs6/`（不随 Git 分发）。该检查仅覆盖连接通路。

- Channel 真实全量 UAT：待后端故障修复后执行（Issue #10），当前替代集明确标记 backend_complete=false，不代表生产全量。
- 认证 UAT（login headed/headless 交接、logout 范围）与 Cost/SLA 生产只读 UAT：待用户完成一次人工 `dogopencli login` 后执行；待办命令清单与验收证据见被 Git 忽略的 `tmp/acceptance-2026-09-11.md`。
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
