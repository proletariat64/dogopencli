# Bounded native history observations

History planning freezes a finite desired native range, meaningful filters,
environment, destination binding and explicit work packages. Export attempts and
coverage are separate from that immutable desired scope. Capture timestamps never
become business dates or source modification times.

```bash
dogopencli workflow plan create --leaf liquidity.cash.balances --mode history \
  --parameters '{"account-alias":"ACCOUNT","from-date":"20260918","to-date":"20260920"}' \
  --windows '[{"from":"20260918","to":"20260918"},{"from":"20260919","to":"20260919"},{"from":"20260920","to":"20260920"}]'
dogopencli workflow plan show --plan PLAN_ID
dogopencli workflow history show --plan PLAN_ID
dogopencli workflow export run --plan PLAN_ID
dogopencli workflow export run --plan PLAN_ID --package PACKAGE_ID
dogopencli workflow status
```

`--windows` selects exact native ranges within the desired bounds; endpoints use
the format declared by the leaf. Omit it to retain one unchanged native range.
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

## Native declaration

An adapter may expose `history_contract(parameters) -> dict` at the exporter
boundary. Full observations do not require it. The current planner supports
`interpretation: calendar_date` and `boundary: inclusive`; other semantics remain
available as unchanged full scoped observations. Required facts are `time_basis`,
native `format`, `from_parameter`/`to_parameter` (normalized parameter names), and
normalized finite `from`/`to`. `splitting: explicit_windows` permits individually
selected native windows; it does not assert cross-range equivalence. Preserve
`timezone`, `cross_range_equivalence` and source modification-time information
without guessing unknown facts. No importer leaf profile or source qualification
table is involved.

`cash.balances` declares calendar `valueDate`, inclusive compact bounds, explicit
account aliases and separately labeled range observations. Its `updateTime`
retains native local formatting with unknown timezone. It does not declare daily
concatenation equivalent to a multi-day result, historical account ownership,
source freshness, or deletion coverage. Its existing custom List parser and
pagination establish acquisition completeness for each exact request.
