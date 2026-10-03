# 银行账户原生查看返回未知异常999

Observed: 2026-10-02
Scope: general
Status: snapshot

## 发生了什么

2026-10-02的专用Liquidity已登录会话中，原生账户列表前100条包含100个不同账户身份组合，但所有行返回同一个`id`。
原生页面`handleView(row)`使用`row.id`跳转`IntNalBankAccountView/<id>`；查看页将route中的id传给GET `/queryaccountbyid.json`，字段为`tntInstId,id`。

按照该原生查看身份只读查询两次，HTTP都为200，`resultFlag=false`、`result.success=false`、`result.errorCode="999"`、`result.errorMessage="未知异常"`。耗时约1.45/0.30秒。未出现认证失败或传输超时。

这不能当作成功详情。多个列表账户共用id与详情异常均需后台检查；本报告没有确认根因，也未将它归为权限问题。

## 界面复现

1. 已登录Liquidity，进入 **信息维护 / 银行账户**：`https://iliquidity.alipay.com/GUAPW3SG/menu/IntNalBankAccount`。
2. 打开DevTools Network，查询账户列表，查看`queryintnalbkactlist.json`返回行的`id`。
3. 选择第一条账户的原生 **View**，核对跳转路径及`queryaccountbyid.json`请求参数；无需新增、编辑或提交。
4. 查看响应是否HTTP200但业务flag为false、errorCode为999；选择另一账户行比较传入id是否相同。

本轮证据来自当前源码的原生查看caller和共享transport发出的相同只读请求；**未逐项点击UI复现**，上述点击步骤由已确认caller推导。具体账户身份和请求参数只保留在私有证据`request-043.json`、`request-044.json`以及列表对照中。

## 期望

原生列表查看身份应可正确取得对应账户详情，或返回明确的业务错误。不同账户身份不能因共享不可用的查看id而全部落到未知异常。
已有账户列表3690/3691 count差异另有报告，本轮未确认两者有共同根因。
