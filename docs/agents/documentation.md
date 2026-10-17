# 代码与文档目录规范

宿主使用 `src/dogopencli/`，负责中立协议、认证、传输、安装、缓存和渲染。
`src/dogopencli/leaf_packages/<domain>/<dotted-leaf>/` 是显式安装的 bundled 资源；
根目录 `leaf_packages/<domain>/<dotted-leaf>/` 是单独交付的迁移包，不进入宿主 wheel。
每个 adapter 自行拥有原生请求、解析、身份、过滤和采集策略。
`examples/leaf_simple/` 提供合成示例，`tests/` 保存公开 CLI 和共享宿主测试。

Python 使用四空格缩进、类型注解、`snake_case` 模块/函数和 `PascalCase` 类。
测试文件名为 `test_<module>.py`，使用项目 pytest/Ruff 配置。

## 当前文档归属

| 位置 | 内容 |
| --- | --- |
| `README.md` | 安装和可运行命令入口 |
| `AGENTS.md` | 任务规则与有条件读取的指南指针 |
| `CONTEXT.md` | 业务术语，不记录实现过程 |
| `docs/README.md` | 当前指南导航 |
| `docs/agents/<slug>.md` | 当前契约和操作方法，每项规则有一个维护位置 |
| Leaf `README.md` / `leaf.json` | 包内说明 / 机器声明及 CLI、GUI 文档 |
| GitHub Issue | 需求、规格、范围、验收与执行状态 |

直接更新当前指南。删除失效规则、重复副本和失去用途的文档，并修复引用；
不在仓库维护旧设计、决策过程、版本过程或验收日记的归档副本。
已安装帮助和参数优先从公开 CLI 读取，避免在指南缓存易变清单。

## 数据与格式

私有导出写入授权范围内被 Git 排除的目录；仓库 `tmp/` 适合保存任务证据，
显式配置的私有 Duckdog 目录也可使用。私有目录0700、数据文件0600。
认证、profile、真实响应、缓存、数据集和构建产物不进入 Git 或公共日志。

Markdown 使用 UTF-8、一个 H1、末尾换行，文件名使用小写英文、数字、连字符；
README/AGENTS/CONTEXT 等入口名和现有 leaf identity 目录为例外。
仓库文件使用相对 Markdown 链接；外部资料使用 HTTPS；本机私有资料只写路径和必要定位。

提交文档前运行 `rtk proxy make doc-guard` 和 `rtk proxy git diff --check`。
Doc Guard 检查格式、命名和本地链接，不证明事实、远程链接或标题锚点正确。
遇到私有数据被误扫描时修正工具输入范围，不修改或删除用户数据以通过检查。
