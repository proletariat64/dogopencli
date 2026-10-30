# Bounded native history observations

History planning freezes a finite desired native range, meaningful filters,
environment, destination binding and explicit work packages. Export attempts and
coverage are separate from that immutable desired scope. Capture timestamps never
become business dates or source modification times.

```bash
dogopencli workflow plan create --leaf liquidity.cash.balances --mode history \
  --parameters '{"account-alias":"ACCOUNT","from-date":"20260918","to-date":"20260920"}' \
  --windows '[{"from":"2026-09-18","to":"2026-09-18"},{"from":"2026-09-19","to":"2026-09-19"},{"from":"2026-09-20","to":"2026-09-20"}]'
dogopencli workflow plan show --plan PLAN_ID
dogopencli workflow history show --plan PLAN_ID
dogopencli workflow export run --plan PLAN_ID
dogopencli workflow export run --plan PLAN_ID --package PACKAGE_ID
dogopencli workflow status
```

`--windows` selects exact native ranges within the desired bounds. A calendar
contract accepts only ISO `YYYY-MM-DD`; an instant contract accepts only UTC
milliseconds `YYYY-MM-DDTHH:mm:ss.SSSZ`. Desired ranges, cutoffs and coverage
metadata use that same canonical format. The leaf decides which public date or
datetime formats its parameters accept and converts them at this boundary. Omit
windows to retain one unchanged native range.
The planner never automatically expands a query into days. A selected package run
still returns a nonzero aggregate outcome while any desired scope or requested
package remains unresolved. Inspect `meta.history` or use `history show` for the
retained results. `--package` is valid only for a package belonging to that plan.

Resume runs skip complete-empty and complete-nonempty packages, retry failed or
incomplete packages as whole new inquiries, and retain every previous exact export.
An interrupted package is a failed attempt; the untouched tail stays unqueried.
Independent package errors do not discard successful exports or prevent other
packages from running. There is no assumed durable native cursor across attempts.

`history show` and `status` are read-only. They report desired bounds, finite
cutoff, each package's exact native query, attempt evidence and export identities.
`unplanned_ranges` exposes omitted intervals; `unqueried_ranges` exposes
intervals with no attempted query; `uncovered_ranges` exposes intervals without a
complete query observation. An overlapping complete query cannot hide a failed,
incomplete or unqueried requested package in the aggregate `complete` result.
Overlap diagnostics retain up to 100 package pairs and indicate truncation.
Coverage derives from requested ranges and acquisition conclusions, never record
maxima, empty-date filling or capture time. `complete` means all requested query
observations succeeded and their ranges span the desired interval; it does not
establish equivalence to one wider query or a merged historical publication.

Every package export uses the [exact export/import contract](export-import-workflow.md).
Pass the selected package's `export_id` to `workflow import plan --action preserve`
and apply that import plan offline. Complete-empty observations remain identifiable;
incomplete/failed artifacts cannot be normal import inputs. Each exact query is a
separate observation and does not update the registered current table. Equal or
overlapping records from different exports therefore do not become a double-counted
current history view. Historical merge, range replacement and separate frozen
repair plans require their own explicit actions.

## Native declaration and temporal boundary

A List opts in through `operations.list.history` in its manifest. The declaration
is independent of standard/custom acquisition. Declare verified business facts:

```json
{
  "interpretation": "calendar_date",
  "time_basis": "valueDate",
  "boundary": "inclusive",
  "timezone": null,
  "from_parameter": "from-date",
  "to_parameter": "to-date",
  "splitting": "explicit_windows",
  "cross_range_equivalence": false
}
```

The parameters name declared scalar string CLI options. A single calendar axis
uses `from-date`/`to-date`; a single instant axis uses `from-time`/`to-time`. The
host normalizes their adapter keys to underscores.
Keep an unknown timezone explicitly null; never manufacture UTC instants from an
unqualified business date. Optional `modification_time` describes a separate native
field. `splitting: explicit_windows` permits exact windows, without asserting
daily concatenation equivalent to a wider inquiry.

Optional `max_day_difference` limits the difference between inclusive endpoints:
0 allows only one day, while 31 allows up to 32 calendar dates. Optional
`applicability` limits history to one selector's declared values, for example
`{"parameter":"source","values":["market","bank"]}`. A nonapplicable variant
can still use its existing full observation path. `max_day_difference` is a
calendar-only limit. Other native limits, including calendar-month and whole-second
restrictions, remain leaf validation. The declaration adds no generic condition
language or multiple time axes.

The adapter supplies two pure conversion methods:

