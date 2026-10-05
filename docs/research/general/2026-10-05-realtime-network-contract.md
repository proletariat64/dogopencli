# Realtime network configuration list (#104)

Observed: 2026-10-05
Scope: general
Status: snapshot

The authorized Liquidity PortfolioMgmt application's native default network
configuration range is implemented for this list only. Independent production
public CLI UAT passed; local Kimi review remains blocked by automatic approval review of external
source/spec transfer. No Kimi confidence is claimed.

## Native contract and evidence boundary

[#104](https://github.com/proletariat64/dogopencli/issues/104) records fresh native
1000/5000-width inquiries returning 204 arrivals, 204 unique nonempty string IDs,
and native total 204 at each width, with identical ordered arrays. Historical
small-page offset overlap remains recorded in the
[October 1 probe report](2026-10-01-liquidity-live-probes.md). The fresh probe is
contract evidence, not production acceptance of the new public CLI.

The only request is JSON POST to `iliquidity.alipay.com`, endpoint
`/api/ai/decision/network/queryDecisionNetwork.json`, with exactly
`{"rowStart": 0, "pageSize": 5000}`. No tenant field, search filter, UI pagination
state, alternate source, or additional page request is added. The top-level
`success` must be boolean true, `data.data` an object array, and
`data.totalCount` a nonnegative integer. Complete means arrivals, unique native
IDs, and reported total all agree. A future range exceeding the fixed response
capacity has no proven offset acquisition mechanism.

Native `id` identifies the network within the authorized application scope.
`routeId` is an independent reference, `version` a native configuration version.
No tenant echo is invented. Same-ID conflicting raw content fails before public
projection, including conflicts confined to excluded fields. Exact duplicates
remain quality evidence and cannot establish completeness.

## Settings projection and interpretation

The public allowlist is `id`, `routeId`, `version`, `scene`, `fundAction`,
`debitAliasName`, `debitBankId`, `debitCurrency`, `debitLegalEntityCode`,
`creditAliasName`, `creditBankId`, `creditCurrency`, `creditLegalEntityCode`,
`clearingNetworkName`, `clearingNetworkType`, `networkStatus`, `runStatus`,
`processStatus`, `operationCalendar`, `operationDateType`, `operationTime`,
`operationTool`, `singlePaymentLimit`, `timeZone`, `gmtCreate`, and `gmtModified`.
Only present fields are emitted, with native values and precision. Null, empty
string, zero, and unknown values remain distinct; absent values remain absent.
Only native identity and reading-protocol checks impose required types. Optional
configuration types, timestamp units, and timezone semantics are not inferred.

Dynamic `avgEffectiveness`, `successRate`, `effectiveness`, `effectivenessLevel`,
and `lastOperationTime` are excluded, as are creator/updater, free text, workflow
URLs and action payloads. No success-rate calculation or derived runtime summary
is provided. Native statuses do not establish transfer success, actual execution,
or current availability. `gmtCreate`/`gmtModified` are source configuration times,
`fetched_at` is capture time; none is a guaranteed business observation time.

## Cache and result policy

The settings snapshot has its own `realtime-network-settings-v1` namespace.
Offline is the default; refresh atomically publishes the captured list; live
never writes or falls back to the database. ADR 0019 preserves valid safe partial
rows by default with continuing warnings; `--require-complete` refuses partial
and prevents publication. Hard identity/protocol/auth/permission/transport
failures preserve the old capture. Existing retention applies unchanged.

Realtime network get, generic routes, realtime rules and all other network
leaves retain separate contracts/caches. Monitoring rules remain HOLD. This
branch adds one list: 83 supported / 48 unsupported / 131 total, with no version
bump. Other independently developed specs must reconcile catalog counts when
merged serially.

## Verification

Public CLI → fake CDP → temporary real SQLite tests cover exact request and
single-response behavior; all allowlisted fields; excluded private/dynamic
fields; separate network/route identity; raw duplicate conflicts; arbitrary
complete count and synthetic empty success; malformed total/envelope/container;
partial default/strict policy and hard-failure cache preservation; disconnected
offline capture equality; live byte-identical database; invalid request arguments;
help/describe/snapshot and unchanged unsupported guards. Synthetic identifiers
and configuration values are invented and do not prove the native contract.

Production public CLI UAT must run independently and serially before readiness:
nonempty total/ID alignment, all projected native values, refresh/offline capture
identity, and live database isolation. No production records, tokens, profiles,
or identifiers are stored in this report or test fixtures.

## Independent production CLI UAT

The root coordinator ran the implemented public CLI through the dedicated
healthy CDP 9223 session, serially on 2026-10-05. The settings list returned
204 arrivals, 204 unique nonempty native IDs, and native total 204, complete.
Exactly one JSON POST carried the two fixed fields. All 5,304 projected
native values (204 records × 26 allowlisted fields) were compared with their
source values and matched, with private/dynamic fields excluded. The saved
capture was read offline with browser access disabled; the same scope,
capture time, acquisition facts and configuration records matched. Live
returned the same complete range and left the SQLite byte hash unchanged.

The private summary is `/tmp/dogopencli-uat-104-summary.json`; only aggregate
counts and verdicts are recorded here. This result establishes this list's
current native scope, not future pagination beyond the fixed response capacity,
detail inquiry support, execution guarantees or dynamic status observation time.
Local Kimi review remains blocked as described above; remote checks remain
separate acceptance gates.

## Review fix and repeated production UAT

The review found that the endpoint allowlist accepted changed or missing
rowStart/pageSize values. The leaf template now pins exactly rowStart=0 and
pageSize=5000 through existing shared fixed-body validation. Seven actual
CdpQueryTransport regression cases reject missing/changed pagination and added
tenant fields before target creation, expression evaluation or fetch. The
public describe evidence date now correctly reports 2026-10-05.

The root coordinator repeated independent production CLI UAT after these fixes:
204 native arrivals = 204 unique IDs = reported total; all 5,304 projected values
matched, with exactly one fixed request. Disconnected reads matched the capture
fetched at 2026-10-05T10:41:47.647552+00:00; live SQLite byte hashes stayed unchanged.
Focused CLI/capability tests passed 50 cases; the evidence-date assertion passed
separately. Ruff, formatting, doc guard and whitespace checks passed. Independent
Standards/Spec re-review closed the request-boundary and navigation findings.
Kimi remains blocked by automatic approval review of external source/spec transfer.
