# 四项付款查询契约的综合验证

Observed: 2026-09-08
Scope: general
Status: snapshot

## 范围与证据标准

本轮仅覆盖付款渠道列表、渠道成本列表、产品 SLA 基线列表和详情。Astra 探查成本，Sol 探查渠道，Terra 探查两项 SLA 查询，Luna 独立审计报告；主线程整合证据并独立复验。完整菜单和写入功能不进入运行时建模。

“查询成功”表示具体请求返回成功；“字段已观察”不代表所有空值、枚举和嵌套分支均被穷尽。前端源码只证明当前页面如何构造或展示请求，不能单独证明服务器对所有输入的处理。所有契约均为账号与站点版本视角的快照。

## 四项契约结论

| 查询 | 已补齐的主要证据 | 实现边界 |
| --- | --- | --- |
| [渠道列表](../payment/2026-09-08-channel-query-contract.md) | 精确 POST、九个筛选及数组类型、字典来源、场景/状态、双层业务结果、页码与空结果、行字段 | 显式选择场景；处理末页回退；未知值保留，动态字典不能固定为穷尽枚举 |
| [付款成本列表](../payment/2026-09-08-cost-query-contract.md) | 精确 POST、七个筛选、付款范围、计费样本、空结果和参数错误；追加单次 5000 条容量查询取得 3291 个唯一 ID | 当前全量可通过单次大页读取；跨页重叠和更大容量仍未解决；保留金额和比例单位，不能推算完整实际费用 |
| [SLA 基线列表](../payment/2026-09-08-sla-query-contracts.md) | 精确 POST、五个字段映射、四个字段结果复验、状态字典、零基分页、成功无匹配分支 | `bizLegalEntity` 筛选效果未独立证实；未知嵌套和日历语义原样保留 |
| [SLA 基线详情](../payment/2026-09-08-sla-query-contracts.md) | 精确 GET、列表 `id` 到 `slaBaselineId` 映射、成功/不存在/缺参数分支、秒单位 | `resultData=null` 区分不存在与业务失败；不能凭前端引用猜测未返回字段 |

四项查询的主要请求与解析契约已具备受限实现依据，并非“完整无缺口”。成本完整遍历、未出现的数据分支、长期认证、限流及部分领域语义仍有明确限制；本轮没有实现业务 CLI，也没有通过改动生产数据来制造样本。

## 当前记录规模

按用户要求，主线程额外复验接口 `totalCount`，只读取一页，不下载全量数据：

| 查询范围 | 本轮总数 |
| --- | ---: |
| 渠道：`payoutType=EXTERNAL`，其余业务筛选省略 | 4914 |
| 产品 SLA 基线：无业务筛选 | 23 |
| 成本：`costTypeCode=FUND_OUT_CHANNEL_TRANS_FEE` | 3291 |
| 共享成本页面：省略成本类型和其他业务筛选 | 3847 |

以上均小于一万，是当前账号、筛选及时间点的记录数，不是后端容量上限。成本计费子项不另计为顶层记录；SLA 详情读取列表中的同一基线，也不增加记录总数。低于一万不能消除分页完整性问题。

## 共用 CDP 与认证证据

本轮使用 `http://127.0.0.1:9222`、Chrome 148。独立 target 分工避免并发导航互相干扰，保留用户原有标签页。未连接或使用 9330–9340。

默认 websocket-client 连接被 Origin 检查拒绝；使用 `suppress_origin=True` 后连接成功，不需要修改 Chrome 的允许来源配置。HTTP `/json/version` 可达不等于 WebSocket 可连，两步须分别检查。

主线程核对了专用 Chrome 的可执行文件、PID、进程启动标识、UID、profile 和 CDP 端口。profile 为本轮专用本机临时目录，不是版本库内容。仅检查与目标应用有关的 Cookie 元数据；`ctoken` 的域为 `.alipay.com`、路径为 `/`、Secure、非 HttpOnly、会话 Cookie。没有输出或落盘 Cookie 值。

认证模板使用浏览器上下文及新读取的令牌。成功模板并不证明所有 Cookie 或请求头均不可省略；不通过清除登录态或修改权限来制造失败。过期、限流、网络中断和所有权限错误仍需在实现时进行失败关闭处理。

主线程保持 Cookie 存储不变，仅对已允许的查询将 `fetch` 的 `credentials` 设为 `omit`：成本返回 HTTP 200、`success=false`，envelope 改为 `buserviceErrorCode`、`buserviceErrorMsg`、`redirectUrl`、`success`；SLA 列表的 fetch 抛出 `TypeError`。没有输出跳转 URL 或其中票据。后者只能记为 fetch 失败，不能单凭 `TypeError` 认定登录过期、CORS 或某个具体原因。

## Headed 与 headless 复验

主线程在探查 target 全部关闭后，核对进程归属，正常关闭专用 headed Chrome，再以同一 profile、同一端口启动 `--headless=new`。`/json/version` 的 User-Agent 确认进入 HeadlessChrome；没有两个进程同时占用 profile。

