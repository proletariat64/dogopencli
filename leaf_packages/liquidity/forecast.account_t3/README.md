# Account T3 forecasts

Install this independent package with `dogopencli plugins install PATH`.

Use `liquidity list forecast.account_t3 --live --account-alias ACCOUNT --from-date YYYYMMDD --to-date YYYYMMDD --limit 0 --require-complete`. Replace `list --live` with `refresh` to save a complete nonempty acquisition. Bare offline List replays the saved scope.

The inclusive window selects native `forecastDate`, independently of `expectValueDate`. The leaf sends only aliasName/startDate/endDate/rowStart/pageSize to POST JSON `/t3ForecastDemandList.json`, with qualified width 1000. The host offset SDK checks native totals and the eight-component identity; it performs no extra terminal-empty probe.

All native fields, unknown nested values, nulls, precise numbers and arrival order remain unchanged. Offline alias/date flags select local rows; changing the source scope does not prove new coverage and `--require-complete` rejects it. This leaf has no account resolver, Get, related-source joins, balance calculation or T0 inquiry.

Contract evidence: current T3 frontend inquiry and private positive native qualification; pinned v0.4.3 `plugins/liquidity/account_forecasts.py` supplies the business dimensions. Historical source is comparison-only and is never imported by this package.
