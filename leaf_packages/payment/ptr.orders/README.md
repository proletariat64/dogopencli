# Payment PTR orders

List existing outflow PTR orders in one explicit updated-time interval. Provide
`--from-time` and `--to-time` with second-precision numeric UTC offsets.
Equivalent instants normalize to Shanghai +08:00. The interval is ordered, at
most 31 days, with a nonfuture upper bound; the public interval is half-open.

Two declared SDK sources each call the same fixed-500 List query. Both responses
must completely cover their one-second-padded native scope and have identical
retained projections when sorted by native `ptrOrderId`. Stability includes
padding rows. Only then does the leaf trim to `start <= gmtModified < end`.
Each native padded total and acquisition remains separate from the output count.
The host owns request restrictions, retries, shared budgets and publication.
The two single-page sources share a 900-second deadline and two logical pages;
each page permits at most three physical attempts, retaining the six-request bound.

History uses the `gmtModified` instant axis and explicit windows only. The host
range is inclusive UTC milliseconds `[start, end - 1ms]`; reverse conversion
recovers the exclusive whole-second end. Non-whole-second lower bounds and upper
bounds not ending `.999` fail without rounding. Fixed local filters remain frozen.
No equivalence between concatenated smaller queries and a larger query is claimed.

The original PTR retained-field policy applies, including native money and nested
baseline allowlists. Unknown fields are omitted. No amounts, dates or results are
recomputed. Exact local filters OR repeated values and AND different fields;
commas and asterisks are literal. Offline replays its saved scope. Acquisition
bounds require live/refresh; live makes no business-cache publication, while only
complete nonempty refresh replaces the prior snapshot.

This package exposes List only. Existing orders and verification results are
queried; no trial, execution, withdrawal, verification or approval is triggered.
The application entry is
`https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/productPTRManagement/orderInquiry`;
the named inquiry uses GET `/api/ptr/manage/query.json` on
`iglobalfundcontrol.alipay.com` with the fixed, window-bound request above.
