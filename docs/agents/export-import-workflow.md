# Durable export and scoped observation import

`export` retrieves an installed List scope online. `import` writes an exact saved
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
are added without migrating or rewriting current rows. Uninstallation retains data
and registered binding history.

`observation show` reads stored DuckDB rows and their receipt. `export show` reads
the acquisition artifact; it does not prove import. `status` reads saved desired
plans, per-plan unqueried/latest attempt states, latest export attempt, last complete
export and committed observations. It initializes no schema and advances no stage.
Workflow artifacts live under `workflow/` beside the selected configuration file;
Duckdog destinations remain the leaf registry's existing database/relation bindings.

This workflow supports scoped preservation. Replacement, keyed updates, historical
coverage planning, repair orchestration and scheduling require their own explicit
contracts and commands.
