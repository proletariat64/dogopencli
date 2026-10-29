# Historical range replacement

`workflow import plan --export EXPORT_ID --action replace-range` previews an
explicit historical replacement. Apply the saved import plan with
`workflow import apply --plan IMPORT_PLAN_ID`; read the current namespace with
`workflow current show --export EXPORT_ID`. Export and import remain separate:
apply reads the exact saved export offline and never calls the leaf adapter.

The exporter freezes the optional leaf adapter method
`range_replacement_contract(parameters)` into the saved export. This declaration
must establish that a complete query replaces all records in its native range
and business namespace, including removal of records absent from that result.
The contract contains:

- `namespace`: nonempty business scope and variant mapping. Include meaningful
  account/tenant/filter identity; omit the date bounds only where native evidence
  establishes that the resulting ranges share replacement semantics. The host
  adds leaf, operation and environment.
- `field`: the native calendar date field used to retain range-external rows.
- `from`, `to`, `format`: exact native bounds and their date format.
- `interpretation: calendar_date` and `boundary: inclusive`: the supported range
  interpretation. No time zone or artificial date is inferred.

A history planning contract or date-looking record field alone does not authorize
replacement. Current native cash-balance history provides query observations;
it does not declare this replacement contract. Unsupported semantics, unknown
coverage, incomplete/failed exports and invalid/outside-range records cannot
publish a replacement. Complete exact observations remain eligible for
`--action preserve` without any range identity declaration.

Plans report the exact replacement range, expected current publication, replaced
row count, new row count and retained count in the business namespace. Initial
publication expects no prior publication. Apply checks the expected publication
again under the writer lock, subtracts only the owned occurrences within the
range, and atomically commits new rows, the immutable observation, receipt and
current pointer. Equal occurrences in other namespaces and rows outside the
range remain intact. A complete-empty export clears only its established range.

The same export's range action is idempotent across regenerated plans and process
restart. Replaying an older action does not restore its historical current state.
An intervening publication in the same namespace makes an uncommitted plan stale,
even when its range is disjoint; compile a fresh plan. Changed date-field or range
interpretation semantics cannot open overlapping current history in that same
namespace. Failed refreshes, lock contention and failed transaction writes retain
the last committed current data and exact observations.

Full, keyed and range current ownership cannot be mixed in one registered relation
without an established equivalence. Guards apply both during preview and under
the writer lock. Preservation stores only an observation and remains available
before or after a current action; it never changes current rows. Raw observations
remain available with `workflow observation show --export EXPORT_ID` independently
of current state. `workflow status` reports current range publications separately
from the latest export attempt and full/keyed publications.
