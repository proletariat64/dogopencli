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
Duplicate composite identities leave collection incomplete; records outside the
requested native scope fail. Neither can publish a refresh. There is no native detail or offline scope filter.
The default list reads saved data; live does not publish.

Full native rows preserve unknown fields and source value types. This corrects
legacy whitelist field loss without changing financial values or introducing
new fields. No row aggregation, currency conversion or amount scaling occurs.
The SDK hashes the reviewed typed composite internally; native rows gain no ID. Null, empty text and zero remain distinct. `valueDate`,
`transDate`, `transTime` and `date` keep their separate source meanings and
representations. `fundDirection` is sourced, never inferred from amount sign.
Capture time does not establish statement observation time.

The manifest selects the host List SDK with native offset paging and only the
qualified width. The leaf retains native request/response, scope and member
validation. The SDK owns paging, identity collection and publication. Duplicate
or conflicting arrivals and short/interior gaps remain explicitly incomplete;
conflicts retain the last arrival without proving it is newest. Strict acquisition
and refresh reject incomplete data. Failed/empty refresh preserves prior captures.
