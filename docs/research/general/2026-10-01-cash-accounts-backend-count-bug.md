# 银行账户列表总数与实际返回数量不一致

Observed: 2026-10-01
Scope: general
Status: snapshot

## 发生了什么

生产银行账户列表接口 `GET https://iliquidity.alipay.com/queryintnalbkactlist.json` 持续返回 `resultFlag=true`、`count=3691`，但实际只能取得 **3690 条账户记录**。记录数组为 `result.bankAccountPropertyVOList`。

在同一未筛选查询范围下，分别使用 pageSize 10、50、100、1000、5000，最终取得的账户集合相同，无重复或身份内容冲突。5000 单页也只返回 3690 条，因此本次缺口不依赖客户端跨页拼接。后端计数与数据返回存在异常；具体是计数多算还是列表漏返，尚未确认。

## 界面如何复现

1. 登录 [银行账户信息维护](https://iliquidity.alipay.com/GUAPW3SG/menu/IntNalBankAccount)，清空查询条件，查询普通银行账户列表。
2. 将每页条数设为 **50**，翻到 **第 41 页**（从 1 开始）：对应 `rowStart=2000,pageSize=50`。
3. 在开发者工具 Network 中找到 `queryintnalbkactlist.json`：本次对应响应 `count=3691`，但 `result.bankAccountPropertyVOList` **只有 49 条**。这不是末页；后续页面仍有数据。
4. 保持相同条件、每页 10 条时，第 **203 页**对应 `rowStart=2020,pageSize=10`，响应只含 **9 条**，总数仍为 3691。

上述界面页码按已确认的原生分页协议换算；短页已通过相同接口和请求范围复现，本轮未重新逐页点击界面。总数是当次数据快照，后续新增或删除账户可能改变页码和数量。

## 给后端的补充证据与验收

| pageSize | 短页 rowStart | 预期条数 | 实际条数 | 全量实际 / count |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 2020 | 10 | 9 | 3690 / 3691 |
| 50 | 2000 | 50 | 49 | 3690 / 3691 |
| 100 | 2000 | 100 | 99 | 3690 / 3691 |
| 1000 | 2000 | 1000 | 999 | 3690 / 3691 |
| 5000 | 0 | 3691 | 3690 | 3690 / 3691 |

5000 为经过共享只读传输验证的接口请求值，不是页面下拉框选项。技术人员可在授权环境复用相同查询，仅更改 `bankAccountQueryVO` 中的 `rowStart/pageSize`，核对单页完整数组与 `count`。

预期：同一稳定查询范围下，`count` 与实际可返回的账户数一致；非末页按请求页宽返回，末页与剩余总数一致。请检查计数和列表的数据来源、筛选及组装逻辑，确定这 1 条差异的原因。

私有脱敏汇总位置：`tmp/accounts-page-sizes-20261001T142545Z/summary.json`、`tmp/accounts-page-sizes-20261001T142921Z/summary.json`。本报告不包含账户标识、原始响应或认证信息。
