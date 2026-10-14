# Duckdog v0.1.0：初始设计

日期：2026-10-14。状态：初始规格；settings 导入 helper 的本地验证与生产导入分别验收。

规格登记：[GitHub Issue #160](https://github.com/proletariat64/dogopencli/issues/160)。

## 目标与范围

沿用 [CONTEXT.md](../../CONTEXT.md) 的 duckdog 定义：独立的数据集与分析层，负责导入、保存、合并和查询在线 JSON。遵循 [ADR 0020](../adr/0020-temporary-query-cache-and-duckdog.md)，dogopencli 负责只读查询，临时缓存不作为导入源。

初期导入 `liquidity/reference/banks`、`liquidity/reference/entities`。用户已选择下线的 calendars、ledger accounts、business-lines 不纳入导入清单。Runtime 共用存储结构，其采集范围、分区和历史规则另行定义。

## Selector 与存储

Selector 按业务 list leaf 路径组织，去掉 `dogopencli` 前缀和末尾 `list`。来源应用、domain、leaf、契约和采集命令作为元信息。

```text
<dataset-root>/
  duckdb/duckdog.duckdb
  parquet/liquidity/reference/banks/<generation>.parquet
  parquet/liquidity/reference/entities/<generation>.parquet
  parquet/<runtime-selector>/<已验证业务日期分区>/...
```

默认私有目录为 `<dogopencli 仓库>/duckdog-data/`，已排除出 Git；允许明确指定其他目录。借鉴 DI 的 `data/duckdb`、`data/parquet` 组织方式，不修改 DI 数据。初期一个 DuckDB catalog；业务记录存 Parquet，DuckDB 提供登记与查询视图。

| Selector | DuckDB 当前视图 | 来源记录唯一键 | 下游标识 |
| --- | --- | --- | --- |
| `liquidity/reference/banks` | `liquidity_reference_banks` | `bankId` | 银行属性 |
| `liquidity/reference/entities` | `liquidity_reference_entities` | `id` | `instId`、`instCode`、`state` |

`instId` 用于主体查询；`instCode` 在现有数据中不唯一，不能据此去重。现有 ANY 读取的 selector 已是 `liquidity/reference/entities`，映射到上述视图的 `instId` 列。导入保留全部状态；如只选 VALID，须另行明确选择政策并配置视图。

## 采集与 JSON 保真

Settings 使用 `dogopencli <leaf> list --live --limit 0 --offset 0 --require-complete --format json`。要求命令成功、source 为 live、simulated 为 false、capability 对应、范围未筛选、complete 为 true、has_more 为 false，且采集／匹配／返回／报告数量与记录数一致。`limit 0` 仅控制输出，不扩大后台采集范围。

`.data` 为完整业务对象，`.meta` 为采集质量与来源信息，分别保存。保留原生字段、未知字段、嵌套对象、标识字符串、金额精度和 null／空字符串／零的区别，不推断来源时间单位或时区。

初期 Parquet 保存 `_row_order` 和 JSON `record`；DuckDB 视图暴露完整 `_record` 及常用原生标识字符串列。其他字段可从 `_record` 查询，新增类型转换须有明确契约。Runtime 后续增加可供分区和分析的类型化列，同时保留原始 JSON；settings helper 不承担大体量 runtime 导入。

`_duckdog_datasets` 每个 settings selector 只保留一条当前登记：kind、视图、Parquet 路径、记录数、内容哈希、来源采集时间、导入时间与完整 acquisition metadata。元信息包保存 application、domain、leaf、采集命令和原始 `.meta`。记录修改时间属于业务数据，不能用采集时间替代；认证数据不入库。

## Settings 全量覆盖

每次完整成功采集替换整个当前数据集，不逐行更新、不合并、不积累历史。完整空结果覆盖为零条；失败、partial、截断或筛选结果不替换。

先验证并写入新 Parquet，核对数量，再于一个 DuckDB 事务中切换视图和登记。相同内容可复用当前文件并更新采集元信息；拒绝较旧采集覆盖较新采集，同一采集时间的不同内容也拒绝。目录采用单写入者锁，外部 DuckDB 读写遵循其文件锁限制。

提交前失败保留旧视图和登记、清理候选文件。提交后只清理该 leaf 未被引用的旧 generation，不保留 settings 业务历史。进程中断可能留下孤立文件，下次成功替换清理；清理失败报告 pending cleanup，不将已提交的数据误报为导入失败。不宣称断电情况下的文件持久性保证。

## Runtime 扩展

保持相同 selector、DuckDB＋Parquet、来源质量元信息。每个 runtime leaf 先定义业务日期分区键、原生唯一键或观测保留规则、日期／主体范围，以及同范围重采集的替换或去重规则。不能用采集日期代替业务日期；不默认做无条件 append。大批量数据采用有界批次采集和导入，避免整库 JSON 常驻内存。历史保留政策按 leaf 定义，初版不实现通用 runtime importer。

## Skill 与验收

[duckdog-import](../../.agents/skills/duckdog-import/SKILL.md) 支持上述两个 settings selectors，可主动执行 live 查询，或消费已确认来源的完整 live JSON 文件；不增加核心 CLI 业务写命令。

验收：Parquet 回读数量正确；JSON 精度、未知字段和嵌套数据保留；重复导入不增加重复记录；全量替换只保留当前文件；完整空结果清空；不完整、错误来源、筛选结果、重复唯一键和较旧采集不替换；发布事务失败保留旧数据。合成验证使用临时目录；真实导入与 ANY 配置另行验证。

实现依据：[DuckDB JSON](https://duckdb.org/docs/current/data/json/loading_json)、[Parquet](https://duckdb.org/docs/current/data/parquet/overview)、[事务](https://duckdb.org/docs/current/sql/statements/transactions)。
