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

`--windows` selects exact native ranges within the desired bounds and accepts only
ISO `YYYY-MM-DD`. Desired ranges, cutoffs and coverage metadata use the same ISO
format. The leaf decides which public date formats its own parameters accept and
converts them at this boundary. Omit windows to retain one unchanged native range.
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
`unplanned_ranges` exposes omitted calendar intervals; `unqueried_ranges` exposes
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

## Native declaration and date boundary

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

The parameters name declared scalar string CLI options. The single calendar axis
uses `from-date`/`to-date`; the host normalizes their adapter keys to underscores.
Keep an unknown timezone explicitly null; never manufacture UTC instants from an
unqualified business date. Optional `modification_time` describes a separate native
field. `splitting: explicit_windows` permits exact windows, without asserting
daily concatenation equivalent to a wider inquiry.

Optional `max_day_difference` limits the difference between inclusive endpoints:
0 allows only one day, while 31 allows up to 32 calendar dates. Optional
`applicability` limits history to one selector's declared values, for example
`{"parameter":"source","values":["market","bank"]}`. A nonapplicable variant
can still use its existing full observation path. The declaration does not add
a generic condition language, multiple time axes or instant-range support.

The adapter supplies two pure conversion methods:

| Method | Boundary |
| --- | --- |
| `history_bounds(parameters)` | Parse the leaf's accepted public formats and return only `{"from":"YYYY-MM-DD","to":"YYYY-MM-DD"}`. |
| `history_parameters(bounds)` | Convert validated ISO bounds into a patch containing only the two declared adapter parameter keys. |

The host constructs the contract, strictly validates ISO dates, ordering,
applicability and limits, and verifies the parameter round trip. It preserves all
other frozen selectors and reuses native capability/scope validation. Plan
creation and export revalidation use this same resolution path. The adapter does
not construct a host `history_contract` dictionary.

Whole desired ranges must also be executable native inquiries. A single-day leaf
therefore cannot accept a multi-day desired range merely because supplied windows
each select one day. No automatic decomposition is performed.

Full observations need no temporal declaration, no conversion methods and no ISO
parameter requirement. Existing full-only leaves keep their List, Refresh,
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
