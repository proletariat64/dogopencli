# 付款与收款运营领域术语

本词汇表描述付款与收款运营查询中的业务对象及其区别。

## Language

**查询（Inquiry）**：读取已有业务配置、状态或记录的操作，不推进业务状态，也不发起付款、重试、退款或测试交易。
_Avoid_: 将重新执行路由或业务试跑称为查询。

**付款渠道（Payment Channel）**：以机构账户、清算网络及币种等条件表达的付款能力；银行名称本身不能唯一标识一个渠道。
_Avoid_: 将银行、银行账户和渠道作为同义词。

**渠道成本配置（Channel Cost Configuration）**：描述渠道费用的适用条件、计费方式、金额或比例及有效期的配置记录；一条记录可包含多条计费规则。
_Avoid_: 将成本配置、渠道成本评分和实际交易费用作为同义词。

**流量规则（Flow Rule）**：针对业务、币种、地区等条件选择和分配流出渠道的运营配置，具有版本及不同的配置、审批和灰度状态。
_Avoid_: 将所有状态合并为“启用”。

**降本规则（Cost Reduction Rule）**：围绕降低付款成本设置的切流配置，与渠道自身的费用或报价记录不同。
_Avoid_: 用“渠道成本”代指降本规则。

**重试规则（Retry Rule）**：规定交易异常情况下重试条件和处理方式的已有配置；读取规则不等于发起重试。
_Avoid_: 用“重试交易”代指查询重试规则。

**产品 SLA 基线（SLA Baseline）**：在业务、目的地等条件下约定付款成功和到账时效的配置，与渠道 SLA 规则分别表示。
_Avoid_: 将 SLA 基线与实际到账耗时作为同义词。

**付款单据（Payment Order）**：记录实际付款业务处理的单据；与关联调拨单、银行处理记录及 PTR 单据分别识别。
_Avoid_: 将不同层次单号合并为无类型的通用单号。

**收款交易成本配置（Collection Transaction-Cost Configuration）**：描述收款渠道交易费用的适用条件、计费方式及费率的配置记录；不同于已发生交易的实际费用，也不同于 VA 账户费用配置。
_Avoid_: 将收款交易成本配置简称为实际收款费用，或与 VA 费用混用。

**收款 SLA 配置（Collection SLA Config）**：按收款业务线、主体、币种与地区约定的
时效目标，包含端到端和内部处理时长以及节假日限制。详情与列表摘要分别表示。
_Avoid_: 将收款 SLA 配置称为付款 SLA 基线，或将配置目标等同于实际订单耗时。

**收款 VA 规则（Collection VA Rule）**：在银行账户 VA 规则之上附加主体、场景与地区等
业务维度、用于后续 VA 申请匹配的规则配置；以字符串 `vaRuleId` 标识，列表与真实详情
分别表示。
_Avoid_: 将收款 VA 规则与 `bankRuleId` 指向的银行账户 VA 规则（bankAccountVaRule，
不在查询范围）、VA 池/容量监控/PTR 库，或已撤回的 va-value 候选命名混用。

**收款 VA 容量监控行（Collection VA Capacity Row）**：VA Capacity Monitoring 菜单中一条
VA 规则的容量与预警快照，以字符串 `ruleId` 标识；`id`、`bankAccountVaId` 与
`accountNo` 都不唯一，不能充当行身份。计数器是后端实时值，`canUseDays` 是后端估算，
不做本地推导。
_Avoid_: 将容量监控行当作 VA 规则、银行账户 VA 规则、VA 池或单个 VA 账户；将
`bankVaRuleId` 请求字段与行字段 `bankAccountVaId` 以外的字段对应；将预警状态
（Y/N）等同于 `warningCount` 或 `warningDays` 的任何阈值。

**详情拒绝（Detail Refusal）**：后端明确拒绝单个已列出对象的详情读取（HTTP 200 且
`success=false`）；列表行仍是真实配置数据，与“记录不存在”和“列表覆盖不完整”分别表示。
_Avoid_: 将详情拒绝称为详情为空、缺失记录或查询成功。
