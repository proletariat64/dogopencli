# reference.blacklist.account

Inspect native account blacklist settings:

```bash
dogopencli liquidity list reference.blacklist.account -h --format text
dogopencli liquidity list reference.blacklist.account --live --limit 0 --require-complete
dogopencli liquidity refresh reference.blacklist.account --require-complete
dogopencli liquidity list reference.blacklist.account --bank-id BANK_ID
```

GET `/accountFilterConfigQuery.json` on `iliquidity.alipay.com` sends outer
`tntInstId=GUAPW3SG` and a JSON-string `accountFilterConfigQuery` containing the
same tenant, `timezone=GMT+08`, `currentArea="3"`, native `rowStart` and `pageSize`.
These constants define the qualified query scope, not backend mandatory defaults.
Widths5000 and1000 are qualified, not maximum-capacity claims. Shared SDK fallback
restarts the full scope at offset0; native response offsets are not echoed.

Both success markers and equal integer inner/outer counts are required. Complete
coverage requires native aliases and total to agree without duplicate or missing
rows. Full native records, source order, precision, nulls and unknown nested
values remain intact. Absent/empty row tenant fields stay unchanged; a contradictory
tenant fails. No new identity or account-directory join is inferred.

`--entity`, `--bank-id`, `--account-alias`, `--status` filter locally before windows
and projection. Repeated values OR, dimensions AND; strings match exactly and
case-sensitively, commas and `*` are literal, blank inputs fail. Status accepts
VALID/INVALID, but those values alone do not prove blacklist enforcement.
No Get, latest-version reducer, account balance or related-source query is added.
