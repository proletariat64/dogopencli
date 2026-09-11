# 面向 Agent 的查询 CLI 与独立登录流程

Status: accepted
Date: 2026-09-08

2026-09-11 更新：[ADR 0005](0005-channel-snapshot-source.md)明确 Channel 替代源及分阶段验收。Channel 改用本地 seqid 作为数据集内部排序与编号，不宣称 abilityId 是已验证主键；Cost/SLA 原排序保持。下文真实 Channel 全量 UAT 要求在后端修复后执行，不阻塞本阶段工程交付。

用户在设计访谈第一、二轮确定 v0.1.0 优先服务 AI Agent 和脚本，同时支持人工阅读。

## 输出协议

业务查询默认输出 JSON，统一包含 `data`、`meta`、`error`。元数据标明来源、时间、范围、新鲜度和完整性；支持 `--format table` 及 `--fields` 字段投影。默认保留完整业务字段与未知扩展字段。

stdout 保持可解析，诊断信息进入 stderr。以下协议和退出码适用于业务查询及刷新；认证命令采用下文明确的 DI 输出协议。第四轮确定少量退出码，并通过 `error.code` 区分具体原因：

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功，包括空列表和允许的部分结果 |
| 1 | 运行失败，包括无缓存、过期、认证失效、取数失败、不完整或详情不存在等 |
| 2 | 参数或配置错误 |
| 130 | 用户中断 |

错误对象提供 `code`、`message`、`retryable`。缓存过期只有在要求新鲜度时失败；部分结果只有在完整性要求不满足时失败。要求无法满足时不输出可被误用的成功数据。具体机器错误码名称和完整元数据 schema 仍待整理。

第三轮确定本地列表默认最多返回 100 条，提供 `--limit`、`--offset` 和 `--all`。元数据分别标明筛选后总量、实际返回数量及是否还有记录。输出截断与缓存不完整分开标记；完整缓存只展示 100 条不代表缓存缺失。第四轮确定实时列表也先采集匹配范围，再执行本地排序及展示分页；不把 CLI 的展示分页直接映射成一次后端请求。

默认按记录 ID 升序。本地筛选默认精确匹配，同一字段多个值为 OR，不同字段之间为 AND。v0.1.0 不增加模糊搜索、自定义排序或表达式语言。实时筛选遵循已验证的后端语义，不能证明等价时明确标注差异。

保留后端字段名、类型及单位。JSON 数值金额精确保留，不经过浮点转换；后端字符串金额保持字符串。业务时间字段原样保留，CLI 自己的抓取时间统一采用带时区的 UTC 时间。`--fields` 仅裁剪 `data`，不裁剪完整性、新鲜度等元数据。

## 插件交付

v0.1.0 支持仓库内新增插件，通过统一接口注册查询能力；独立发布和安装外部插件延期。新增插件应无需修改核心传输逻辑，以验证扩展接口有效。

内置插件按 `channel`、`cost`、`sla` 三个领域划分；SLA 提供列表和详情两项能力。核心负责登录接入、请求限制、缓存机制和输出框架，插件负责端点契约、领域字段、筛选及响应解析。具体接口结构待确定。

## 登录与浏览器

2026-09-11 访谈确认：移植 DI 必要代码到本仓库，记录来源版本，dogopencli 独立安装运行，不依赖本机 DI。用户要求相关命令与逻辑保持一致，包含 `dogopencli login [--timeout-seconds SECONDS]`、`dogopencli auth check`、`dogopencli logout`，覆盖此前暂不加入 logout 的建议。

当前核对基线为 DI commit `8eb163c6d140554ca167bd50349a85ca224ac342`，主要代码为 `src/diauth/` 中的 login、browser、coordination、logout，以及通用 CDP、文件锁和启动器依赖。复用流程，适配入口、应用认证判据、配置和专用 profile/锁/端口；不把 DI 的业务错误码照搬为付款认证判据。

`auth check` 只检查现有会话，不恢复浏览器或启动人工登录。`logout` 对齐 DI 本地退出：通过可达 CDP 清除专用 profile 中适用的认证信息并验证，不发起公司全局远程登出、不删除业务缓存；CDP 不可用则失败，不直接改 Cookie 数据库。当前没有执行实际退出。付款平台的认证判据与有效清理域需要实现验证，不能只替换 URL 就宣称通过。

