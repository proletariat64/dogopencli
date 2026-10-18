# Leaf 开发

[手册](handbook.md) · [接口](interfaces.md) · [流程](workflow.md) · [样例](example/) · [批次](batches.md) · [Duckdog 导入](duckdog-import.md)

普通 List 使用宿主 SDK：leaf 声明 provider、分页和原生主键，只实现请求与解析；
宿主负责采集循环、重试、完整性及缓存发布。

1. 读[手册](handbook.md)，核对 PDKB／历史 UAT 中有依据的查询范围。
2. 按[样例](example/)和[接口](interfaces.md)实现并测试 SDK leaf。
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
