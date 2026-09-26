# Collection VA capacity inquiry contract verification

Observed: 2026-09-26
Scope: general
Status: snapshot

Verifies the native inquiry contract of the **VA Capacity Monitoring** menu for
[#36](https://github.com/proletariat64/dogopencli/issues/36), closing
[#37](https://github.com/proletariat64/dogopencli/issues/37). All findings are
from the production account visible on 2026-09-26; counts are snapshots, not
invariants. No production row values, account or VA identifiers, tokens, raw
responses or HAR files were persisted; production rows were held in memory
only for counting, typing, deduplication and identity comparison.

## Method and boundaries

- Read `~/dev/di/docs/spec/browser-cdp-v1.1.md` and this repository's browser
  implementation first. Work ran on the dedicated headless Chrome at CDP
  **9222** with the dedicated profile; `dogopencli auth check` returned
  `authenticated: true, healthy: true` before and after the session. Ports
  9330–9340 were not touched. No SSO interaction was needed.
- One temporary CDP target opened the embedded page
  `https://ifundbossportal.alipay.com/voucher/VACapacityMonitoring`
  (outer menu entry
  `collectionProductManagement/networkConstruction/VACapacityMonitoring`).
- The native **Search** button was clicked under `Network` observation; only
  the observed inquiry action was replayed. No create/edit/delete,
  allocation, import, warning-configuration or export action was touched. The
  separate **Spontaneous account balance inquiry** page and its
  `/api/fundIn/selfIssueIbanVACapacity/list` observation were not used.
- UI filter mapping was verified by entering unique non-matching sentinel
  values and observing which request keys they populate; responses were
  empty. The warning-state options were read from the opened dropdown.

## Verified inquiry contract

Native Search issues:

```text
POST https://ifundboss-api.alipay.com/ivostro/api/warningUseCount/pageList.json?ctoken=<auth>
Content-Type: application/json

{"pageNo": 1, "pageSize": 10}
```

- `ctoken` is the only authentication parameter; it is carried from the
  browser cookie and never enters configuration, cache, output or logs.
- Native default body is exactly `{"pageNo": 1, "pageSize": 10}`.
- Observed optional business request fields, mapped from UI labels by
  sentinel probes (request key = form control id):

  | UI label | Request key | Observed value type |
  | --- | --- | --- |
  | Bank Account VA Rule ID | `bankVaRuleId` | string |
  | Account No. | `accountNo` | string |
  | Bank Account Entity Code | `bankAccountingEntityCode` | string |
  | Legal entity code | `serviceAccountingEntityCode` | string |
  | VA Rule ID | `ruleId` | string |
  | Scene code | `sceneCodes` | multi-select; request encoding not observed |
  | currency | `currency` | string |
  | Memo | `memo` | string |
  | Warning state | `waringState` (sic) | string, single select `Y` / `N` |

## Response envelope

Success responses are HTTP 200 with `success=true`, empty-string
`errorCode`/`msg`/`resultStatus`/`resultCode`/`resultDescription`, `data=null`,
`errorContext` an object with `errorStack`/`thirdPartyError` keys, a
`sofaTracerId` string, echoed `pageNo`/`pageSize`, `totalCount`, and
`resultDataList` rows.

**A filtered query with no matching rows is a failure envelope, not an empty
success**: HTTP 200, `success=false`, `errorCode="IPAY_RS_330090381"`,
`errorDescription="invoke ivostro failed"`, `msg` containing a per-request
trace id, `pageNo=0`, `pageSize=0`, `totalCount=0`, `resultDataList=[]`.
The same shape appears for an invalid `waringState` value. Consequences:

- `success=false` does not imply authentication or permission failure; an
  empty filtered result uses the same envelope.
- Raw `msg` contains a trace id and must not enter persisted artifacts.
- A genuine authentication expiry, access denial or malformed-response branch
  could not be induced safely and remains a synthetic SIT requirement.

## Row schema

Every observed row (full 532-row scope, three sweeps) carries exactly the same
22 keys; no null values were observed in any field:

| Field | Observed type | Reading boundary |
| --- | --- | --- |
| `id` | string | row surrogate; **not unique** (514 distinct / 532) |
| `ruleId` | string (digits) | VA rule identifier; unique across the full observed scope |
| `bankAccountVaId` | string (digits) | bank-account VA rule identifier; **not unique** (368 distinct / 532) |
| `accountNo` | string | account number; not unique (357 distinct) |
| `bankAccountingEntityCode` | string | bank-account entity code |
| `serviceAccountingEntityCode` | string | legal entity code |
| `financialInst` | string | financial institution |
| `currency` | string (3 letters) | currency code |
| `sceneCode` | string (3 chars) | scene code |
| `memo` | string, may be empty | free text; values not recorded |
| `totalCount` | int | per-row capacity counter; shares its name with the envelope total — keep distinct |
| `usedCount`, `availableCount`, `canAllocateCount` | int | capacity counters; units are VA counts |
| `lastDayUseCount`, `averageApplyCount`, `totalMaxUseCount` | int | yesterday / average / peak application counters; averaging and peak periods unverified |
| `warningCount`, `warningDays` | int | warning counters; neither equals the warning state (see below) |
| `canUseDays` | int | backend remaining-days estimate; do not recompute or derive |
| `gmtCreate`, `gmtModified` | int | timestamps; unit/timezone not asserted |

Counters are live values; identical queries minutes apart can legitimately
return changed rows. `availableCount + usedCount == totalCount` and similar
arithmetic were **not** asserted; no derived metric is computed.

## Identity and grain

One row represents one VA rule capacity/warning projection within the
menu's scope. Across the full 532-row sweep (three consecutive runs, identical
ordered sets):

- `ruleId` is unique (532/532) and always a nonempty string.
- `id`, `bankAccountVaId`, `accountNo`, and `(accountNo, currency, sceneCode)`
  are not unique.
- `(bankAccountVaId, ruleId)` is also unique, but `ruleId` alone suffices in
  every observed sweep.

Stable identity is `ruleId`, with acquisition rejecting duplicate or empty
identities rather than silently discarding rows. This is an observed property
of the current scope, not a backend uniqueness guarantee; validation must keep
rejecting duplicates if the scope changes.

## Pagination and complete scope

- Pagination is one-based. `pageNo=0`, `pageNo=-1`, `pageSize=0` and a string
  `pageNo` are silently clamped to the defaults (success, first page);
  unknown extra body fields are ignored. `pageSize` values 10, 20, 50, 100,
  500, 1000 and 100000 are all honored.
- **Interim `totalCount` is a running estimate, not the scope size.** With
  `pageSize=10` it reads 31, 61, 91, 121, 151 … converging only at the final
  page; with `pageSize=100`, page 1 reports 299 and page 2 reports the
  converged 532. A mid-sweep `totalCount` must never be used for
  completeness.
- A complete small-page sweep (pageSize=10, pages 1–54 until the first short
  page) collected 532 rows covering 531 of the 532 large-page identities plus
  exactly one duplicate — live counter changes re-order rows between page
  queries, so sequential paging can drift by individual rows.
- Beyond-end pages are clean: `pageNo=60/999, pageSize=10` and
  `pageNo=2, pageSize=1000` return `success=true`, zero rows, echoed
  pagination, and the converged `totalCount`.
- Three consecutive `pageSize=1000` single-page sweeps returned identical,
  fully ordered 532-row sets with unique `ruleId`s.

**Acquisition rule supported by this evidence**: page with `pageSize=1000`
from page 1 until the first short page (`rows < pageSize`); the scope is
complete iff every page succeeded, the final converged `totalCount` equals
the collected row count, and all `ruleId`s are unique and nonempty. Any
duplicate, truncation, inconsistent final total or failed page fails the
acquisition and preserves the prior snapshot; a bounded whole-acquisition
retry absorbs single-row drift. Whether a server-side maximum `pageSize`
exists is unverified (the scope is below every probed size); the
rows-equals-final-total check is the truncation guard.

## Filter semantics (server-side, for the record)

Verified by replay against the live scope; counts compared in memory:

- `ruleId` matches row field `ruleId` exactly (filtering by a real value
  returned exactly its row). Prefixes, leading or embedded `*` and empty or
  whitespace values match nothing (empty results surface as the failure
  envelope above). Trailing `*` characters are stripped before an exact
  match (`v+"*"` and `v+"**"` return `v`'s row; `v[:-1]+"*"` returns
  nothing). `*` is not a wildcard.
- `bankVaRuleId` matches row field `bankAccountVaId` exactly (a real value
  returned exactly the rows carrying it; the surrogate `id` and `ruleId`
  fields do not match).
- `currency` matching is case-insensitive server-side (upper- and lower-case
  queries returned the same 83 rows). `ruleId`/`bankAccountVaId` values are
  digit-only in this scope, so case is not observable there.
- `waringState` accepts `Y`/`N`; other values yield the failure envelope. The
  classification is volatile and not derivable from row fields: Y=190 and
  N=343 rows with a 2-row overlap and a non-covering union across consecutive
  queries, and no tested row-field predicate (warningCount/warningDays
  thresholds, zero counters, used≥total, canUseDays≤30, …) separates Y from
  N. Rows carry no warning-state field.

## CLI filter decisions

Local exact matching over the acquired snapshot, per #36 (same-field
repetition OR, cross-field AND, case-significant, `*` literal, empty or
whitespace-only values rejected, no normalization):

