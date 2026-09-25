# 收款 VA 池查询研究

Observed: 2026-09-23
Scope: general
Status: snapshot

## 当前状态

用户要求逐项验证 VA 池列表、再验证 VA 实体账户列表，并明确只读。此记录先处理 VA 池。已完成本轮可见导航与关联详情调查，**尚未定位独立 VA 池列表并取得其查询契约**，因此不能将 `collection va-pool list` 标为已验证或可实施。这不证明功能不存在；下一步需要准确菜单名称/页面 URL 或新的导航证据。

本轮 auth check 最初返回 headless 会话 healthy，但打开前轮已观察的 VA Capacity Monitoring 菜单后重定向至 `ipaybuservice.alipay.com/login.htm`。已通过正常 `dogopencli login` 打开专用 headed Chrome，等待人工 SSO。重定向只证明本次页面需要登录，不能据此认定 VA 池查询不存在或业务权限不足。

后续一次默认入口 login 返回成功，但同一 VA Capacity Monitoring 页再次重定向，目标 appName 为 `ifundcontrolprodops`。因此默认付款入口的 healthy 判定不能代替目标页登录验证。本轮未修改认证代码或持久配置；使用现有 login 函数及同一专用 profile，仅在内存中将 startup_url 指向已观察的目标页，保留所有归属检查、锁与 headed/headless 复验。等待曾超时，用户随后确认完成登录；重新运行该流程返回 authenticated/healthy、headless，并成功打开目标页。没有绕过登录或尝试其他入口规避权限。

## 生产观察与未命中的路径

以下操作均为导航、读取结构或已确认查询，未使用写入表单：

