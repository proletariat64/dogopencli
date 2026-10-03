# 现金流预测准确率列表跨页重复和遗漏

Observed: 2026-10-02
Scope: general
Status: snapshot

## 发生了什么

2026-10-02原生当天范围，GET `/bankCashForecastRecordAccuracyQuery.json`。
请求字段`tntInstId,bankCashForecastRecordQueryVo`；VO沿用UI当天日期、000000–235959时间及默认金额过滤，仅将分页设为pageSize=1000、rowStart=0/1000/2000/3000/4000。

五页业务成功，报告总数始终4419；每页到达1000/1000/1000/1000/419条，合计4419条，**只有4416个唯一record.id，3条跨页重复**，重复内容相同。

| 第一次出现 | 重复出现 |
| --- | --- |
| 第1页第999条 | 第2页第2条 |
| 第2页第1000条 | 第3页第5条 |
| 第3页第999条 | 第4页第1条 |

作为独立对照，预测结果原生列表在相同日期用5000单页，两轮均4419个唯一ID、内容一致；准确率多页集缺少其中3个ID、没有新增ID。这是跨接口对照，不等同于单独证明准确率接口的全部期望ID。稳定总数与边界重复已足以证明本次多页取得不完整。

未触发响应10MiB截断，未出现认证/传输错误。**此准确率endpoint的5000尚未探测**；不要引用预测结果接口的5000成功作为其兼容性证明。后台是否缺稳定排序、执行时发生更新或其他问题，尚未确认。

## 在界面与Network复现

1. 登录Liquidity，进入 **现金流预测准确率**：`https://iliquidity.alipay.com/GUAPW3SG/menu/CashFlowForecastAccuracy`。
2. 选择已有记录日期（本轮2026-10-02）与全天创建时间，点击原生查询。
3. DevTools Network找到`bankCashForecastRecordAccuracyQuery.json`。保留原生筛选，使用开发工具的只读Edit and Resend，将JSON字符串VO中的pageSize设1000，依次设置上述五个rowStart；若浏览器工具不支持编辑重发，由技术团队用相同已登录会话重放查询。
4. 汇总`$.result.dataValue[].id`，与`$.result.count`对比，检查上表的相邻边界。不要仅按总到达条数判断完整。

UI原生小页不会提供1000选项；此步骤使用Network重放同一inquiry检查后台分页。本轮**未点击UI分页验证上述五页，也未证明原生10页宽能复现同样边界**。真实参数与响应仅在私有`request-032.json`至`request-036.json`。

## 期望

固定查询范围的分页须可靠收敛，record.id不跨页重复，总数与唯一到达数相符；前端/CLI必须在不完整时明确失败或告警，不能因总到达数等于count而认为成功。
页面准确率指标另从`cashFlowDetailDay.json`补充，这与本报告基础列表分页异常是两个独立问题。
