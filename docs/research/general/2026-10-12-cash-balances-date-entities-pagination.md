# Cash balances: business dates, all entities and page width

Observed: 2026-10-12
Scope: general
Status: snapshot

Retired source references: local links removed by #255 now point to pinned release v0.4.3; this historical snapshot does not describe the current installed runtime.

## Findings

1. Keep `--live` online, default reads offline, and explicit refresh as the only cache writer. `--from-date` / `--to-date` must mean the same inclusive source business-date window online and offline, not capture time.
2. The existing `POST /latestBalanceQuery.json` returns current balance snapshots. Its native list caller has no business-date bounds. Do not attach invented date fields or filter current rows and call that historical lookup.
3. A separate native inquiry, `POST /balStatisticalQuery.json` with `balanceType=day`, returns per-account daily balance observations for an inclusive date range. It does **not** return historical versions of the entire latest-snapshot schema.
4. Entity discovery returned 71/71 distinct, nonempty `instId`s. Send these IDs, not `instCode`, to `entitys`. All-entity latest requests succeeded on sampled pages.
5. Recommended latest acquisition width: **100**, not 10 or the old configured 30. Widths 1, 30, 31, 50 and 100 succeeded in this investigation; 500, 1000 and 5000 were rejected. The backend rejection text says a maximum of 30, but observed success above 30 disproves that text as an accurate limit. The actual maximum between 100 and 500 was not determined.
6. Historical account discovery remains incomplete: 3710 returned versus 3711 reported. This quality fact must propagate into entity-wide historical acquisition; successful daily requests cannot erase it.

