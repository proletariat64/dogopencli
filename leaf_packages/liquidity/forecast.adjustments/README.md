# Forecast adjustments

GET `/bankCashForecastAdjustmentQuery.json` through the Liquidity PortfolioMgmt
entry uses tenant `GUAPW3SG` and a JSON-string `bankCashForecastAdjustmentQueryVO`
containing the same tenant, `startValueDate=null`, `endValueDate=null`, `rowStart`
and fixed `pageSize=1000`. This reads the full current adjustment set; it adds
no date filter or aggregation.

Boolean `resultFlag=true`, `result.dataValue` object rows and integer
`result.count` are required. An explicit inner failure is rejected. Typed native
`id` identities, fixed totals and duplicate checks establish collection coverage.
Native amounts, currencies, valueDate/valueTime and unknown fields retain their
original types and precision; no scaling or timezone conversion is performed.
Absent, null and empty tenant echoes remain unchanged; a nonempty conflicting
tenant is rejected.

Default list reads the saved cache. `--live` queries without publication;
`refresh` saves the full current set. There are no filters or detail action.

The manifest selects the host List SDK with native offset paging and only the
qualified width. The leaf retains native request/response, scope and member
validation. The SDK owns paging, identity collection and publication. Duplicate
or conflicting arrivals and short/interior gaps remain explicitly incomplete;
conflicts retain the last arrival without proving it is newest. Strict acquisition
and refresh reject incomplete data. Failed/empty refresh preserves prior captures.
