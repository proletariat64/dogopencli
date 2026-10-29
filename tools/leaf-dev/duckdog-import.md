# Duckdog 显式 settings 导入

查询与 refresh 管理安装绑定及临时查询缓存，不自动导入。
宿主的 [workflow](../../docs/agents/export-import-workflow.md) 可显式保留完整导出为 scoped observation；
它复用已注册目标，不改变当前 `_record` 表，也不使用下述外部 helper 的来源名单。
本文其余部分仅说明独立 settings helper。
refresh 与 adapter 不导入数据。外部 settings helper 仅在任务明确要求导入时运行；
它和宿主的 `_record VARCHAR` 安装表是不同的所有权边界。

## 来源契约

先查看已安装 leaf 的 help/describe，再采集完整、未筛选的真实 live JSON：

```bash
dogopencli liquidity list <dotted-leaf> --live --limit 0 --require-complete --format json
```

来源必须为真实 live CDP；`meta.leaf` 匹配 dotted identity，`meta.operation="list"`。
不接受旧 capability envelope、缓存、get、模拟、截断、筛选或不完整来源。
记录数、公开计数、原生身份唯一数及 acquisition evidence 必须一致；未知身份/覆盖语义
不能升级为完整。完整原始 metadata 与 JSON 类型、数值、嵌套和未知字段原样保存。

当前 helper 经已验证补丁支持以下九个独立迁移包的 installed-leaf envelope：

| Selector | 原生身份 |
| --- | --- |
| `liquidity/reference/banks` | `bankId` |
| `liquidity/investment/benchmarks` | `id` |
| `liquidity/rules/forecast` | `ruleId` |
| `liquidity/rules/action_mapping` | `id` |
| `liquidity/rules/funding` | `id` |
| `liquidity/rules/fx_settlement` | `id` |
| `liquidity/rules/operation` | `ruleId` |
| `liquidity/rules/realtime` | `id` |
| `liquidity/risk/thresholds` | `benchmarkId` |

每个 selector 都须由当前 helper 的显式契约支持，不从相似名字推断支持。
`liquidity.reference.entities` 当前包以 `instId` 为身份；外部 helper 的 entities
声明仍要求旧 envelope 和 `id`，不在上述九项 installed-leaf allowlist 中。
当前 entities 输出不能据此宣称可导入，需另行适配与验证；安装时空表初始化不证明导入支持。
九个独立迁移包的 host `scope=""`、`query={}`；原生范围仍由各包定义。
forecast 固定 `instId=["Z21"]`，benchmarks 保留空原生日期边界；
这些输出不证明其他主体或日期的全量范围。银行 country 筛选结果不能覆盖完整目录。

## 发布与验收

settings/reference 使用当前数据集全量替换，不累积历史、不逐行合并。
完整空来源可以覆盖为空；失败、不完整、重复身份、旧采集或矛盾 metadata 保留旧数据。
一个 writer 独占数据根目录；先写并校验 Parquet generation，再在 DuckDB 事务中切换
视图与登记，成功后清除该 selector 无引用 generation。提交后清理失败单独报告，
不把已提交结果误报为导入失败。不宣称断电持久性。

Parquet 保留完整 JSON；视图暴露字符串身份列与 `_record`。
导入后回读 DuckDB、Parquet、计数、metadata 和逐条记录；日期、金额、类型与身份
多重性都需匹配真实来源。`--input` 文件需要可核验的来源和范围，不能用临时缓存替代。

外部 helper 属于本机独立工具，可能未分发到新工作树；缺失时报告并按批次工具指导准备。
当前 helper 的契约与补丁验证以 [迁移流程](workflow.md) 为入口；
不得为支持新 envelope 合成或改写原始 metadata。新增 runtime 导入须另有业务日期分区、
身份和重采集策略，settings helper 不推定这些能力。
