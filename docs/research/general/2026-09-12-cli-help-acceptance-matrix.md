# CLI 帮助验收矩阵：全部命令路径

Observed: 2026-09-12
Scope: general
Status: snapshot

## 结论

本矩阵是 Issue #13（DI 风格渐进式帮助）的规范性验收清单：枚举现行 CLI 全部 20 条命令路径，逐条给出类型、今日 handler、帮助定位入口、错误协议归属、effects/effects_variants、输出块与叶子参数清单，并以 2026-09-12 的 20 次子进程探针作为 before 基线。Task 2–4 按本矩阵实现；Task 4 必须自动化覆盖每条标记行，不得遗漏。

## 依据与方法

- 命令树与参数清单：`src/dogopencli/cli.py` 的 `build_parser` 与 `cmd_*` handler；`src/dogopencli/auth/spec.py` 的 `COMMANDS`/`GLOBALS`；`src/dogopencli/auth/cli.py` 的调度与错误协议；`src/dogopencli/plugins/payment/{channel,cost,sla}.py` 的筛选字段、范围与状态。
- before 基线：20 次子进程探针，原始 stdout/stderr/退出码存于 Git 忽略的 `tmp/help-reference-evidence.json`，复现脚本 `tmp/probe-help.py`；对照分析见 [DI 渐进式帮助参考](2026-09-12-cli-help-reference.md)。未单独探针的路径按同一 argparse required-subparser 机制推导并标注“推导”。
- 目标行为：Issue #13 计划 Global Constraints（`.superpowers/sdd/issue-13-plan.md`，非仓库文档）；本矩阵把每条约束落到路径行。

## 全局规则速记

以下规则绑定所有行，各行只写增量：

- 帮助是独立的 `help_version=1` 文档，不裹业务 data/meta/error 或认证 output_version envelope；帮助成功必退出 0、stderr 为空。
- 入口等价：根 `dogopencli` == `--help` == `-h` == `help`；`--format text` 等价路径同理；每个组/叶子 `PATH`（无 handler 的完整路径）、`PATH --help`/`PATH -h`、`help PATH` 定位同一节点。
- 根 children 固定顺序：payment、refresh、auth、login、logout；help 是 meta 命令，可经 examples/next 发现，永不出现在 children；组只展开直属 children，叶子 `children=[]`。
- 帮助不触碰配置、缓存、浏览器、CDP、网络；在业务配置解析、认证调度、缓存构造、CDP 初始化之前完成。
- 字段固定顺序：help_version、command、summary、arguments、options、constraints、effects、output、exit_codes、errors、examples、next、children；无运行时值。
- 参数条目含 name、summary、type、required、default，旗帜给 flags/choices，可重复项 `type=append`；解析哨兵与生效默认不同时写生效值（list 生效 limit=100、offset=0）及 `--all` 冲突。
- 帮助 `--format` 仅接受 json/text，拒绝 table/markdown（不静默降级）；业务执行格式不因此扩宽。无选项缩写；`--` 结束选项解析；不得把值为 help/login/auth 的选项值误路由（如 `--id login`）。
- 未知命令、未知选项、非法格式、拼写错误一律失败，绝不回退根帮助或以最近节点冒充成功；错误指向最近有效路径的帮助命令。
- 错误协议：根/业务导航参数错误 → 业务 JSON `error.code=INVALID_ARGUMENT`、退出 2；已解析到认证路径的参数错误 → 认证 `invalid_arguments`、退出 1；显式 text 帮助的失败只向 stderr 打印文本，默认 JSON 错误只向 stdout 打印一个匹配 envelope。两套协议不统一。

## 路径总表

T4 列标 ✓ 的行必须被 Task 4 自动化验收覆盖（见文末清单）。本矩阵全部 20 行均为必覆盖行。

