# Cash credit line settings

Read native credit configuration: one record per typed line `id`, with ordered
`bankAccountCreditLineList` account members and their typed parent links.

`GET /queryBankCreditLineByParams.json` uses tenant `GUAPW3SG` and a JSON-string
`bankCreditLineQuery` containing only `rowStart` and fixed `pageSize=100`.
The application entry is the Liquidity PortfolioMgmt menu. Success requires
Boolean `resultFlag=true` and `result.success=true`; rows are `result.data`,
and outer `count` must equal `result.count` as nonnegative integers.
Changing totals, duplicate line/member identities, invalid parent echoes and
out-of-scope tenants fail without publishing new data.

```bash
dogopencli liquidity list cash.credit_lines --live --limit 0
dogopencli liquidity refresh cash.credit_lines
dogopencli liquidity list cash.credit_lines --limit 0
```

The default list reads saved data; live does not publish. No source filter or
native detail action is verified. Configuration includes credit limits, native
currency, validity, status and account membership. Parent and member amounts and
currencies remain separate; no sum, conversion, scaling or derived usage exists.
Null, empty text and zero are distinct, and unknown fields retain their types.
Full native records correct legacy whitelist field loss, including discarded
source fields outside the settings display. The package interprets configuration
independently from the usage package and owns a separate cache and dataset.
Source timestamps and validity dates do not establish usage observation time.
