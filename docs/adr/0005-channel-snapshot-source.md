# Channel 故障期间采用显式离线替代源，保持正式查询架构

Status: accepted
Date: 2026-09-11

用户确认 Channel 经常查询失败属于后端故障，并决定用此前导出整理成的本地数据源推进工程，后端修复后切回。接受此决定；不要求继续生产复现作为实现前置条件。具体后端代码根因未在本仓库独立审计，历史研究保留原观察结论。

本 ADR 调整 [ADR 0003](0003-local-query-snapshots.md) 的缓存发布边界和 [ADR 0004](0004-cli-runtime-boundaries.md) 的交付验收边界：允许完整载入已知不覆盖全后端的、显式标记的 Channel 离线替代集；只在独立来源命名空间发布，不放宽真实 CDP 完整快照的要求。该阶段不阻塞工程交付，真实 Channel 全量 UAT 后置。

## 数据整理与身份

输入为每页 50、10、100、1 条四轮导出的 `records.jsonl` 和对应 `manifest.json`。先验证文件、场景、行数、来源时间、seqid 和逐页编号区间，再移除旧 seqid，按完整 JSON 内容去重：对象键顺序不参与比较，数组顺序、字段差异及版本均保留。不依靠 abilityId、账户或名称合并，不选择“最新一条”覆盖其他观察；数值不经过浮点转换。

不同内容按内容哈希确定顺序，重建 seqid=1…N，作为该数据集内部主键；输入目录排列不改变结果。seqid 不代表源系统主键，也不跨数据集关联。每条整理后的记录通过独立 provenance 文件关联所有来源文件、旧 seqid 及页码。manifest 记录内容哈希、原观察时间范围、构建时间、源失败页及原总数。发现同业务标识不同内容时保留，不静默裁决版本冲突。

这是一份跨多轮观察整理的固定开发基线，不是某一时刻的生产快照，也不能把历史总数 4914 写为其有效行数。`dataset_complete=true` 表示完整包含整理集；`backend_complete=false` 表示后端覆盖未通过。不从统计数据生成原始行，不给空缺数据造假。

源分页完整性独立记录为每个 source 及汇总 manifest 的 `source_pages_complete`：必须无失败页、总数稳定、页号连续且每页行数与总行数闭合；汇总值要求每轮均通过。缺页或失败页不阻止使用整理集 mock，重复或非法页号则拒绝整理。此字段仅证明分页账目闭合，不证明去重后的后端覆盖；旧整理集没有该字段时视为未验证。`dataset_complete` 根据整理行及来源引用计数校验得出，不能由源失败页直接替代。

单轮真实 CDP 采集中，同 `abilityId` 出现不同内容会使 `complete=false`，即使总行数闭合也不得刷新覆盖旧缓存。实时查询保留两种内容并标记不完整，`--require-complete` 失败。该一致性检查独立于完整内容去重，不把 abilityId 升格为主键，也不改变跨轮历史整理集保留版本的规则。

[离线整理工具](../../scripts/prepare_channel_snapshot.py)不联网，不能覆盖已有目录。包含 records、provenance、manifest 三个文件；原始业务数据不进入 Git、日志或公共 fixture。

2026-09-11 用户进一步明确使用本仓库 `tmp/`，而非系统 `/tmp/`。按此覆盖此前“必须位于仓库外”的路径约定：真实导出与整理集可以写入已被 Git 忽略、权限受限的 `<repo>/tmp/`，继续拒绝仓库内其他目录；仓库外私有路径仍可配置。`.gitignore` 的 `/tmp/` 必须保持生效。浏览器 profile 使用持久私有目录，系统临时目录不再作为本轮数据归档位置。

## 替身放在传输边界

```text
公开 CLI → Channel 插件 → 统一查询校验 → QueryTransport
                                      ├─ CDP：正式后端
                                      └─ Snapshot：本地替代集
           同一响应解析 ← 相同成功响应结构 ←─────┘
           → 同一筛选、排序、缓存和输出逻辑
```

