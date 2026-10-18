# Leaf 开发

开发独立 leaf 的统一入口。从仓库根目录执行命令。

- [开发手册](handbook.md)：从可运行样例开始。
- [接口契约](interfaces.md)：manifest、adapter 和共享宿主边界。
- [开发与验收流程](workflow.md)：宿主复用、隔离、业务验收和 HTTP 交付。
- [样例](example/)：合成接口，不连接生产。
- [批次与票据](batches.md)：任务范围；[机器清单](batches.json)。
- [Duckdog 导入](duckdog-import.md)：支持范围与读回规则。

工具：[`plugin_helper.py`](plugin-helper.md) 做静态校验和确定性打包；
`leaf_migration.py` 提供 `host-check`、`pack`、`capture`、`compare`、`http-smoke`、`batches`。

```bash
rtk proxy uv run python tools/leaf-dev/plugin_helper.py --help
rtk proxy uv run python tools/leaf-dev/leaf_migration.py --help
```
