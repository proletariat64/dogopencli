# Forecast cashflows

Read native forecast points through inquiry-only `GET /queryCashFlowData.json`.
Online List, Refresh and workflow planning require explicit `--inst-id`,
`--account-alias`, `--currency`, `--from-date` and `--to-date`. No entity, account,
currency or date is supplied by the leaf. Missing or blank selectors fail before
browser access. Dates use `YYYYMMDD`, with inclusive bounds on the native
`expectValueDateTime` target day in GMT+08.

Supply the intended business scope in every acquisition:

```bash
dogopencli liquidity list forecast.cashflows --live --inst-id ENTITY --account-alias ACCOUNT_ALIAS --currency CURRENCY --from-date YYYYMMDD --to-date YYYYMMDD --require-complete --limit 0
```

The capitalized values above are placeholders, not query defaults. Help and
Describe remain offline. A cached List can omit acquisition parameters to read
its saved scope, or pass supported selectors to filter that snapshot locally.

The leaf preserves native rows, amounts, nullable values and identity dimensions.
`gmtCreate=null` means no valid forecast value has formed yet; the point remains
in the returned records. Count witnesses, identity and returned entity/account/
currency/date scope must pass validation. Explicit parameters do not bypass these
checks. Live List does not publish a cache snapshot or import Duckdog data.
