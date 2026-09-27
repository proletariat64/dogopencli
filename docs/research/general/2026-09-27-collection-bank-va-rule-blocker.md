# Bank-account VA rule completeness blocker

Observed: 2026-09-27
Scope: general
Status: snapshot

Focused revalidation for #52 confirms the
[historical pagination failure](2026-09-23-collection-discovery.md).
The existing authenticated headless dedicated Chrome/CDP 9222 was used after
reading the DI browser spec and launcher. Only native Search and verified
read-only list replay were performed. Temporary targets were closed; no raw
rows, identifiers, account values, credentials or HAR were retained.

Native Search on `https://ifundbossportal.alipay.com/voucher/bankAccountVARuleManage`
uses POST JSON to
`https://ifundboss-api.alipay.com/ivostro/api/bankAccountVaRule/pageList.json`.
The current native unfiltered body has bankVaRuleId="0", pageNo=1, pageSize=10.
This differs from the older empty-string selector; both variants were rechecked.

Loaded static sources `umi.bfbf5fa6.js` and
`f6981a7d-async.cce70798.js` under
`https://renderoffice-intl.alipayobjects.com/p/yuyan/180020010001284167/`
confirm the query action, default selector and UI page sizes 10,20,30,40,50.
Verified GET metadata reads for querySettleInstId and common/getCurrency were
allowed to finish page initialization before Search; unknown requests remained
blocked. No lifecycle actions or detail endpoints were invoked.

| Selector / request | Observed result |
| --- | --- |
| Empty string or "0", page 1 size 10 | success=true, 10 rows, 10 unique numeric IDs, totalCount=450; correct page/size |
| Empty string or "0", page 34 size 10 | success=true, no rows, pageNo/pageSize/totalCount all zero |
| "0", page 34 size 10 retry | Same zeroed metadata failure |
| Empty string or "0", page 1 size 1000 | Same zeroed metadata failure |
| "0", page 1 size 20 | 20 rows, 20 unique IDs, totalCount=450 |
| "0", page 17 size 20 | Same zeroed metadata failure |
| "0", page 1 size 50 | 50 rows, 50 unique IDs, totalCount=450 |
| "0", page 7 size 50 | Same zeroed metadata failure |

The returned sample schema has numeric id, boolean supportMultiCurrency/tempSave,
array extAccountNos/vaCheckRules, integer timestamps, and string accountNo,
aliasName, assembleStrategy, cardTemplateId, country, currency, financialInst,
memo, operator, reconInst, status, virtualAccountCategory and virtualAccountType.
These samples do not establish full coverage or all filter semantics.

Changing selector or trying verified UI page sizes does not resolve completeness.
The observations suggest a failure around the same record range, but do not
establish an internal backend cause. No failed pages were skipped or partial
rows stitched into a snapshot. Zeroed responses cannot establish an empty scope
when adjacent valid responses report 450 records.

Issue #52 stays needs-info. No bank-va commands, allowlist entry or partial cache
are registered. Its specification explicitly gates implementation on complete
acquisition. Resume after a backend fix or independently verified complete
acquisition contract; recheck identity/filters, then implement and perform full
argument SIT/UAT. ID-only live inquiry would require a separate scope decision.
