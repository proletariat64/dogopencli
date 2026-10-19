# Investment strategy results

List requires `--task-type FUND_DECISION_TASK|PRODUCT_DECISION_TASK`, `--from-date`
and `--to-date` (YYYY-MM-DD or YYYYMMDD). One native task variant is queried at a
time using inclusive GMT+08 trigger dates and qualified offset widths5000/10.
These widths are verified requests, not measured maximum capacity. Native totals,
identities and scope determine completeness; native pageSize metadata is not an echo.

Get uses the List `id` as positional lookup and requires `--task-type`. Only
`taskId` is sent in the native form. Returned `taskId` and `taskType` must match.
`list --live --with-detail` binds those exact native values for its selected window.
Full native records, precise values, logs and nested structures stay unchanged.
Get does not publish; incomplete/empty refresh preserves saved List data.
Recommendations and adoption status do not establish executed investment or income.