2026-09-12 生产 UAT（票据 #3/#8 待验证项）：清理域验证为四族——`antglobal-inc.com`、`ifundcontrol.alipay.com`、`iglobalfundcontrol.alipay.com` 及父域 `alipay.com`；仅删前三族入口仍认证，入口会话由 `.alipay.com` 族承载（`sso.global.authtoken`、`IAM_TOKEN`、`BUSERVICE_SSO_V2`、`zt-auth`、`ctoken` 等），删除该族仅为专用 profile 的本机操作，不撤销公司全局 SSO 服务端状态。未认证落点为 `ipaybuservice.alipay.com/login.htm`（`appName=ifundcontrolprodops` / `iglobalfundcontrol`），与 `tonelogin.antglobal-inc.com` 一并归类为需要登录；其他 ipaybuservice 路径证据不足，不预先归类。删除 Cookie 后入口页在 settle 后数秒才经 JS 驱动跳转到登录页，探针对停在入口 URL 的结果增加有界稳定窗口轮询，预算仍受 timeout 约束。

用户确认统一为 DI 的默认值：人工登录等待 600 秒，通过 `--timeout-seconds` 覆盖，替代早先的 300 秒决定。dogopencli 专用 profile 和禁用端口要求保持；认证 JSON 格式按下述 DI 契约对齐。

2026-09-11 参数决定：对齐 DI 当前有效参数，不实现历史兼容层。`auth check` 不接受已废弃的 `browser_context`，不提供隐藏兼容别名 `--json`，显式 JSON 使用 `--format json`。`login --timeout-seconds` 接受有限正数，默认 `600.0`；`logout` 无专用参数和确认提示，不增加 `--yes` 或 `--force`。

认证公共参数为 `--config-dir PATH`、`--format json|text`、`--verbose`、`--quiet`、`--no-color`、`-h/--help`、`--version`，允许位于命令前后，不允许缩写；verbose/quiet 互斥，空配置目录非法。认证不支持 table/markdown。配置目录、环境变量、profile 和锁采用 dogopencli 专用约定，不继承 DI 私有配置。

认证默认结果和帮助为 JSON，沿用 DI 的 `output_version`（1）、`command`、`exit_code`、`result`、`error` envelope；命令标识为 `login`、`logout`、`auth.check`。失败时 result 为 null，error 含 code、message、retryable、details、next。认证退出码为 0 成功/帮助/版本、1 参数或运行失败、130 中断；裸 `auth` 显示帮助并退出 0。这是上文业务输出协议的明确例外。SIT 验证有效参数对齐及废弃参数拒绝。

由 `dogopencli login` 负责人工登录及专用 Chrome 生命周期，使用 headed 完成登录、headless 执行日常查询。业务查询层连接既有 CDP；登录失效时明确引导人工登录，不因普通查询而突然切换浏览器。

`login` 先确认所需应用会话有效，再将同一 profile 切换到 headless 并执行轻量只读校验，成功才退出 0。已有健康 headless 会话时直接成功；登录不自动触发全量缓存刷新。

人工登录默认等待 600 秒，可配置；超时或 Ctrl-C 返回非零并保留专用 headed Chrome，便于继续人工登录。再次执行 `login` 时继续检查，只有完成 headless 校验才报告成功。

浏览器的进程/profile 归属、单进程占用和禁用端口 9330–9340 等已有约束继续有效。配置及 profile 默认位置见 [ADR 0003](0003-local-query-snapshots.md)。独立登录流程避免交互式认证混入脚本查询。

## SIT 与 UAT

2026-09-09 用户确认公开 CLI＋假 CDP 测试属于 SIT，真实生产环境的显式只读验收属于 UAT。两者是正常测试验收流程，不阻止规格发布，也不增加额外审批步骤。

SIT 从公开命令入口验证插件、请求限制、解析、SQLite 和输出，使用假 CDP 隔离生产依赖。UAT 验证真实登录接入、headless 查询、完整采集与离线缓存行为；只更新本地缓存，不改变生产业务配置。测试通过与规格可发布分别判定。
