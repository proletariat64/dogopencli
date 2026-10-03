# 变更记录

## v0.2.5（2026-10-04）

合并 PR #83，新增 `liquidity operations swaps list` 与对应 refresh，必填
`--trade-from`、`--trade-to`（YYYYMMDD，包含两端）。默认离线读取精确范围缓存，
显式 live 不写缓存；无日期、单边、倒置范围拒绝，get 继续 unsupported。
正式注册 CLI 生产只读 UAT 21/21 通过。

四列表 batch 交付 1/4；demands、executions、investable-funds 仍缺少非空原生
证据，#82、#84、#85、#86 尚未完成。查询叶子为 69 supported、64 unsupported。
同步 README 与 snapshot 回归测试的支持状态；源码版本由 0.2.4 增加至 0.2.5。
此记录不表示安装包或 GitHub Release 已发布。

## v0.2.4（2026-10-03）

新增 `dogopencli snapshot`，离线查看当前命令树及本地缓存元数据，支持 JSON、
文本树和表格。报告命令 supported/unsupported、记录数、采集时间、完整性、
新鲜度与留存范围；保留延期叶子及原因，不读取业务行、不启动浏览器或刷新缓存。
支持子树和叶子选择，详情缓存独立统计。规格 #80，实现 PR #81。

本次发布同时包含此前合并的 Liquidity v0.2.3 查询能力及以下统一 incomplete
结果策略。版本由 0.2.3 增加至 0.2.4；wheel 与源码分发包随 GitHub Release 提供。

### 统一 incomplete 结果策略

默认 live、离线列表及 refresh 可以使用经过验证的 incomplete 数据：返回
`error=null`、退出 0，JSON `meta.warnings` 与 stderr 每次告警，完整性仍为 false。
首次 partial refresh 可建缓存，最新 partial 可以替换旧完整缓存；不从旧缓存补行。
需要完整结果的脚本应使用 `--require-complete`，刷新也支持该参数；严格拒绝退出 1，
`data=null`、`INCOMPLETE_RESULT`，并在提交前保留原缓存。

完整性证据随数据原子保存，区分后端总数、原始行次、唯一记录、重复与留存缺口。
没有原生身份时保留行次，不以整行哈希去重；去重本身不证明完整。
格式、身份、范围、权限、超时及稳定性失败继续拒绝整个候选。PTR 的双轮稳定校验保留，
Collection cost 仍为固定单页 1000，holdings 仍为 500。

Liquidity dated 按最新同范围请求窗口确定有效行与覆盖证明；最新 partial 不复用
旧窗口内的行补洞。默认刷新报告实际 `meta.published` 和提交后的留存质量。
新 Liquidity 索引带 acquisition 格式标记，旧读取器会拒绝该格式。
回滚应恢复迁移前的缓存备份，或隔离新格式缓存后重新刷新；不能只回退二进制。
离线缓存读取不建库或迁移库。

规格与边界见[统一 incomplete 规格](docs/design/unified-incomplete-v0.1.0.md)及
[ADR 0019](docs/adr/0019-usable-incomplete-acquisitions.md)。离线回归及新策略的
[生产只读 UAT](docs/research/general/2026-10-03-unified-incomplete-production-uat.md) 已完成：
82/83 个目标命令通过，Payment channel EXTERNAL 源端阻塞，ledger balances 按用户要求跳过。
后端阻塞与跳过项仍按原报告保留，不因发布版本而视为通过。
