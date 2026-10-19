# account_isolation

List collection account-isolation **opening-rule configurations**:

```bash
dogopencli collection list account_isolation -h --format text
dogopencli collection list account_isolation --live --limit 0 --require-complete
dogopencli collection refresh account_isolation --require-complete
dogopencli collection list account_isolation --currency USD
```

The List SDK acquires one JSON POST to
`https://ifundcontrolprodops.alipay.com/api/virtualAccountRuleConfig/search`,
with only `pageNo=0,pageSize=1000`. Native integer page echoes and total are
validated; unique acquired records must cover that total. `totalPageNo` is a
native placeholder, not coverage evidence. Width 1000 is qualified, not a claim
about maximum backend capacity.

Records keep native string IDs, nulls, precision and nested/unknown fields.
Output uses lexical native string-ID order.
Filters apply locally before windows and projection: repeated values OR,
different fields AND. Values match exactly and case-sensitively; commas and `*`
are literal. Blank filters fail. No backend business filters are sent.

These records are opening rules, not individual virtual accounts, balances,
capacity, or bank-account VA rules. No related detail or relationship is fetched.
Native timestamps are retained without assuming units or timezones.
