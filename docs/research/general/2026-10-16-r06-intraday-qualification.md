# R06 account fund-demand intraday qualification

Observed: 2026-10-16
Scope: general
Status: snapshot

Issue #191 D03 uses the deployed Fund Demands / Intraday Trend caller and
`POST /passiveFundDemandsIntraDayStatistical.json`. The flat JSON request carries
one alias, resolved entity/bank, and equal inclusive `startDate/endDate` in
`YYYYMMDD`. Native success data is a direct array; no pagination contract applies.

A stable 2026-10-14 sample returned 96 unique `HH:mm` labels from 00:00 through
23:45. `statisticalDate`, `inflowAmount`, `outflowAmount`, and `totalAmount` were
strings. A separate busy account/date returned 96 slots, including 95 nonzero
slots. Source rows carry no timezone, currency, alias or business-date fields;
account/day identity comes from the acquisition scope. Account timezone metadata
is reference information and does not add a timezone field to native statistics.

Exact decimal comparisons against a complete 15,270-row individual-demand
capture distinguished local expected-value-clock floor intervals from cumulative,
ceil and tested timezone-offset alternatives. Included off-quarter events at
03:25:20, 03:30:20, 06:03:20 and 06:05:20 aligned with 03:15, 03:30 and 06:00 labels.
The reference demand timezone was Europe/London for that account/date; this is a
bounded observation, not a universal timezone assignment.

Both SUCCESS and NO_NEED_PROCESS demands contributed in that sample. Two distinct
NDF demands were absent from the aggregate. Their currency, status and shared
business classifications did not explain the omission. Backend inclusion for
other statuses and books remains unverified. Statistics are independent native
results; the CLI never fetches individual demands to recompute them, and does not
promise equality with any demand-row sum.

A matching native action-type filter reproduced the baseline exactly. An unrelated
valid action filter returned successful `data=[]`; an older date and four other
busy account contexts also returned successful empty arrays. Empty success does
not mean a synthetic 96-zero grid. No filter flag is added from these research
controls.

The implementation preserves native order, strings, null, empty and absent amount
fields. A nonempty unique full 96-slot grid proves acquisition coverage. Valid
missing slots remain usable incomplete data with `INTRADAY_SLOT_GAP`; strict mode
rejects them without publishing. Duplicate or invalid labels and malformed
response types fail. Empty success is complete acquisition but preserves the
previous nonempty temporary cache, as required by ADR 0020.

This records native inquiry qualification and local fake-CDP CLI coverage;
production CLI UAT and remote CI are separate verification layers. F01, F03 and
F04 remain independently gated pending nonempty response qualification.
