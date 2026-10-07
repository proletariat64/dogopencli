# Liquidity 资产交易与报价组版本行原生详情

权威规格：[GitHub Issue #141](https://github.com/proletariat64/dogopencli/issues/141)。
这是已发布规格的可读副本；实施、审查及生产 UAT 状态另见
[验收报告](../research/general/2026-10-07-liquidity-asset-quote-group-getters.md)。

## Problem Statement

用户希望把剩余 Liquidity get 中有实际证据的能力推进为下一个开发批次，而不是把列表行当作详情。PR #140 合并后的 master `d379e3e073f2863ed21695db44f825d5fda1b1e7` 的完整 snapshot 尚有 **24 个 unsupported get**。本轮全量研究中，两个叶子取得了当前原生独立调用、非空详情和正确身份绑定，可作为一个实施批次；其余 22 项由 [#137](https://github.com/proletariat64/dogopencli/issues/137) 保留资格化门槛，总入口为 [#72](https://github.com/proletariat64/dogopencli/issues/72)。

本票是 **implementation-ready spec**，不是已实施或已验收声明。研究只进行了 8 次明确的只读业务请求，并核对了当前前端部署；没有应用代码修改、新 PR、公共 getter CLI UAT 或发布。

## Solution

将下面两条独立原生 getter 一起实施、审查并逐叶验收，采用已有独立详情缓存与 inquiry-only transport：

| Command | Kind | Public identity | Exact native request | Positive proof |
| --- | --- | --- | --- | --- |
| `dogopencli liquidity operations asset-trades get` | runtimes | `--order-no`：原生交易根 orderNo | form **POST `/assetTransferOrderDetailQuery.json`**，body 只有 `orderNo` | 有 86 条父交易的日期范围；2/2 非空详情根 orderNo 与父记录一致 |
| `dogopencli liquidity investment quote-groups get` | settings | `--quotation-group-row-id`：物理版本行 id | form **POST `/queryQuotationDetail.json`**，body 只有 `quotationGroupId`，其值为 **selected row.id** | 4/4 非空详情正确绑定；包括同一业务组版本 3、1 的不同物理 row IDs |

`quote-groups list` 仍 unsupported；其分页/结束协议问题不因独立详情成功而消失。原生 UI/历史版本链接可提供物理行 ID，详情不能暗中抓全列表或从业务 group ID 选择“最新”。asset-trades 第一版只提供已绑定的根交易与产品字段，不提供尚未绑定的日志。

## User Stories

1. As a Liquidity operator, I want to read one native asset-transfer order by orderNo, so that I can inspect the actual trading object independently of a list capture.
2. As a Liquidity operator, I want to read a quotation-group configuration by its physical version-row ID, so that I retrieve the exact version selected in the native page.
3. As a Liquidity operator, I want help and describe to explain the difference between row.id and business quotationGroupId, so that I do not repeat the historical wrong-ID request.
4. As a Liquidity operator, I want an explicit detail refresh, so that I control when the dedicated authenticated browser is used.
5. As an offline operator, I want get to read only an independently acquired native detail, so that a list summary cannot masquerade as a detail.
6. As an offline operator, I want a missing detail capture to report the existing cache-miss behavior, so that missing local evidence is not presented as a nonexistent business object.
7. As an operator, I want live get to perform exactly the verified inquiry without publishing or falling back to cache, so that its source and freshness remain clear.
8. As an operator, I want a failed refresh to preserve the previous valid detail capture, so that authentication, network or parsing failure does not destroy usable data.
9. As an operator, I want list and detail captures to remain independent, so that reading one object never starts an all-object detail crawl.
10. As an operator, I want two physical version rows of one quotation group to have separate detail captures, so that one version cannot overwrite the other.
11. As an operator, I want the returned quotation-group root to retain the selected version, so that a historical version is not silently promoted to the latest one.
12. As an operator, I want native business group ID, physical ID and integer version to remain distinct fields, so that their meanings are not conflated.
13. As an operator, I want native contacts and version history to remain structured arrays in their source order, so that meaningful configuration composition is retained.
14. As an operator, I want asset product fields to remain a structured native object, so that category, product, tenor and type remain distinct.
15. As an operator, I want native amounts, currencies, dates, precision, nulls and blanks preserved, so that the CLI does not manufacture financial meaning.
16. As an operator, I want unknown native status and process codes preserved, so that new source values are not silently discarded or mislabeled.
17. As an operator, I want returned identity or tenant contradictions rejected before publication, so that another object's detail cannot enter my cache.
18. As an operator, I want authenticated request scope reported separately from absent native tenant echoes, so that metadata never fabricates response evidence.
19. As an operator, I want the first asset getter to exclude unproved log ownership, so that unrelated records cannot be presented as my trade's logs.
20. As an operator, I want quotation-group inquiry to avoid attachment downloads and review/mutation links, so that it remains a bounded read.
21. As an operator, I want unsupported list and other getter reasons retained, so that this batch does not imply delivery of unrelated abilities.
22. As a maintainer, I want public CLI tests using fake CDP and temporary real SQLite, so that request construction, parsing, cache isolation and rollback are verified at the existing highest useful seam.
23. As a maintainer, I want separate production CLI UAT for both implemented leaves, so that successful research requests do not substitute for delivery validation.

## Implementation Decisions

- Reuse ADR 0016 independent list/native-detail captures and existing typed detail capability, allowlist, shared transport, projection, CLI and SQLite seams. No duplicate browser/auth/cache framework. Keep both leaves in one batch/PR with per-leaf evidence and serialized production UAT.
- Both detail requests are **form POST**, not JSON POST or GET. Allow exactly the verified host `iliquidity.alipay.com`, path, method and one native body key. `ctoken` and cookies stay in the browser. Do not add tntInstId/date/version/page fields absent from these native callers.
- Asset identity is a nonempty native string orderNo; validate `data.orderNo` equals the requested order number before output/cache. Do not use reportId, globalOrderId, processId, product code or tradingDate as substitutes. Scope is the authenticated Liquidity tenant; metadata may name the configured scope but must not claim a native tenant echo that was absent. Reject a contradictory native tenant field if one is returned.
- Asset envelope is HTTP success plus native `success: true` and nonempty object `data`. Project observed root trading, accounting, counterparty, amount/currency, date, state and product fields. Preserve native product keys including the source spelling `assertProductCategory`, `assertProductCode`, `assertProductName`, `assertProductTenor`, `assertProductType`. Nested objects must be structurally valid when present; absence/null/blank remain distinct where the source permits them.
- Asset **transFerOrderLogVoList is excluded from the first projection**. Both successful sampled details had nonblank log order numbers that matched neither root orderNo nor any root string identity field. This does not invalidate the correctly bound root, and it does not prove the logs are trade-owned. No guessed ID transformation, implicit log fetch or mutation/comment operation is allowed. Any future log scope requires separate native owner proof.
- Quotation-group public identity is explicitly **quotation-group-row-id**. Wire `quotationGroupId` receives that physical `row.id`; echo validation targets root `data.id`. Do not offer an ambiguous business-group-ID input or implicit latest/version resolution. Native business `quotationGroupId` remains a response field. The supplied physical row ID selects the native version; no extra version request option is introduced.
- Group envelope is native `success: true`, nonempty object `data`; require exact physical ID echo, native tenant GUAPW3SG, native string business ID and structurally valid integer version. Preserve selected root version even when history contains newer versions. Cache identity uses source scope plus physical row ID, not business ID; retain the observed version as response/capture evidence.
- Group projection includes id, quotationGroupId, quotationGroupName, bankId, department, tenant, version, native status/process metadata, dates, memo/contact fields, contactInfoList and operationHistoryList. Preserve complete native contacts and the projected version-row composition, order and distinct physical IDs. Do not deduplicate history by business group ID or impose identity uniqueness across root and its history (the selected root may also appear in history). Within observed history, version row IDs are distinct and business ID/tenant match the root; reject contradictory identity/context rather than silently clipping it.
- Apply the same curated group projection to history entries. Exclude fileDownloadUrl, fileKey, reviewLink and action plumbing from root/history; do not follow attachments or approval links. Observed history entries have empty nested histories; keep the contract bounded and reject a new unsupported recursive composition instead of dropping unexpected nonempty nested data silently. Preserve allowed native fields without converting contact objects into display strings.
- Reuse the current exact-identity validation, native precision and failure taxonomy; never round fractional JSON numbers through binary float. No speculative local date/amount/status conversion, source total fabrication, request retries at alternate endpoints or empty placeholder detail on failure.
- Default get stays offline. Explicit refresh atomically publishes only validated detail; live is nonpublishing and never falls back. Hard business/auth/HTTP/identity/schema failures leave prior detail unchanged and do not invalidate a separate list capture. Catalog/help/describe/snapshot change only for these two supported get leaves after implementation; all lists and other get leaves retain their concrete gates.

## Testing Decisions

- Prefer the existing **public CLI + fake CDP + temporary real SQLite** seam, following native getter and qualified RFQ/route-quota tests. Assert external requests/output/capture behavior, not private helper implementation. Fixtures contain invented IDs and sanitized contact/financial values.
- Prove exact POST/form host/path/body, correct row-ID-to-wire mapping, rejection of unsupported parameters/method/path, no implicit list read and no business-group-ID resolution. Exercise both real parsing paths and fake transport error responses.
- Asset cases: positive root/product; missing/wrong/blank orderNo; invalid root/product shape; native string and fractional-number precision; absent/null/blank fields and unknown status; unbound log array excluded while the valid root remains readable. Assert no fabricated tenant echo.
- Group cases: two physical rows of one business group with versions 3 and 1; root stays selected version; distinct detail keys; tenant/physical-ID/business-history contradiction refusal; malformed contacts/history; duplicate historical physical IDs; selected root present in history allowed; attachment/action fields excluded at both levels; unsupported nonempty recursive history refused explicitly.
- Verify explicit refresh then browser-unavailable offline get of the same capture, live nonpublication, no live fallback, detail cache miss despite a cached list, separate list/detail generation, cross-object/source isolation, atomic rollback for business failure, HTTP/transport refusal, authentication expiry and malformed/identity-mismatched response.
- Run focused relevant tests, Ruff lint/format, doc-guard and required repository CI gates. Separate standards/spec review from CI and production UAT; do not claim unavailable external review ran.
- After implementation, perform inquiry-only public CLI production UAT **2/2**: asset root by actual parent orderNo and group by exact native physical row ID, refresh/offline comparison, live nonpublication, and failure-preserves-cache where safely demonstrable. Validate a same-business-group cross-version pair for group cache/root isolation. Research or list UAT does not satisfy these gates. Release/merge are separate user-authorized steps.

## Out of Scope

All other 22 unsupported get leaves; quote-groups list completeness or activation; asset logs without owner binding; global routes (route quotas already delivered); monitoring HOLD and excluded cash account detail; business mutation, approvals, comment editing, downloads, arbitrary request/JavaScript entry points; implicit all-detail crawl; wider list research without new evidence; version bump or release in this research round.

## Further Notes

Observed 2026-10-07. Current loaded first-party frontend asset was checked by cookie-free HTTP read: HTTP 200, **15,763,128 bytes**, SHA-256 `cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`. Character offsets in that exact artifact: asset detail service 1476250 (`BJ -> le`), loader 9576722, URL mount 9578124; quotation-group Detail link 9889568, historical link 9900361, loader 9901722, service 1529847 (`E0 -> x`). Parent readers used dates 2026-09-01–2026-10-07/pageSize1000 for asset trades, and rowStart0/pageSize1000 for quotation groups. Detail requests had only their one native body key.

Research results: asset **2/2**, root identity/tradingDate bound; groups **4/4**, including same logical group's native versions **3 and 1** with distinct physical IDs. The pair returned history [3,2,1] with consistent business ID and tenant. Parent group response had 54 physical IDs/48 business IDs and no complete-list protocol proof. Prior generic group failure does not refute this corrected physical-ID getter.

Knowledge-base Graphify discovery preceded original Liquidity whitepaper page197368565 (operations 365–409, institution inquiries 735–749/915–931, pricing/charging1029–1039) and related native-menu PRDs. PRDs establish vocabulary, not live endpoint authority. Current native source and successful typed requests establish these bounded detail contracts.

Private production evidence remains machine-local and uncommitted; future checked-in fixtures must be sanitized. **Done when** both leaves pass focused checks, required CI, review and separate per-leaf production CLI UAT, with their catalog/help/cache behavior and deferred scope updated truthfully. No implementation has occurred during this spec publication.


