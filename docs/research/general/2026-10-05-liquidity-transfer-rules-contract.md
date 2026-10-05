# Transfer-rule configuration list contract (#103)

Observed: 2026-10-05
Scope: general
Status: snapshot

Evidence scope: Fixed Liquidity tenant and native default debit/credit entity scope. Implementation and synthetic CLI acceptance; independent production CLI UAT pending. Times are Asia/Shanghai.

Authoritative specification: [issue #103](https://github.com/proletariat64/dogopencli/issues/103), under [#72](https://github.com/proletariat64/dogopencli/issues/72). The issue records the new native ruleCount evidence; historical small-page overlap remains a historical limitation.

The existing settings leaf `liquidity rules transfer list` executes one allowlisted GET to `iliquidity.alipay.com/transferRuleQuery.json`. Outer query keys are `tntInstId` and JSON-string `transferRuleQueryRequest`; the VO fixes the same application tenant, `rowStart=0`, `pageSize=5000`, `debitEntity=[]`, and `creditEntity=[]`. There are no native filtering, page-width, arbitrary payload, action, or offset-fallback options.

Both `resultFlag=true` and `result.success=true` are required. Records are objects in `result.transferRuleVOS`; `result.ruleCount` is a mandatory nonnegative integer. The native nonempty string `ruleId` identifies each record. ruleNo, version, edit/process references cannot replace identity. Raw identity conflicts fail before projection. Duplicate arrivals remain completeness evidence, so complete requires raw arrivals = unique identities = ruleCount. A valid response exceeding this coverage remains incomplete under ADR 0019: default refresh publishes safe rows with a persistent warning; strict mode rejects without replacing the old capture.

The summary preserves the specification's configuration fields, native values, precision, null, blank, zero, states and unknown units/times. It does not perform amount, currency, effective-period or scheduling calculations. Nested conditions retain known configuration members and calendar/grade nesting, excluding personnel, contacts, notification recipients, URLs, free text and arbitrary parameter maps. Full action payloads, permissions, account numbers and runtime next-trigger fields are omitted. Missing optional fields remain missing. The summary does not claim to be a complete detail document.

Settings capture uses the versioned `transfer-rules-v1` namespace and existing retention policy. Explicit refresh publishes atomically; offline/help/describe/snapshot never access Chrome, and live never writes cache. Genuine existing get keeps its independent identity and detail namespace.

Synthetic tests exercise the public CLI through fake CDP with temporary real SQLite. They cover exact single GET/VO, projection, raw conflicts, identity/tenant/envelope/total failures, authentication and permission failures, complete empty success, safe partial and strict rejection, unchanged cache on hard failure/live, offline capture consistency and independent get. Examples use invented SYN identifiers only. Native production records, credentials and identifiers are excluded from Git and review materials.

Production acceptance must separately compare full native identity/count/projection evidence with public CLI refresh, compare offline to that same capture, verify live database immutability and preserve a seeded genuine detail cache. A native probe or passing local test is not production CLI UAT.
