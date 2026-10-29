# Durable export and scoped import

`export` retrieves an installed List scope or its declared Get inquiry online. `import` writes an exact saved
export into its registered Duckdog destination offline. Each command executes its
own stage. Query cache publication, successful export and committed import are
separate outcomes.

```bash
dogopencli workflow plan create --leaf payment.sla.baselines --parameters '{}'
dogopencli workflow plan show --plan PLAN_ID
dogopencli workflow export run --plan PLAN_ID --limit 10 --fields id
dogopencli workflow export show --export EXPORT_ID
dogopencli workflow import plan --export EXPORT_ID --action preserve
dogopencli workflow import apply --plan IMPORT_PLAN_ID
dogopencli workflow observation show --export EXPORT_ID
dogopencli workflow import plan --export EXPORT_ID --action replace-full
dogopencli workflow import apply --plan REPLACEMENT_PLAN_ID
dogopencli workflow current show --export EXPORT_ID
dogopencli workflow status
```

The JSON response contains `data.id` for newly saved plans and exports. IDs select
one exact artifact; there is no implicit latest/cache input. Native parameter keys
use the leaf's CLI spelling without `--`, with arrays for repeatable parameters.
Planning reuses native argument and scope validation without browser access or
schema initialization. Native defaults and source scope are inspected at planning;
a changed scope or inquiry environment requires a new plan before export.

A plan selects one installed List leaf and its native scope. `mode: full` means a
full observation of that exact query, including a native date filter when supplied;
it does not claim daily coverage or synthesize a business time index. Get-only
leaves are not enumerable datasets. Help and inspection remain offline.

Use `plan create --operation get --identity NATIVE_ID` for a declared Get on a
List-capable leaf. It captures only the native root/components declared by that
Get, with their acquisition evidence; it does not discover additional children.
Get observations retain a separate operation/identity namespace and cannot replace
wider List data. Get-only leaves remain outside dataset enrollment. Use
`plan create --with-detail` only with an existing declared List/Get binding; export
composes every selected List row before applying preview limits or projection.

`ANY` entity selectors resolve read-only from the configured local Duckdog selector
when compiling a plan. The effective native IDs are saved in the plan and checked
again before acquisition; a changed selector requires a new plan. Planning does not
query an account directory online. Entity-wide account inquiries retain the leaf's
exporter-owned enumeration, directory quality and reported gaps during export.

Local record filters retain the requested selected records and their exact filter
scope. Their saved coverage is labeled `local_selection_of_native_acquisition`;
native totals and acquisition evidence remain separately recorded as
`source_acquisition`. A complete selection means the complete acquired source was
filtered locally, and does not claim that selected rows are the entire native scope.


Exports save qualified public records before presentation limit, offset and field
projection. Intentional leaf allowlists remain effective. Nested values, exact JSON
numbers, native amount strings, row order and valid duplicate occurrences survive.
The immutable completed artifact includes native scope, environment, acquisition
interval, conclusions, warnings and gap evidence. Each run produces a new identity.
Complete-empty, complete-nonempty, usable incomplete, failed and unqueried plans are
distinct. Incomplete records remain inspectable; normal import accepts only complete
exports. A failed refresh does not hide the last complete export or committed data.

`preserve` adds one scoped observation with provenance. It leaves the registered
`_record VARCHAR` current table unchanged, including existing rows. Import plans show
`existing_count` for preserved rows in the exact scope/environment, `new_count`
(zero for replay), `current_count`, and `current_effect: unchanged`. Counts preserve
multiplicity; a new equal-valued export is another observation. No business key,
version, date, or merge rule is invented.

Import reads the frozen artifact and registered binding without loading adapters,
consulting later export configuration, or accessing networking. Input format,
record count, frozen plan equality, ownership and destination schema are checked
locally. Plans retain their exact input for direct comparison, including numeric
representation; no whole-adapter/configuration fingerprint is required. Missing,
malformed or changed local input and conflicting destinations fail explicitly.

Observation rows and their replay receipt commit in one DuckDB transaction under
the host lifecycle writer lock. A failed write rolls back both. Reapplying the same
export/action/destination, including a regenerated import plan after restart,
returns `replayed: true` without inserting rows. The receipt is authoritative if a
process stops after commit but before printing its response. Host observation tables
are added without migrating the registered `_record` schema. Uninstallation retains data
and registered binding history.

`observation show` reads stored DuckDB rows and their receipt. `export show` reads
the acquisition artifact; it does not prove import. `status` reads saved desired
plans, per-plan unqueried/latest attempt states, latest export attempt, last complete
export and committed observations. It initializes no schema and advances no stage.
Workflow artifacts live under `workflow/` beside the selected configuration file;
Duckdog destinations remain the leaf registry's existing database/relation bindings.

`replace-full` explicitly publishes a complete exact full query observation as
current data. Its preview shows the namespace (leaf, operation, environment, native
parameters and scope), existing and new counts, and `expected_current`. Initial
publication expects `null`; it needs no fabricated predecessor. Complete-empty
replacement intentionally clears that namespace. Failed, incomplete and unavailable
exports cannot prepare a normal import plan.

Apply checks the expected publication under the writer lock. A stale plan fails
without changing records. Rows, saved observation, publication receipt and current
pointer commit atomically. Replacement removes the previous scope's exact row
occurrences and inserts the selected export, preserving unrelated scopes and existing
rows. Nested values and legitimate duplicate multiplicity remain intact; no inferred
business key or time field is needed. Previous exports and observations stay readable.
Replaying an already published export is a no-op even after another export became
current; retry never moves the pointer backwards. An already preserved export can
be explicitly published without duplicating its saved observation.

`current show --export EXPORT_ID` uses that export's exact namespace to read the
current committed observation and publication receipt. `status.current_publications`
identifies the current exports separately from latest attempts and saved history.
A failed refresh leaves current data visible. Import, current readback and status
remain offline. [Bounded history](bounded-history.md) adds explicit native query
packages and coverage inspection. [Scoped keyed history](keyed-history.md)
reconciles overlaps only with explicit native identity, namespace and ordering
facts. [Frozen repair](repair-workflow.md) fills known acquisition gaps through
separate exports and an exact offline input selection. Scheduling requires its
own explicit contracts and commands.
