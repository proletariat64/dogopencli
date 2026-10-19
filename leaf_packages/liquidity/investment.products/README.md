# Investment products

Install this package directory or ZIP with `dogopencli plugins install PATH`.
Use `liquidity list investment.products --live --limit 0 --require-complete` or `liquidity refresh investment.products --require-complete`. Offline List reads the saved acquisition. Exact local `--currency`, `--bank` and `--status` filters accept repeated OR values; dimensions combine with AND. They never change the native request.

List uses POST JSON `/incrementProductsPage.json`, fixed tenant GUAPW3SG, rowStart 0 and qualified width 5000. One native response must cover its native total with unique physical `incrementProductId` values. Current qualification returned 910 rows, an observation rather than a limit or maximum. The host SDK owns count/identity completeness and publication; no historical terminal query or custom collector remains.

`liquidity get investment.products PHYSICAL_ID` independently reads POST form `/incrementProductDetail.json` with only tenant and physical ID. Product code is not the lookup. `list --live --with-detail` uses standard same-value binding and acquires details only for the selected local-filter/offset/limit window. Each native record and detail retains its own complete root, nested children, unknown fields, nulls, numeric precision and arrival order. Get/composition preserve saved List data. Returned nonblank tenant values must match GUAPW3SG; missing, null and blank tenant values remain unchanged.

History is a separate unresolved leaf, not automatically appended to Get. No latest-version reduction, rate calculation, downloads or related-source discovery occur. Contract references are the current frontend/native qualification and pinned v0.4.3 `liquidity/leaves.py` product List/Detail declarations; the archive is comparison-only and is never imported by this package.
