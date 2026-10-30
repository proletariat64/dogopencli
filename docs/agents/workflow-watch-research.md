# Workflow 单任务 watch：DI 参考与 v0.6.0 差距

本报告是 [调查 DI watch 契约与 workflow 可观察性差距](https://github.com/proletariat64/dogopencli/issues/407)
的研究资产，仅留在 `research/workflow-watch-reference` 分支，供 wayfinder 后续决策引用。
它描述被固定提交的事实和设计选项，不是已经实现的产品契约。

## 已确定的用户边界

- 规划终点是可交付实现的规格，以及 GitHub map / 决策 tickets；本研究不实现功能。
- 一次观察一个明确任务；跨重试继续观察同一任务。
- watch 只读，退出观察器不影响任务执行。
- 文本 watch 持续显示；JSON 使用单次 status，不做 JSON 流。
- 普通 shell 和 Herdr 指定 pane 都需要支持。
- 不建立通用任务平台，不把 export 成功当作 import 提交成功。

以上来自当前访谈和 research ticket，不再作为未决问题重新询问。

## 证据范围与校验

研究日期：2026-10-31（Asia/Shanghai）；仅本地代码、文档和帮助，无生产查询或 pane 操作。

| 仓库 | 固定提交 | 本地路径 |
| --- | --- | --- |
| dogopencli v0.6.0 基线 | `14c229624f0456beeb417eb7e1a5dcfe3c4a8a30` | `/tmp/dogopencli-watch-wayfinder/research-worktree` |
| DI master | `c3400d11f116fdcd198de69cceed157df823dc5c` | `/home/ubuntu/dev/di` |

先用 code-review-graph 定位。研究 worktree 原无索引，建立本地索引后核实：
dogopencli 307 files / 4,132 nodes / 1,348 Test nodes；DI 167 files / 2,731 nodes / 982 Test nodes。
两图 `built_at_sha` 均匹配其 HEAD；检索覆盖目标源码和 watch / workflow 测试。
图中存在 unresolved CALLS，DI `resume_run` 的名称检索也遗漏实际生产方法；
因此关系图用于缩小范围，以下结论均回到源码和测试逐项核实，不把搜索空结果当作功能不存在。
`.code-review-graph/` 仅本地使用，不随研究提交。

已实际执行三个 DI watch `--help` 和 dogopencli `workflow --help`。
首次研究 worktree 的直接 `python -m dogopencli` 因未安装包失败；
改用 `PYTHONPATH=src` 只读加载本分支后帮助成功，未安装或修改 host CLI。

## DI：明确对象，而非进程或最新结果

| 入口 | 选择身份 | 状态来源 |
| --- | --- | --- |
| `di exporter run watch RUN` | 精确 Run ID 或 Run directory | Manifest / control / lease，必要时派生 effective state |
| `di exporter fix watch CAMPAIGN` | 精确 Campaign ID | Campaign 控制面和 repair child 状态 |
| `di importer run watch PLAN` | 精确不可变 Import Plan JSON 路径 | 同 Plan 身份的 progress sidecar；full commit 另读 DB 核对 |

这些身份由实际 CLI help 核实；Export/Fixer/Import 的读取入口分别见 [D1]、[D2]、[D3]。
Exporter `resume_run(run_id)` 继续原 Run，并保留完成 Slots，重新排队 stale in-flight 工作；
Fixer `resume(campaign)` 继续原 Campaign，重新验证 baseline 并接续未完成映射。[D4]
Importer sidecar 路径绑定 `plan_id`，读取时同时校验 source 与 database path，
不从任意 PID 或目录中猜当前任务。[D5]

可复用的原则是“稳定的执行任务身份 + 变化的执行状态”，而不是每次执行命令换一个观察目标。
DI 的 Run / Campaign / Plan 不是 dogopencli 已存在的统一 task 类型，不能直接换名套用。

## DI：shell、输出与 Herdr

三个 watch 默认常驻文本面板，默认轮询 3 秒；共同提供：

- `--snapshot`：一帧后退出。
- `--until-settled`：观察到终态后按对象结果退出。
- `--attach PANE`：在指定现有空闲 Herdr pane 启动常驻 watcher。

三种显式模式互斥。watch 执行只接受 text，JSON 会被拒绝；机器读取用有限 status。
有限命令默认一个 stdout JSON envelope；进度和诊断走 stderr。
watch 面板自身写 stdout；TTY 清屏更新，非 TTY 逐帧追加，无清屏控制码。
这些是当前 DI 的事实，也符合本轮用户已经选择的文本 / JSON 分工。[D6][D7]

`--attach` 重建同一个 watcher 命令，固定当前 Python、模块、解析后的 config、
精确对象路径及允许的 interval / no-color 等参数；新命令不再携带 `--attach`。
它要求 `HERDR_ENV=1`，从实时 `pane current` 确认调用 pane，拒绝附着自身 pane、
agent 占用或有前台进程的 pane，不改变 layout / focus，不终止原 occupant。
启动后再检查前台进程 exact argv，而不是把 `pane run` 的接收当作启动成功。[D8]

attachment receipt 仅证明 watcher 进程已启动，不证明 Export / Repair / Import 完成。
普通 shell 运行同一 watcher；Herdr 是启动适配层，不应成为状态存储或业务身份。

## DI：终态、读错和提交证明

常驻模式在对象完成后仍继续刷新；只有 `--until-settled` 才因终态退出。
Export / Fixer 的映射为 completed=0、completed_with_holes=2、paused=3、
stopped=4、failed/interrupted=1；Import 为 completed=0、holes=2，其余失败终态=1。
`--snapshot` 的 0 表示本次观察读取成功，并不等价于对象业务成功。
观察器 Ctrl+C 返回 130，不向业务 runner 发送 pause / stop。[D7][D9]

读取失败时保留 last-good 面板，显示读取错误及上次观察年龄；
不能把记住的旧成功状态当作当前成功。`--until-settled` 的读取失败返回失败。[D7]
Export 默认状态读取无网络 / CDP；仅显式 `--live` 额外探测已有浏览器认证。[D1]
Import sidecar 有 PID / heartbeat，applying 且进程不存在或记录过期时派生 interrupted；
该派生是读模型，并不重写持久记录。[D5]
snapshot/full 的 status 另查只读 DuckDB committed 记录，校正“DB 已提交、sidecar 落后”。
不能泛化为所有 DI import 观察都已在每次轮询完成同等强度的 DB 验证。[D3]

## dogopencli：已有身份和可恢复边界

| 对象 | 已有身份与语义 | 对 watch 的含义 |
| --- | --- | --- |
| Full inquiry plan | 保存 query scope 的不可变 plan ID | 同 plan 可产生多次新 export |
| Export artifact | 每次 `run_export` 新建 UUID，结果完整后保存 | export ID 是一次结果，不能单独覆盖跨重试观察 |
| History plan / package | 冻结 desired range 和 package ID | 重试按 package 找 attempts，并跳过已完整结果 |
| Repair plan / package | 冻结 baseline、gaps 与新 package ID | repair 是独立工作，baseline 不随新重试改变 |
| Import plan | 冻结 exact export / action / destination 与输入 | 同计划 apply 可恢复；重新生成的等价计划也可 replay |
| Target execution | 冻结 target work 的 execution ID | 是已有聚合 export 执行对象，不是自动跨阶段工作流 |

Plan/export/import 身份见 [W1][W2][W3]；history / repair 重试见 [W4]；target 见 [W5]。
已有命令分别推进阶段：repair 由 `workflow export run --plan REPAIR` 执行，
import 必须显式 plan / apply；target run 只执行 export，不自动导入。[W1][W4][W5]

## dogopencli：目前“黑盒”的具体机制

`run_export` 在内存先分配 export ID、started_at 与 `unqueried`，
执行成功或捕获 Exception / KeyboardInterrupt 后才 `store.save("exports", result)`。
因此运行中的这次 attempt 没有已发布 artifact；硬终止未进入异常处理时，
不能从保存结果推断它是否正在运行、已经中断，还是尚未执行。[W2]
保存本身是 metadata / records 一起写入临时目录再原子 rename；
这保护结果可见性，不能把它改成反复覆盖同一个“运行中 export”文件。[W1]

`workflow status` 从完成 exports 的 `completed_at` 排序推导 latest / last-success，
再读 receipts/current publications；没有独立执行中 run 状态，也没有 scoped watch。
读取列表只开 metadata，不扫描所有 records，这是应保留的现有成本边界。[W1][W6]
History / Repair / Target 在每个 child 完成后才出现对应新结果；
已有 inspect 能重建成功与缺口，但不能证明当前 child 的活跃执行状态。[W4][W5]

Importer `stage_rows` 按最多 10,000 行事务提交隐藏 observation rows，
在恢复时逐 ordinal / record 对照 exact input，再继续未完成批次。
`stage_checkpoint` 当前只是空的故障注入 seam，没有外部进度 sidecar。[W7]
最终 observation receipt 与 publication 分开于 staging 语义：
暂存行即使 durable 也不是已提交 observation/current。
receipt 已提交但 CLI 还没打印响应时失败，重试以 receipt replay，不能倒退成未提交。[W7]
Repair import 先验证所有 frozen inputs，再逐 observation 独立 preserve；
中途失败不撤销前面已经提交的独立 observation。[W8]

现有 crash tests覆盖 batch commit 前后和 publication commit 前后：
status 不做恢复写入；publication 前看不到已提交 observation，之后可读 receipt；
replace-full 在最终提交前仍保留旧 current，重试不重复发布。[W9]
这些测试是已有回归证据的源码核对，本研究未重跑业务测试或百万行测量。

## 可复用机制与仍需决定的接口

可复用：单对象身份、读取 / 展示 / pane 启动分层、有限 JSON status、
常驻文本面板、带年龄的读取失败、明确观察器退出语义、提交以 receipt 为准。
新的运行记录若要补足当前空档，应独立于 immutable export artifact 和 DB receipt；
这是由现有持久化边界推出的设计约束，不是已选定的文件格式或新平台。

以下是需要后续决策 ticket 落定的选项，不改变已确认的用户原则：

1. 用户用什么已有身份附着一个可跨重试观察的任务：stage-specific plan / execution，
   还是显式新增 workflow 执行身份；必须说明 full plan 再次采集与 retry 的区别。
2. 一次只观察一个任务时，history/repair 的 child attempt 和 import 多观察提交，
   如何归属该任务；不能把“最近一次全局 export”当附着选择器。
3. 运行中哪些事实有依据可显示：当前包、phase、页/行、暂存/提交、错误、
   心跳与更新时间；哪些分母和 ETA 无法证明时显示未知。
4. crash 后如何派生有效状态，如何防止旧 sidecar 掩盖新 attempt 或已提交 receipt；
   活跃 DB writer 期间 status 的读取路径不能依赖可随时打开 DuckDB 的假设。
5. CLI 拼写、text 默认格式、snapshot / until-settled 是否全部需要，
   以及观察器自身读错、被观察任务失败与 Ctrl+C 的退出码分工。

不建议添加 DI 中未证明必要的暂停、调度、自动 SSO 或自动修复；
不扫描 raw/business records 来算终端进度，不添加未论证收益的额外指纹协议。

## 精确源码索引

以下 GitHub 链接均固定提交，行号以本次只读核对为准。

- [D1] [Exporter 状态源与 live 边界](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/diexporter/application.py#L691-L722)。
- [D2] [Fixer 状态入口](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/difixer/application.py#L377-L381)。
- [D3] [Importer status / full commit 校正与 watch](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/diimporter/application.py#L522-L606)。
- [D4] [Exporter resume](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/diexporter/application.py#L650-L676)；[Fixer resume](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/difixer/application.py#L239-L268)。
- [D5] [Import sidecar 身份和 publisher](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/diimporter/progress.py#L19-L139)；[读时派生中断](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/diimporter/progress.py#L157-L173)。
- [D6] [输出规范](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/docs/spec/cli-v0.2.md#L108-L166)；[CLI 格式和输出路由](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/di/cli/__init__.py#L105-L154)。
- [D7] [只读 watch 循环、读错、TTY 与退出](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/di_common/watch.py#L306-L381)。
- [D8] [重建命令、验证空闲 pane、exact argv 确认](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/di_common/watch_attach.py#L60-L228)。
- [D9] [Export 终态映射](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/diexporter/watch.py#L23-L34)；[Fixer 映射](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/difixer/watch.py#L14-L25)；[Import 映射](https://github.com/proletariat64/di/blob/c3400d11f116fdcd198de69cceed157df823dc5c/src/diimporter/watch.py#L93-L118)。
- [W1] [Store 与分阶段 dispatch](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/src/dogopencli/workflow.py#L197-L292)；[阶段入口](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/src/dogopencli/workflow.py#L442-L521)。
- [W2] [Export attempt 的内存创建与最终保存](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/src/dogopencli/workflow.py#L647-L801)。
- [W3] [Import plan 的 exact input](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/src/dogopencli/workflow.py#L865-L899)。
- [W4] [History retry](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/src/dogopencli/workflow_history.py#L215-L256)；[Repair inspect/run](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/src/dogopencli/workflow_repair.py#L94-L176)。
- [W5] [Target execution status](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/src/dogopencli/workflow_targets.py#L94-L127)；[Target run](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/src/dogopencli/workflow_targets.py#L206-L233)。
- [W6] [当前 status 汇总](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/src/dogopencli/workflow.py#L532-L625)。
- [W7] [Import staging、durable batch 和 receipt](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/src/dogopencli/workflow_storage.py#L142-L277)。
- [W8] [Repair import 的独立 preserve](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/src/dogopencli/workflow_repair.py#L227-L247)。
- [W9] [批次 / 发布中断回归](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/tests/integration/test_workflow_scale_cli.py#L27-L90)；[current 原子性回归](https://github.com/proletariat64/dogopencli/blob/14c229624f0456beeb417eb7e1a5dcfe3c4a8a30/tests/integration/test_workflow_scale_cli.py#L297-L340)。
