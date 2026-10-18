# BANK cash pool settings

`dogopencli liquidity list cash.pools` reads the saved pool list. Add `--live`
to acquire without publication, or use `liquidity refresh cash.pools` to replace
the saved list after acceptance. This delivery is List-only; Get is deferred.

The inquiry fixes tenant `GUAPW3SG` and category `BANK`, using POST JSON
`/cashPoolList.json`, `rowStart` offsets and `pageSize=100`.

Pool settings, member settings and sweep rules retain every native field,
including unknown fields, native JSON types and precise amounts. No historical
field whitelist, amount scaling or synthetic timestamp is applied. Balances
returned alongside configuration remain source values; `mainCurrency` does not
establish the currency of pool summary balances. Capture time does not establish
source observation time.

Absent, null and empty tenant echoes remain unknown native values. A nonempty
tenant echo must match `GUAPW3SG`, including nested members and sweep rules.

The manifest selects the host List SDK with native offset paging and only the
qualified width. The leaf retains native request/response, scope and member
validation. The SDK owns paging, identity collection and publication. Duplicate
or conflicting arrivals and short/interior gaps remain explicitly incomplete;
conflicts retain the last arrival without proving it is newest. Strict acquisition
and refresh reject incomplete data. Failed/empty refresh preserves prior captures.
