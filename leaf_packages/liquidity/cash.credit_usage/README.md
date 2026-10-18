# Cash credit usage

Native inquiry-only credit usage snapshots, one record per typed line `id`,
with account members retained in their original order and currency grain.

`GET /queryBankCreditLineByParams.json` uses tenant `GUAPW3SG` and a JSON-string
`bankCreditLineQuery` containing `rowStart` and fixed `pageSize=100`. The
application entry is the Liquidity PortfolioMgmt menu. Success requires Boolean
`resultFlag=true` and `result.success=true`; `result.data` holds rows and the
outer `count` must match `result.count`. Native identities and fixed totals
establish coverage. Duplicate line arrivals remain incomplete; duplicate member
identities are invalid. Neither can publish new data.

```bash
dogopencli liquidity list cash.credit_usage --live --limit 0
dogopencli liquidity refresh cash.credit_usage
dogopencli liquidity list cash.credit_usage --limit 0
```

The default list reads the saved cache. Live does not publish. This inquiry has
no verified filters or native detail action. The full native object, including
unknown nested fields and absent/null member lists, remains intact. This corrects
legacy whitelist projections that discarded source fields; it adds no derived
values. Settings and usage retain independent identities, caches and datasets.

Line `currency`, member `creditCurrency`, and member account `currency` are
distinct grains. `amount`, `usedAmount`, `availableAmount`, `creditAmount`,
`usedCreditAmount`, `availableCreditAmount` and `equvAmount` remain separate,
with native values and types. Null, empty text and zero are distinct. No scaling,
summing, exchange-rate calculation or inferred account limits is performed.
Source `shareTag`, `mergeFlag` and `isMasterAccount` do not collapse members.
Optional tenant and typed parent identity echoes must match their source scope.
Usage observation time is unknown; capture time and `gmtModified` are not usage
timestamps.

The manifest selects the host List SDK with native offset paging and only the
qualified width. The leaf retains native request/response, scope and member
validation. The SDK owns paging, identity collection and publication. Duplicate
or conflicting arrivals and short/interior gaps remain explicitly incomplete;
conflicts retain the last arrival without proving it is newest. Strict acquisition
and refresh reject incomplete data. Failed/empty refresh preserves prior captures.