| # | 路径 | 类型 | 今日 handler | 错误协议 | T4 |
| --- | --- | --- | --- | --- | --- |
| P01 | `dogopencli`（根） | 组 | 无（argparse 报错退出 2） | 业务 INVALID_ARGUMENT/2 | ✓ |
| P02 | `payment` | 组 | 无（required target） | 业务 INVALID_ARGUMENT/2 | ✓ |
| P03 | `payment channel` | 组 | 无（required action） | 业务 INVALID_ARGUMENT/2 | ✓ |
| P04 | `payment channel list` | 叶子 | `cmd_channel_list` | 业务 INVALID_ARGUMENT/2 | ✓ |
| P05 | `payment cost` | 组 | 无（required action，推导） | 业务 INVALID_ARGUMENT/2 | ✓ |
| P06 | `payment cost list` | 叶子 | `cmd_cost_list` | 业务 INVALID_ARGUMENT/2 | ✓ |
| P07 | `payment sla` | 组 | 无（required collection，推导） | 业务 INVALID_ARGUMENT/2 | ✓ |
| P08 | `payment sla baselines` | 组 | 无（required action，推导） | 业务 INVALID_ARGUMENT/2 | ✓ |
| P09 | `payment sla baselines list` | 叶子 | `cmd_sla_list` | 业务 INVALID_ARGUMENT/2 | ✓ |
| P10 | `payment sla baselines get` | 叶子 | `cmd_sla_get` | 业务 INVALID_ARGUMENT/2 | ✓ |
| P11 | `refresh` | 组 | 无（required domain，推导） | 业务 INVALID_ARGUMENT/2 | ✓ |
| P12 | `refresh payment` | 组 | 无（required target，推导） | 业务 INVALID_ARGUMENT/2 | ✓ |
| P13 | `refresh payment channel` | 叶子 | `cmd_refresh_channel` | 业务 INVALID_ARGUMENT/2 | ✓ |
| P14 | `refresh payment cost` | 叶子 | `cmd_refresh_cost` | 业务 INVALID_ARGUMENT/2 | ✓ |
| P15 | `refresh payment sla` | 叶子 | `cmd_refresh_sla` | 业务 INVALID_ARGUMENT/2 | ✓ |
| P16 | `auth` | 组 | 无（spec 无 handler → 帮助） | 认证 invalid_arguments/1 | ✓ |
| P17 | `auth check` | 叶子 | `auth.check` | 认证 invalid_arguments/1 | ✓ |
| P18 | `login` | 叶子 | `login` | 认证 invalid_arguments/1 | ✓ |
| P19 | `logout` | 叶子 | `logout` | 认证 invalid_arguments/1 | ✓ |
| P20 | `help`（meta） | meta | 无（新帮助路由） | 随已解析路径归属 | ✓ |

## 逐路径验收明细

### P01 根 `dogopencli`

- 类型/今日 handler：组；无 handler，argparse 报“required: group”退出 2。
- 帮助入口：裸 `dogopencli`、`--help`、`-h`、`help` 四者定位同一根 JSON；`--format text` 与 `help --format text` 给同一根文本帮助。
- 错误协议：业务 INVALID_ARGUMENT、退出 2（如未知 group）。
- effects：全 false（无操作），无 effects_variants。
- output：无执行输出；`help_default_format=json`、`help_formats=[json,text]`。
- 内容要求：summary 为只读付款运营查询、默认读本地缓存；children 固定 payment、refresh、auth、login、logout；next 指向 payment 帮助、显式 refresh 帮助、人工 text 帮助；不得声称 login 是缓存查询前提。
- before（探针 run 11、12、13、20）：裸命令退出 2 stderr 报缺 group；`--help` 退出 0 argparse 文本且只列 refresh/payment；`help` 退出 2 invalid choice；`--help --format text` 退出 0 argparse 文本、--format 未被解释。

### P02 `payment`

