# Cash 与 Forecast 分页配置验证

Observed: 2026-10-01
Scope: general
Status: snapshot

## 配置与证据

| 已实现查询 | 正式请求 pageSize | 证据 |
| --- | ---: | --- |
| cash accounts | 5000 | 单页取得 3690 条，后端报告 3691；保留不完整状态 |
| cash waterlevels | 1000 | 空范围 0 条、有数据范围 1 条；各两次大页完整返回，与 10 条分页的记录内容一致 |
| cash statements intraday | 1000 | 空范围 0 条、有数据范围 5 条；各两次大页完整返回，与 10 条分页的记录内容一致 |
| forecast adjustments | 1000 | 两次大页完整返回 13 条；与 10 条分页的两页记录内容一致 |
| forecast cashflows | 不发送分页参数 | 原生请求没有 rowStart/pageSize，维持单次查询 |

这些值是各查询当前已接受的请求规格，不代表后端最大容量，也不证明未来数据规模下无截断。仍逐次校验总数、唯一身份及完整性。未支持的 cash/forecast 叶子保持延期状态。

页宽随各自 ListSpec 配置，采集 offset、页数预算、进度与结果元数据使用该页宽。其他 liquidity 叶子维持原有 10 条配置。通用大页失败后缩小分页的能力仍是后续事项，见[记录](2026-10-01-pagination-followups.md)。

## 账户部分结果兼容

账户列表完整性不足时，普通 live 查询和刷新返回实际取得的记录，同时输出 `complete=false`、`INCOMPLETE_RESULT` 错误、结构化 warnings 和 stderr 告警，退出码为 1。刷新不发布不完整缓存，保留旧完整快照；默认离线读取仍只读取既有缓存。`--require-complete` 保持严格拒绝，不返回部分 live 数据。没有将 3690 归一化为后端总数或把少 1 条当成成功；业务失败、身份内容冲突等继续拒绝。

私有验证汇总：`tmp/cash-forecast-page-probe-20261001T144649Z/summary.json`。这里只记录原有授权查询范围与计数，不公布生产参数值或记录。

## 正式代码复测

- 本地 liquidity 单元测试与 CLI SIT：89 项通过，包含每叶页宽、跨页 offset、账户短缺、部分数据投影/表格、非零退出、严格完整性拒绝及旧缓存保留。
- 生产只读复测：14 项符合预期；五个 waterlevels/intraday/adjustments 范围刷新及离线读取通过。账户 refresh、普通 live、严格 live 三项均按预期退出 1；前两项各一次 5000 请求返回 3690 条、报告 3691，并给出不完整告警；严格 live 拒绝返回数据。账户查询前后缓存哈希相同。
- Ruff、格式与 Doc Guard 通过；上述结果为本地验证，不是远程 CI。

正式复测私有汇总：`tmp/cash-forecast-formal-uat-20261001T145620Z/summary.json`。后端数量差异仍未修复，客户端兼容不代表源数据完整性通过。
