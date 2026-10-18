# Account waterlevels

POST JSON `/bufferReportList.json` through the Liquidity PortfolioMgmt entry
uses `aliasNameList` containing the explicit `--account-alias`, `rowStart`
offsets and fixed `pageSize=1000`. Boolean `success=true`, `data.data` rows
and integer `data.totalCount` are required. Identity is `(aliasName, currency)`;
contradictory aliases, missing identities and changing totals fail acquisition.

Every native field and exact amount is preserved. Null, empty text and zero
remain distinct; source valueDate/timeZone values are never inferred from capture
time. This is observed buffer state, rather than a buffer rule definition.

Default list reads the saved cache; `--live` acquires without publication and
`refresh` saves the complete account scope. Repeated `--currency` values form an
exact local union filter and do not narrow refresh publication. Offline replay
needs no repeated alias. There is no detail action.
