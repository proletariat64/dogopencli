# Temporary query cache and duckdog v0.1.0

Authority: [GitHub Issue #157](https://github.com/proletariat64/dogopencli/issues/157).

Date: 2026-10-13.

## Problem Statement

dogopencli 原本用于执行只读查询，现在却承担了历史 dataset 的职责。Liquidity 将缓存按查询主体、契约及时间范围分割，再保留和合并多次 capture；同一 list 查询可能读到过时的特定主体缓存，也可能无法筛选已经采集的其他范围。FX 又采用不同的 live-only 行为。用户很难判断默认 list 到底会读取什么，以及缓存、显示分页和后台采集范围之间的关系。

`--all` 同时表示显示全部记录、扩大主体范围和遍历后台参数，在 cash balances 上还有特殊含义。这个参数把三种不同操作混在一起。缓存架构因此越来越重，但它仍不能作为稳定的业务数据集使用。

用户决定把历史保存、合并及分析交给独立的 **duckdog**。dogopencli 只负责在线查询、临时保存最近一次非空查询结果及重放该结果。本规格替代本次讨论早期的统一历史缓存池、保留上限和缓存查询参数严格匹配方案。

## Solution

统一所有已启用的 list 类查询，包括现有终端命令 `fx trade`：

| 操作 | 用户可见行为 | 持久写入 |
| --- | --- | --- |
| 默认 list | 读取该 leaf 最近一次保存的缓存；显式业务参数在其中筛选 | 无 |
| list `--live` | 执行一次有界在线查询；可包含必要分页、分块和参数遍历 | 无 |
| `refresh <leaf>` | 在线查询；有效非空结果完整替换该 leaf 的唯一缓存 | 仅该 leaf 的临时缓存 |
| `<leaf> prune` | 清空该 leaf 的缓存，重复执行仍成功 | 仅删除该 leaf 的缓存 |
| get | 按原生详情契约在线查询一个对象 | 无 |

每个 leaf 只保留一个结果，查询主体或时间范围变化也直接替换，不积累历史。成功空结果返回本次空结果并保留旧缓存。硬失败保留旧缓存。合法非空 partial 继续遵守默认允许、严格模式拒绝的质量规则。

所有 list 默认输出 JSON，显示 `--limit 100 --offset 0`。`--limit 0` 输出筛选后从 offset 开始的全部剩余记录，不改变后台采集预算。彻底删除 `--all`；需要枚举主体等参数时使用经过声明的 `--entity ANY` 等选项。ANY 从 duckdog 的指定 selector、指定列读取参数值，不从 dogopencli 缓存推导。

cash balances 在线无主体参数默认使用 Z17 对应的原生 `instId=ALIPAYGM`。FX 在线未提供交易 ID 或日期时，默认查询 GMT+08 的上一个完整自然日。这些在线默认值不参与无参数的离线重放。

duckdog 使用 DuckDB 与 Parquet，支持 JSON 业务记录，按 list leaf 组织 selector，例如 `fx/trades` 和 `liquidity/cash/balances`。用户会另外建设导入 skill，以在线 JSON 输出为源；dogopencli 不负责导入、历史存储或判断数据是否应该入库。

## User Stories

1. As a CLI user, I want every enabled list to read cache by default, so that I can predict its behavior across payment, collection, liquidity and FX.
2. As a CLI user, I want an explicit live option to perform an online inquiry, so that the source of my result is intentional.
3. As a CLI user, I want a live inquiry to leave cache unchanged, so that inspecting another scope does not overwrite my temporary working result.
4. As a CLI user, I want refresh to save the full validated inquiry result, so that display limits do not discard records from cache.
5. As a CLI user, I want one cache slot per list leaf, so that I do not have to choose between historical captures or query-specific caches.
6. As a CLI user, I want a nonempty refresh for another entity or date range to replace the previous result, so that the cache always represents one acquisition.
7. As a CLI user, I want an empty refresh to preserve the existing cache, so that an empty inquiry does not erase useful temporary data.
8. As a CLI user, I want an empty refresh to report its own empty result and publication status, so that preserved old data is not presented as the new inquiry result.
9. As a CLI user, I want a failed refresh to preserve the existing cache, so that authentication, network or validation failures do not destroy it.
10. As an offline user, I want list without business arguments to replay the last cache, so that I need not repeat the acquisition arguments.
11. As an offline user, I want explicit supported arguments to filter existing cached records, so that I can query a subset without another acquisition.
12. As an offline user, I want unmatched filters to return an explained empty cache result, so that local absence is not confused with backend absence.
13. As an offline user, I want unsupported local filters to fail with a live-query instruction, so that the CLI does not silently ignore my arguments.
14. As an offline user, I want cache reads to avoid both browser and DuckDB access, so that they work without online services or duckdog.
15. As a CLI user, I want the cached contract variant and original query to remain visible, so that a cached daily balance is not mistaken for a latest balance snapshot.
16. As a CLI user, I want every list to default to JSON with 100 rows and offset zero, so that automation and interactive queries share predictable defaults.
17. As an automation author, I want limit zero to return every remaining matched record, so that I can export a complete acquired result without an ambiguous all flag.
18. As an automation author, I want display limits and field projection to affect output only, so that refresh retains complete records and acquisition remains bounded independently.
19. As an automation author, I want counts and quality metadata to distinguish acquisition from displayed rows, so that a short display is not mistaken for a short acquisition.
20. As a CLI user, I want the ambiguous all flag removed from commands and documentation, so that display expansion and business scope expansion are explicit.
21. As a liquidity operator, I want ANY to enumerate native entity IDs from a configured duckdog selector, so that my selected universe has an explicit source.
22. As a liquidity operator, I want ANY values frozen for one inquiry, so that changes to duckdog cannot alter later pages of the same acquisition.
23. As a CLI user, I want missing or invalid ANY selector data to fail clearly, so that the CLI does not substitute cached values or a broader backend query.
24. As a CLI user, I want ordinary explicit and default queries to work without duckdog, so that the dataset layer is optional unless enumeration is requested.
25. As an offline user, I want cached ANY results to retain their original selected values, so that replay never invents a new entity universe.
26. As a CLI user, I want ANY traversal to obey aggregate request and time budgets, so that enumeration cannot produce unbounded backend load.
27. As a liquidity operator, I want cash balance live and refresh queries to default to ALIPAYGM, so that no-argument online queries use the agreed Z17 business entity.
28. As a liquidity operator, I want explicit entity arguments to override the online default, so that I can choose another native scope.
29. As an offline user, I want online defaults excluded from cached filtering, so that a stored result for another entity is replayed faithfully.
30. As an FX operator, I want FX trade to use the same cache, live, refresh and prune model, so that FX does not require a separate mental model.
31. As an FX operator, I want a no-argument online inquiry to use the previous GMT+08 calendar day, so that it has a bounded useful date scope.
32. As an FX operator, I want an explicit trade ID or date pair to control my online inquiry, so that date defaults do not narrow an explicit ID lookup.
33. As a CLI user, I want a prune action for each cached list leaf, so that I can discard temporary results without clearing other leaves.
34. As a CLI user, I want pruning an absent cache to succeed without creating storage, so that cleanup is safe to repeat.
35. As a CLI user, I want prune and refresh to operate atomically, so that concurrent commands cannot leave a half-published cache.
36. As a detail-query user, I want get to perform a genuine online detail inquiry, so that I receive current object details rather than a cached list row.
37. As a detail-query user, I want list refresh to avoid detail crawling, so that saving a list does not trigger unrelated object inquiries.
38. As an analyst, I want valid incomplete results and their warnings preserved, so that partial observations remain useful without appearing complete.
39. As a strict automation author, I want require-complete to reject incomplete data and publication, so that completeness remains an explicit gate.
40. As an analyst, I want original monetary precision, unknown fields and null values preserved where supported, so that transport and caching do not alter business records.
41. As a cash analyst, I want daily native balance described as closing book balance in GMT+08, so that its agreed business meaning is clear.
42. As a cash analyst, I want closing available balance distinguished from closing book balance, so that missing source fields are not fabricated or inferred.
43. As a CLI user, I want ledger balances retired from the command surface, so that I use the agreed cash balances entry instead.
44. As a dataset owner, I want dogopencli to provide online JSON output without automatic dataset writes, so that my external duckdog importer controls persistence decisions.
45. As a dataset owner, I want duckdog selector names to follow list leaves, so that data sources are easy to identify without treating get as a dataset.
46. As a maintainer, I want old business caches cleared at the implementation switch without compatibility code, so that the temporary-cache model stays small.
47. As a maintainer, I want cache cleanup to preserve authentication, browser profiles and duckdog, so that an architecture change affects only disposable query data.
48. As a maintainer, I want help, describe and cache inspection to state the same contract, so that discovery does not advertise retired behavior.
49. As a maintainer, I want behavior tested through the existing public CLI, so that acceptance proves actual command behavior rather than private helper structure.
50. As a maintainer, I want local checks and production smoke recorded separately, so that synthetic tests do not become claims of production data availability.

## Implementation Decisions

1. **Unified operation model.** Apply the shared mode, display, quality and cache-publication rules to every currently executable list-like leaf in payment, collection, liquidity and FX. Preserve domain-native request validation and existing unsupported gates. Maintain a catalog-derived inventory so that the implementation cannot silently omit a leaf. Configuration/help/auth operations are not business datasets. Existing alternate source adapters are not permission to invent a native contract.

2. **Small shared boundary.** Reuse the command catalog, argument metadata, inquiry transport, result-policy module and SQLite cache. Centralize mode selection, display pagination and publication outcomes; plugins declare native acquisition, contract variants, local-filter mappings and supported defaults. Remove the Liquidity capture-history/retention complexity instead of building another dataset engine. No arbitrary endpoint or backend-argument passthrough.

3. **One slot per leaf.** Key the temporary list cache by stable leaf identity within the existing configured cache boundary, not query arguments, business dates or capture time. Store full validated records, their reproducible order, original effective source arguments, contract variant, acquisition time, backend provenance, quality evidence and frozen ANY selection. Different scopes and variants replace this same slot. Preserve verified within-acquisition identity checks; FX may preserve validated rows in sequence without inventing an unverified global deduplication key. No cross-acquisition deduplication, merge, retention or historical coverage manifest.

4. **Refresh publication.** Validate the whole candidate before any display filtering and before replacement. Valid nonempty default-allowed candidates replace atomically; strict incomplete candidates and all hard failures never replace. Empty valid candidates return zero acquired records with `published=false` and a reason explaining that the prior cache was preserved. With no prior cache, empty refresh creates no cache slot. Empty display after offset or local filtering does not suppress publication of an otherwise nonempty acquired candidate. Preserve old content, original fetched time and quality on every non-publication outcome.

5. **Current output versus saved output.** Retain the existing refresh summary style where applicable; it must describe this acquisition and its publication outcome, never substitute old rows or old counts. A subsequent offline list reads the preserved or replaced slot. Live/get do not publish, update freshness or write duckdog, even when successful. No automatic detail acquisition during refresh, including payment/collection flows that previously coupled list and detail snapshots.

6. **Offline selection before online default resolution.** Read the saved leaf variant first. With no explicit business filters, replay that variant and its saved scope; absence of dates must not force a daily cache through the latest-balance resolver. Normalize explicitly supplied business filters using the existing typed argument rules. Filter only fields whose semantics are declared for the saved variant. AND different dimensions; preserve each option's documented scalar/repeated-value semantics. An entity filter may select cached rows from a multi-entity result. It does not require an independently acquired singleton cache.

7. **Local filtering limits.** Explicit parameters are not matched against an exact acquisition key. Source-only controls such as native page width, or filters lacking a reliable row mapping in the saved variant, are rejected with a specific live/refresh instruction. In particular, daily date bounds cannot be evaluated against latest statement timestamps as though those were daily observations. Preserve paired-date validation and native business-date semantics. A supported filter with no matches returns `data=[]` and an explicit cache-only explanation; missing cache remains an actionable cache miss. Never fetch online implicitly.

8. **Scope and quality evidence.** Keep original source scope and acquisition quality distinct from current local filters and display counts. `matched_total` counts filtered cached/acquired rows before display; `returned_count` counts displayed rows; `has_more` describes remaining rows after the window. Native totals keep their original meaning. Filtering does not make a partial acquisition complete or prove absence beyond its acquired scope. Expose whether an explicitly requested scope is covered by the stored acquisition evidence; unknown coverage stays unknown. Effective completeness must not be asserted when source or requested coverage is unproven. Strict mode retains these checks before display truncation. A successful finite ANY inquiry proves only its frozen selected universe, not every possible backend object.

9. **Display and order.** JSON is the default result format; explicit table formatting remains available. All list-like commands use limit 100 and offset zero. Limit zero means all remaining matched rows after offset; offset beyond the result yields an empty display. Negative or malformed values are usage errors before network activity. Preserve the leaf's declared deterministic result order across online output and replay from that same acquisition. “Latest cache” means the most recently published acquisition, not a sort by each row's business date. Field projection is output-only. Native paging/chunk widths and aggregate acquisition budgets remain independent controls.

10. **Remove all.** Remove the flag from public parsing, generated help/describe, refresh options, examples, completion/catalog metadata and active automation that invokes it. An old invocation fails clearly and directs callers to limit zero for output or a supported ANY argument for enumeration. Do not keep a compatibility alias. Do not rename unrelated business arguments or command leaves.

11. **ANY capability registry.** An enumerable option must declare its logical duckdog selector, native-ID column, value validation, cardinality, row-filter mapping and allowlisted native execution strategy. Initial required capability: cash balances entity uses logical selector `liquidity/reference/entities`, column `instId`. `instCode`, labels and directory row IDs are not substitutes. Both latest and dated cash variants accept the same entity universe, subject to their respective native query contracts. Other options gain ANY only when their declared selector and native semantics are verified; do not advertise generic ANY support on every scalar argument.

12. **Read-only selector adapter.** Add an optional duckdog configuration boundary for an explicit database path and mappings from registered logical selectors to physical relations/views. Resolve relative configured paths against the configuration location, not the shell's current directory. Columns and native semantics come from the capability registry. The adapter opens an existing database read-only, selects the registered column using safely quoted identifiers, and exposes no arbitrary SQL interface. Load its dependency and access its database only for online ANY. Ordinary queries, offline list, get, prune and help work without an existing duckdog database. Do not create or initialize duckdog as a side effect.

13. **ANY value and execution rules.** Read and freeze the distinct validated native values once before browser business requests. Deduplicate deterministically while preserving native value types and case. Missing database/dependency/relation/column, empty universe, null/blank or invalid identifiers and incompatible cardinality produce actionable errors without cache/default/discovery fallback. Exact uppercase `ANY` is a reserved enumeration value; mixing it with explicit values for the same argument is invalid. Support one ANY dimension per inquiry in this iteration; reject multiple enumeration dimensions rather than generating an unbounded Cartesian product. Use verified native array/batch support where available, otherwise bounded traversal. Record selected values and attempted/acquired coverage. The shared deadline/request budget spans the entire fanout. Hard failure in any required partition withholds data/publication according to the existing hard-failure contract; valid quality shortfalls follow default/strict partial policy.

14. **Dependency inquiries and replay.** Native account-directory inquiries still needed to bind daily cash aliases may execute online under their verified allowlists; they cannot become a substitute source of ANY entity IDs. Preserve dependency quality and scope/identity checks. Offline ANY must be an already registered cache-filter operation: it uses the saved frozen values for that dimension, requires their saved evidence, and never rereads duckdog or discovers new values. If the cache was not acquired with that ANY dimension and lacks this evidence, instruct the caller to omit ANY for replay or use online ANY.

15. **Online defaults.** Apply defaults only to live and refresh acquisition after explicit option validation. For cash balances, omitted entity becomes ALIPAYGM, the user-confirmed native identifier corresponding to Z17. Explicit entity values or ANY override it. No-date online balances still use the verified latest contract; paired dates use the daily contract. Declare defaults in shared metadata so help and effective-query output agree. Audit other required scopes per leaf; preserve meaningful requirements when no business default was agreed rather than manufacturing broad or empty native queries.

16. **FX convergence.** Preserve the existing `fx trade` inquiry command and treat it as a list-like leaf. Its default becomes offline cache; `--live` performs inquiry, `refresh fx trade` publishes its sole slot, and `fx trade prune` clears that slot. For online acquisition with neither a trade ID nor any date bound, compute yesterday once in GMT+08 and use that complete calendar day. An explicit trade ID does not acquire implicit date bounds; explicit dates retain paired validation and override the default. Preserve existing date, scene, BCode, customer and transport validation. Do not invent additional business defaults or claim a globally verified identity/total contract. Existing unproven completeness remains incomplete, including after caching; normal nonempty refresh is still allowed by the result policy. Logical external selector naming may use `fx/trades` without renaming the CLI.

17. **Get and other native detail actions.** Get is implicitly online-only, independent of list cache and duckdog; preserve existing IDs, compound version keys, query allowlists and genuine native response validation. Remove cached-get behavior, detail refresh commands and detail cache publication. Do not fake unsupported get from a cached list row. Other genuine native detail actions such as history keep their action names and native contracts but also cease storing/replaying a detail cache; a true list of business history remains a list with its own temporary result, not local capture history. Synchronize capability metadata and discovery.

18. **Prune.** Register a sibling prune action on each cached list leaf, including the existing terminal FX trade grammar. It takes no acquisition filters, performs no browser or duckdog access, and affects only that leaf's slot and associated temporary metadata. It is idempotent when storage or slot is absent and does not create an empty database. Reuse existing per-cache locking/transactions: concurrent prune/refresh/read observe an atomic valid state; lock failures use the existing actionable error policy. No cross-leaf clearing.

19. **Clean implementation switch.** The user explicitly permits discarding all old business caches. Introduce a small cache-format marker or equivalent switch that invalidates/removes legacy list/detail/capture metadata without migration, compatibility reads or historical backups. The switch completes before new-format results are published and does not repeat on every startup. Old data cannot reappear under the new leaf key. Preserve configuration, credentials, browser profiles, separate source inputs and external duckdog. First ordinary offline read after clearing reports cache miss. Cache inspection reports current slots and quality, without obsolete capture-history/retention selectors. No operational cache deletion occurs merely by publishing this specification.

20. **Ledger balances retirement.** Completely remove the liquidity ledger balances list leaf, its refresh/prune/describe/help/catalog entries and leaf-exclusive query/allowlist code. Remove or revise active tests, examples and automation that advertise it. Preserve unrelated ledger queries and shared transport. Historic research/Issue records remain historical and may be annotated as superseded. This is the user's product decision about overlapping functionality; it is not new proof that every native field is semantically identical to cash balances. No compatibility alias or online request through the retired command.

21. **Duckdog boundary and private data.** Record duckdog's name and external role in the single domain context. Its selector organization follows list leaves, with get excluded. DuckDB relations may expose Parquet and JSON records, but their storage layout, loading and history policy belong to duckdog. Permit private repository-local data storage when configured and exclude it from Git; do not infer production schemas, partition settings or performance results from a directory name. No data artifacts are created by this implementation beyond temporary query cache and temporary test fixtures.

22. **Domain and documentation alignment.** Native daily `balance` means 日终账面余额 / closing book balance by confirmed business convention; daily business dates are GMT+08. Closing available balance is a separate required concept whose unsupported source values remain unavailable, not inferred or zero-filled. Keep native daily request schemas intact rather than adding an unverified timezone key. Update actual help, supported-mode descriptions, cache inspection, domain docs and a successor ADR. Explicitly supersede historical cache/detail/retention portions of the earlier ADRs; retain inquiry-only authorization and usable-incomplete quality policy, with the new empty-refresh preservation rule.

## Testing Decisions

1. **Approved primary seam:** existing public CLI, synthetic/fake CDP, temporary SQLite cache and temporary DuckDB selector. The user explicitly approved these entrances. Assert command outputs, exit codes, warnings, allowed native requests and observable persistence; avoid tests tied to private helper structure. Use focused storage/allowlist tests only where concurrency or prohibited request validation needs a lower seam. Never access production cache/profile/DuckDB in automated checks.
2. **Prior art:** existing cash-date and balance-update CLI SIT, FX trade SIT, payment/collection cache-integrity and refresh SIT, incomplete-result regressions, help/catalog/describe tests and atomic cache tests. Extend these entrances; remove assertions for discarded legacy scope matching, history merging, detail caching and ALL semantics. Preserve unrelated native-contract regressions.
3. Use a catalog-driven mode/display/capability acceptance matrix covering every enabled list-like leaf. Combine representative executable end-to-end cases from each domain with declaration checks; do not claim uniform behavior from one cash test alone. Unsupported leaves retain their explicit refusal.
4. Prove online list/get make no cache writes; offline list makes no browser, network or DuckDB access. Offline reads remain possible when Chrome is unavailable and configured duckdog is missing. Ordinary online scopes do not open duckdog. Missing cache is a cache miss, never implicit online refresh.
5. Refresh scope A with more than 100 records, replay A, then refresh nonempty scope B or another balance variant and prove only B remains. Include entity and date changes. Verify full records survive output limit/offset/fields. Prove an acquired nonempty result publishes even when its displayed slice is empty.
6. With and without a prior slot, exercise valid empty refresh, hard failures and strict rejection. Check new inquiry counts and `published=false`, unchanged prior records/timestamps/quality, and absence of a newly created empty slot. Cover failure after successful earlier pages/chunks, plus default nonempty partial replacement and its persisted warning.
7. Exercise local filtering of a multi-entity cache into a singleton without separate captures; no-argument daily replay; typed/repeated filters; matched and unmatched dates/entities; outside and unknown source coverage; unsupported source-only filters; latest-versus-daily mapping rejection. Verify an unmatched result is explained as local absence and no filter promotes completeness or silently invokes online defaults.
8. Verify JSON default, table override, default 100/0, positive limits, zero with zero/nonzero offset, offset beyond end, negative/malformed values, fields projection, stable same-acquisition order, totals and has-more. Prove limit zero leaves request/page/deadline limits intact. Verify removed ALL fails before browser effects and no active discovery advertises it.
9. Build synthetic DuckDB relations/views for registered selectors. Cover native instId versus display code/row ID, duplicates, case/type preservation, malformed/null/blank/empty lists, absent database/dependency/relation/column, wrong mapping, mixed ANY and explicit values, unsupported ANY options and multiple ANY dimensions. Failures produce no business request and never fall back to cache or native directory enumeration.
10. Prove values are frozen once even if the external selector changes during native pagination; verify read-only opening and no DuckDB modification/initialization. Cover native arrays and bounded fanout, aggregate exhaustion, partition failure, native scope echoes, incomplete dependencies and saved selection evidence. Offline ANY replay uses only the saved universe and fails helpfully when it is unavailable.
11. Verify cash online omitted entity sends ALIPAYGM, explicit IDs/ANY override it, and offline omitted entity does not filter an earlier different-entity cache. Keep daily date/alias chunking, native identity, source scope, monetary precision and no-fabricated-field regressions.
12. Freeze time for FX defaults, including GMT+08 midnight, month/year changes and leap day. Verify previous complete local day, explicit trade ID without injected dates, paired explicit dates and one-bound rejection. Exercise FX refresh/offline/prune with synthetic valid partial quality and existing request allowlisting; ensure the old live-only fixture assumption is revised without weakening side-effect assertions.
13. Verify get is online, retains genuine detail and compound-ID validation, never reads/writes list/detail caches, and no detail refresh remains. Prove list refresh does not crawl details across domains. Unsupported native details still fail safely. Cover remaining native detail action names separately from local capture history.
14. Verify prune present/absent/idempotent cases, leaf isolation, no DB creation, zero online/duckdog effects and concurrent refresh/read locking. Verify legacy-cache invalidation occurs once before new publication while auth/profile/config/source inputs/duckdog remain byte-for-byte unaffected. No compatibility migration test is required.
15. Verify ledger balances is absent from executable/catalog/refresh/describe discovery and invoking the old path makes no request. Unrelated ledger leaves remain discoverable and keep their query contract.
16. Run focused behavioral tests and repository-required pytest, Ruff and document gates during implementation. A clean gate is separate evidence from production UAT; no runtime suite is claimed by publishing this design.
17. **Separate implementation acceptance:** use the installed implementation in an isolated authorized browser/profile to run inquiry-only production smoke for default cash ALIPAYGM, one explicit cash daily range, default FX yesterday, a genuine getter and supported cash ANY using a prepared duckdog selector. Record executable/version, config/cache paths, effective args, source/quality/counts, time and publication. Prove same-acquisition cache replay after disconnecting the browser, empty preservation and prune using disposable cache. Do not disturb shared CDP or authentication; never use ports 9330–9340. Missing production access or legitimate empty data is reported honestly, not a fabricated nonempty pass or authorization to broaden the backend query.

## Out of Scope

- Building duckdog itself: imports, collector skills, Parquet writers/partition layout, history, upsert/deduplication, retention, ingestion checkpoints, deciding whether empty/partial results should be imported, analysis APIs and performance tuning.
- Automatically exporting live/refresh/get into duckdog, importing from CLI cache, or treating cache as a reliable dataset. The external importer consumes online JSON output and owns its decisions.
- Persistent merged cache pools, historical captures, coverage stitching, million-record historical retention, per-query cache partitions, cache migration/compatibility and historical backups.
- Keeping `--all`, cached get, detail refresh or the ledger balances leaf as legacy aliases.
- Generic ANY on undeclared arguments, multiple ANY dimensions, arbitrary SQL, backend mutation, exports, script execution or unbounded collection.
- Fabricating native identities, global totals, source completeness, historical available/opening balances, zero records or dates not returned by the source.
- Expanding currently unsupported leaves, unblocking unrelated native-contract defects, changing unrelated CLI argument names or rebuilding external production datasets.
- Applying runtime changes, clearing operational caches, production UAT, release/version bump, commit or push as part of this specification-publication task.

## Further Notes

- Authority is the GitHub Issue carrying this specification. Status at publication: **designed; implementation and production acceptance pending**. No historical UAT report proves the new behavior.
- Confirmed decisions: one temporary cache per list leaf; empty refresh preserves old cache; offline explicit parameters filter saved rows; online/default FX convergence; no ALL; online-only get; leaf prune; cash ALIPAYGM default; complete retirement of ledger balances; external duckdog with selector-based ANY. Earlier unified history-pool and exact-scope cache-rejection proposals are withdrawn.
- [ADR 0003](https://github.com/proletariat64/dogopencli/blob/master/docs/adr/0003-local-query-snapshots.md), [ADR 0016](https://github.com/proletariat64/dogopencli/blob/master/docs/adr/0016-liquidity-independent-list-and-detail-caches.md), [ADR 0017](https://github.com/proletariat64/dogopencli/blob/master/docs/adr/0017-liquidity-one-million-record-retention.md) and [ADR 0018](https://github.com/proletariat64/dogopencli/blob/master/docs/adr/0018-liquidity-capture-store-and-retention.md) contain conflicting historical-cache/detail decisions. Implementation must record explicit supersession rather than silently retaining those promises.
- [ADR 0019](https://github.com/proletariat64/dogopencli/blob/master/docs/adr/0019-usable-incomplete-acquisitions.md) remains the quality-policy basis: legal partial usable by default; strict rejects; hard failures preserve data boundaries. Empty refresh preservation is an explicit new publication exception.
- [Cash balances #147](https://github.com/proletariat64/dogopencli/issues/147) retains verified latest/daily native contracts and identity safeguards, while its ALL, scoped-history cache and retention behavior is superseded. [Argument normalization #127](https://github.com/proletariat64/dogopencli/issues/127) remains useful shared metadata; unrelated aliases are unaffected. [Ledger bug #144](https://github.com/proletariat64/dogopencli/issues/144) becomes obsolete on actual leaf retirement; this publication does not close it. [FX #70](https://github.com/proletariat64/dogopencli/issues/70) retains independent native/authentication evidence gaps. No issue is closed automatically.
- The reference data directory inspected on this machine contains DuckDB databases and an empty Parquet subtree. It establishes a storage convention, not a verified Parquet implementation or performance baseline. The user permits private repo-local data storage; implementation must update conflicting historical location guidance and Git exclusions. The external physical selector schema remains duckdog's responsibility; the CLI requires only the declared read-only selector/column binding.
- Authoritative domain vocabulary remains [CONTEXT.md](https://github.com/proletariat64/dogopencli/blob/master/CONTEXT.md). Daily balance meaning/timezone comes from the user's confirmed business convention, not a newly observed backend guarantee. Reporting closing available balance requires separate verified source evidence.