- 类型/今日 handler：组；无 handler（required target）。
- 帮助入口：裸 `payment`（无 handler 自动显示）、`payment --help`/`-h`、`help payment`。
- 错误协议：业务 INVALID_ARGUMENT/2。
- effects：全 false，无 variants。output：仅帮助块（json/text）。
- children：channel、cost、sla（直属）。
- before（探针 run 14）：裸 `payment` 退出 2 stderr“required: target”。

### P03 `payment channel`

- 类型/今日 handler：组；无 handler（required action）。
- 帮助入口：裸路径、`--help`/`-h`、`help payment channel`。
- 错误协议：业务 INVALID_ARGUMENT/2。effects 全 false；output 仅帮助块。
- children：list（直属）。
- before（探针 run 15）：裸路径退出 2 stderr“required: action”。

### P04 `payment channel list`

- 类型/今日 handler：可执行叶子；`cmd_channel_list`（裸路径执行缓存查询，不得改为显示帮助）。
- 帮助入口：`payment channel list --help`/`-h`、`help payment channel list`；帮助不得触发配置/缓存/CDP。
- 错误协议：业务 INVALID_ARGUMENT/2。
- effects：默认缓存查询 mutates=false、network=false、browser_required=false、destructive=false。effects_variants：
  1. 缓存初始化/旧库迁移：mutates=true、network=false；
  2. `--live`：需要已存在 CDP 会话、读后端、不启动浏览器、不刷新缓存（network=true、browser_required=true、mutates=false）。
- output：执行 `default_format=json`、`formats=[json,table]`；帮助 `help_default_format=json`、`help_formats=[json,text]`。
- 参数清单（全部 optional 除非注明）：

  | 选项 | type | 生效默认 | choices/约束 |
  | --- | --- | --- | --- |
  | `--payout-type` | str | `EXTERNAL` | EXTERNAL、LIQUIDITY、MANUAL、SETTLEMENT |
  | `--financial-inst-id` | append | `[]` | live 每筛选仅单值 |
  | `--debit-inst-country-code` | append | `[]` | live 每筛选仅单值 |
  | `--status` | append | `[]` | ENABLE、DISABLE、GRAY、TEST、INIT；live 单值 |
  | `--debit-account-name` | append | `[]` | 后端数组参数 |
  | `--debit-account-no` | append | `[]` | 后端数组参数 |
  | `--clearing-system-name` | append | `[]` | 后端数组参数 |
  | `--debit-currency` | append | `[]` | 后端数组参数 |
  | `--credit-currency` | append | `[]` | 后端数组参数 |
  | `--limit` | int | 100（解析哨兵 None） | 正整数；与 `--all` 冲突 |
  | `--offset` | int | 0（解析哨兵 None） | 非负；与 `--all` 冲突 |
  | `--all` | bool | false | 与显式 `--limit/--offset` 冲突 |
  | `--live` | bool | false | snapshot 源不支持 live |
  | `--require-fresh` | bool | false | 超 72h（可配置）报错 |
  | `--require-complete` | bool | false | 快照不完整时报错 |
  | `--format` | str | `json` | json、table（执行格式） |
  | `--fields` | str | None | 逗号分隔，至少一个字段 |

- 约束文案：同字段多值 OR、跨字段 AND；缓存 72h 默认 TTL 可配置、stale 与 complete 独立；默认显示 100 行与 `--all`；seqid 跨数据集不稳定；snapshot 源仅覆盖 EXTERNAL 且不支持 live；替代源 kinds 为 simulated/backend_complete。
- 示例/下一步：至少一个可运行形态示例与一条 next；同时给默认缓存与显式 `--live` 示例，全部用占位值。
- before（探针 run 16）：`payment channel list --help` 退出 0，argparse 文本（usage＋options），无 JSON、无 effects/errors/examples/next。

### P05 `payment cost`

- 类型/今日 handler：组；无 handler（required action，推导）。
- 帮助入口：裸路径、`--help`/`-h`、`help payment cost`。
- 错误协议：业务 INVALID_ARGUMENT/2。effects 全 false；output 仅帮助块。
- children：list。
- before：未单独探针；与 P02/P03 同机制，推导退出 2。

