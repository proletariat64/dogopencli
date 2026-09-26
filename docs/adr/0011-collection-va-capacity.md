# Collection VA capacity monitoring

Status: accepted for implementation — issues #36–#38. Verified contract:
[collection VA capacity inquiry contract](../research/general/2026-09-26-collection-va-capacity-contract.md).

Collection VA capacity uses `collection va capacity list` and
`refresh collection va capacity`. It models the VA Capacity Monitoring menu:
one row is one VA rule's capacity/warning projection. Capacity rows are
distinct from VA rules (ADR 0009), bank-account VA rules, VA pools and
individual VA accounts; the snapshot never substitutes for any of them.

The sole production source is `sources.collection_va_capacity.kind=cdp`,
cached in the isolated namespace `collection.va.capacity.list:capacity:cdp`
through the shared restricted transport. The only registered request is POST
`https://ifundboss-api.alipay.com/ivostro/api/warningUseCount/pageList.json`
with a JSON body of `pageNo` (one-based, varying) and `pageSize` (fixed
1000). Backend business filters stay unexposed: the CLI filters locally.

Decisions that differ from the VA rule acquisition:

- **Multi-page acquisition is verified here.** Refresh pages from page 1 at
  pageSize 1000 until the first short page. Interim page `totalCount` values
  are a backend running estimate (observed climbing 31, 61, 91 … at pageSize
  10) and are never trusted mid-sweep; only the final converged total, the
  collected row count and unique nonempty string `ruleId` identities validate
  completeness. A changed total mid-sweep, a duplicate `ruleId`, drifted
  content for a repeated `ruleId`, or any malformed page fails the
  acquisition and preserves the previous snapshot.
- **Row identity is `ruleId`.** It was unique and nonempty across three
  identical full sweeps (532 rows each on 2026-09-26). The surrogate `id`,
  `bankAccountVaId` and `accountNo` are not unique and are never used as the
  identity. Uniqueness remains a checked acquisition invariant, not an
  assumed backend guarantee; the observed count is never an invariant.
- **Two local filters only.** `--va-rule-id` matches the `ruleId` row field;
  `--bank-va-rule-id` matches the `bankAccountVaId` row field. Both are
  exact, case-sensitive, literal (`*` is not a wildcard), repeatable (OR)
  and composed across fields (AND); empty or whitespace-only values are
  rejected and missing/null fields never match. The UI warning state is
  deliberately not exposed: rows carry no warning-state field, no tested
  counter predicate reproduces the server classification, and consecutive
  server queries disagree on it. All other UI filters are deferred.

Envelope edge cases frozen by the contract: a filtered query with no matching
rows returns a failure envelope (`success=false`, errorCode
`IPAY_RS_330090381`), never an empty success; local CLI filtering never
reaches it. An unfiltered genuinely empty scope was not observable in
production; a successful `totalCount=0` response with an empty
`resultDataList` publishes an empty snapshot, and every `success=false`
response fails the acquisition. The raw failure `msg` embeds a per-request
trace id and stays out of outputs, caches and logs.

Capacity and warning counters are live backend values preserved raw:
`canUseDays` is the backend's remaining-days estimate and is never
recomputed, `availableCount` is never derived by subtraction, and the
averaging/peak periods of `averageApplyCount`/`totalMaxUseCount` remain
unverified. Because counters drift between refreshes, help and describe state
the time sensitivity and point to `refresh`/`--live`; the shared 72-hour
default TTL is unchanged. Refresh accepts no business selector; bare
`refresh collection va` keeps executing the VA rule refresh.
