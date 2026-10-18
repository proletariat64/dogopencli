# BANK cash pool settings

`dogopencli liquidity list cash.pools` reads the saved pool list. Add `--live`
to acquire without publication, or use `liquidity refresh cash.pools` to replace
the saved list after acceptance. `liquidity get cash.pools POOL_ID` queries native
detail and requires an exact string id echo.

Both inquiries fix tenant `GUAPW3SG` and category `BANK`. List uses POST JSON
`/cashPoolList.json`, `rowStart` offsets and `pageSize=100`; detail uses POST JSON
`/cashPoolDetail.json` with `id` and `inUse=Y`.

Pool settings, member settings and sweep rules retain every native field,
including unknown fields, native JSON types and precise amounts. No historical
field whitelist, amount scaling or synthetic timestamp is applied. Balances
returned alongside configuration remain source values; `mainCurrency` does not
establish the currency of pool summary balances. Capture time does not establish
source observation time.

Absent, null and empty tenant echoes remain unknown native values. A nonempty
tenant echo must match `GUAPW3SG`, including nested members and sweep rules.
