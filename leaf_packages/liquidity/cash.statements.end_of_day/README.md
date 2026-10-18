# End-of-day cash statements

Read inquiry-only native bank statement rows using
`POST /bankAccountDetailDayQuery.json` from the Liquidity PortfolioMgmt entry.
Requests contain only tenant `GUAPW3SG`, `instIds`, `bankAccountAliasName`,
`currency`, `timeZone=GMT+08`, `queryDateBegin`, `queryDateEnd`, `rowStart` and
fixed `pageSize=1000`. Institution and account selections are native arrays;
account values are aliases. Public dates accept `YYYY-MM-DD` or `YYYYMMDD` and
use compact request values. Bounds are inclusive on the source value date.

```bash
dogopencli liquidity list cash.statements.end_of_day --live --entity Z21 --account-alias ACCOUNT_ALIAS --currency USD --from-date 2026-10-01 --to-date 2026-10-01 --limit 0
dogopencli liquidity refresh cash.statements.end_of_day --entity Z21 --account-alias ACCOUNT_ALIAS --currency USD --from-date 2026-10-01 --to-date 2026-10-01
dogopencli liquidity list cash.statements.end_of_day --limit 0
```

Success requires Boolean `success=true`, object-array `data.data` and a
nonnegative integer `data.totalCount` unchanged across pages. Coverage requires
all arrivals to match the total with unique typed composite identities
`(instId, bankAccountAliasName, currency, valueDate, bankTransNo)`. Reused
transaction numbers in distinct composite scopes remain distinct records.
Duplicate composite identities and records outside the requested native scope
fail without publishing. There is no native detail or offline scope filter.
The default list reads saved data; live does not publish.

Full native rows preserve unknown fields and source value types. This corrects
legacy whitelist field loss without changing financial values or introducing
new fields. No row aggregation, currency conversion, amount scaling or identity
synthesis occurs. Null, empty text and zero remain distinct. `valueDate`,
`transDate`, `transTime` and `date` keep their separate source meanings and
representations. `fundDirection` is sourced, never inferred from amount sign.
Capture time does not establish statement observation time.