| 观察位置 | 当前证据 | 不应推断 |
| --- | --- | --- |
| [VA Capacity Monitoring](https://ifundcontrol.alipay.com/productOperation/collectionProductManagement/networkConstruction/VACapacityMonitoring)，iframe `https://ifundbossportal.alipay.com/voucher/VACapacityMonitoring` | 控件包括银行账户规则 ID、VA 规则 ID、账户、主体、场景、币种、告警状态；表头为总量/已用/未用/可分配、日申请量及告警天数等 | 容量监控不是独立 pool 记录列表；未将初始零值当作无库存 |
| Product Operation Center 的 Collection、Collection/Payment Operations、Fund Operations 导航 | 已知 22 个收款菜单之外，关联分组主要为工单、邮件、资金流查询；未见独立池列表 | 仅代表本轮当前账号的可见导航，不能断言平台无池功能 |
| Global Standard Collection、C&P Products Service、C&P Products Signing | 当前可见介绍、订单/工单、签约查询与签约入口；没有识别到 pool list | 未执行签约动作，也未扩展为订单数据调查 |
| ifundboss 原生 voucher、accounts、dictionary、basicInfo、customerAccount 菜单 | 有 VA-Collection、New VA-Collection、VA Batch Import/Batch fix、规则/账户相关入口 | 未进入导入/修复操作；名称中含 VA 不等于池查询 |
| [New VA - Collection](https://ifundbossportal.alipay.com/voucher/VA1) | 表头/条件为 collection voucher、到账时间、金额、交易/退款状态，是收款凭证查询 | 没有执行该页 Search，不把其当作池或物理 VA 账户列表 |
| igfc 的 Standard payment and collection、Basic Info 导航 | 套餐/业务签约、银行账户及基础资料菜单 | 未发现可证实的 VA 池列表；没有以银行账户管理替代池查询 |

还读取页面实际加载的 route asset：`https://renderoffice-intl.alipayobjects.com/p/yuyan/180020010001284167/umi.1910fa74.js`，SHA-256 `7f5d09281465affd7a58d7b1ee83f3e371f0adaae464e9d0206c6930d5e860ad`。其中可见 VA/VA1、导入/修复、银行账户 VA 规则、VA 规则和容量监控等路由；未匹配到独立 VA pool 路由名称。该搜索不是全站功能不存在的证明，也没有据 bundle 字符串调用未经观察的 API。

### 银行账户规则详情关联线索

在已验证的银行账户规则列表上只点击 **Details**。页面跳至 `/voucher/bankAccountVARuleManage/edit`，显示 VA import information、导入/分配数量和号码、可分配量及操作历史表头。这些是页面结构，不是成功返回的池记录。

原生 GET `https://ifundboss-api.alipay.com/ivostro/api/bankAccountVaRule/detail.json` 带 `bankVaRuleId`、`bankAccountNo`、`ctoken` 参数。页面请求及一次只读重放均 HTTP 200，但 `success=false,status=false,resultObj=null`；错误码 `IPAY_RS_510090491`，errorName `CROSS_INVOKE_PARAM_CAN_NOT_NULL`。两个业务参数在 URL 中不是空字符串、undefined 或 null 字面量；后端内部根因未确定，不修改参数试探绕过。

Details 页面同时渲染 Temporary storage、Submit 等表单控件；本轮没有点击它们，也没有使用 Preview、VA_import、add VA rule、Offline、Delete 或 Sync。查询失败不得解释为池为空或没有分配记录。

## 历史对象与来源

先执行 graphify query 再核对源文档，未重建图谱或保存查询结果。以下来源路径相对于 `/home/ubuntu/dev/dogpdkb/graphify_flatten_ready/`。

| 来源 | 位置 | 历史证据 |
| --- | --- | --- |
| `收付款产品__流入流出中心__来账中心__来账需求__VA号随机分配-2026-04-19-[117375059].md` | 54–63 行 | 原始号码库存隶属银行账户规则，部分分配给开户规则，再选取单个 VA；一个开户规则可能有多个池 |
| 同上 | 66–86 行 | Pool 策略导入逐个号码，可连续或不连续；Segment 策略导入号段，两种库存表示不能混同 |
| `收付款产品__收款产品__产品建设PRD__自助运营__ifundboss运营__VA基础规则管理及VA导入-资金平台PRD__VA规则及导入管理-优化-2026-04-19-[120652638].md` | 65–76、152 行 | 机构收款能力绑定特定银行账户的 VA 池，支持单/多币种并可补充库存；池不是底层银行账户 |
| `收付款产品__收款产品__产品介绍文档__全球收款产品说明书-2026-04-19-[216566174].md` | 599–606、617–623 行 | 原始 VA 池与银行收款账户关联；产品开户规则的池可从原始池补充 |
| `Planning-and-progress-of-key-projects__Key-business-line-s-project__B__WF__WF-RP-WAVE1__WF-RP-WAVE1资金平台PRD__清算域PRD含M1-M2-M3__WF-VA管理页面优化-2026-04-18-[52161101].md` | 15–19、47–58、80–91 行 | 曾有“VA池管理运营页面”；旧上传表单字段不是当前 list 查询参数或菜单路由证据 |

历史用语包含 VA池、VA号池、原始VA号池、VA号段。`Pool` 同时也是具体分配策略名，因此不能把所有“池”查询固定为 `POOL` 策略。

## 只读调查约束

仅导航、读取页面结构，以及执行观察确认的查询或详情。不得执行创建、导入、上传、分配、补池、激活、删除、同步或配置修改；不从这些动作的表单反推查询契约。仅保存脱敏结构、字段名、计数和证据，不保存 VA/银行账号值、客户数据、凭证或原始响应。

## 后续核验与设计门槛

1. 从实际导航识别 VA 池查询入口；VA Capacity Monitoring 是已知导航线索，不预设它就是池列表。
2. 区分原始池、按开户规则分配的池、号段与逐个 VA 库存；只按真实页面和 API 返回定义对象。
3. 确认查询 endpoint/method/action、默认范围、参数类型、pool/rule 标识、状态、计数及分页；池容量摘要不等于个体账户列表。
4. 只重放已确认查询，校验业务成功、总数、重复与截断；不通过写动作制造验证样本。
5. 保存结果及设计缺口，再开始独立的 VA 实体账户研究。历史上传字段、策略名或推测路由不进入允许清单。

本轮结论：登录已恢复，但独立池列表尚未验证。用户随后要求找不到就停止，故停止 VA 池和物理/实体 VA 账户入口搜索，两项均保持未验证并排除在实现范围之外；不再等待用户提供 URL，也不注册占位命令。已完成的首期收款交易成本规格见 GitHub Issue #21。
