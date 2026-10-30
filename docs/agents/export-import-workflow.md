# Durable export and scoped import

`export` retrieves an installed List scope or its declared Get inquiry online. `import` writes an exact saved
export into its registered Duckdog destination offline. Each command executes its
own stage. Query cache publication, successful export and committed import are
separate outcomes.

```bash
dogopencli workflow plan create --leaf payment.sla.baselines --parameters '{}'
dogopencli workflow plan show --plan PLAN_ID
dogopencli workflow export create --plan PLAN_ID
dogopencli workflow export status --run RUN_ID
dogopencli workflow export watch --run RUN_ID --snapshot
dogopencli workflow export run --run RUN_ID --limit 10 --fields id
dogopencli workflow export show --export EXPORT_ID
dogopencli workflow import plan --export EXPORT_ID --action preserve
dogopencli workflow import apply --plan IMPORT_PLAN_ID
dogopencli workflow observation show --export EXPORT_ID
dogopencli workflow import plan --export EXPORT_ID --action replace-full
dogopencli workflow import plan --export EXPORT_ID --action replace-range
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

Use `plan create --operation get --identity NATIVE_ID` for any declared Get. It
captures only the native root/components declared by that Get, with their acquisition evidence; it does not discover additional children.
Get observations retain a separate operation/identity namespace and cannot replace
wider List data. A Get-only export has `binding: null`: its exact artifact can be
inspected or repaired, but import and current-data actions report that no registered
dataset destination exists. Exporting it does not invent a Duckdog binding or enroll
it as an enumerable dataset. Use
`plan create --with-detail` only with an existing declared List/Get binding; export
composes every selected List row before applying preview limits or projection.
The plan pins the installed adapter implementation and the complete Get declaration,
including its row binding. It does not call Get capability factories with missing
row values. A changed adapter or Get declaration requires a new plan.

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
interval, conclusions, warnings and gap evidence. Each deliberate acquisition
creates a new Export Run. Retrying that Run retains its identity and starts a new
attempt; each saved export has its own immutable identity.
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

Imports prepare hidden observation rows in transactions of at most 10,000 rows
under the host lifecycle writer lock. Each batch commit is durable progress;
unpublished rows have no observation receipt and are never exposed as committed
observations or current data. An interrupted explicit apply compares retained
ordinal/record values with the same frozen input and resumes after durable batches.
Publication commits the observation receipt and any current rows/pointer together.
A failed publication retains the previous current result and resumable staging. Reapplying the same
export/action/destination, including a regenerated import plan after restart,
returns `replayed: true` without inserting rows. The receipt is authoritative if a
process stops after commit but before printing its response. Host observation tables
are added without migrating the registered `_record` schema. Uninstallation retains data
and registered binding history.

`observation show` reads stored DuckDB rows and their receipt. `export show` reads
the acquisition artifact; it does not prove import. `status` reads saved desired
plans, per-plan unqueried/latest attempt states, latest export attempt, last complete
export and committed observations. It initializes no schema and advances no stage.
Completed exports are published by one atomic directory rename, containing
`metadata.json` and `records.json`. Offline listings, coverage and target planning
read only metadata; they do not parse all retained records. Exact export/import
commands still read their selected records. Import-plan previews omit the frozen
record copies while retaining exact identities, scope and affected counts. Full
artifact parsing uses memory proportional to the selected input; bounded write
transactions do not imply a streaming acquisition or constant-memory importer.
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

[Historical range replacement](range-replacement.md) requires explicit native
replacement coverage; ordinary history planning does not establish deletion
semantics. Read it before selecting `--action replace-range`.

## Saved targets and explicit following

`workflow target create --plan ID` preserves an exact full/history plan as bounded
intent. `workflow target plan --target ID` freezes an execution;
`workflow target run --execution ID` executes that exact work and reuses completed
child Runs within that execution. A fresh execution owns fresh child Run
associations. Repeating bounded work never advances the requested date range.
Planning writes workflow files only; it never exports or imports.

Following is explicit: `workflow target create --plan ID --policy following`.
For full observations each explicit planning call freezes a fresh observation
plan and capture cutoff. A capture cutoff is not a business timestamp.
For history, also provide `--timezone Asia/Shanghai` (the operator's cutoff
calendar zone), and optionally `--lookback-days 2`. History requires the leaf's
declared inclusive calendar contract and permission for explicit windows.
The cutoff is frozen when planning, so a later run cannot widen it. Retained
coverage is clipped to the frozen start and cutoff; out-of-range intervals do not
create or extend requested work. Work includes uncovered native query intervals
plus the explicit lookback, measured from that
cutoff, including its calendar day. Without lookback, completed native query
intervals are reused. Row maxima never establish coverage. An unknown native
timezone remains unknown; the cutoff zone does not relabel source timestamps.

`workflow target enroll --scopes '{"domain.leaf":{"native-argument":"value"}}'`
creates a bounded set from currently installed List datasets. `--mode history`
requests native history support. The saved enrollment shows exact required native
arguments, validation/capability diagnostics, declared limitations, and excluded
Get-only leaves. It never fabricates parameter combinations. Omitted scopes and
unsupported capabilities stay visible and make execution fail in aggregate;
independent successful exports remain saved and are reused on retry. Installing a
new leaf does not change existing target sets: run enrollment again explicitly
to create a new set. Diagnostics are frozen intent; supply corrected scope in a
new enrollment rather than silently changing old work.

`workflow target show --target ID` and `workflow status` inspect target intent,
frozen work and attempts offline. Status retains exact export IDs, latest attempt
and last successful exports, exporter metadata (counts, capture times, time basis,
cache facts when supplied), known history gaps, and committed import receipts and
current publications separately. Inspection/help never authenticate, export,
import, or initialize a schema. Execution performs export only; import remains an
explicit separate stage bound to exact saved exports.

## Synthetic scale verification

The opt-in public CLI scale test installs an unrelated synthetic leaf, exports
one million history rows through fake CDP, imports offline, replays the exact plan,
and checks status/coverage without opening retained record files. It reports
elapsed times, process peak RSS and batch bounds to a task-owned evidence file.
These measurements are separate from native inquiry UAT.

```bash
DOGOPENCLI_RUN_SCALE=1 DOGOPENCLI_SCALE_EVIDENCE=/tmp/dogopencli-scale.json \
  python -m pytest -q -n 0 \
  tests/integration/test_workflow_scale_cli.py::test_million_row_synthetic_history_measurement