本次重启显式使用 `--restore-last-session`，保留会话 Cookie 与用户原有页面；没有把令牌复制到新 profile。以下是独立 headless target 的实际结果：

| 查询 | headless 请求范围 | 结果 |
| --- | --- | --- |
| 渠道列表 | `EXTERNAL`、`pageNum=1`、`pageSize=1` | HTTP 200，外层 success/status 和内层 success 均为 true，返回 1 行 |
| 成本列表 | 固定付款类型、`pageSize=10`、分别请求页 0/1 | 两次 HTTP 200、success=true、各 10 行、成本类型匹配，仍有相邻页重叠 |
| SLA 列表 | `pageNo=0`、`pageSize=10` | HTTP 200、success=true、返回 10 行，总数 23 |
| SLA 详情 | 仅在内存中取上述列表第一条 `id` | HTTP 200、success=true、详情标识与所查标识一致 |

全部复验 target 随后关闭；主线程正常退出 headless 并恢复 headed，继续使用同一 profile 和原有页面。没有要求用户再次登录。

这证明本次会话在显式会话恢复参数下可用，不证明省略该参数、换 profile、认证过期或长时间运行也同样成立。探针通过产品页面/iframe 建立执行上下文；尚未验证完全不加载产品页面的轻量启动路径。

## 独立审计与修订

Luna 只读审计三个报告，主线程结合源码及独立请求处理结论：

- 校正 SLA 重放示例的绝对 API 主机，明确 `igfc` 上下文到 `iglobalfundcontrol` 的跨 origin 请求。
- 将“完整 schema”收紧为已观察字段和分支，明确字段缺失、null、空数组及未知业务字段的处理。
- 补充 SLA 筛选的 serializer、四个字段结果验证、状态字典及静态资源定位；业务主体效果保留为未验证。
- 主线程两次验证 SLA 合成不匹配地区查询：成功、零总数、正常分页回显但省略列表键；该分支可规范化为空，不能将其他结构异常也吞成空。
- 分别记录渠道末页回退、SLA 空页和省略列表、成本跨页重叠，避免共享错误的分页规则。
- 明确金额十进制精度和未知数据保留规则；区分字典映射证据与完整字典能力契约。
- 审计提出固定 EXTERNAL 的建议；主线程将其限定为默认范围建议，未把其他流出场景擅自判为收款或写操作。

## 成本范围与分页审计

成本默认页面未加付款筛选；接口支持收款、付款、流动性和外汇等成本类型。付款专用模板建议显式发送 `costTypeCode=FUND_OUT_CHANNEL_TRANS_FEE`，校验响应 `itemType`；这是 CLI 范围建议，不是原页面默认行为。外汇及流动性成本是否需要另行纳入，不能从它们同在字典中推断。

主线程在独立 headed target 复验固定付款类型、`pageSize=10` 的页 0/1：HTTP 200、业务成功、页码回显分别为 0/1、各返回 10 行、付款类型一致，但两页存在重复 `itemId`。这一观察独立确认了成本代理的结果。

原因尚不能归为排序或偏移中的某一种。不能仅凭跨页查询去重就认定结果完整；成本与渠道能力也没有已验证的一对一关联 ID。命令路径已由 [ADR 0002](../../adr/0002-payment-v010-scope.md) 确定为 `payment cost`。

同日追加验证修正了此前“当前只能做受限单页查询”的结论：每页 50 条、66 页连续两轮均成功，累计返回 3291 行，但唯一 ID 为 2999、重复行 292；同 ID 内容无冲突，两轮集合一致。随后同一查询接口接受 `pageNo=0,pageSize=5000`，连续两次各返回 3291 行、3291 个唯一 ID，与后端总数相等，记录内容及集合稳定。因此 50 是前端分页选项上限，并非当前后端硬限制；当前全量可单次读取，无需触发导出任务。

主线程重新核对前端分页选项及查询适配器，检查计数脚本，确认临时 target 关闭且用户原有成本页面保留。此次大页验证在 headed 模式完成，未另外复验 headless 大页请求。随后 `pageSize=10000` 同样成功取得 3291 个唯一 ID，服务端最大值仍未知。详细计数与限制见[成本追加验证](../payment/2026-09-08-cost-query-contract.md)。

## 三个列表的大页支持追加核验

用户提出优先使用 5000–10000 的大页，仅在取数失败时 fallback。主线程与代理分别在既有 headed CDP 9222 的独立 target 中验证已知查询端点；没有切换浏览器、改动用户标签页或执行写操作。

| 能力 | 已验证的大页结果 | 当前限制 |
| --- | --- | --- |
| Channel EXTERNAL | 50 和 100 条的第二页成功，分别返回 50/100 个唯一 ID；总数 4914 | 50/100 首页均重复业务失败；5000 首页也业务失败，原因未知；10000 未执行，不能认定为容量上限 |
| Cost 付款类型 | 5000 两次成功，10000 也成功；均取得 3291 个唯一 ID | 10000 初次触发客户端 20 秒超时，延长预算后约 15 秒成功；不把超时当作容量拒绝 |
| SLA 基线列表 | 5000 和 10000 均成功；均取得 23 个唯一 ID 且内容一致 | 大页仅适用于列表，详情仍逐 ID 查询；服务端最大页大小未知 |

