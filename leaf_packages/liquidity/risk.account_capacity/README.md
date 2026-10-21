# Account capacity

List native capacity snapshots for 1–10 distinct explicit account aliases:

```bash
dogopencli liquidity list risk.account_capacity --live --account-alias ACCOUNT_A --account-alias ACCOUNT_B --limit 0 --require-complete
dogopencli liquidity refresh risk.account_capacity --account-alias ACCOUNT_A --require-complete
dogopencli liquidity list risk.account_capacity --limit 0
```

Aliases are sorted before acquisition. Each account uses one GET to
`/api/fund/capacity/queryFundCapacityByAliasName.json` with only `aliasName`.
There is no account discovery, tenant/date input, paging, public Get or history.
The host bounds physical requests, including retries, to 30 within 300 seconds.
Any failed request, business envelope or alias echo rejects the whole candidate.

Complete means one validated native object for every requested alias:
`requested_count == resolved_count == collected_total`. `reported_total` is null;
this is not a global account inventory or an atomic multi-account snapshot.
`--limit` and `--offset` affect display after all requested accounts resolve.
`--fields` projects the retained native fields after validation.

The business output retains the ten assigned capacity fields when present:
`aliasName`, `currency`, `accountAvailableBalance`, `availableIod`,
`availableResource`, `cashPoolSupportAvailableResource`, `outFlowCapacity`,
`totalIod`, `usedIod`, `valueTime`. Optional values keep their native types,
precision, null, empty, zero, negative and unknown values without arithmetic.
UI Outflow Capacity refers to `availableResource`; `outFlowCapacity` remains a
separate field with an unverified business definition. `valueTime` is native
source time with unknown timezone; `fetched_at` is capture time.

Live does not publish. Complete nonempty refresh saves the explicit set; failed
refresh preserves the previous capture. Bare offline List replays that set.
An explicit offline `--account-alias` selects native aliases locally; changed
sets carry coverage diagnostics and strict reads reject unproved coverage.
No account source or installed leaf dependency is introduced.
