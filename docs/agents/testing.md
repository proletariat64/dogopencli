# 测试组织

测试按当前宿主契约和 leaf 业务归属组织，文件名使用能力名称，不使用迁移批次或工单编号。

| 目录 | 覆盖责任 |
| --- | --- |
| `unit/` | 纯解析、参数与身份验证、采集策略、缓存及传输边界 |
| `integration/` | 离线公共 CLI、鉴权编排、SDK、插件和样例契约 |
| `integration/leaves/payment/` | Payment leaf 的原生请求、响应与查询行为 |
| `integration/leaves/collection/` | Collection leaf 的原生请求、响应与查询行为 |
| `integration/leaves/liquidity/` | Liquidity leaf 的原生请求、响应与查询行为 |
| `imports/` | 当前受支持的外部 Duckdog settings 导入契约 |
| `fixtures/` | 脱敏输入和外部 helper 的补丁验证基准 |
| 根目录 `test_*.py` | 宿主配置、发现、安装、交付、GUI 和公开输出 |

`integration/` 及子目录继承离线约束：使用 fake CDP，禁止实际网络和浏览器进程启动。
这些测试不证明生产认证或业务 UAT 通过。

## 运行

```bash
rtk proxy make test
rtk proxy .venv/bin/python -m pytest tests/integration/leaves/payment -q
rtk proxy .venv/bin/python -m pytest tests/imports -q
rtk proxy .venv/bin/python -m pytest -n 0 tests/unit/test_cache.py -q
```

默认八个 worker；`-n 0` 用于串行调试。修改单个契约时先运行负责该契约的测试，
公共宿主或结构调整完成后运行全量。

## 覆盖与隔离

- directory 和 ZIP 的交付覆盖集中在安装生命周期用例；安装后的参数、解析、
  请求限制和失败矩阵默认使用 directory。交付格式新增独有行为时才扩大对应矩阵。
- 不适用的 leaf/操作组合在参数化时排除，不先安装插件再跳过。
- 保留原生身份、精度、顺序、分页、完整性、失败原子性和缓存保护等业务断言。
  测试体相同但 leaf 契约不同，不等于重复覆盖。
- 配置、数据库、已安装插件和 fake transport 逐用例隔离；共享 fixture 只复用
  不可变构建结果或纯 helper。外部 settings helper 每 worker/session 准备一次，
  发布目录仍逐用例创建。
- 删除旧基线的辅助代码时，同时删除其专属测试；仍受支持的业务契约先迁入当前测试，
  不保留旧 CLI 或旧 envelope 的运行兼容路径。
