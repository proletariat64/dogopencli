# Batch F F4: network routes contract evidence and deferral

Observed: 2026-10-06
Scope: general
Status: snapshot

Evidence chain for the `dogopencli liquidity network routes list` candidate in
[#119](https://github.com/proletariat64/dogopencli/issues/119), part of the
2026-10-06 Batch F round tracked by
[#72](https://github.com/proletariat64/dogopencli/issues/72). The PRD probe and
CDP investigation were completed in the issue; this document records why the
leaf stays unsupported with a specific named blocker. No list was enabled, no
detail request was issued and no production CLI UAT was attempted.

## PRD object versus native object

Read-only graphify queries located the owning knowledge-base sources, followed
by direct source inspection:

- P5 (*运营透明度提升-路由决策状态查询*, source 168871821, lines 84 and 118)
  describes transfer-order-scoped routing traces. That runtime trace is
  distinct from a Liquidity route configuration list and cannot stand in for
  routes settings.
- The verified realtime network contract
  ([realtime network list](2026-10-05-realtime-network-contract.md), #104) is a
  network configuration object: it carries its own native network id and
  independent `routeId` references. The network id is network identity and
  `routeId` is a reference, so realtime network records are not a generic
  routes list and must not be reused as routes acceptance.

## New clue: queryWhaleRouteDetail (discovery only)

Static frontend inspection found the q4b export wrapping
`/queryWhaleRouteDetail.json`: the native caller sends `routeId`, `aliasName`
and `tntInstId` and consumes `result.data.dynamicQuotas`/`staticQuotas`. This
is a per-route quota-detail view inside the network baseline screen. It does
not establish a global routes configuration list, row identity, scope, totals
or pagination. Consistent with the issue's decision, no `queryWhaleRouteDetail`
request was ever issued; unknown requests are not probed and no get is in scope
this batch.

## Decision

`network routes list` and `network routes get` remain unsupported with status
`unverified` (settings kind). The named blocker: no native global routes-list
caller exists; RealTimeNetwork is a network configuration object whose routeId
values are references, not routes; queryWhaleRouteDetail is network-scoped
per-route quota detail, not a routes list with pagination. Discoverability
(help/describe/snapshot) and rejection behavior (`UNSUPPORTED_CAPABILITY`
offline; `INVALID_ARGUMENT` for live/strict/refresh variants) are preserved and
covered by `tests/integration/test_liquidity_issue119_routes_gate.py` and
`tests/unit/plugins/liquidity/test_network_routes_deferred.py`. The unsupported
leaf count is unchanged at 42.

## Next evidence actions

Follow the PRD route configuration object and the queryWhaleRouteDetail caller
toward a real list or parent-object mapping; verify route identity scope,
configuration versus quota/runtime projection, scope, totals and pagination. If
only detail or network-row references exist, record an explicit business
decision request rather than reusing the 204 realtime network records as
routes acceptance. Investigation closing is not delivery; per-leaf production
UAT remains pending and serial on the dedicated CDP 9223.