### P06 `payment cost list`

- 类型/今日 handler：叶子；`cmd_cost_list`。
- 帮助入口与隔离：同 P04。
- 错误协议：业务 INVALID_ARGUMENT/2。
- effects/effects_variants：同 P04（默认缓存读；缓存初始化/迁移 mutates=true、network=false；`--live` 需既有 CDP 会话）。
- output：执行 json/table；帮助 json/text。
- 参数清单：

  | 选项 | type | 生效默认 | choices/约束 |
  | --- | --- | --- | --- |
  | `--legal-entity-code` | append | `[]` | live 每筛选仅单值 |
  | `--financial-inst-code` | append | `[]` | live 单值 |
  | `--bank-account` | append | `[]` | live 单值 |
  | `--trans-currency-code` | append | `[]` | live 单值 |
  | `--charge-bearer` | append | `[]` | live 单值 |
  | `--clearing-network-name` | append | `[]` | live 单值 |
  | `--limit` / `--offset` / `--all` | int/int/bool | 100/0/false | 同 P04 |
  | `--live` / `--require-fresh` / `--require-complete` | bool | false | 同 P04 |
  | `--format` | str | `json` | json、table |
  | `--fields` | str | None | 同 P04 |

- 约束：范围固定 costTypeCode=FUND_OUT_CHANNEL_TRANS_FEE（无 scope 选项）；同字段 OR、跨字段 AND；缓存语义同 P04。
- before：未探针 `--help`；与 P04 同 argparse 机制，推导为退出 0 argparse 文本。

### P07 `payment sla`

- 类型/今日 handler：组；无 handler（required collection，推导）。
- 帮助入口：裸路径、`--help`/`-h`、`help payment sla`。
- 错误协议：业务 INVALID_ARGUMENT/2。effects 全 false；output 仅帮助块。
- children：baselines。before：推导退出 2。

### P08 `payment sla baselines`

- 类型/今日 handler：组；无 handler（required action，推导）。
- 帮助入口：裸路径、`--help`/`-h`、`help payment sla baselines`。
- 错误协议：业务 INVALID_ARGUMENT/2。effects 全 false；output 仅帮助块。
- children：list、get。before：推导退出 2。

### P09 `payment sla baselines list`

- 类型/今日 handler：叶子；`cmd_sla_list`。
- 帮助入口与隔离：同 P04。
- 错误协议：业务 INVALID_ARGUMENT/2（含裸 `--biz-legal-entity` 无 `--live` 的参数错误）。
- effects/effects_variants：同 P04。
- output：执行 json/table；帮助 json/text。
- 参数清单：

  | 选项 | type | 生效默认 | choices/约束 |
  | --- | --- | --- | --- |
  | `--biz-category` | append | `[]` | live 单值 |
  | `--creditor-currency` | append | `[]` | live 单值 |
  | `--region-code` | append | `[]` | live 单值 |
  | `--status` | append | `[]` | 无 choices；live 单值 |
  | `--biz-legal-entity` | append | `[]` | 仅 `--live` 透传；独立筛选效果未验证；无 `--live` 为参数错误 |
  | `--limit` / `--offset` / `--all` | int/int/bool | 100/0/false | 同 P04 |
  | `--live` / `--require-fresh` / `--require-complete` | bool | false | 同 P04 |
  | `--format` | str | `json` | json、table |
  | `--fields` | str | None | 同 P04 |

- 约束：缓存行为同 P04；`--biz-legal-entity` 的 live-only 与未验证效果必须写入帮助。
- before：未探针；推导同 P04 argparse 文本。

### P10 `payment sla baselines get`

