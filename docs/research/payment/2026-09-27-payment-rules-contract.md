# Payment rule inquiry contracts

Observed: 2026-09-27
Scope: payment
Status: snapshot

## Verification method

Reused the 2026-09-08 menu survey and the existing authenticated headless Chrome
on CDP 9222 under the shared inquiry lease. Observed native query requests on
only the five ticketed pages. No configuration, approval, retry, switch, export
or PTR action was executed. All response values remained in memory; only
schema, counts and structural comparisons are recorded here.

## Frozen complete-list acquisition (#55–#58)

| Capability | Exact endpoint | Request | Envelope / identity | Observed complete rows |
| --- | --- | --- | --- | --- |
| same-bank-transfer | POST https://ifundboss.alipay.com/payout/api/bookDecisionRule/search.json | pageNum=1,pageSize=1000 | resultObj.payoutBookDecisionRuleVOList / integer ruleId | 34 |
| cost-reduction | GET https://ifundcontrolprodops.alipay.com/api/fundOut/costCutFlow/query | pageNo=0,pageSize=1000 | data.businessDataList / string groupId | 30 |
| retry | GET https://ifundcontrolprodops.alipay.com/api/fundOut/flowOperation/exceptionRetryRule/page | pageNo=0,pageSize=1000 | data.businessDataList / string ruleId | 89 |
| bank-switch | GET https://ifundcontrolprodops.alipay.com/api/fundNavigation/nodeSwitch/query | pageNo=0,pageSize=1000 | data.businessDataList / string switchNodeCode | 46 |

Each endpoint independently returned rows=totalCount, unique identities and
identical full records on repeat reads. Native smaller pages were observed;
size 20 returned 20 rows and the same full total for each capability. Counts
above are observations, never constants. GET request values are query parameters;
POST uses JSON. ctoken remains transport-owned, never a public selector.

Acquire exactly the frozen first page, no selectors or paging fallback. Require
success=true, valid nonnegative integer pagination, exact page/size echoes,
rows=totalCount<=1000 and unique identities. Same-bank also requires nested
resultObj.success=true and totalPages matching the complete single-page count;
the other endpoints' totalPageNo stayed zero for nonempty scopes and must not
be used to establish coverage. Beyond-end same-bank queries returned page 1
again; bank-switch omitted its list. Neither behavior is used for acquisition.
A correctly echoed empty array with zero total is supported synthetically;
null/missing lists, zeroed size and ambiguous empty envelopes fail. Unfiltered
empty production scopes were unavailable. Failures preserve the old snapshot.

## Filters: include decisions

All are local for cached and live queries. Same-field repeated flags use OR;
different flags use AND. Strings match whole values, case sensitively, without
trimming, wildcard expansion or comma splitting. For the explicitly named
string arrays, match an exact member. Null/missing never match, empty or
whitespace-only input rejects. Unknown row fields remain raw.

| Capability | Flags → raw fields | Match kind |
| --- | --- | --- |
| same-bank-transfer | --bank → debitInstId; --status → ruleStatus | scalar |
| cost-reduction | --name → ruleName; --business-line → businessCategory; --currency → creditCurrency; --market → creditorMarket; --status → status | scalar |
| cost-reduction | --entity → legalEntity; --obo → needObo; --fvt → needFvt | string-array member |
| retry | --name → ruleName; --status → status; --communication-mode → communicationMode; --integration-mode → integrationMode | scalar |
| retry | --entity → bizLegalEntityList; --business-line → businessCategoryList; --bank → debtorInstList; --currency → creditorCurrencyList; --region → creditorCountryList; --bank-account → debtorAccountNoList; --clearing-network → clearingNetworkList | string-array member |
| bank-switch | --source-account → switchNodeCode | scalar on source node |
| bank-switch | --source-network → switchClearingNetwork; --status → status; --target-account → targetNodeCode; --target-network → clearingNetworkList | correlated nested match below |

These decisions include all candidate dimensions from #55–#58, plus the native
retry name selector. Local semantics are deliberate; no equivalence to backend
substring/wildcard matching or closed enum vocabulary is claimed. OBO/FVT are
raw string-array values, not booleans. Both mode fields were observed as strings
or null. Timestamp units and ratio scaling remain unverified.

## Bank-switch grain and correlation

46 source nodes contained 90 requirements, 90 rules and 91 target nodes.
Every requirement's switchBankAccount equalled its parent switchNodeCode.
Preserve fundNavigationNodeSwitchRequirementVOList, switchRuleVOList, ratioList
and targetNodeInfoList as nested raw arrays. Do not flatten or deduplicate child
versions. A source row matches nested filters only if ONE requirement and ONE
rule satisfy the source-network/status predicates, and (when target predicates
exist) ONE targetNodeInfo entry satisfies BOTH target-account and target-network.
Multiple ratio entries remain alternatives within that rule. Return the entire
matching source row, including nonmatching children; filtering selects nodes,
not an edited subset of their rule history. With no nested predicates, nodes
with empty child arrays remain visible.

## Identity, source and scope

Same-bank IDs remain JSON integers, sorted numerically; boolean, float and
string IDs reject. The other three preserve nonempty string IDs and lexical
ordering. No identity is derived from a name or assumed account/network join.
Cost-reduction rows are group summaries keyed by groupId, not verified complete
historical rule versions. Preserve all versions the endpoint actually returns.

Names are payment.rules.<slug_with_underscores>.list, scope all, source
sources.payment_rules_<slug_with_underscores> kind=cdp. Each has an independent
:all:cdp snapshot. First slice is list/refresh/help/describe only, no get, joins
or mutation commands. The shared display options and 72h TTL remain unchanged.
