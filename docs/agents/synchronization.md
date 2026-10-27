# Durable synchronization

The host owns saved targets, acquisition orchestration and transactional Duckdog
publication. Leaves own native identity, scope, source time and completeness
contracts through validated `sync` declarations. Query commands do not import
implicitly, and temporary cache publication is not durable acceptance evidence.

## Commands and targets

- `dogopencli sync --all` evaluates every installed List variant. Settings acquire
  their full declared scopes; qualified historical queries enroll today with
  following enabled; current-only runtime captures observations. Missing native
  scope, unsupported clocks and unqualified variants remain explicit blocked
  enrollments. Get-only inquiries are not enumerable datasets.
- `dogopencli <domain> sync <leaf> <native arguments>` saves a bounded target.
  `--follow` opts into future extension where the native clock permits it. An
  explicit valid scope can resolve a previously blocked automatic enrollment.
- `dogopencli sync` executes saved targets without enrolling new installations.
  It refreshes settings/current observations, retries unresolved windows and
  advances following history. Explicit repeated ranges request reconciliation;
  ordinary replay skips completed fixed windows.
- `dogopencli sync status` performs no acquisition, authentication, adapter import,
  database initialization or metadata writes. It reports plans, coverage, attempts,
  counts, gaps and source-time meaning. Remote changes remain unknown.

The run cutoff is fixed. Native timezone, inclusive/exclusive boundaries and
precision determine chunks. Unknown boundary semantics stay exact-scope-only;
they cannot be partitioned or followed. Modification-time coverage does not prove
complete event-time history. Recent overlap can recover late arrivals only within
that policy; explicit older ranges are needed for older corrections. Source
retention or unavailable historical APIs can leave unrepairable gaps.

Targets are separate from coverage. Save the target before its first acquisition,
then record attempts and commit data with successful coverage per chunk. A newer
completed date does not hide an interior gap. Complete-empty is different from
unqueried or failed. A failed refresh retains the original successful as-of
coverage and exposes the failed latest attempt. Removed leaves retain data and
become inactive; changed contracts or configured sources block ordinary replay.
Changing durable key or version policy also blocks explicit publication until an
explicit data migration preserves the existing records; re-running a command is
not a schema migration.

The source namespace identifies the configured browser context and domain. The
platform does not expose a stable authenticated-principal identity to this
interface. Changing account or tenant within the same browser context cannot be
detected from the URL; use a separate configured store/context for separate
principals rather than treating this namespace as proof of account identity.

## Publication and current views

Sync uses raw qualified List acquisitions before local display filtering,
projection or output limits. Shared strict result policy and independent
scope/dataset completeness are required. A local selector making no authoritative
source request cannot clear settings or mark runtime coverage complete. Get
completeness describes its declared root/components only; there is no new generic
Get crawl or implied full-history acquisition.

Settings and untimed observations replace one authoritative query scope per
qualified identity family.
Another query scope within that family could overlap or retain stale records after
a broader refresh, so publication fails closed and preserves prior data. Use one
scope for the current snapshot, or separate stores when comparing query scopes.
Different qualified business identity scopes remain independent. Native settings
versions that belong to identity are preserved. Complete authoritative empty
settings replace the scope with empty data; partial/error results never do.

Runtime identity includes the declared source, variant and business namespace;
query dates and pages do not become record keys. Complete chunks merge by native
identity. A qualified newer source version can update records, older versions do
not regress them and equal-version conflicts fail. Without source ordering the
policy is latest observed, not a claim of source-newest. Empty incremental windows
do not delete older history. Current-only runtime stores observed generations and
a current read model; it does not reconstruct unobserved historical state.

The registry-owned public relation retains exactly `_record VARCHAR`. Separate
host-owned metadata stores plans, provenance, attempts, keys, coverage and
observation generations. No external helper-owned table or view is adopted.
Public relations can contain multiple qualified variants or business scopes;
readbacks must constrain the intended variant/scope using its provenance and
native contract. Native records are preserved within the leaf's qualified public
field policy, including any deliberate allowlist.

A nonblocking writer lock covers a sync run. The write connection is temporarily
closed during native acquisition so existing read-only selector connections work,
while writer ownership remains held. Settings publication or each runtime chunk
commits records and coverage together. Independent successful chunks remain after
later failures; interruption/restart retries unfinished work without claiming it
complete. Private temporary staging contains canonical record strings with typed
VARCHAR ingestion and is cleaned on normal exit, errors and interruption. A hard
process kill may leave a protected staging directory, which is never a checkpoint.

## Failures and evidence

Use shared structured diagnostic codes, reasons, components, stages and
retryability. Complete acquisitions can retain qualified recovery warnings.
Authentication failure blocks affected domain work; independent domains can still
make progress. A run with any requested failure returns nonzero while reporting
committed successes. Status can return success while showing gaps or blocked work.
No result is promoted to complete merely by process exit, matching counts or cache
publication.

The existing public CLI/fake-CDP seam verifies requests, stored records, coverage,
restart and diagnostics. The scale workload in `tests/integration/test_sync_scale.py`
generates native pages lazily, interrupts halfway and resumes without rereading
completed history. Set `DOGOPENCLI_SYNC_SCALE_DAYS=100` and
`DOGOPENCLI_SYNC_SCALE_ROWS=10000` for one million records; an optional
`DOGOPENCLI_SYNC_SCALE_REPORT` path records timing, Python allocation peak and RSS.
Run serially in a fresh process for comparable memory measurements. These are
synthetic workload measurements, not production performance or business UAT.
Real UAT separately requires installed candidate packages, inquiry-only sources,
at least three distinct days, gap repair and independent native-value comparison.

Cash-balance daily synchronization is on source-qualification HOLD: identical
native date/account keys returned different values for single-day and multi-day
requests. Existing List behavior remains available, but sync must not infer
partition-invariant history from those responses. Host behavior tests use an
explicitly range-invariant offline fixture and do not qualify that production
source. Consult the qualification matrix for all current limitations.

Published coverage remains bound to its acquisition contract. Changes to the
adapter, manifest or sync profile block reuse and publication in that namespace,
including explicit sync and `--all`; a separately qualified data migration is
required. Extending a date horizon under the same contract remains supported.
A valid explicit selection resolves matching never-published automatic enrollment
failures. When an explicit target already exists, status retains the old enrollment
as `resolved` with `resolved_by`, alongside its attempt history; plain sync skips
it. A later `--all` reevaluates automatic enrollment and can report it blocked again.

Timed observations retain each complete capture generation with its requested date
scope; successive dates do not manufacture a dated row identity. Intraday account
demands use this policy because native `statisticalDate` contains only an HH:mm
slot. Account cashflow and intraday-demand sync require explicit entity and bank;
List-only implicit ownership resolution does not bind a durable namespace.
Intraday statement sync is on HOLD because `bankTransNo` is only qualified inside
a date query and native `valueDate` is optional. List inquiries remain available.

Explicit followed ranges acquire only the submitted range while preserving the
saved plan's earliest start. `--all` reports installed-package scan failures even
when other leaves succeed. Owned synchronized selectors also work with default or
environment configuration when no config file exists; explicit external bindings
continue to take precedence.
