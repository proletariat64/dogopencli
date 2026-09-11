# v0.1.0 聚焦渠道、SLA 基线和成本查询

Status: accepted
Date: 2026-09-08

沿用 [ADR 0001](0001-query-capability-model.md) 的查询能力建模方式，用户确定 v0.1.0 纳入付款渠道、产品 SLA 基线和成本页面查询。流量、同行转账、降本、银存切换及重试规则整体移至下一版本，不注册为本版本的占位命令。

渠道使用单数分组，对应 `payment channel list`；产品 SLA 基线对应 `payment sla baselines list` 和 `payment sla baselines get --id ID`。用户在设计访谈第一轮确定成本采用与 `channel` 同级的 `payment cost list`，覆盖付款根下 `productPriceManagement/channelCost` 页面的付款成本查询。

渠道默认场景为 `EXTERNAL`，允许通过 `--payout-type` 显式指定已验证的其他场景 `LIQUIDITY`、`MANUAL`、`SETTLEMENT`。成本固定 `costTypeCode=FUND_OUT_CHANNEL_TRANS_FEE`，本版本不纳入共享成本页面的收款、外汇和流动性成本。该限制是 CLI 的已接受范围，不是后端参数的必填规则。

## 默认状态与版本可见性

用户在 Q27 确定默认展示接口实际返回的全部配置状态，包括草稿、灰度、生效、下线等，不隐式限定为当前有效。需要缩小范围时显式筛选状态；不把默认过滤造成的缺失解释为配置不存在。

接口返回的不同配置版本分别保留，不按同名渠道、机构或账户合并。去重仅消除已确认属于同一记录的重复，不能丢弃不同版本。这一决策规定查询可见性，不证明后端提供完整历史版本，也不增加历史查询能力。

## 范围与验证

成本指渠道费用记录；降本切流规则归入下一版本的 `rules cost-reduction`。产品 SLA 基线与渠道 SLA 规则分别建模，本版本包含前者。全部业务操作保持 inquiry-only，收款产品不在本版本范围内。

决策时的[付款研究](../research/payment/2026-09-08-payment-operations.md)已观察到渠道和 SLA 基线查询成功，以及成本页面列表数据；当时成本接口、筛选、分页和响应契约尚待核验。后续补充证据见[成本查询契约](../research/payment/2026-09-08-cost-query-contract.md)。纳入版本范围不代表已经实现或完成接口验证。此范围取代研究报告中优先实现流量规则的建议；研究快照保留原有观察。
