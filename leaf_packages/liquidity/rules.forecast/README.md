# Cash forecast rule configurations

`liquidity.rules.forecast` reads existing bank cash forecast rule configuration,
not forecast observations, forecast accuracy or an execution task. It exposes only
`dogopencli liquidity list rules.forecast`; refresh, prune and describe use the host
lifecycle. No getter, user scope, entity expansion or date filter is registered.

The inquiry is GET `/bankCashForecastRuleQuery.json` on `iliquidity.alipay.com`.
The top-level `tntInstId` is `GUAPW3SG`. `bankCashForecastRuleQueryVO` is a JSON
string containing that tenant, fixed `instId=["Z21"]`, zero-based `rowStart` and
`pageSize=10`. Collection reads every native offset independently of display limit.
Boolean `resultFlag` establishes envelope success; records are `result.dataValue`
and the nonnegative integer total is `result.count`. `ruleId` is the native identity.
All native fields and JSON types are preserved, including null, empty strings,
zero, decimal precision and timestamp text. `ruleName`, `ruleType`, `accountNo`,
`currency` and `ruleStatus` remain source fields rather than projected columns.

The manifest selects the host List SDK with offset paging, width 10 and native
`ruleId`. The leaf owns the fixed Z21 request and native parser. Changed totals,
malformed identities and oversized pages fail collection. Duplicate/conflicting
rows and short or empty interior pages retain incomplete evidence. Conflicts use
the last arrival without claiming it is newest. Strict queries and refresh reject
incomplete acquisitions.
Live does not publish cache. A qualified nonempty refresh replaces only this
leaf's cache. Errors, empty results and strict rejection preserve the last cache.
Offline reads make no business request. Dataset relation: `liquidity_rules_forecast`.

The business reference is release `v0.4.3`, resolved commit
`a7e5c5ead675487646eb9a53d73ec9e0aeb944f9`, `RULES_FORECAST` in
`src/dogopencli/plugins/liquidity/leaves.py`. Reference code stays outside this
package and is never imported. The knowledge-base document “匡算介绍”
(2023-04-17, 245795715), sections 1–2 and 9, explains forecast models and rule-time
configuration; it does not establish current API availability or permission.
[Issue #257](https://github.com/proletariat64/dogopencli/issues/257) records dated
local production qualification and isolated historical comparison. cn.ant hosts
HTTP artifacts only; it does not execute this inquiry.
Controlled CDP tests establish request, parser, paging and lifecycle behavior only.

Install this directory or pack its root contents as one ZIP with the existing
plugin-helper. Install using `dogopencli plugins install <package>` and uninstall
using `dogopencli plugins uninstall liquidity.rules.forecast`. This is a portable
source package and is not added to the four bundled pilots.
