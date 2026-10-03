# 变更记录

## 未发布：统一 incomplete 结果策略

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
[ADR 0019](docs/adr/0019-usable-incomplete-acquisitions.md)。本次验证限于合成离线数据，
未执行新策略的生产 UAT；本节不表示已发布版本。
