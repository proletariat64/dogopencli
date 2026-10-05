# Explicit account-capacity list (#111)

Observed: 2026-10-05
Scope: general
Status: snapshot

Implementation contract; independent production public CLI UAT passed.

[#111](https://github.com/proletariat64/dogopencli/issues/111) records successful
native capacity objects for three explicitly selected aliases. The saved UI
caller and API constants establish one GET inquiry at
`iliquidity.alipay.com/api/fund/capacity/queryFundCapacityByAliasName.json` with
`aliasName` as its only business request field. Fresh native inquiry evidence
and previously saved static UI evidence are separate; neither proves public
CLI production acceptance of this implementation.

## Request, identity and bounded completeness

`liquidity risk account-capacity list --account SYN-A --account SYN-B` reads the
exact declared account set offline by default. `refresh liquidity risk
account-capacity` accepts the same required repeated scope option. The client
requires 1–10 distinct nonempty aliases, sorts the set deterministically and
issues one inquiry for each alias. The 10-account limit is a client fan-out
budget, not a backend capacity limit. Display `--all` cannot enumerate accounts.
No dates, tenant field, pagination, account discovery or guessed account aliases
are sent. Authentication material stays inside the existing shared browser
transport and outside request construction, cache, output and logs.

Every response requires top-level boolean `success=true`, a nonempty `data`
object, and nonempty string `data.aliasName` equal to the requested alias.
Native aliasName identifies the object within the application's tenant/origin;
currency and valueTime are separate attributes. No pseudo-ID is generated.
Missing data, mismatched alias, business refusal, authentication, permission,
transport failure or exhausted request budget abort the entire candidate and
preserve the old capture. Earlier successful accounts cannot become a synthetic
empty or partial full-set result. This leaf has no skip-failed-account policy.

Complete means exactly one validated native object per requested alias.
`requested_count` and `resolved_count` are retained acquisition facts for this
client-declared set; `reported_total` remains null because the native response
provides no global account total. Display slicing never changes these counts.
No deduplication or invented server total establishes complete coverage.

## Native runtime fields

The public runtime projection retains present fields `aliasName`, `currency`,
`accountAvailableBalance`, `availableIod`, `availableResource`,
`cashPoolSupportAvailableResource`, `outFlowCapacity`, `totalIod`, `usedIod`, and
`valueTime`. It preserves native values, string precision, null, empty string,
zero, negative and unknown values. There is no arithmetic, balance/IOD relation,
currency consistency or business correctness audit, scaling or field fallback.
Only the required native identity and request echo impose a business-field type.

The saved UI labels accountAvailableBalance as Avl Bal, availableIod as Avl IOD,
and availableResource as Outflow Capacity. outFlowCapacity and
cashPoolSupportAvailableResource remain independent native fields with unknown
business definitions. valueTime remains the original source-time string with
unknown timezone; it is never substituted for fetched_at capture time or a
query date. Unknown source observation age remains visible in metadata.

## Storage and verification boundary

`account-capacity-runtimes-v1` isolates exact sorted alias-set history captures
from cash accounts, other lists and native details. A single-alias capture
cannot satisfy a multi-alias query. Refresh atomically publishes only a complete
validated candidate; live writes no database and provides no offline fallback.
Existing history retention and ADR 0019 result handling apply. If retention
leaves a gap, default reads expose truthful warnings and strict reads refuse
incomplete coverage; acquisition hard failures never publish half a candidate.

Public CLI → fake CDP → temporary real SQLite acceptance covers three-account
fan-out, native field fidelity, exact sorted scope, refresh/offline same-capture
quality equality, live byte hash isolation, invalid and oversized scopes,
transport allowlist rejection, hard failures on the second alias, preservation
of the old capture, schema and scope isolation, history captures, display
slicing, help/describe/snapshot, source-time interpretation and special query
characters. All fixtures and identifiers are invented.

Focused pytest, lint, format, document guard, independent review, production UAT
and remote CI are distinct gates. Independent production public CLI UAT passed
for three explicit native aliases, all ten projected fields and echo, strict
complete refresh, disconnected reads of that same capture, and live SQLite/WAL
byte hash isolation. See the [integrated acceptance record](2026-10-05-liquidity-batch-f-acceptance.md).
No production records,
account identifiers, tokens or browser profiles are stored in this report.