- 类型/今日 handler：叶子；`cmd_sla_get`。裸路径缺 `--id` 今日即参数错误，保持该语义（仅帮助入口豁免）。
- 帮助入口：`... get --help`/`-h`、`help payment sla baselines get`；帮助不得要求缺失的必填项。
- 错误协议：业务 INVALID_ARGUMENT/2。
- effects/effects_variants：默认缓存读全 false；缓存初始化/迁移 mutates=true、network=false；`--live` 需既有 CDP 会话读详情。
- output：执行 json/table；帮助 json/text。
- 参数清单：

  | 选项 | type | required | 生效默认 | 约束 |
  | --- | --- | --- | --- | --- |
  | `--id` | str | 是 | 无 | 列表 `id`；占位示例 |
  | `--live` | bool | 否 | false | 需既有 CDP 会话 |
  | `--require-fresh` / `--require-complete` | bool | 否 | false | 同 P04 |
  | `--format` | str | 否 | `json` | json、table |
  | `--fields` | str | 否 | None | 至少一个字段 |

- 约束：详情永不以列表行替代；缓存内未命中为 NOT_FOUND。
- before：未探针；推导同 P04 argparse 文本。

### P11 `refresh`

- 类型/今日 handler：组；无 handler（required domain，推导）。
- 帮助入口：裸路径、`--help`/`-h`、`help refresh`。
- 错误协议：业务 INVALID_ARGUMENT/2。effects 全 false；output 仅帮助块。
- children：payment。before：推导退出 2。

### P12 `refresh payment`

- 类型/今日 handler：组；无 handler（required target，推导）。
- 帮助入口：裸路径、`--help`/`-h`、`help refresh payment`。
- 错误协议：业务 INVALID_ARGUMENT/2。effects 全 false；output 仅帮助块。
- children：channel、cost、sla。before：推导退出 2。

### P13 `refresh payment channel`

- 类型/今日 handler：叶子；`cmd_refresh_channel`（按配置源分 snapshot/CDP 两支）。
- 帮助入口：同 P04；帮助静态列两个分支，绝不读当前配置决定帮助内容。
- 错误协议：业务 INVALID_ARGUMENT/2。
- effects：mutates=true（写缓存）。effects_variants：snapshot 分支 network=false、browser_required=false；cdp 分支需既有 CDP 会话（network=true、browser_required=true）。destructive=false。
- output：执行为业务 JSON envelope（stdout）＋进度 stderr，无 `--format` 选项；帮助 json/text。
- 参数清单：`--payout-type`，str，默认 `EXTERNAL`，choices EXTERNAL、LIQUIDITY、MANUAL、SETTLEMENT。
- before：未探针；推导为 argparse 文本帮助。

### P14 `refresh payment cost`

- 类型/今日 handler：叶子；`cmd_refresh_cost`（仅 CDP 源）。
- 帮助入口：同 P04。错误协议：业务 INVALID_ARGUMENT/2。
- effects：CDP 查询＋缓存重建：mutates=true、network=true、browser_required=true、destructive=false；无 variants。
- output：业务 JSON envelope＋进度 stderr；帮助 json/text。参数：无自有选项。
- before：未探针；推导 argparse 文本帮助。

### P15 `refresh payment sla`

- 类型/今日 handler：叶子；`cmd_refresh_sla`（仅 CDP 源；列表＋逐条详情）。
- 帮助入口：同 P04。错误协议：业务 INVALID_ARGUMENT/2。
- effects/output：同 P14。参数：无自有选项。
- before：未探针；推导 argparse 文本帮助。

### P16 `auth`

- 类型/今日 handler：组；spec 无 handler，今日已显示 JSON 帮助退出 0。
- 帮助入口：裸 `auth`、`auth --help`/`-h`、`help auth`（Task 2 起经统一目录定位，认证协议保持不变）。
- 错误协议：认证 invalid_arguments、退出 1。
- effects：全 false，无 variants。output：`default_format=json`、`formats=[json,text]`（认证结果与帮助同格式域）、`help_default_format=json`。
- children：check（直属）。GLOBALS：--config-dir、--format(json|text)、--verbose、--quiet、--no-color、--help/-h、--version；--verbose 与 --quiet 互斥。
- before（探针 run 17）：裸 `auth` 退出 0，`help_version=1` JSON、children=[check]——已是目标行为。