主线程对 Channel 的 50/100 各两页做了两轮有效复验。第一页均返回 `IPAY_RS_510090020 / SERVICE_RESULT_NOT_TRUE`，第二页成功且范围和标识正常。首两页不能凑成完整比较，因此跨页重叠未验证。各能力详情见 [Channel](../payment/2026-09-08-channel-query-contract.md)、[Cost](../payment/2026-09-08-cost-query-contract.md)、[SLA](../payment/2026-09-08-sla-query-contracts.md)。

结论是大页优先可以简化 Cost/SLA 的正常列表采集，但当前不能把三个列表统一标为支持 10000。Channel 需先处理已观察的首页业务失败。统一核心执行流程、各插件声明已验证的容量和失败分类，比从前端选项推断后端上限更符合证据。

用户随后要求验证每页 10 条能否完整运行。主线程两次顺序遍历尝试均在第 4 页以同一业务错误停止；第 1–3 页累计 30 行、25 个唯一 ID、5 个无内容冲突的重复行，报告总数 4914、总页数 492。这不满足“完整运行后改用 10 条”的条件；既没有完整遍历，也不能仅靠减少页大小排除异常。

## DI 的失败恢复与 fallback 参考

按用户指定，先通过 code-review-graph 定位 `~/dev/di` 中的 `difixer` 和 `SplitRequired`，再读取精确实现。图索引与当前 HEAD 不一致，因此图仅用于定位，以下结论以实际文件为准；没有运行 DI 修复流程或修改该项目。

- `src/diexporter/adapters/spread_query.py:56` 的 `SpreadQueryAdapter.execute` 先执行原查询，暂时传输失败在配置次数内恢复；等待预算耗尽或传输恢复耗尽才返回 `SplitRequired`。Chrome 丢失直接上抛，不能当作分页或范围问题。
- 同文件 `:105` 的 `_classify` 区分认证失效、可恢复网关/业务错误及结构错误。仅对 DI 明确声明的 `DI_DETAIL_10000` 能力，返回恰好 10000 行被视为可能触及容量上限，触发拆分；不是所有端点都把 10000 行判为不完整。
- `src/diexporter/runner.py:443` 的 `_split_required` 按能力的分区策略生成子范围；到最小粒度仍失败就记录 Hole，不无限重试。
- `src/difixer/runner.py:339` 的 `_execute_child` 调用 exporter 的 repair/run 接口并验证产物；`docs/spec/difixer-v1.md:440` 定义修复阶段的更细分区阶梯，例如 15 分钟 → 5 分钟 → 1 分钟，并保留原 Baseline。

可以借鉴“正常查询优先，失败分类后才恢复或缩小范围，校验通过才接纳结果”的原则。Dogopencli 查询的是配置实体，目前没有 DI 那样已验证的时间切分区间，不能直接复制该分割算法或把不同页大小的数据盲目合并。Cost 小页已有重叠证据；任何分页 fallback 仍要满足完整性检查，失败则保留旧缓存。

## 知识库使用记录

下节记录最初知识库检索；后续大页探查只验证运行态端点和本机 DI 代码，没有重新检索或改写知识图谱。

主线程先运行 graphify CLI，再核对命中资料或在未找到相关节点时按文件名回退检索。没有使用 `find` 替代 graphify，没有更新或重建图。

```bash
rtk proxy graphify query '渠道成本 成本类型 费用承担 费率' --graph ~/dev/dogpdkb/graphify_flatten_ready/graphify-out/graph.json --budget 2200
rtk proxy graphify query '付款 产品SLA 基线 时区 工作日' --graph ~/dev/dogpdkb/graphify_flatten_ready/graphify-out/graph.json --budget 1800
rtk proxy graphify query 'SLA基线' --graph ~/dev/dogpdkb/graphify_flatten_ready/graphify-out/graph.json --budget 1800
rtk proxy graphify query 'SLA' --graph ~/dev/dogpdkb/graphify_flatten_ready/graphify-out/graph.json --budget 1800
```

成本查询命中知识库文档 `[152865220]`（收款产品成本报表运营）及 `[449176577]`（渠道运维升级草稿），随后用 `rg` 核对原文。前者第 72、80、81 行描述共享收付款成本类型及网络、承担方式；后者第 21 行列出流出渠道成本类型。这些是历史设计佐证，当前接口证据优先。

SLA 图查询未准确定位产品基线契约；通过文件名回退找到 `[188392002]`（付款产品流出 SLA 运营）。其第 212–214 行描述小时/分钟显示及节假日选择，第 245 行描述业务、币种地区筛选。这不证明 wire 字段单位；秒单位由本轮前端渲染代码核实。

所有外部本机源文档位于 `~/dev/dogpdkb/graphify_flatten_ready/`。生产请求和响应中的真实账号、实体 ID、费率与凭证未作为报告或 fixture 保存。
