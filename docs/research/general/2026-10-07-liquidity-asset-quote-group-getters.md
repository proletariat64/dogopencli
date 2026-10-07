# Liquidity 资产交易与报价组原生 getter 验收

Observed: 2026-10-07
Scope: general
Status: snapshot

权威规格 [#141](https://github.com/proletariat64/dogopencli/issues/141)，
[可读副本](../../design/liquidity-native-asset-quote-group-getters-v0.1.0.md)。
本轮仅实施两个独立原生详情；列表采集、其他 getter、报价组列表覆盖协议和资产日志归属不在本轮范围内。

## 原生契约

| 公共命令 | 原生请求 | 身份和范围 |
| --- | --- | --- |
| `liquidity operations asset-trades get --order-no` | form POST `/assetTransferOrderDetailQuery.json`，仅 orderNo | 根 data.orderNo 精确匹配；认证租户与缺失原生租户回显分开 |
| `liquidity investment quote-groups get --quotation-group-row-id` | form POST `/queryQuotationDetail.json`，仅 quotationGroupId | wire 传物理 row.id，根 data.id 精确匹配，原生租户 GUAPW3SG、字符串业务组 ID 与整数版本均保留 |

报价组不得以业务 quotationGroupId 输入隐式选最新版本；版本由物理行 ID 选择。
根和历史同一投影，历史保持顺序与不同物理 ID；允许所选根出现在历史中，拒绝历史内重复物理 ID、
业务组/租户矛盾及未支持的非空递归历史。完整 contactInfoList 保持对象数组。
根与历史均排除附件下载地址、fileKey、reviewLink 和动作字段，不跟随附件或审批入口。

资产详情只包含已绑定交易根和产品对象，保留 `assertProductCategory` 等原生拼写、金额精度、
币种、日期、状态及原生空值。采样日志 orderNo 不匹配交易根任何原生身份，因此首版排除
`transFerOrderLogVoList`；不猜 ID 转换或调用日志接口。

普通 get 离线；独立 detail refresh 仅在验证通过后原子发布；live 不写缓存、不回退。
HTTP、认证、业务拒绝、身份或结构失败保留旧 capture；列表缓存不能代替详情。

## 来源与方法

来源是 #141 的已验证原生契约：研究阶段仅八次明确只读业务查询，资产详情 2/2，
报价组详情 4/4；同一业务组版本 3 和 1 使用不同物理行，历史为 [3,2,1]。
研究查询不是公共 CLI 生产 UAT。

当前前端产物 SHA-256：`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`，
15,763,128 字节。零起点字符偏移：资产 service 1476250、loader 9576722、mount 9578124；
报价组 Detail link 9889568、history link 9900361、loader 9901722、service 1529847。
Graphify 先行的原始 PRD 核对见权威规格；本轮复用已有证明，没有重复做列表研究。
真实 ID、联系人和响应仅在本机私有目录；提交 fixture 全部使用合成数据。

## 实施与验收状态

实施提交 `16a9d59`，集成代码 `0e7442663f9f7a38aa3e30a3261a067f60281a74`，
[PR #142](https://github.com/proletariat64/dogopencli/pull/142) 关闭规格 #141。
本地针对性 279 tests 通过（其中新增公共 getter 用例 75 项）；
Ruff check、format（358 文件）及 doc-guard（142 Markdown）通过。
Standards 审查 0 文档标准违规、1 个可选注册重复判断；Spec 审查 0 确认的实质问题。
完整本地测试 3014 tests 和 28 subtests 通过；最终远程 CI 以 PR 对应提交的结果为准，不以研究请求替代。

独立公共 CLI 生产 UAT 在上述集成代码上通过 **2/2 叶子、3/3 原生对象**：
一个资产交易，以及同一业务报价组的物理版本 3、1。
使用现有专用 9222 浏览器、真实共享控制锁、临时 config 和 SQLite；public liquidity auth check 成功。
三个对象各一次显式 detail refresh 和一次 live，共六次真实原生只读业务请求；
每个请求精确核对 form POST、原生 host/path、单字段 body 与正确物理身份绑定。
输出使用独立硬编码投影与该次真实 CDP 原始响应逐值比较，没有调用产品 projector 构造 expected。

资产日志被排除，产品五个原生字段正确保留；报价组的联系人完整对象、历史次序和组成
与原生响应一致。版本 3 和 1 的所选根保持自身版本，不被历史较新版本提升；
刷新另一物理行后仍能离线读取原对象及原 capture 时间。
请求租户、wire 请求范围、原生租户回显存在性和 source_version 分别核对，settings/runtimes 类型正确。

断开 CDP 后普通 get 与该 capture 相等且不调用 CDP；live 不改变 SQLite 字节哈希；
断开 live 不回退，失败 refresh 保留旧 capture ID、时间、数据和缓存字节。
原有 browser target inventory 完全相同，生产缓存 SHA-256 未变。
真实对象 ID、联系人、金额和原始响应只存私有 UAT 目录，不进入 Git 或本报告。

当前唯一公共目录为 **98 supported / 34 unsupported / 132 total**，
含 66 list、32 detail/history；其中仍有 22 unsupported get。
报价组 list 继续不支持，monitoring HOLD 及其他门槛保持原状。
用户明确跳过 Kimi CLI，并授权本批 PR 收尾时评论 @greptile 触发一次审查/CI。
版本发布和合并仍由用户单独授权。
