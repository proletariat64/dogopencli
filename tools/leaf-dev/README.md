# Leaf 开发

[手册](handbook.md) · [接口](interfaces.md) · [流程](workflow.md) · [样例](example/) · [批次](batches.md) · [Duckdog 导入](duckdog-import.md)

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