| Candidate | Decision | Frozen mapping |
| --- | --- | --- |
| `--bank-va-rule-id` | **include** | local exact match on row field `bankAccountVaId` (string; null/missing never match) |
| `--va-rule-id` | **include** | local exact match on row field `ruleId` (string; null/missing never match) |
| `--warning-state` | **defer** | no row field and no verified predicate; server classification is volatile and cannot be reproduced locally |

All other UI filters (`accountNo`, entity codes, `sceneCodes`, `currency`,
`memo`) are deferred from this slice.

## Source and cache identity

- New source: `[sources.collection_va_capacity] kind = "cdp"`, reusing the
  shared restricted transport and the verified endpoint above.
- New cache namespace: `collection.va.capacity.list`, isolated from the
  existing VA rule, SLA, cost and payment snapshots.
- The existing 72-hour default TTL applies unchanged; capacity counters are
  time-sensitive, so help and describe must surface snapshot age and point to
  explicit refresh or `--live`.

## Remaining evidence limits

- Authentication expiry, access denial and malformed-response branches were
  not safely inducible; they remain synthetic SIT requirements.
- A genuinely empty unfiltered scope could not be produced (inquiry-only;
  current scope is 532 rows). Verified adjacent behavior: filtered no-match
  returns the failure envelope, and beyond-end pages return a clean
  zero-row success with the full total. Refresh may publish an empty
  snapshot only on an unfiltered `success=true` + `totalCount=0` +
  empty-list response; every `success=false` is a failed acquisition.
- `sceneCodes` request encoding was not observed (deferred filter).
- Null field values were not observed in any row; parsers must still
  preserve missing/null/zero/empty distinctions rather than assuming the
  observed all-present shape.
- Whether `pageSize` has a server maximum is unknown; completeness is guarded
  by the rows-equals-final-total and unique-identity checks, not by a chosen
  page size.
- No historical row count (532 today) is an invariant.
