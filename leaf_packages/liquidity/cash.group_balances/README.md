# Account group balances

`dogopencli liquidity list cash.group_balances` reads saved native group balances.
Add `--live` for an inquiry without publication, or use
`liquidity refresh cash.group_balances` to replace the accepted saved list.
`--group-code CODE` accepts repeated exact native group codes and also filters
saved records. `--equi-currency USD` is the only verified equivalent scope.

GET `/bankAccountGroupQuery.json` sends tenant `GUAPW3SG` and the JSON string
`bankAccountManageUnitQueryVO`: tenant, equivalent currency USD, optional
`userGroupCode` array, zero-based `rowStart` and `pageSize=100`. A successful
response requires `resultFlag=true`, inner `success=true`, and agreeing inner
and top-level counts.

Native group and member values retain their full fields, precise amounts,
unknown fields and null/empty/zero distinctions. Original member balances use
`currencyCode`; equivalent values use the requested USD scope. No original
currency summing, conversion or forecast derivation occurs.

Member observation times are independent. `gmtModified` and capture time do not
establish balance observation time. Missing `equiCurrency` and `forecastTime`
stay absent; no value or timestamp is synthesized.