### P17 `auth check`

- 类型/今日 handler：叶子；handler `auth.check`（裸路径执行探测，帮助入口不得调用）。
- 帮助入口：`auth check --help`/`-h`、`help auth check`。
- 错误协议：认证 invalid_arguments/1。
- effects（保持真实认证契约）：mutates=false、network=true、browser_required=true、destructive=false；无 variants。
- output：执行 json/text（GLOBALS --format）；帮助 json/text。参数：无自有选项，仅 GLOBALS。
- errors：invalid_arguments、auth_required、browser_unavailable、service_failure。
- before：未单独探针 `auth check --help`；由 auth/cli.py 的 `global_args.help` 分支推导为退出 0 JSON 帮助，与 P18 探针同机制。

### P18 `login`

- 类型/今日 handler：叶子；handler `login`。
- 帮助入口：`login --help`/`-h`、`help login`；帮助不得触发登录流程。
- 错误协议：认证 invalid_arguments/1。
- effects：mutates=true、network=true、browser_required=false（自行启动 headed Chrome）、destructive=false。
- output：执行 json/text；帮助 json/text。
- 参数清单：`--timeout-seconds`，type=positive，默认 600.0；加 GLOBALS。
- errors：invalid_arguments、auth_required、browser_unavailable、browser_busy、login_in_progress、service_failure。
- before（探针 run 18）：`login --help` 退出 0 JSON 帮助——已是目标行为；`help login` 今日退出 2（未支持）。

### P19 `logout`

- 类型/今日 handler：叶子；handler `logout`。
- 帮助入口：`logout --help`/`-h`、`help logout`；帮助不得触发登出。
- 错误协议：认证 invalid_arguments/1。
- effects：mutates=true、network=true、browser_required=true、destructive=false。
- output：执行 json/text；帮助 json/text。参数：仅 GLOBALS。
- errors：invalid_arguments、browser_unavailable、browser_busy、login_in_progress、logout_unverified、service_failure。
- before：未单独探针；与 P18 同机制，推导 `logout --help` 为 JSON 帮助退出 0。

### P20 `help`（meta 命令）

- 类型/今日 handler：meta；今日不存在（探针 run 13、19：`help`、`help payment channel list` 均退出 2 invalid choice）。
- 目标行为：`help` == 根帮助；`help PATH` 定位任意节点；`help login`/`logout --help` 等认证路径只显示帮助，绝不调用认证 handler。
- 语法约束：只接受命令路径＋帮助控制选项（`--format json|text`）；未知路径/选项/格式失败，指向最近有效路径的帮助命令；无缩写；`--` 之后不视为帮助开关；`--id login` 等值不得误路由为 help/login/auth。
- 错误协议：随 PATH 已解析归属——解析到认证路径用认证 invalid_arguments/1，其余用业务 INVALID_ARGUMENT/2；`help` 自身解析失败（未知首词）按业务协议。
- effects：全 false（帮助自身无操作）。output：`help_default_format=json`、`help_formats=[json,text]`，拒绝 table/markdown。
- 可发现性：永不出现在任何 children；经根与节点的 examples/next 发现。

## 20 次探针 before 基线（dogopencli 侧）

以下为 Task 4 证明“行为已改变/保持不变”的对照。run 编号对应 `tmp/help-reference-evidence.json` 的记录顺序（1–10 为 DI，11–20 为 dogopencli）。