| Method | Boundary |
| --- | --- |
| `history_bounds(parameters)` | Parse the leaf's accepted public formats and return only `from`/`to` in the declared model's canonical host format. |
| `history_parameters(bounds)` | Convert validated canonical bounds into a patch containing only the two declared adapter parameter keys. |

The host constructs the contract, strictly validates canonical bounds, ordering,
applicability and limits, and verifies the parameter round trip. It preserves all
other frozen selectors and reuses native capability/scope validation. Plan
creation and export revalidation use this same resolution path. The adapter does
not construct a host `history_contract` dictionary.

### Instant ranges and public input precision

An instant declaration changes `interpretation` to `instant` and maps
`from_parameter`/`to_parameter` to `from-time`/`to-time`; declare the native time
field and its qualified timezone explicitly. The same conversion methods and
planner apply. Optional `precision: "millisecond"` describes the canonical host
boundary; it does not broaden the leaf's accepted public input precision. Canonical
bounds always contain exactly three fractional digits
and `Z`, for example `2026-10-16T01:30:00.123Z`. Numeric offsets, missing fractions
and date-only values are public leaf inputs, not valid host window values.

The leaf may accept a date, a whole-second datetime, or a datetime with one to
three fractional digits when its native contract supports them. Date expansion
requires an explicit leaf timezone: the lower endpoint becomes local midnight,
the upper endpoint local 23:59:59.999. An explicit instant retains its precise
boundary. Reject unknown offset `-00:00`, unsupported precision and unrepresentable
windows rather than truncating or widening them. The side-effect-free helpers in
`dogopencli.temporal` are:

| Helper | Meaning |
| --- | --- |
| `parse_date_or_instant(value)` | Return a strict ISO calendar date or an aware explicit-offset datetime; datetime fractions may contain zero to three digits. |
| `parse_iso_millisecond_instant(value)` | Parse an explicit-offset datetime through milliseconds; return an aware datetime. |
| `normalize_utc_milliseconds(value)` | Normalize a supported datetime string or aware datetime to exact UTC milliseconds; reject naive values and submillisecond precision. |

These helpers do not expand dates to a day or choose a timezone. The leaf chooses
accepted public formats and business boundaries. Existing seconds-only parsers
keep their restrictions for unaffected leaves.

For example, `fx.trade` has one `from-time`/`to-time` pair accepting dates and
explicit-offset datetimes through milliseconds. Its date boundaries use GMT+8;
`2026-10-16T09:30:00.123+08:00` normalizes to
`2026-10-16T01:30:00.123Z`. Other leaves retain qualified whole-second input limits.
A rule-status upper second includes its final `.999`; an explicit FX upper
instant remains exact. UTC formatting alone does not make these semantics equal.

Coverage uses whole calendar days for calendar contracts and integer milliseconds
for instant contracts. It does not infer coverage from returned row timestamps.
Explicit windows must remain native-executable, including precision restrictions;
no automatic splitting or range-replacement support follows from an instant
history declaration. Daily clock filters such as forecast `record-from-time` are
fixed selectors, not independent instant axes. Defaults that depend on the current
day must be materialized when the plan is created, before execution or resume.
For such defaults, a List may opt in with `operations.list.freeze_parameters: true`
and a pure `freeze_parameters(parameters)` adapter hook. The hook returns a
parameter dictionary that retains every explicit input unchanged and may add only
declared, correctly typed parameters. It performs no inquiry. The host freezes
that output in the ordinary planning path; a hook without the declaration is not
implicitly invoked. Fixed clock defaults can remain manifest defaults.

Whole desired ranges must also be executable native inquiries. A single-day leaf
therefore cannot accept a multi-day desired range merely because supplied windows
each select one day. No automatic decomposition is performed.

Full observations need no temporal declaration, no conversion methods and no
canonical-format parameter requirement. Existing full-only leaves keep their List, Refresh,
export/import and package validation paths. Undeclared leaves do not gain history
from date-like option names or output timestamps. See the executable
[calendar sample](../../tools/leaf-dev/example-history/) and its
[fake CLI exercise](../../tests/integration/test_leaf_calendar_handbook.py).

`cash.balances` declares calendar `valueDate`; its public parameters accept compact
and ISO dates, while the SDK boundary uses only ISO. Its `updateTime` retains
native local formatting with unknown timezone. Account-directory quality and
current ownership limitations remain separate from per-request completeness.
It does not declare source freshness, historical ownership or deletion coverage.

A saved plan whose installed leaf binding or temporal contract changed must be
recreated. Existing plans, exact exports and imported observations are retained
for inspection; the host does not silently rewrite or delete them.
