# Intraday cash statements

POST JSON `/bankAccountDetailQuery.json` reads native bank movements through the
Liquidity PortfolioMgmt entry. Tenant is `GUAPW3SG`, timezone is `GMT+08`, and
`rowStart` advances by fixed `pageSize=1000`. Supply `--account-alias`, `--currency`,
`--from-date` and `--to-date`; `--inst-id` defaults to `Z21`. Dates accept
YYYY-MM-DD or YYYYMMDD and are sent as inclusive compact date bounds. Account
alias and institution are sent as arrays containing one string each.

Boolean `success=true`, `data.data` object rows and integer `data.totalCount`
are required. Fixed totals and typed `bankTransNo` identities establish coverage.
Duplicate identities and contradictory account/currency/date scope are rejected.
Native amount, fundDirection, transDate, transTime, valueDate and unknown fields
are preserved without amount scaling, arithmetic or timezone conversion.

Default list reads the saved cache. `--live` acquires without publishing;
`refresh` saves the full acquired scope. Repeated `--fund-direction` values filter
locally by exact source value; they do not narrow refresh publication. Offline
replay needs no acquisition scope. There is no detail action.
