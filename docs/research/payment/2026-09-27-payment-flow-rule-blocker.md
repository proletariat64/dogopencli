# Payment flow-rule detail identity blocker

Observed: 2026-09-27
Scope: payment
Status: snapshot

Issue #54 requires a complete list plus true details with matching rule identity
and version; it explicitly forbids silently reducing the feature to list-only.
That gate is currently blocked. No flow-rule runtime command is registered.

The native page Query uses GET
https://ifundcontrolprodops.alipay.com/api/fundOut/flowOperation/rule/query,
with pageNo/pageSize plus the browser-owned ctoken. Native Detail uses GET
https://ifundcontrolprodops.alipay.com/api/fundOut/flowOperation/rule/detail,
with ruleId plus ctoken; no additional version selector was observed.

The first page at size 1000 returned 755 records, 755 unique string ruleId values,
pageNo=0, pageSize=1000, totalCount=755 and totalPageNo=0. Repeated full reads
were identical. groupRuleId is nullable and not unique (410 repetitions when
counting null as one group). It must not replace row identity.

The first 30 ruleId detail requests succeeded at the business layer and returned
objects, but 3 returned different ruleId and ruleName values. The other compared
fields (ruleVersion, groupRuleId, businessCategory, creditorCurrencyCode, status,
auditStatus) agreed. A separate serial run reproduced the same 3 mismatches;
this is not explained by the three-worker concurrency of the first probe.
The returned mismatched ruleId did not equal the requested row's groupRuleId.
Full-list reads around the checks remained identical.

These observations establish a mismatch, not its backend cause. They do not
prove that every other detail is correct; the remaining 725 were not checked
because the mandatory identity gate already failed. Do not rewrite returned
IDs, substitute list summaries, invent a version selector or use a different
endpoint to bypass the mismatch. No raw IDs or rule names are stored here.

Recovery: establish the supported native lookup semantics for the mismatched
rows (or obtain a backend fix), then verify requested identity/version and
complete detail coverage. Freeze filters and the complete acquisition only
after this gate is resolved. #55–#58 have independent list contracts and can
ship without claiming #54 or the whole #59 roadmap complete.