This is design research, not implemented-feature or full production CLI UAT evidence. Finalized implementation specification: [Issue #147](https://github.com/proletariat64/dogopencli/issues/147), with a [versioned readable copy](../../design/liquidity-cash-balances-v0.1.0.md).

## Primary sources and method

- Current code at commit `0a3c460b191d`: [latest contract](https://github.com/proletariat64/dogopencli/blob/a7e5c5ead675487646eb9a53d73ec9e0aeb944f9/src/dogopencli/plugins/liquidity/cash_forecast.py), [entity/account contracts](https://github.com/proletariat64/dogopencli/blob/a7e5c5ead675487646eb9a53d73ec9e0aeb944f9/src/dogopencli/plugins/liquidity/leaves.py), [offset acquisition](https://github.com/proletariat64/dogopencli/blob/a7e5c5ead675487646eb9a53d73ec9e0aeb944f9/src/dogopencli/plugins/liquidity/collect.py), [result policy](../../adr/0019-usable-incomplete-acquisitions.md), and [capture profiles](../../adr/0018-liquidity-capture-store-and-retention.md).
- Independently verified Liquidity authentication at `https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt`, dedicated profile, headless Chrome, CDP `127.0.0.1:9222`. No forbidden CDP port, login automation, credential extraction or business mutation.
- Current native bundle: `https://gw.alipayobjects.com/render/p/yuyan/180020010000002482/S090011910164/umi.js`; 15,763,128 bytes; SHA-256 `cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`. Matches the [October 2 source proof](2026-10-02-cash-forecast-business-probe.md), but API behavior was probed again rather than inferred from that match.
- Zero-based character offsets in that bundle: service `he` / latest query near 1513803; services `Le` / `tt` for statistical inquiry near 1514300–1514900; daily chart renderer near 4088900; daily date/alias callers near 4105915–4107420; latest list caller near 4110239–4111800. Daily renderer uses `statisticalDate` as x-axis, `balance` as value and `data` as account series.
- Research requests used narrow temporary descriptors with the existing inquiry session, shared lease, validated request transport and native source-derived templates. Research descriptors are not registered production capabilities. No arbitrary request entry point was added.
- Read-only graphify KB research preceded historical document inspection. Whitepaper document 197368565, local export `Liquidity__平台介绍__Liquidity-Product-of-Global-Fund-Platform-Whitepaper__国际流动性产品白皮书-2026-06-29-[197368565].md` in `~/dev/dogpdkb/graphify_flatten_ready/`, lines 153–175, distinguishes intraday/opening/closing and account-local T+1 statement delivery. It supplies vocabulary, not current API/date/page-size contracts. The KB graph was not rebuilt.

Raw native source, account identifiers, requests and responses remain only in ignored `tmp/cash-balances-research/`, directory 0700 and evidence files 0600. They are not sanitized fixtures. Published evidence below contains fields and aggregate counts only.

## Latest balance page-width evidence

Same positive single-entity scope, `timeZone=GMT+08`:

| pageSize | Success | Rows returned | Reported total | Observation |
| ---: | --- | ---: | ---: | --- |
| 1 | yes | 1 | 399 | Lower-bound sample |
| 30 | yes | 30 | 399 | Existing width |
| 31 | yes | 31 | 399 | Rejection message's stated maximum is inaccurate |
| 50 | yes | 50 | 399 | 8.46 seconds |
| 100 | yes | 100 | 399 | 9.77 seconds |
| 500 | no | — | — | HTTP 200, business rejection |
| 1000 | no | — | — | HTTP 200, business rejection |
| 5000 | no | — | — | HTTP 200, business rejection |

Rejected requests returned `success=false`, with `detailMessage` / `errorMessage` text `pagesize can&#39;t more than 30 for performance`. This does not establish an actual hard maximum of 30. The user's successful 500 observation may involve a different request shape or contract; it was not reproduced here.

A positive single-entity scan at width 100 used rowStart 0/100/200/300, arrivals 100/100/100/99, with fixed total 399. However, only **396 unique composite identities** arrived: three duplicate arrivals mean count coverage is incomplete. The final page also contains **one row whose `entity` is outside the requested singleton**; its alias maps to the requested entity in the account roster. This is a separate scope/identity inconsistency, not permission to silently rewrite that row from the roster. Do not call this complete or a passed strict UAT. The width is accepted by the server, but that alone does not qualify every acquisition as safe.

An empty entity accepted 31 and returned 0/0; that initial observation alone was not used to qualify positive-scope page widths.

## All entities

`GET /entityMaintQuery.json` returned 71 rows, reported total 71, and 71 distinct nonempty `instId`s. There is no proven ALL sentinel; expansion is an explicit frozen ID array.

The latest request with all 71 IDs returned:

| Width | rowStart | Success | Rows | Reported total | Seconds |
| ---: | ---: | --- | ---: | ---: | ---: |
| 30 | 0 | yes | 30 | 2787 | 32.94 |
| 30 | 30 | yes | 30 | 2787 | 33.32 |
| 100 | 0 | yes | 100 | 2787 | 33.73 |
| 100 | 100 | yes | 100 | 2787 | 33.85 |
| 500 | 0 | no | — | — | 1.31 |
| 500 | 500 | no | — | — | 6.01 |

Sampled returned `entity`s belonged to the discovered `instId` set. The two width-30 pages and the two width-100 pages each had no identity overlap. Two independently selected positive entities reported 399 and 664; their combined request reported 1063. This supports disjoint per-entity acquisition as a candidate optimization, not an already completed full all-entity scan.

The current collector has a shared 900-second budget and 1000-page guard. At roughly 34 seconds per all-entity page, 28 width-100 pages may exceed 900 seconds. That arithmetic is a risk estimate, not measured full-scan runtime. A combined scan needs an explicitly documented larger leaf-specific budget or a separately qualified partition strategy. Singleton partitions cannot be assumed safe given the observed out-of-scope singleton row. No silent deadline extension or per-partition deadline reset. The proposed design retains the native combined ID-array request and explicitly budgets all-entity latest acquisition; full-scan UAT remains required.

`--all` currently only disables the display limit within the selected scope. Any entity-expansion change must explicitly document this leaf's broadened unscoped behavior, preserve explicit-entity use and avoid changing other list commands.

## Daily historical inquiry

Exact source-derived request:

- Method/path: `POST /balStatisticalQuery.json`, JSON body.
- Fixed fields: `tntInstId=GUAPW3SG`, `balanceType=day`.
- `aliasNames`: selected account-alias array.
- `queryStartDate`: inclusive start, compact `YYYYMMDD`.
- `queryDate`: inclusive end, compact `YYYYMMDD`.
- No `entitys`, `timeZone`, `rowStart` or `pageSize` fields in this native daily caller.
- Success: top-level `success`; rows: `data` array; no reported total.
- Observed row fields: `id`, `data`, `statisticalDate`, `balance`, all strings. `data` echoes the selected account alias; `statisticalDate` is ISO `YYYY-MM-DD`. Native `id` repeats across dates and is not a daily row identity.

| Probe | Result |
| --- | --- |
| One alias, 2026-10-10 only | 1 row |
| Same alias, 2026-10-10–11 | 2 rows, both endpoints present |
| Two aliases, 2026-10-10–11 | 4 unique alias/date observations, no unrequested aliases |
| Nonzero alias, 2026-10-07 only | 1 nonzero observation; amount equals that account's same-day native EOD close in the latest response |
| Nonzero alias, 2026-10-06–08 | 3 observations, both endpoints present |
| One alias, 2020-01-01–02 | Successful empty array; not historical membership/retention proof |
| 30 aliases, 2026-10-05–11, two rounds | 210/210 unique alias/date observations each; identical content; 5.96/1.84 seconds |

The native daily value remains `balance`; one same-day EOD match is corroboration, not proof that every row is closing, available, opening or converted balance. No division by 100, inferred availability or currency conversion. No response timezone was established, and the request has no timezone selector.

A successful empty response does not justify fabricating dense alias/date rows or zero balances. Completeness can concern executed source request coverage; it cannot prove that every historical account or business event exists in the response.

## Account and entity binding for dated mode

`GET /queryintnalbkactlist.json`, existing width 5000 and fixed `wallet=false`, returned 3710 unique alias/currency rows versus total 3711. All 3710 aliases were unique in this sample, nonempty, and had nonempty `instId`; fields include `instId`, `entityCode`, `currency`, `aliasName`, open/close dates and status.

- 3665 account rows belonged to the current 71-entity directory; 45 were outside that selected entity universe. Do not substitute `entityCode` for `instId` or quietly expand the selected entity universe to absorb them.
- All 30 daily-probe aliases mapped unambiguously to one account roster entity/currency. Bind output labels through that frozen roster and disclose its observation time.
- A current account mapping is **not** proof of historical ownership, nor a roster of every deleted historical account. Keep those limitations explicit.
- The one-row catalogue coverage gap persists even though every observed row had a valid identity. It must remain incomplete under the current default usable-partial policy; strict acquisition refuses it.

## Design recommendation and remaining gates

- Preserve no-date latest mode. Add a separate dated variant under the same command using the daily native inquiry and a clearly different, documented daily-balance schema.
- Use `--from-date` / `--to-date` online/offline/refresh consistently. Cache dated observations by `statisticalDate`, independently from retained latest captures.
- Freeze entity and account selection once per online acquisition; persist its provenance. Offline reads never fetch catalogues and never silently reinterpret ALL using a different current entity list.
- Expose latest `--page-size`, proposed default 100 and supported operational range 1–100. This is a client support bound, not a discovered server maximum. Historical requests cannot carry pageSize; keep internal alias/date chunking separate from backend paging and display `--limit`.
- Initially bound native daily requests to at most 30 aliases and seven inclusive dates, partitioning larger windows disjointly under existing aggregate budgets. These are probed operational chunk sizes, not claimed native hard limits.
- No export requests: `/dayEndBalanceExport.json` is present in the Download caller but was not executed or qualified. Neither this path nor its UI's 180-day bound establishes the daily inquiry contract.

Required before enabling: public-CLI fake-transport tests, exact allowlisting and scope isolation, full all-entity latest convergence, daily batch-versus-singleton comparison, strict/partial coverage propagation, cache-only reads with browser unavailable, and same-acquisition refresh/offline equivalence. Full all-entity and historical CLI UAT were not run in this design-only task.
