# Forecast results: reported total exceeds collected unique records

Observed: 2026-10-02
Scope: general
Status: snapshot

## Summary and evidence boundary

The dated full-scope forecast-results inquiry reports **7504 records**, but
acquisition at the unchanged native contract width **5000** collects only
**7502 unique record IDs**. The deficit is **2**. This is a backend
count/list-convergence defect requiring investigation; its root cause is not
established.

The original 7504/7502 observation comes from audited private CLI evidence in
`tmp/spec76-cli-uat-20261002T022914Z/`. A fresh inquiry-only compatibility UAT after
renewed, independently verified Liquidity SSO is now confirmed in
`tmp/spec76-cli-uat-20261002T144041Z/`: ordinary full live received **20135 rows**
but only **20129 unique IDs**, with six cross-page repetitions; subsequent strict
live and refresh observed changing totals and failed closed. These are distinct
dated acquisitions, not a count invariant or proof of a common cause. The
source backend remains unfixed; no tracker issue/comment was published.

Contract source: [specification #76](https://github.com/proletariat64/dogopencli/issues/76)
and the [implementation/UAT chronology](2026-10-02-liquidity-spec76-implementation-uat.md).
The implementation baseline is `a015620`. The recorded final core apex review
is `657bec2cdb9b`, confidence **5/5**, `comments=[]`; that review is not fresh
production UAT or evidence that the backend defect is fixed. Historical
specification/probe baselines and their observations remain unchanged.

## Expected versus actual

Native inquiry: `GET /bankCashForecastRecordQuery.json` on Liquidity.
The request uses `tntInstId` and JSON-string
`bankCashForecastRecordQueryVo`; records are in `$.result.dataValue`,
reported total in `$.result.count`, identity in `record.id`.

| Check | Expected for a stable, identical scope | Prior observed result |
| --- | --- | --- |
| Width and offset stride | Keep `pageSize=5000`; `rowStart=0`, then `5000` | Acquisition uses the declared 5000-row width |
| Completeness | Reported total equals the complete unique-record set | Reported 7504; collected 7502 unique IDs |
| Refresh | Publish only a complete validated capture | `INCOMPLETE_RESULT`, exit 1, `meta.complete=false`, `meta.published=false` |
| Strict live | Reject an incomplete scope rather than return it as complete | `INCOMPLETE_RESULT`, exit 1, `data=null` |

The saved refresh envelope preserves `reported_total=7504` and
`collected_total=7502`. Do not silently normalize the source count to 7502,
invent the missing records, or mistake successful business responses for
complete acquisition. These aggregate observations alone do **not** establish
real-page arrival counts, duplicate locations, or the backend cause.

## Inquiry-only reproduction for an authorized backend investigator

1. Use the existing authorized Liquidity session and native forecast-results
   inquiry. Recover the original full scope from the private evidence; retain
   the same tenant, date/creation-time bounds and native amount filters. Do not
   substitute an account-filtered scope or include its private values in a
   public report.
2. Replay only the verified list inquiry, preserving `pageSize=5000` and
   `rowStart=0/5000`, continuing 10000/15000/20000 when the reported count requires it. Offsets advance by requested width, not by returned row
   count. Do not shrink pages, broaden filters, issue per-row accuracy/balance
   requests, or execute any mutation/export action.
3. Privately reconcile each page's reported count, arrival count, unique
   `record.id` count and repeated/conflicting identities. Compare repeated
   acquisitions of the same stable scope. Keep raw requests, arguments,
   records and authentication material private; publish aggregate findings only.
4. Separately verify ordinary live, strict live and refresh behavior without
   interpreting partial data as success. With an existing complete capture,
   confirm failed refresh leaves it unchanged; without one, offline must remain
   `CACHE_MISS`, not a fabricated empty complete result.

These are reproduction instructions, not claims of newly executed UI or CLI
checks. Later data changes may change totals; 7504/7502 identifies this dated
snapshot, not an invariant for future queries.

## Uncertainty and candidate backend checks

Check whether count and list use identical tenant/date/time/amount filters,
joins and deletion/visibility rules; whether pagination has a stable unique
ordering and a consistent read snapshot; and whether list assembly drops rows
or multiplies identities. Compare the two native pages privately to distinguish
count overstatement, omission, overlap, concurrent changes or another cause.
A count/list deficit does not independently prove which mechanism occurred.

The focused integration regression constructs **synthetic overlap** to produce
7504 arrivals but 7502 unique IDs. It proves client handling of those counts,
**not** overlap or those arrival counts in the real backend. The earlier
4419/4419 single-page forecast probe is a different dated scope/observation and
cannot establish completeness of this later two-page scope.

## Supported client compatibility and rollback

The user authorizes forecast results to use the same truthful incomplete-result
compatibility as cash accounts. Backend repair remains required; compatibility
is not a claim of complete results or an activation decision.

- Ordinary live can return the available rows, with `INCOMPLETE_RESULT`,
  structured warnings, stderr warning, exit **1**, `meta.complete=false`, and
  separate unchanged source/collected totals. Display windows or filters do
  not redefine source completeness. Live never updates the cache.
- `--require-complete` remains strict: incomplete acquisition returns the error
  and no dataset (`data=null`), exit **1**.
- Incomplete refresh can return available rows for diagnosis but must set
  `meta.complete=false` and `meta.published=false`, exit **1**. It must not
  replace, evict or advance the previous complete cache. Offline can continue
  reading that prior complete capture under its existing coverage/freshness rules.
- Keep native width/offset behavior and identity validation. No smaller-page
  fallback, silent count correction or incomplete cache publication is authorized.

Source evidence: [`collect.py`](../../../src/dogopencli/plugins/liquidity/collect.py)
(`collect_liquidity_scope`, `_collect_offset`, `_merge_page`),
[`query.py`](../../../src/dogopencli/plugins/liquidity/query.py)
(`_run_list_live`), and
[`refresh.py`](../../../src/dogopencli/plugins/liquidity/refresh.py)
(`run_refresh_list`). The
[integration SIT](../../../tests/integration/test_liquidity_spec76_cli_sit.py)
`test_forecast_7504_7502_uses_accounts_partial_contract_and_preserves_cache`
checks width 5000, offsets 0/5000, ordinary/strict live, incomplete refresh,
byte-identical prior-cache protection and disconnected offline reading. These
are source/synthetic proofs. Fresh production compatibility confirmation is
recorded below; complete source-data convergence is still not proven.

## Fresh production compatibility UAT

Renewed SSO was verified headless at CDP 9222 against Liquidity PortfolioMgmt,
independently of Payment. Actual CLI calls retained native width 5000 and all
original full-scope filters. Counts-only instrumentation observes existing
request/parser calls without changing requests or exposing record IDs.

| Full ordinary live rowStart | Received | Unique within page | Overlap with earlier pages | Reported total |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 5000 | 5000 | 0 | 20135 |
| 5000 | 5000 | 5000 | 2 | 20135 |
| 10000 | 5000 | 5000 | 3 | 20135 |
| 15000 | 5000 | 5000 | 0 | 20135 |
| 20000 | 135 | 135 | 1 | 20135 |

There were no within-page duplicates. Received rows total 20135; independently
reconciled unique IDs total 20129. This acquisition establishes cross-page
repetition, not which records were omitted or the backend root cause. Ordinary
live returned available data with **exit 1**, `INCOMPLETE_RESULT`, structured
warnings and `complete=false`; native total stayed 20135 in metadata.

- Strict live: page 0 reported 20135, page 5000 reported 20200. The client rejected
  the changing total with `INVALID_RESPONSE`, exit 1, `data=null`.
- Failed refresh: page 0 reported 20484, page 5000 reported 20515. It likewise
  returned `INVALID_RESPONSE` with no dataset or publication; the complete
  previously seeded independent account scope remained byte-identical in SQLite.
  A total-change hard failure does not return the partial-result metadata envelope.
- A genuine account-scoped refresh obtained 6/6 complete records. With a transport
  factory that throws on any browser contact, full-scope offline returned
  `CACHE_MISS`, while that independent scoped offline inquiry returned all six
  prior complete rows. A narrow cache was not misrepresented as full coverage.
- Same-full-scope prior-cache preservation is separately proven by synthetic SIT;
  the native full scope has no complete cache to pretend to seed.

The first private harness stopped when it expected only `INCOMPLETE_RESULT` from
strict live. Inspection confirmed the existing fail-closed total-change behavior,
not an identity/date error. The continuation accepted **only** that classified
`INVALID_RESPONSE` and finished refresh/offline checks; it did not suppress an
unexpected error, normalize counts, retry smaller pages or change product code.
A forecast-specific synthetic test now covers ordinary/strict live and refresh
for 20135-to-20200 total change, preserving a valid same-scope cache.

Backend investigation should check deterministic unique ordering and read
consistency across pages, as well as identical count/list filtering and join
semantics. Changing totals are observed; concurrent writes, replica/cache
inconsistency and nonunique ordering remain hypotheses until backend evidence
establishes the mechanism.

## Related investigation, not a merged defect

Recommend cross-linking this report with the
[cash-accounts count bug](2026-10-01-cash-accounts-backend-count-bug.md) and its
[implementation record #73](https://github.com/proletariat64/dogopencli/pull/73)
when backend tracking is authorized. Accounts reported **3691** but returned
**3690**, including a single-page deficit at width 5000, with **no duplicates**.
That distinct evidence justifies related investigation into count/list logic,
not automatic issue merging or a claim of the same root cause. #76 owns the
forecast contract; #73 documents the accounts-compatible handling.

The [forecast-accuracy pagination bug](2026-10-02-forecast-accuracy-pagination-backend-bug.md)
is a separate endpoint/case: its 4419 reported versus 4416 unique records and
observed boundary duplicates must not be attributed to forecast results.
**#10 is a separate Payment Channel issue**, not the accounts or forecast defect.
No issue or comment has been published by this report.

## Acceptance conditions

1. At unchanged width/offset and a stable original scope, backend count equals
   the independently reconciled complete unique-record set. Pages neither omit
   nor repeat records; ordering/read-consistency and count semantics are explained.
   Validate repeated acquisitions and a genuinely multi-page populated scope;
   a smaller/account-only sample is not sufficient.
2. Preserve original reported counts in diagnostic evidence, investigate any
   change rather than normalize it, and document the confirmed backend cause
   and fix separately from client compatibility.
3. Fresh ordinary live, strict live and refresh UAT confirms the authorized
   partial contract, nonzero failure status and unchanged prior-cache rollback
   on the defective scope. After repair, full-scope completeness permits normal
   success/publication; release/activation must be explicitly recorded elsewhere.

## Private evidence pointers

- `tmp/spec76-cli-uat-20261002T022914Z/forecast-results-list-refresh.json`:
  audited refresh envelope, 7504 reported/7502 collected, incomplete and unpublished.
- `tmp/spec76-cli-uat-20261002T022914Z/forecast-results-list-live.json`:
  saved strict-live rejection envelope, `INCOMPLETE_RESULT`, exit 1, `data=null`.
- `tmp/spec76-cli-uat-20261002T144041Z/page-stats.json`: counts-only native
  widths, offsets, per-page overlaps and changing totals.
- The same fresh directory's `compatibility-accepted.json`, normal/strict live,
  failed-refresh and disconnected offline envelopes confirm client compatibility.
- The original private directory's `summary.json` and isolated cache support the
  dated UAT chronology; do not attach their raw contents to a public tracker.

Only sanitized contract names, aggregate counts and private file pointers are
included. No record identifiers, raw business values, credentials or raw
arguments are reproduced.