QueryTransport 接收已注册的 host/path/method/body 查询请求，返回 HTTP 状态、JSON 正文及独立来源元数据。SnapshotTransport 只支持已选 Channel 查询契约，拒绝其他动作；无浏览器依赖。它按已验证参数筛选和分页，用数据集真实 N 产生 totalCount/totalPages，返回与后端相同的成功 envelope，交给正式 parser。seqid 属于本地导出层；生成模拟响应时移除该字段，输出层按固定数据集顺序恢复编号。

不把清洗后的列表直接塞进 CLI、不绕过 parser 或完整性校验，也不把故障响应录制成日常 mock 的默认行为。错误、重叠、回显钳制等另用合成测试响应验证。CDP 实现仍按正式接口编写，Channel 100 条分页不变；Cost、SLA 不切换替身。

配置按能力选择：本阶段 `sources.payment_channel.kind="snapshot"`，`path` 指向上述数据集；其他能力为 cdp。修复后把 Channel kind 改为 cdp 即可，不修改 CLI、插件、parser 或缓存业务流程。无自动故障回退至替身；配置与数据集必须显式存在。

## 命令及可观察行为

| 操作 | Snapshot 模式 |
| --- | --- |
| `refresh payment channel` | 读文件、校验哈希与 N、经模拟分页和正式 parser 完整载入本地替代集，不访问 Chrome |
| 普通 `payment channel list` | 仅查当前来源缓存，支持原有本地筛选、展示分页及 fields；默认按本地 seqid 排序 |
| `--live` | 返回 LIVE_SOURCE_UNAVAILABLE；不把历史文件冒充实时后端 |
| `--require-complete` | 因后端覆盖未验证而失败，不能用 dataset_complete 绕过 |
| `--require-fresh` | 使用原始观察时间及 72 小时 TTL，重建或重载不延长新鲜度 |
| 非 EXTERNAL 场景 | 返回 SOURCE_SCOPE_UNAVAILABLE；保留正式场景契约，不复制 EXTERNAL 数据冒充其他场景 |
| 文件缺失、校验失败 | 返回 SOURCE_DATA_MISSING / SOURCE_DATA_INVALID，不返回空成功或自动联网 |

SQLite 以能力、场景、source_kind 区分当前缓存；每个命名空间只保留一份当前快照，dataset_id 记录在元数据，不建立多代历史服务。不同 kind 的快照不可互相读取或覆盖；配置的 dataset_id 与缓存不符时要求刷新。缺失新数据、导入失败均不发布新缓存。多个来源空间只为安全切换，不能将旧 CDP 与替代行合并补数。

标准 meta 增加 `backend`、`simulated`、`dataset_id`、`dataset_complete`、`source_observed_from/to`。已有 `complete` 始终指后端范围完整性，替代源为 false；source 仍区分 cache/live。table 也必须显示替代来源、历史时间及不完整标记，fields 不隐藏质量信息。采集时间与导入时间分别保存；stale 对最早的源观察时间计算，不能伪造新鲜度。

## 工程与验收

1. 工程交付：真实 CDP 路径和替代路径均实现；公开 CLI 的正常成功行为通过替代源驱动，异常通过合成响应驱动；Cost/SLA 保持原生产只读验收。Channel 缺少真实后端全量验收不再阻塞该阶段。
2. 替代数据验收：真实导出清洗通过、所有来源可追溯、编号连续唯一、同内容去重且版本不丢失；导入/离线查询/来源隔离/新鲜度标记符合规定。此验收不能由合成样例冒充。
3. 修复后：先显式选择 cdp，在 CDP 命名空间执行登录、分页、总数、重复及完整覆盖 UAT。成功后发布真实完整缓存并停止选用替代集；失败则保持验收未通过，回退须显式选回 snapshot。后端数据以当前真实结果为准，不要求等于历史替代集 N。

只有第三项通过才可声明 Channel 真实后端全量可用。真实 UAT 后置是已接受的范围决定，不是工程尚未完成的功能。