| run | 输入 | before 实测 | 目标（after） |
| --- | --- | --- | --- |
| 11 | 无参数 | 退出 2，stderr 缺 group | 退出 0，根 help_version=1 JSON，stderr 空 |
| 12 | `--help` | 退出 0，argparse 文本，仅 refresh/payment | 同根 JSON（含全部 5 个 children） |
| 13 | `help` | 退出 2，invalid choice 'help' | 同根 JSON |
| 14 | `payment` | 退出 2，缺 target | 退出 0，payment 节点 JSON |
| 15 | `payment channel` | 退出 2，缺 action | 退出 0，channel 节点 JSON |
| 16 | `payment channel list --help` | 退出 0，argparse 文本 | 退出 0，叶子 help_version=1 JSON |
| 17 | `auth` | 退出 0，auth JSON 帮助 | 不变（回归保护） |
| 18 | `login --help` | 退出 0，auth JSON 帮助 | 不变（回归保护） |
| 19 | `help payment channel list` | 退出 2，invalid choice 'help' | 退出 0，同 run 16 目标 JSON |
| 20 | `--help --format text` | 退出 0，argparse 文本，format 未解释 | 退出 0，根 text 渲染 |
| 1–10 | DI 侧参考实现 | 参考实现行为 | 仅作对照，不构成 dogopencli 阈值 |

未单独探针的路径（P05–P10、P11–P15 裸组与叶子帮助、P17/P19 帮助）按同一 argparse/auth 机制推导 before，Task 4 首跑即固化实测。

## Task 4 自动化验收覆盖清单

下列每条必须至少有一个自动化断言（测试名不限）；P01–P20 全部在覆盖范围：

1. P01–P03、P05、P07–P08、P11–P12（根与全部组）：裸路径、`--help`、`-h`、`help PATH` 四入口定位同一 JSON 节点；退出 0、stderr 空；children 仅直属且根顺序为 payment、refresh、auth、login、logout；`--format text` 两位置等价。
2. P04、P06、P09–P10、P13–P15（业务叶子）：`PATH --help`/`-h` 与 `help PATH` 定位同一 JSON 叶子；`children=[]`；参数清单逐字段结构断言（required/default/choices/append）；生效默认 limit=100、offset=0 与 `--all` 冲突；effects 与 effects_variants（缓存初始化/迁移 mutates=true network=false；`--live` 变体；refresh channel 双分支静态列出）；output 区分执行格式（查询 json/table、refresh envelope）与帮助格式（json/text）。
3. P10 特项：裸 `get` 缺 `--id` 仍为业务参数错误退出 2；`help payment sla baselines get` 成功退出 0。
4. P16–P19（认证路径）：`auth`、`auth check --help`、`login --help`、`logout --help`、`help auth`、`help login`、`help logout` 为 JSON/text 帮助且退出 0，不调用认证 handler；认证参数错误保持 invalid_arguments 退出 1；GLOBALS 与互斥约束不变。
5. P20（meta）：`help` == 根；未知路径/选项/非法格式（table/markdown）失败且不回退根帮助；错误协议按归属（业务 2/认证 1/帮助 0）；`--format` 前置/后置等价；无缩写；`--` 分隔；`--id login`、值为 help/login/auth 的误路由回归。
6. 隔离：每个非叶子帮助入口在配置解析、SQLite/源文件、浏览器/CDP、网络入口全部 fail-on-call 下通过；缺失/损坏配置、无缓存、只读 cwd 下帮助成功且不新建文件。
7. 文档形态：stdout 为单个完整 JSON 文档、字段顺序确定；text 渲染与 JSON 同信息、无 ANSI/pager/TTY 分支。
8. 基线回归：run 17、18（auth、login --help）保持 byte 级或结构级不变；run 11–16、19、20 证明目标行为取代 argparse 行为。

## 未验证与边界

本矩阵是验收规范，不声称新帮助已实现。`--biz-legal-entity` 的独立筛选效果、后端字段 schema 不在本轮复验范围；帮助不引入 DI 运行时依赖；ADR 0004/0005 对业务/认证协议、退出码、缓存、传输白名单与 CDP 端口的约束保持不变。
