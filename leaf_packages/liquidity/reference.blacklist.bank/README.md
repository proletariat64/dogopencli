# reference.blacklist.bank

Inspect bank blacklist configurations:

```bash
dogopencli liquidity list reference.blacklist.bank --live --limit 0 --require-complete
dogopencli liquidity refresh reference.blacklist.bank --require-complete
dogopencli liquidity list reference.blacklist.bank --bank-id BANK_ID --status VALID
```

GET `/bankFilterConfigQuery.json` on `iliquidity.alipay.com` sends outer
`tntInstId=GUAPW3SG` and JSON-string `bankFilterConfigQuery` with the same tenant,
`timezone=GMT+08`, `currentArea="2"`, `rowStart` and `pageSize`.
Widths 5000 and 1000 are qualified query widths. Both success markers and equal
integer inner/outer counts are required. Contradictory row tenants fail; absent
and empty tenant values remain unchanged.

The business primary key is `(bankId, bankSwiftCode)`. An observed empty Swift
string stays a literal component. Select greatest `(gmtModified, gmtCreate)`
within each key, preserving the full selected native row and first-key order.
Creation time breaks modification ties, including differing configurations.
Identical fully tied records collapse; different records tied on both timestamps
fail because no ordering remains established. Timestamps must be nonnegative
integer epoch milliseconds; no dates are synthesized.

Custom execution uses named host inquiries with one shared request/time budget.
The source total counts row occurrences, not selected configurations. Acquisition
restarts at width 1000 after an undersized width-5000 response. Shifted beginning
and page-join overlaps must equal the corresponding acquisition slices, and an
independent read at the exact total must be empty. Selection occurs only after
these checks, with raw counts, selected counts and source coverage retained through
offline replay. Legitimate duplicate entries do not imply missing source rows.

`--bank-id` and `--status` filter selected rows locally, exactly and case
sensitively. Repeated values OR; dimensions AND. Commas and `*` are literal.
All statuses are retained by default; VALID/INVALID do not establish enforcement.
No Get, bank-directory join or business mutation is exposed.
