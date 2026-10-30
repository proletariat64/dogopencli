# Leaf 开发

[手册](handbook.md) · [接口](interfaces.md) · [List SDK](../../docs/agents/list-collection-sdk.md) · [Get SDK](../../docs/agents/get-sdk.md) · [Custom SDK](../../docs/agents/custom-query-sdk.md) · [流程](workflow.md) · [批次](batches.md) · [Duckdog 导入](duckdog-import.md)

普通 List 使用宿主 SDK：leaf 声明 provider、分页和原生主键，只实现请求与解析；
宿主负责采集循环、重试、完整性及缓存发布。
已验证稳定位置及跨宽度顺序的编号／offset 查询可显式选择
`paging.termination: "short_page"`；宿主忽略后端 total／总页数，仍负责去重、
冲突检查及预算；短缺区间局部定位并绕过稳定 hole，连续两个大空批次才结束，
正常容错完成仍 exit 0 并带提示，按查询范围保留最新5次记录、仅验证复用最新一次。示例见 [VA capacity](../../leaf_packages/collection/va.capacity/)。
已单独确认整份响应覆盖范围但无原生 total 的 List，可声明 `single_response`；
已确认的多源关系声明 `sources`，由宿主完整采集各源后调用 leaf 的纯 `assemble`。
缺少 total 或发现相似字段本身不构成这两种声明的依据。
需要根据前一查询结果取得详情等依赖编排时，按操作显式选择 `execution: "custom"`；
leaf 用 Python 调用宿主命名查询工具，宿主共享请求预算并保留失败和采集证据。
声明、入口与覆盖责任见 [Custom SDK](../../docs/agents/custom-query-sdk.md)。
已验证的单自然日或时间点范围可通过 `operations.list.history` 显式启用共享时间能力，
standard/custom List 均可使用。leaf 决定公开日期／时间格式并负责双向转换；宿主自然日
只接受 `YYYY-MM-DD`，时间点只接受 UTC 毫秒 `YYYY-MM-DDTHH:mm:ss.SSSZ`。全量观察无需时间声明，现有参数不受该格式限制。
声明与限制见[有界历史](../../docs/agents/bounded-history.md)，
可执行示例见[日期范围](example-history/)。
Get 使用独立详情 capability，只实现原生请求构造和解析验证。已确认关联可声明
`list_binding`，让 `list --live --with-detail` 组合本次输出窗口的 List 行与详情；
Get 和组合查询不保存业务缓存，也不导入 Duckdog。完整契约见 [Get SDK](../../docs/agents/get-sdk.md)。

1. 读[手册](handbook.md)，用 [leaf-relations helper](../../.agents/skills/leaf-relations/SKILL.md)
   轻扫描 PDKB、当前前端和少量只读查询，提议本次范围是 simple 还是 complex。
   人确认后形成 spec／sample，并明确选择继续开发或结束研究；历史 UAT 可复用但非依赖。
2. 按[接口](interfaces.md)选择最小样例实现并测试：
   [List+Get](example/)、[Get-only](example-get-only/)、
   [单响应无 total](example-single-response/) 或[独立多源](example-sources/)。
3. 使用 `leaf.py` 校验／打包，再对同一 ZIP 做隔离安装和真实验收。
4. 批次迁移另读[流程](workflow.md)；显式数据导入另读[导入契约](duckdog-import.md)。

只有一个工具 `leaf.py`，从仓库根目录运行：

```bash
rtk proxy uv run python tools/leaf-dev/leaf.py --help
rtk proxy uv run python tools/leaf-dev/leaf.py verify tools/leaf-dev/example
rtk proxy uv run python tools/leaf-dev/leaf.py pack tools/leaf-dev/example --output /tmp/leaf-delivery
```

| 命令 | 用途 |
| --- | --- |
| `verify` | 静态校验目录或 ZIP，不执行 adapter |
| `pack` | 一个或多个 leaf → 新目录，含 ZIP、SHA256SUMS、delivery.json |
| `host-check` | 检查已安装宿主与源码是否一致；使用该宿主的 Python |
| `http-smoke` | 下载一次、核对 ZIP SHA256、本地安装并卸载；不查业务 |
| `capture` | 私下保存原生响应和 CLI 结果；会执行指定查询 |
| `compare` | 比较两份 JSON 的完整值、类型和数组顺序 |
| `batches` | 检查批次清单并显示进度 |

各命令用 `--help` 查看参数。打包不构建宿主、不安装、不做业务验收。

样例的 `.invalid` 接口只在 fake CLI 测试运行：普通 List/Get 见
`tests/integration/test_leaf_handbook.py`，单响应／多源见
`tests/integration/test_leaf_sdk_shapes.py`；日期范围见
`tests/integration/test_leaf_calendar_handbook.py`。多源样例明确将 `child.parentRef`
归到 `parentRef` 根下，各源保留独立 scope、total、子记录顺序和完整值；
这是样例的已确认关系，不是 SDK 的自动关联规则。
