# DI 渐进式帮助参考与 dogopencli 差距

Observed: 2026-09-12
Scope: general
Status: snapshot

## 结论

DI 的无参数入口是机器可读的导航，不是错误或交互向导。每一级只列直属子命令，叶子提供完整调用契约；JSON 为默认，人工显式选择 text。dogopencli 已移植认证帮助模型，但根入口与业务查询仍使用另一套 argparse 帮助，导致导航和输出不一致。建议复用现有认证模型，统一命令声明、帮助和解析，不引入对 DI 安装的运行时依赖。

## 参考版本与方法

DI：`~/dev/di`，commit `8eb163c6d140554ca167bd50349a85ca224ac342`。dogopencli：commit `d415e3afa234789eccc96a689efdba0775b1b940`，标签 v0.1.1。

2026-09-12 通过真实子进程执行 20 个帮助或无参数命令。DI 使用 `uv run --no-sync --offline di`，避免同步环境；dogopencli 使用当前虚拟环境的 `python -m dogopencli`。原始 stdout、stderr、退出码保存在 Git 忽略的 `tmp/help-reference-evidence.json`，复现脚本为 `tmp/probe-help.py`。未执行登录、退出、业务查询或刷新。

先查询两库 code-review-graph。DI 图未找到当前统一 CLI 节点且架构结果未覆盖该包，因此依据 README 的目录导航对指定文件直接核对，未将不完整图作为依赖结论。

## 运行态对照

| 输入 | DI 实测 | dogopencli 实测 |
| --- | --- | --- |
| 无参数 | 退出 0；一个 help_version=1 JSON 对象 | 退出 2；stderr 报缺少 group |
| 根 --help | 同无参数 JSON | 退出 0；argparse 文本，只列 refresh/payment |
| help | 同无参数 JSON | 退出 2；无此命令 |
| 裸中间节点 | exporter、exporter run 均为当前层 JSON 帮助 | payment、payment channel 均退出 2 |
| help 路径 | exporter run start 返回叶子 JSON | help payment channel list 不支持 |
| 叶子 --help | 声明式完整契约 | 业务叶子为 argparse 文本；login 已为 JSON |
| --format text | 根和叶子帮助均可显式选 text | 根 --help --format text 仅由 argparse 提前退出，未真正解释 format |
| 认证中间节点 | auth 直属 check | auth 已有 JSON 帮助并退出 0 |

DI 根 children 仅 exporter/importer/snapshot/config/auth/login/logout；exporter 只展开 source/run/fix。根 JSON 为 2689 UTF-8 字节，叶子示例为 3164 字节；这是该版本观察值，不是 dogopencli 大小验收阈值。

## 代码与规格证据

- DI `docs/spec/cli-v0.2.md` 的 Help and architecture：help_version、直属 children、叶子参数/约束/影响/错误/示例/下一步，以及声明驱动解析和两种帮助。
- DI `src/di/cli/__init__.py` 的 main：默认 JSON；help 命令与 --help；无 handler 的完整路径自动显示帮助，处理发生在配置解析和 dispatch 之前。
- DI `src/di/cli/help.py` 的 document/render_text 与 `spec.py` 的 CommandSpec/ArgumentSpec：JSON/text 共享元数据。
- dogopencli `src/dogopencli/auth/spec.py`：已有 DI 移植声明与双格式帮助；`auth/cli.py` 在 dispatch 前生成帮助。
- dogopencli `src/dogopencli/cli.py` 的 build_parser/main：业务路径使用 required 子解析器，根帮助没有认证命令。

## 应沿用与应保留的边界

沿用无参数导航、显式 help 路径、默认 JSON、text、人机共享声明与渐进披露。根提供完整入口，叶子才解释筛选、展示分页、缓存、live 和完整性约束。

保留现行 [ADR 0004](../../adr/0004-cli-runtime-boundaries.md) 的业务 data/meta/error、认证 output_version envelope 和各自退出码；业务人工输出仍为 table，帮助为 text。不照搬 DI 导入、写数据操作、历史兼容参数、特殊退出码或配置默认路径。

帮助描述叶子操作的影响时，应区别默认离线查询、显式 live、snapshot/CDP refresh 与本地认证生命周期；帮助操作本身始终不读取配置、缓存、profile，不连接 CDP 或生产网络。不能因为业务只读便把刷新和登录描述为完全无本地变更。

## 未验证与规划边界

本报告证明现有命令行为及参考实现，不代表 dogopencli 新帮助已实现。新帮助仅需公开 CLI 自动化验收；本轮没有复验浏览器、认证或付款后端，不扩大现有生产 UAT 结论。

用户已确认公开 CLI 与少量子进程测试边界；计划与规格发布为 [Issue #13](https://github.com/proletariat64/dogopencli/issues/13)，状态为 ready-for-agent。
