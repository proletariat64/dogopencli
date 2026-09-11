# Channel 离线替代源的输入核对与整理状态

Observed: 2026-09-11
Scope: payment
Status: snapshot

## 当前决定

用户确认故障属于后端，并要求将历史导出整理为 Channel 替代数据源，继续原设计的实现工作。正式边界见 [ADR 0005](../../adr/0005-channel-snapshot-source.md)，最终产品规格继续保存在 [Issue #1](https://github.com/proletariat64/dogopencli/issues/1)。

## 输入可用性

本轮初次核对发现下列临时目录均已不存在；在 `/tmp`、本仓库和默认 `~/.local/share/dogopencli/` 中未找到相应 records/manifest 副本。用户随后确认系统崩溃导致丢失，授权多个低成本子代理重新采集，并指定使用仓库 `tmp/`。旧文件没有恢复；下节是重新查询得到的新数据，不是对历史快照的重建。

| 原始导出 | 历史行数（非本轮重验） | 原目录 |
| --- | --- | --- |
| pageSize=50 | 2914 | `/tmp/dogopencli-channel-export-bob78hme/` |
| pageSize=10 | 4184 | `/tmp/dogopencli-channel-export-o5ov_hay/` |
| pageSize=100 | 1814 | `/tmp/dogopencli-channel-export-r4pli_z3/` |
| pageSize=1，前 50 页 | 48 | `/tmp/dogopencli-channel-export-dwzhz_cf/` |

四轮历史原始行数合计 8960，前三轮历史内容并集为 3782；这些历史统计未用于生成本轮数据。重新采集已完成，不再等待旧文件备份。

## 重新采集与整理结果

主线程恢复专用 headed Chrome（CDP 9222，持久 profile），用户人工登录后，以实际只读查询确认会话有效。三个 Luna 子代理分工采集：每页 10 条、100 条分别完整尝试遍历；第三个代理依次采集每页 50 条全部页和每页 1 条的前 50 页。未改动业务数据或自动修复故障。

| 每页条数 | 尝试页数 | 成功 / 失败页 | 实际原始行数 | 耗时 |
| --- | --- | --- | --- | --- |
| 10 | 494 | 426 / 68 | 4252 | 263.95 秒 |
| 50 | 99 | 59 / 40 | 2932 | 58.36 秒 |
| 100 | 50 | 19 / 31 | 1832 | 30.96 秒 |
| 1 | 前 50 页 | 50 / 0 | 50 | 25.05 秒 |

本轮成功响应报告总数为 **4932**，不再是历史 4914；每页 1 条的前 50 页全部成功也不代表故障已修复。不同采集并行进行，来源观察时间为 2026-09-11 06:25:05–06:28:25 UTC，不是原子生产快照。

全部原始导出位于 `<repo>/tmp/channel-2026-09-11/exports/`。目录后缀与分页规模对应：

```text
10  → dogopencli-channel-export-orzd65d7
50  → dogopencli-channel-export-h9ax5a4a
100 → dogopencli-channel-export-0gchpiae
1   → dogopencli-channel-export-xj5vjr49
```

清洗结果位于 `<repo>/tmp/channel-2026-09-11/dataset/`：输入 **9066 行**，去除 **5232 行完全重复内容**，保留 **3834 行**，seqid=1…3834。records 保存全部业务字段，provenance 保留去重前每一行的来源，manifest 保存哈希与原始观察信息。

独立子代理核验通过：三个输出文件哈希及 dataset_id 匹配，3834 个 seqid 连续唯一，9066 条来源均能映射回原始行，业务字段比较零差异，完整内容无剩余重复，四个源文件摘要匹配。文件均为 0600、目录为 0700，Git 忽略已核对。

```text
dataset_id = 78d4be99f233c45e05233f2fc32ab9870328fdcbcbdc5c372f1f8e6639801d9e
dataset_complete = true
backend_complete = false
simulated = true
```

`source.toml` 示例位于 `<repo>/tmp/channel-2026-09-11/source.toml`，已指向该整理集。它是后续实现可使用的配置示例，当前尚无业务 CLI，不宣称已经接入或通过端到端 SIT。真实数据准备依赖已经解除，工程可直接使用本数据集开发替代源。

## 已交付的离线整理工具

[prepare_channel_snapshot.py](../../../scripts/prepare_channel_snapshot.py)读取导出目录，验证输入清单，去除旧 seqid 后按完整内容去重，保留不同内容及版本，生成新的连续编号和逐条来源。按用户追加要求，输出可位于被 Git 忽略的仓库 `tmp/`，也支持仓库外私有目录；拒绝仓库内其他路径，不覆盖已有数据集。

其他输入整理时可按以下形式执行；目标必须是尚不存在的新目录：

```bash
rtk proxy python3 scripts/prepare_channel_snapshot.py /path/to/export-50 /path/to/export-10 /path/to/export-100 /path/to/export-1 --output /path/outside/repository/channel-dataset
```

输出包含 `records.jsonl`、`provenance.jsonl`、`manifest.json`。查询适配器加载时必须验证哈希、数量及 manifest，文件缺失或损坏不可发布。manifest 标记 `dataset_complete=true,backend_complete=false,simulated=true`；本工具不导入缓存、不联网、不生成生产就绪证明。

合成输入验证覆盖精确去重、版本与 Decimal 精度保留、seqid 连续、来源追溯、输入顺序不影响结果、重复输入不重复计数、错误场景/缺失输入拒绝及现有目录不覆盖；追加测试覆盖仓库 tmp 允许而其他仓库路径拒绝。真实数据已按上述步骤整理，文件权限为 0600、目录为 0700，Git 忽略规则已生效。数据集覆盖仍明确不完整，不因清洗成功而改为后端全量。