```

Focused crash tests interrupt before and after batch commit, and before/after
publication commit. Database receipts remain authoritative after commit even
when no success response was emitted; status performs no recovery writes.

## Observe one exact task

Preparation returns `data.id` before execution. An inquiry plan freezes intent and
can prepare multiple independent Export Runs. `export create --plan PLAN_ID`
prepares a pending Run offline; `export run --run RUN_ID` executes or retries that
exact task. Failed/incomplete history packages retain independent successes on
retry; a fresh Run does not inherit them as new acquisition.

Use the matching typed selector for each stage:

| Stage | Resident text watch | Finite JSON status |
| --- | --- | --- |
| Export | `workflow export watch --run RUN_ID` | `workflow export status --run RUN_ID` |
| Repair | `workflow repair watch --repair REPAIR_PLAN_ID` | `workflow repair status --repair REPAIR_PLAN_ID` |
| Import | `workflow import watch --plan IMPORT_PLAN_ID` | `workflow import status --plan IMPORT_PLAN_ID` |
| Target | `workflow target watch --execution EXECUTION_ID` | `workflow target status --execution EXECUTION_ID` |

Watch defaults to text every three seconds and remains after settlement to observe
an explicit retry of the same identity. `--snapshot` prints one fresh text frame;
`--until-settled` waits for the current settled result. `--interval SECONDS` accepts
a positive integer. Ctrl+C stops only the observer with exit 130. Non-TTY watch
appends plain frames; TTY watch updates the panel in place. These modes and
`--attach PANE_ID` are mutually exclusive. Explicit JSON watch is rejected; use
status for one machine-readable `data`/`meta`/`error` envelope. Status also supports
`--format text`. A valid status read of a failed task exits zero with `error: null`;
an observation failure is a command error. Invalid usage exits two.

Inside Herdr, `watch ... --attach PANE_ID` starts the same text watcher in an idle
pane and returns a finite verified-start receipt. The exact selected configuration,
working directory, interpreter and module source survive launch. Caller, agent,
busy, missing and unverifiable panes are rejected. Attach preserves layout/focus;
it does not create panes. Herdr exposes separate idle inspection and command
submission, so the preflight check cannot promise atomic exclusion against an
external actor occupying the pane concurrently. Use an uncontended target.

Status and watch read bounded metadata offline and initialize no schema. Runner
ownership, heartbeat, last progress and observation time are separate facts.
Unknown totals stay unknown; physical requests, source pages, received rows and
saved rows have different units. Degraded/stale observations expose read quality
and age. Import staging means durable hidden batches; exact action/destination
receipts prove committed observations/publication. An old successful publication
can remain proven after another export becomes current. Legacy artifacts expose
only retained evidence and may have unknown telemetry.
