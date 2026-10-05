# Credit usage: source evidence and operator clarification

Observed: 2026-10-05
Scope: general
Status: snapshot

Authoritative specification: [issue #98](https://github.com/proletariat64/dogopencli/issues/98).
This follows the completed cash pool balance slice in PR #100. Product baselines
and investment quotes remain deferred.

## Operator-confirmed reading boundary

The operator confirmed that nonshared credit lines allocate limits to individual
accounts, while shared lines provide a common limit without preassigning account
limits. Assigned totals and account usage normally obey credit constraints, but
available plus used need not equal the assigned limit. These are business rules,
not conditions for displaying source data. The CLI must not audit or repair them.

Preserve parent and nested account records, source amounts and currencies,
shareTag, mergeFlag, and null/blank/missing values. Do not calculate totals,
exchange rates, account caps or amount equality. Do not reject source values on
business amount, currency or time rules. API success, structure, identity,
parent links, tenant and collection completeness remain reading-protocol checks.
Existing settings and previously delivered leaves retain their contracts.

## Native contract evidence

The existing allowlisted GET `/queryBankCreditLineByParams.json` uses tenant
GUAPW3SG and JSON-string bankCreditLineQuery containing rowStart/pageSize.
A bounded width-100 inquiry returned explicit resultFlag/result.success and
84 records, matching top-level count and result.count. The 84 parent identities
and 667 member identities within their parents were unique; creditLineId links
and parent tenant matched. This is native contract evidence, not credit-usage
production CLI UAT.

Parent amount/usedAmount/availableAmount and both member amount families are
already returned by this endpoint. Several native monetary strings include
thousands separators. Preserve their exact representation rather than introducing
local numeric normalization or financial validation.

All observed parent/member startTimestamp and expiryTimestamp values and parent
timeZone values were blank. gmtModified is configuration-update metadata; the
source provides no usage-observation time. It remains unknown. Capture time is
only when the inquiry was made, not an inferred observation time or daily scope.

## Source meaning and evidence limits

The current native UI bundle SHA256 is
`cd59b985d544dff8fb7ab89c6081fd1d9713187886db9abccdc554d82eddbf03`.
The parent table labels currency as Credit CCY and usedAmount/amount/availableAmount
as Credit Used Amt / Credit Amt / Credit Avl Amt. The member editor labels
creditCurrency as CreditLine CCY. Its shared-mode configuration clears member
creditCurrency and creditAmount; the read CLI does not execute editor actions.

The member table labels usedCreditAmount as Credit Used Amt and usedAmount as
Equv Used Amt (Orig), and likewise separates the allocated and available amount
families. Preserve these source distinctions and currency fields; do not fill a
blank member currency or infer field meaning from numerical ratios.

The table merges usedCreditAmount display cells by mergeFlag. This proves a UI
grouping, not a new business identity, allocation formula or right to sum repeated
values. Keep each account member and its original flag; never synthesize extra
tree levels from it or from the Sub Limit label.

Read-only graphify research located the owning historical Liquidity operating
center document (19155370, section 4.3, lines 155–172), which describes parent
entity/branch and account credit-usage views. It does not establish current
runtime field mappings or timestamps. The current UI source (line 111, character
offsets 2470610–2470890, 2476990–2478050, 2504915–2507080 and 2513300–2514850)
and the operator clarification above provide the narrower evidence used here.
Whale token/route credit designs were excluded as different business sources.

## Implementation boundary

Implement an independently cached runtimes source-state snapshot using the
existing history capture profile. Keep the original line/member tree and source
values; explicit refresh publishes, default reads remain offline and live does
not publish or fall back. The `cash credit-lines` settings namespace is unchanged.
Unknown time or empty amount/currency is not incomplete acquisition. Independent
public CLI production UAT is still required before claiming this slice delivered.

Live examples, account identifiers and raw responses remain private; no source
amounts from those examples are included in this report or sanitized fixtures.
