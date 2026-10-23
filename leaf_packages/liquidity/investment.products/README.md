# Investment products

Install this package directory or ZIP with `dogopencli plugins install PATH`.
Use `liquidity list investment.products --live --limit 0 --require-complete` or `liquidity refresh investment.products --require-complete`. Offline List reads the saved acquisition. Exact local `--currency`, `--bank` and `--status` filters accept repeated OR values; dimensions combine with AND. They never change the native request.

List uses POST JSON `/incrementProductsPage.json`, fixed tenant GUAPW3SG, rowStart 0 and qualified width 5000. One native response must cover its native total with unique physical `incrementProductId` values. Current qualification returned 910 rows, an observation rather than a limit or maximum. The host SDK owns count/identity completeness and publication; no historical terminal query or custom collector remains.

`liquidity get investment.products PHYSICAL_ID` returns `{detail, history}`. It first reads POST form `/incrementProductDetail.json` with tenant and physical `incrementProductId`, then reads POST form `/incrementProductHistoryQuery.json` with tenant and the returned detail's nonblank `incrementProductCode`. Product code is not the Get lookup. No prior List acquisition is required.

`detail` preserves the complete native root. `history` preserves the complete native array, including nested rules, accounts, unknown fields, nulls, precise numbers and original ordering. Historical physical IDs must be nonblank and unique; every history row must match the detail's product code. History completes at the qualified native response array, including an empty array; its backend total remains unknown. The current detail is not appended to history, and independent same-ID values are not reconciled across responses. The UI's operation log can be represented by the current detail followed by history.

`list --live --with-detail` retains the same-value physical-ID binding and returns each selected pair as `{record, detail: {detail, history}}`. Only the local-filter/offset/limit output window triggers detail/history acquisition. The Custom SDK shares a 10000-request allowance and 300-second deadline across the selected Get window; retries also consume that allowance. Any required inquiry failure or incomplete history aborts the entire query. `--fields` projects the List record in composition; direct Get projects the assembled root only after both inquiries succeed.

Get/composition do not publish cache or Duckdog data and preserve saved List records. Detail and history are sequential reads, without an atomic snapshot or proof of invisible backend versions. `query_evidence` retains per-query acquisition and component coverage. List/detail preserve missing, null and empty-string tenants; history also preserves whitespace-only tenant strings. Every returned nonblank tenant must match GUAPW3SG.

History has no separate public leaf or refresh command. No latest-version reduction, rate calculation, UI-default enrichment, attachment downloads or additional business relationships are acquired.
