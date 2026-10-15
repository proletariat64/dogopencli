# R06 forecast qualification with payment hot accounts

Observed: 2026-10-16
Scope: general
Status: snapshot

Issue #191 requires independent nonempty contracts for account_t0,
account_hours_max and account_daily_max. This follow-up records inquiry-only
research after PR #192. Successful emptiness does not establish a row schema,
business identity, or progressing pagination. No additional forecast leaf was
enabled by this research.

## Payment source and account selection

The requested selector resolves to the existing DI prepared dataset
`deep-insight/payment-transaction-detail`, table `payment_transaction_detail`.
The local DuckDB was opened read-only. At inspection it contained 75,744,251
records dated 2026-01-01 through 2026-10-10. These are local imported source
observations, not a fresh production payment export. No import, refresh,
configuration change, or database repair was performed.

For the latest 30 source days, 2026-09-11 through 2026-10-10, group by
`instaccountno`, `payment_entity`, `fin_institution`, and `payment_currency`.
Rank independently by `count(*)` and `sum(abs(payment_amount_usd))`; the USD
amount is the existing source measure, without local currency conversion.
The top 20 from each ranking produced 40 distinct account contexts. The
highest-count context had 5,247,997 records in this window.

The prepared table has no dedicated native alias column. `instaccountno` has
native label `instAccountNo` and an include policy, not a masking policy; it
contains heterogeneous source identifiers. None of these 40 identifiers matched
a default strategy alias directly.

The verified native cash-account list yielded 3,718 rows. Exact equality of
source `instaccountno` with native `accountNo`, together with equal currency,
resolved 39 of 40 contexts uniquely. Account aliases, bank IDs and ownership
were taken from the same matched directory row. No suffix, account-number
fragment, institution-name substitution, or source payment-entity assumption
was used. The primitive directory capture itself had incomplete count coverage;
these are positive observed matches, not a claim of complete directory coverage
or global absence for the unmatched context. No directory cache was published.

Thirty of the 39 contexts also had matching native default strategy rows,
including seven with T0 Decision and one with RT Decision. Strategy configuration
does not prove forecast production.

## Exact native callers and controls

Source deployment remains the verified `S090011940898/umi.js` referenced in the
[earlier qualification report](2026-10-16-r06-native-qualification.md). The
frontend forecast list retains a `valueDate` ISO pair alongside mapped
`startDate` and `endDate`. Models and direct JSON POST services forward the
request without a discovered per-mode wrapper. The native form defaults to a
30-day difference and rejects larger differences.

The actual native UI was used on the known reference account for T0 Forecast,
Hours Maximum and Daily Maximum. All three requests included `aliasName`,
`valueDate`, `startDate`, `endDate`, `pageSize`, and `rowStart`. Their default
window was 20260916 through 20261016. Native widths were 10, 24 and 10. Each
request returned HTTP 200, business success, total zero and an empty row array.

A separate 26-account RT strategy sample was tested with the exact native UI
payload templates: 78 successful empty inquiries. Another wider diagnostic
range had also produced 78 successful empty inquiries; that wider range exceeded
the UI date limit and is not used as qualification proof. The known T3 control
returned total 42 and a 10-row first page, proving a nonempty inquiry through
the same authenticated browser.

## Hot-account results

Each of the 39 mapped hot contexts was tested independently against all three
forecast endpoints with native widths, flat JSON encoding, scalar alias,
retained date form fields and first offset zero:

- Source activity window: 20260911 through 20261010.
- Recent native window: 20261009 through 20261016.
- Total: 39 contexts x 2 windows x 3 endpoints = 234 inquiries.
- Result: all 234 returned HTTP 200, business success, zero total and zero rows.

The top count and top USD-volume contexts also returned nonempty T3 first
pages on both main windows: native totals were 178 for the source-activity
window and 42 for the recent window. Ten-row first pages were inspected; no
full T3 acquisition is claimed by these controls.

The top count and top USD-volume contexts were additionally tested over
20260801 through 20260831 and 20260701 through 20260731. All 12 inquiries were
successful and empty.

A second source ranking restricted payment rows to `routing_senario=流动性`
and `status=付款成功`. Its top ten count and top ten volume contexts produced
16 distinct candidates, all with exact native account/currency matches. Five
were additional to the original mapped set. Those five were tested over both
main windows and all three endpoints: 30 further successful empty inquiries.
The two main windows therefore cover 44 mapped source contexts, representing
43 distinct native alias/currency pairs, and 264 successful empty forecast
inquiries. One native account occurs in two source payment-entity contexts;
those source contexts were kept distinct rather than silently merged.

## Boundaries and next work

These probes rule out the particular sample-selection and missing-form-field
hypotheses tested here. They do not prove global backend emptiness, retirement,
unsupported accounts, or a particular retention rule. Non-T3 UI column definitions
include `bankID`, `expectValueTime`, `fundDirection`, and `amount`; they differ
from T3 and remain UI expectations, not a qualified nonempty response schema.

F01, F03 and F04 still require independent nonempty samples and subsequent
identity, date and pagination qualification. No forecast computation, operating
action or other production write was invoked to create samples.

The same hot-account selection did produce an independent nonempty D03 sample:
the highest-count HKD context on 20261010 returned 96 canonical slots with 95
nonzero slots and string amount fields. Four other top-count contexts returned
successful empty arrays. See the separate D03 qualification report for its
interval, empty-result and scope evidence. These are native research observations,
not public CLI UAT or cache acceptance.

All requests used the task-owned headless Chrome profile and permitted CDP port
43357. Only probe-owned pages were closed. Authentication values, raw account
numbers, transaction rows and native financial amounts are excluded from this
report and Git. Necessary joins and candidate identities remain private in the
ignored worktree research directory.
