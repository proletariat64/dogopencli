# Shared List Collection API

## Purpose and boundaries

Issue [#291](https://github.com/proletariat64/dogopencli/issues/291). Make ordinary Leaf List development faster by reusing **mechanisms**, not by assuming Payment, Collection, FX and Liquidity have the same business behavior. The Host remains a local Python CLI, not a remote service. Extend the existing `dogopencli.collect`, endpoint contracts, leaf manifest validator, and runtime; do not create a standalone SDK distribution, a business monolith or any SDK version/negotiation scheme.

A single-source SDK List supplies a verified native `TransportCapability`, pure
`page_body(scope, position, size)` and parser, plus optional
`validate_rows_scope(rows, scope)`. It owns `scope`, `filter` and business fields;
the host executes `collect_list`. Declared independent sources use those same
native hooks and the flat assembly seam below, without a leaf-maintained query loop.

Every standard List declares `collection`. Dependent or specialized inquiries
explicitly declare custom execution and named host query tools. A List without
either contract is invalid; adapters never receive a session or transport.

## Native page metadata

A capability may supply the pure optional hook `parse_metadata(body) -> dict`
to retain source aggregates or other response metadata separately from native
records. The hook receives the same successful response bytes as the row parser;
the leaf owns its native meaning and validates the returned JSON object. It must
not make inquiries, recalculate aggregates, or insert metadata into every row.

The host retains each validated response in acquisition order as
`{position, page_size, metadata}` under `acquisition.native_metadata`. Position is
the requested page number or offset. Short-page acquisitions also retain their
successful probe and terminal responses with their actual positions and widths.
The host preserves native values, types, nesting and array order. It does not
merge page aggregates or assume that they cover the same scope. Display windows,
projections and local filters do not reinterpret source aggregates.

Only the selected width candidate's metadata accompanies its records; rebuilding
at another width discards the rejected candidate's metadata. Complete nonempty
refresh saves rows and metadata together through the existing atomic snapshot;
offline replay retains it in both `acquisition` and `source_acquisition`. Live
does not publish, and empty, failed or incomplete refresh preserves the previous
capture. Leaves without the hook omit `native_metadata` and keep their existing
envelope. No cache table or separate metadata store is added.

## Ownership and provider isolation

- **Leaf chooses provider.** `leaf.json` declares a `collection.provider`. Domain declarations remain unchanged and do not register SDKs.
- The Host maintains a **fixed, first-party** resolver: `general` is public to all domains; `payment.collection`, `collection.collection`, `fx.collection` and `liquidity.collection` are private to their named owner. Initial private providers may delegate to the same neutral collector; separate business semantics still come exclusively from leaf contracts.
- Only one provider executes an opted-in List operation. No hot loading, SDK switching, third-party provider execution, multiple active contracts or provider versions.
- Validate provider availability and owner-domain match at static manifest validation, installation and runtime. A payment leaf declaring `fx.collection` is invalid even if their JSON looks identical. A leaf using `general` still belongs to its own domain; the provider grants no cross-domain installation permission.
- This is **contract enforcement for trusted Python plugins**, not a Python security sandbox: arbitrary adapter Python imports are outside this guarantee.

## Leaf manifest

For a standard List leaf, `collection` is a required closed object. Custom List
and Get-only leaves omit it. Optional `latest_by`, `max_pages` and `budget_seconds` retain their
documented defaults; omitted `paging.termination` uses `native_total`:

```json
{
  "collection": {
    "provider": "general",
    "paging": {
      "mode": "offset",
      "page_sizes": [500, 100, 50]
    },
    "primary_id": {
      "type": "hash",
      "fields": ["accountAlias", "currency"]
    },
    "latest_by": "gmtModified"
  }
}
```

`paging.mode`: `offset`, `page_number`, `single` or the explicitly qualified
`single_response` described below. Sizes must be nonempty, unique, positive
(except the explicit unpaged declaration below),
individually endpoint-qualified and descending. `single` and `single_response`
have exactly one size. Offset position is absolute zero-based `rowStart`;
numbered pages start at `contract.one_based ? 1 : 0`.
A field identity has exactly one native field; `hash` uses a reviewed tuple.
Optional `latest_by` chooses a conflicting row while leaving coverage incomplete.
Unproven identity requires empty manifest `identity` and forbids `latest_by`.
Optional `max_pages` (1–1000) and `budget_seconds` (1–900) narrow host bounds.
Get-only omits `collection`; no version negotiation is added.

Source manifest config represents **policy**; it never stores a learned page size. The list/get manifest identity can differ, because some real native gets use a different echo field.

## Qualified response without a native total

Use `paging: {"mode": "single_response", "page_sizes": [5000]}` only after
separate qualification that one response covers the exact declared native query.
The width is a qualified request value, not a demonstrated capacity maximum.
The capability implements pure `parse_rows(body) -> (native_rows, None)` and
declares verified native identity. The host makes one logical page request;
there is no offset iteration, alternate width, rebuild or learned width.
Existing bounded transport retries still apply to that request.

For a native endpoint with no pagination fields, declare `page_sizes: [0]` and
`EndpointContract.page_size=0`. Zero means unpaged, not a capacity limit; the
leaf request builder must omit pagination fields. Only `single_response` accepts
this declaration, and its size must still match the endpoint-qualified contract.
Do not invent a positive width for an unpaged endpoint.

Evidence keeps `reported_total=null`, `total_semantics="unknown"` and
`coverage_basis="qualified_single_response"`; arrivals, unique count and duplicate
count remain separate observations. Completeness follows the accepted response
contract, never a fabricated total. A source ignoring requested pageSize is not
rejected solely for returning more rows. Duplicate/conflict and native failures
still prevent strict success/publication. Empty refresh preserves prior cache.
Native-total termination still requires native totals; a missing total alone does
not qualify this mode. See
[the executable sample](../../tools/leaf-dev/example-single-response/).

## Qualified short-page termination and hole recovery

Declare `paging.termination: "short_page"` for a separately qualified positional
endpoint with stable ordering across its allowed widths. Use `mode: "offset"`
or `"page_number"`, positive endpoint-qualified widths and verified native
identity. Omission or `"native_total"` retains native-total collection. Single
modes cannot select this strategy. The manifest syntax is unchanged.

The SDK advances at the selected large stride. Successful short batches trigger
local inspection rather than immediate termination. Only an endpoint declaring
the explicit last-page clamping hook below retains a final short batch unchanged
after two following large batches confirm its end; these terminal responses need
no smaller-width probes. Other sources still inspect final short batches to retain
their successful-empty hole evidence. Where smaller widths are
qualified, the SDK subdivides only deficient intervals, retaining full intervals
without further subdivision. Successful subdivisions must reconstruct their
successful parent records exactly, including order and types. A contradiction is
a hard invalid-response error, not a recovered hole. Probe responses never add
arrivals or duplicates to the output. Actual primary batches remain native JSON.

Successful empty positions before later records are holes. Once revalidated,
known hole intervals can be skipped with exact positional boundaries. The SDK
ends only after **two consecutive successful empty batches at the original large
stride**. Very large continuous omissions beyond that boundary are outside this
accepted tolerance policy. Native totals and total-page counts are diagnostic,
not stopping or completeness inputs; `reported_total` remains null. Numbered
page/size echoes must still match exactly. No clamped page or duplicate identity
is an end signal by itself.

A separately qualified one-based endpoint may declare pure
`pagination_terminal(page: ParsedPage, requested_page: int) -> bool` for its
verified last-page clamping behavior. The host additionally requires exact
repetition of a previously read successful **short** page at the same width,
including all native values, with the native page strictly before the requested
page. Two later original-stride requests must each satisfy this contract.
Evidence uses `termination_reason="two_clamped_batches"` and retains each
request's original requested/native page numbers and native row count; these
responses are not native empty pages and their repeated rows are not collected.
Full-page repetition, changed content, unknown/clamped widths and undeclared echo
mismatches still fail. This is the explicit terminal contract of `payment.channel`;
its known overlap diagnostics remain independent of traversal termination.

Probe widths come only from `EndpointContract.allowed_page_sizes` or its nested
`json_body_contracts`, bounded by the selected large width. The SDK never loosens
transport permissions. Numbered requests must satisfy
`start = (page_number - first_page) * width`; arbitrary widths do not imply
arbitrary offsets. A normal fixed-width final short page still works after the
two empty confirmations, but an interior deficient page cannot be excused if its
endpoint has not qualified the smaller widths needed to locate the hole.

By default business failures remain hard errors. A leaf may supply pure
`pagination_hole(error: CliError) -> str | None` to recognize a specific verified
record-level failure. It receives only `BUSINESS_QUERY_FAILED`, returns a stable
fingerprint string for that record error, and returns `None` for all other
failures. The SDK hashes that fingerprint, subdivides failed intervals to single
positions, and only bypasses confirmed points. Authentication, HTTP/network,
permissions, schema failures and unclassified business errors never become holes.

Every read, neighbor check, local subdivision and history validation consumes the
same global page/deadline budget as ordinary collection and fallback. Different
large-width fallback candidates still restart at zero and never mix their output.
By default duplicates or identity/content conflicts still prevent strict success and refresh.
The explicitly accepted channel contract sets `EndpointContract.duplicate_policy`
to `allow_identical_overlap`: identical repeats are deduplicated without requiring
a native-total or business-wide completeness proof. Evidence uses
`coverage_basis="accepted_short_page"`, retains arrival/duplicate counts and native
terminal witnesses, and permits strict success, refresh and offline after traversal
completes. Here complete means the accepted traversal contract completed; it is
not a claim that the defective backend exposed every business record. Identity
content conflicts and unknown source errors remain failures. Other leaves retain
the conservative policy.

A recovered stable hole is a normal completed inquiry: strict live/refresh return
exit 0 with `complete=true`. `warnings` includes the informational code
`PAGINATION_HOLES_BYPASSED`. Acquisition evidence records the hole intervals,
neighbor identity fingerprints, reused/checked history counts, actual request
count, source end and the two terminal empty batches. Coverage remains
`qualified_short_page`, total semantics `unknown`, termination reason
`two_empty_batches` (or the explicitly qualified `two_clamped_batches` above).
The message and evidence survive refresh/offline replay and
independent-source assembly. Old first-short-page cache contracts are invalidated.

### Scoped hole memory

The host keeps `<config-directory>/collection-state.holes.json`, separately from
page-size preferences. Existing hashed keys isolate leaf/source, endpoint,
canonical scope and qualified large widths. Each key retains a FIFO of **five
query records**; every acquisition records its result, including an empty hole
list or failure. Only the latest record is consulted. A latest failed/incomplete
query, changed policy or empty list never falls back to an older record.

Before bypassing a saved interval, requery the hole and its neighboring native
identities. Repaired holes, changed error fingerprints or moved neighbors reject
the hint and trigger ordinary discovery. Newly encountered holes enter the current
record. Neighbor identity hashes prevent stale positional skips after reordering
and keep account identities out of operational state; scopes, native rows, tokens,
responses and raw error messages are never persisted there. Use private files,
atomic replacement, a nonblocking writer lock and bounded scope retention. A busy
or unavailable state file does not fail an otherwise successful inquiry; the
attempt exposes `history_saved=false` and the next run discovers holes again.

The [VA capacity package](../../leaf_packages/collection/va.capacity/) exercises
normal fixed-width termination. The cash-directory source of
`liquidity.cash.accounts` exercises stable successful-empty holes; qualifying
that source does not deliver its separate baseline/detail composition.

## Declared independent sources

For an accepted relationship, declare `collection.sources` instead of top-level
`paging`. Keep the provider and aggregate `primary_id`; each named source declares
only `paging` and its own `primary_id`. Source names exactly match the leaf hooks;
sources cannot nest. The [sources sample](../../tools/leaf-dev/example-sources/)
shows the complete declaration and native mapping.

The adapter supplies pure `source_capability(name, parameters)`,
`source_scope(name, parameters)` and `assemble(records_by_source, parameters)`,
plus aggregate `scope` and `filter`. Source capabilities use the same request and
parser hooks as ordinary Lists. The host's `collect_sources` reuses `collect_list`
for all required sources under one global deadline and logical-page budget,
including fallback attempts. It calls assembly only after all sources are complete.
Any failed/incomplete source fails the aggregate atomically and preserves prior
cache. An empty child array can follow a successful complete source with no match;
it cannot stand for a failed or unqueried source.

The leaf owns reviewed parent references, source date meanings, cardinality and
output order. Assembly returns uniquely identified roots, preserves each native
child according to that model and performs no inquiry. The SDK guesses no join,
amount, version, timestamp or business grain. No holdings lookup or automatic
source expansion is implied.

Aggregate evidence keeps `reported_total=null`, `total_semantics="assembled_roots"`
and `coverage_basis="validated_sources"`. `acquisition.sources` maps each source
name to its exact `scope` and independent `acquisition` evidence, retaining native
totals and identity diagnostics through refresh/offline replay. Root count is an
observed output count, not the sum of child totals or a native parent total.
Raw source scopes never enter the preference file; its existing hashed keys apply.

## Identity, duplicates, holes and coverage

- Identity must be selected by the leaf developer at design time and reviewed by a human (HIL) against business semantics. A hash cannot make non-unique columns unique. `hash` uses `sha256(canonical([typed_field_values,...]))` in declared field order, so numbers and strings cannot collide by string concatenation. Missing/null/non-scalar key parts are invalid. Collision of a 256-bit digest with different native tuples is a hard error. Do not mutate native row JSON or generate a synthetic source field.
- Maintain a first-seen position per identity; collapse identical cross-page duplicates. On different content for the same identity, retain the row with the greatest parsed `latest_by` value when configured, breaking equal timestamps with last arrival; otherwise the **last loaded row wins**. Preserve explicit diagnostic reasons and counts, including conflicts. For an unverified ordering, last arrival is not a proof that the row is globally newest.
- A duplicate or conflict is *not* automatically proof of complete coverage: a repeated row can conceal an omitted row. Report arrivals, unique count, duplicate count, conflicting count, reported total, and `scope_complete=false` on page overlaps or unverified holes. Qualified short-page recovery records verified bypasses separately.
- For a reported fixed unique-object total, require `unique_count == reported_total` and **no anomalous gaps/duplicates** to claim complete. Reject changing totals or invalid response envelopes; do not guess other total semantics. An unproven identity uses `primary_id: {"type":"unproven","fields":[]}` and `contract.has_identity=False`. Preserve every native arrival without deduplication; exact repeated JSON is diagnostic only. Unknown totals require a separately qualified `single_response` or short-page contract to establish completeness; count equality does not prove it. Stop an unproven read on overlap, a short page or the logical-page cap, retaining validated arrivals with explicit incomplete evidence; strict modes and refresh reject it. No synthetic ID or hash is justified.
- Detect short pages before the expected end, empty interior pages and final unique/count shortfall. Advance by the requested page stride (not returned row count), so following valid ranges can still be read and exposed as explicitly partial. Never fill missing data or change effective reported total. A bounded fallback must **restart from position zero** using the next declared width, without mixing candidates.
- If all declared widths fail to prove coverage, return the last validated *partial* candidate for live display with incomplete evidence where possible; strict modes reject it. An unavailable or malformed page producing a hard business/authorization/schema error never becomes partial success. Unsupported request widths are never guessed.

## Upstream blacklist filtering and pagination holes

这是多个 leaf 遇到 total 不符、短页、坏页或页面重复时的重要排查参考。
业务负责人在 HIL 中确认：被 blacklist 排除的账户及相应数据不应进入业务输出。
部分上游查询会在取数链路中旁路过滤这些账户；如果计数、分页、关联数据查询和
前端展示没有协调处理，就可能留下输出空洞。排查时应先区分合理的业务排除与
有缺陷的输出处理，不能为凑齐 total 恢复被排除的数据。

### 业务解释与已验证现象

Blacklist 是业务负责人提供的跨 leaf 根因线索；其他 leaf 的类似症状也可能同源，
但相似现象不等于每个 endpoint 已确认该根因。即使返回 `account not exists`，
也不能仅凭错误消息断定该账户已经进入 blacklist。

付款渠道 [payment.channel / #275](https://github.com/proletariat64/dogopencli/issues/275)
已通过原生查询和 Playwright 页面操作复现两类现象：

- 同一账户／币种的 `debit account not exists` 会使包含它的整页查询业务失败，
  后续页仍可成功。观测到的故障位置随 pageSize 移动：10 条／页时第 15 页，
  50 条／页时第 3 页，100 条／页时第 2 页。这支持记录或关联数据相关的故障，
  不是 total 驱动的终止问题；这些位置是定位例子，不是固定验收断言。
- 前端在失败后仍推进显示页码，保留上一成功页的表格，因此相邻页看起来重复。
  另有成功响应之间原生记录完全相同的跨页重复，必须与前端保留旧表格分别判断。
- 该接口越界请求会回显末页页码并重复返回末页记录，而非返回成功空页。
  单条向前遍历也会遇到此行为。必须保留请求与回显页码，不能把末页重复响应作为
  新一批数据保存；诊断遍历因此停止不等于已证明业务数据完整，原有 SDK 的回显
  校验仍然适用。重复 ID 本身也不能充当结束信号。

上述实验验证了输出故障；没有验证后台 blacklist 的执行分支、过滤发生位置，
也没有证明其他 leaf 的 total 偏差都由 blacklist 引起。

位置稳定性与跨宽度覆盖必须分别验证：payment.channel 的单条坏位置、错误特征
及邻接记录可重复命中，同一 pageSize 的查询也可重复返回相同记录；但大页与对应
单条／小页查询的记录集合不一致，单条连续页也会重复返回相同记录。因此固定宽度
下的 hole 提示稳定，不足以证明缩步、绕行及恢复大步长能覆盖同一个原生区间。
channel 已接受使用 `short_page` 的大步长绕行策略；上述差异作为独立覆盖诊断保留，
不再仅因已知报错暂停接入。不能将 `pageSize=1` 自身当作完整性真值，也不能将
绕行遍历完成、去重或用户接受策略等同于已证明业务全量完整。channel 的发布以
已接受的遍历契约为准，不额外要求无法取得的业务全量证明。

### 遇到类似问题时如何定位

1. 同时保留请求范围、页码／offset、pageSize、原生 total、原生响应和业务成功标志。
   分开记录实际到达行数与已验证身份下的唯一行数，不用展示行数覆盖原生 total。
2. 明确 total 统计的是过滤前候选还是过滤后可输出记录；含义未证实时保留未知。
   total 大于输出数量可能与合理的业务排除有关，也可能是真正漏数，不能仅凭差额判断。
3. 用限定范围内的不同 pageSize 定位故障区间，核对关联账户／币种及同一错误。
   每种宽度保留独立证据；诊断实验不代表 SDK 可在业务失败后自动切换宽度。
4. 页面复现同时检查网络响应、当前页码和表格内容。HTTP 200、页码推进或仍有表格
   都不能证明本页业务成功；逐字段核对原生记录，不能从页面重复推定主键不唯一。
5. 逐 leaf 确认过滤与分页的先后关系。total 不可信并不自动证明首个短页就是结尾；
   页内过滤也可能在中间产生短页或空页。采用
   [short-page 策略](#qualified-short-page-termination) 前仍须证明停止条件。
6. 诊断中继续检查坏页之后的页面，只能证明后续范围可读，不能补齐坏页的未知记录。
   保留缺口，不能把失败页当空页、用上一页顶替，或因最终出现短页而宣布完整。

这些参考不授权把任意业务错误当作空页。当前 `short_page` 的稳定空洞容错范围、
显式记录级错误识别及正常退出消息见上述契约。channel 接入该策略时仍保留重复、
跨宽度矛盾和原生页码回显检查；其不稳定结果不作为 SDK 完整性保证的验收依据。
原始响应、实际账户与 blacklist 明细仍只保存在私有证据中。

## Page-size fallback and persistence

- Prefer the last **completely successful** size if present and still declared; otherwise use manifest order. When the primary width times out within its per-attempt allocation or produces a validated short/duplicate/gap candidate, retry the **full** requested scope from offset zero using the next allowed size. No fallback on authentication errors, unknown schema, permissions, changed native totals or unclassified business failures; short-page local hole recovery is distinct from whole-candidate width fallback.
- Share an absolute global deadline and a **single maximum logical-page budget** across all fallback attempts, counting even a page that ends in transport timeout. Each retry of the same page by the existing network retry policy is part of that one logical position; never reset the page allowance on fallback.
- Store only `preferred_page_size` and minimal harmless performance observations in `<config-directory>/collection-state.json`, keyed by a hash of leaf ID, endpoint/method and canonical scope + qualified widths. Never persist tokens, business rows, raw scopes, endpoint responses, or mutate the installed leaf manifest. Read corrupt/missing state or a no-longer-qualified width as no preference. A still-qualified preferred width is only request ordering; every candidate is revalidated, so adapter-source or identity fingerprints are unnecessary. Atomic replacement and restrictive permissions. Limit retained keys.
- Updates happen **only after proven-complete acquisitions**; an unsuccessful fallback must not promote a width. Learning is best-effort: use a **nonblocking preference-file lock** and skip the optimization when another writer holds it, never stalling an otherwise successful inquiry.

## Host integration and quality policy

- `leaves.registry.validate_manifest` requires a standard List `collection` or explicit custom execution, and validates the closed schema, provider boundary and primary-ID fields. Static verification and installation use that same validator. The Host dispatches standard Lists through `collect_list` or `collect_sources`, and custom operations through named query tools, passing configuration-scoped runtime state. Fingerprint the complete current endpoint contract, collection policy and adapter source. There is no transport-taking adapter collector or missing-evidence compatibility path.
- `EndpointContract` and the existing restricted `validate_request` remain authoritative. The declared allowed page widths must be supported by the endpoint allowlist (top-level or nested JSON-body allowances). No broad HTTP capability or arbitrary method.
- Every candidate records attempt size, page count, arrivals, unique count, duplication, holes, timing, and reason codes in `AcquisitionEvidence.attempts`. Selected records are unchanged business JSON.
- Best-effort live can show validated incomplete records plus warnings. For every List, **refresh publishes only a proven-complete nonempty result** and preserves prior cache on partial/failed/empty acquisition. The selected runtime width is operational and must not alter cache contract identity.
- Keep native Get and business query permissions, Duckdog publication/import, display paging and unrelated migration packages intact. Shared transport classifies HTTP 401/403 as authorization failures.

## Acceptance matrix

1. General provider works for a Payment or Liquidity List; a Payment Leaf declaring `fx.collection` fails manifest/install/load. Private provider owner matches and unknown providers fail. Domain declaration remains unchanged.
2. Both field and SHA-256 tuple identity are stable and type-aware. Missing identity fails, hash is *internal*, same-key duplicates use timestamp/latest or last-arrival and keep conflicts visible.
3. Offset and numbered paging validate total/echo and make exactly qualified requests. Same-width duplicate, short/empty interior page and count mismatch yield `complete=false`, not silent success. Changing totals, schema failure and authorization are hard failures.
4. Page-size fallback restarts from zero; attempts are never merged; unknown widths fail at restricted transport. Global deadline and total logical-page cap terminate; fallback cannot reuse another candidate's allowance.
5. A complete candidate persists a preferred width when its optional state lock is available; separate run loads it; corrupt/busy state is harmless. Partial/failure does not change preference or cached business snapshot. Current-contract snapshots replay offline; no historical-hash fallback exists.
6. All four bundled pilots execute via the SDK with no leaf-owned collector. Exercise native values, scope, normal/strict live, refresh/offline, portable install and declaration-only help. The FX pilot uses the native transaction number `uniqueId` and compares unique rows with native `totalCount`; complete acquisitions support refresh/offline, while duplicate/conflicting/short candidates are rejected by strict modes. Production migration needs independent acceptance.
7. Test with fake transport and local Python checks. No production CDP/SSO/network mutation, migration completion count, release or automatic PR merge.

## Implementation posture

Prefer small edits to `collect.py`, `contracts.py`, the first-party manifest/registry/runtime and leaf-dev guidance; create a tiny state helper if needed. Do not introduce a public SDK version, autonomous daemon, interface inheritance hierarchy or another domain register. Existing endpoint JSON parsing remains leaf-owned.

## Bundled pilot contracts

| Leaf | Paging / qualified widths | Identity / coverage |
| --- | --- | --- |
| payment.sla.baselines | Native zero-based pages, 10000 then 5000 | Native `id`; filters stay in the native request; get retains its own endpoint. |
| collection.cost | Single fixed request, 1000 | Native `itemId`, fixed `FUND_IN_CHANNEL_TRANS_FEE`; no invented second page. |
| liquidity.reference.entities | Native rowStart offsets, 5000 | Native `instId`; tenant and nested inquiry fields are allowlisted. |
| fx.trade | Native zero-based pages, 1000; 100 pages / 120 seconds | Native transaction number `uniqueId`; compare unique rows to `totalCount`. Broad queries may fail; use a qualified BCode/scene/symbol/type/fulfilled/date scope. |

Only existing endpoint-qualified widths are declared. Neither this table nor fake
transport acceptance qualifies production ordering or snapshot consistency.
