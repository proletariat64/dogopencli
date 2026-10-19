# Leaf migration procedure

Use [the batch index](batches.md) to find the assigned ticket. Validate the
current scope map with `tools/leaf-dev/leaf.py batches --plan tools/leaf-dev/batches.json`.

The assigned batch ticket defines the exact leaves and list/get actions. Read
[the package/adapter handbook](handbook.md) and [CONTEXT.md](../../CONTEXT.md)
for current contracts. This document owns the execution sequence; tickets contain
only their specific business scope, evidence pointers and blockers.

## 1. Establish ownership and reuse the host

Use a clean worktree/branch based on current master, one worktree per assigned
batch. Work only in that ticket's leaf directories and tests. Check graph coverage
and impact before code changes. Coordinate shared host/helper changes separately.
B numbers group business scope; they do not impose a serial execution order.

Each worker owns its config/cache, Duckdog data root, artifact/private evidence
directories and any browser it starts. Pass the config/data roots explicitly.
Use separate task-owned profiles and allowed unused CDP ports for concurrent UAT;
read the browser specification named in AGENTS before browser/auth work. Human
SSO remains human-controlled. Never copy profiles/cookies or use ports 9330–9340.
A worker without its own authenticated browser can hand its candidate to the
coordinator for UAT with the coordinator's browser; that gate remains pending
until the coordinator records results. Keep the existing authenticated profile.

The coordinator serializes integration, daily installations, shared importer
changes and parent progress updates. Workers do not write the daily configuration,
reset shared data, or replace a host used by other active workers.

Reuse one existing verified installed host for a wave of leaf-only work. Choose
its interpreter once; keep that installation unchanged while workers use it:

```bash
MIGRATION_PYTHON=/path/to/verified-host/bin/python
rtk proxy "$MIGRATION_PYTHON" -I tools/leaf-dev/leaf.py host-check --repo "$PWD"
```

`host-check` compares installed files directly with this worktree, plus version,
requirements and entry points. It rejects editable/source imports and stale extra
files. Run it once when choosing the host; keep that installation unchanged for
the wave. It creates no fingerprints or receipts. Root `leaf_packages/` is outside
the host. Packaging and HTTP smoke do not repeat the host check.
A leaf change, ZIP upload, new worktree or HTTP lifecycle check does **not** require
a host wheel. If host inputs change, coordinate the host fix and its tests, rebuild
and validate that host once, then use the new baseline for affected work.

Use the normal worktree development environment for tests; preparing dependencies
is separate from building a distribution. `scripts/bootstrap.py` prepares the
local environment without launching a browser. The Makefile bootstrap also
prepares a task browser, so choose it only when that browser is needed.

## 2. Establish native meaning and implement the scoped leaves

Record the inquiry-only endpoint/action, exact fixed/allowed keys, encoding,
application entry, scope, paging/capacity, success/failure envelope, identity,
coverage, filters, amounts/time meaning and native detail echo. Use the ticket's
pinned external release source as business reference, not as a current runtime.
Run the reference in a separate process with networking blocked and preserve the
original input bytes. Unknown scope/identity or unexplained differences block
acceptance; the correct native meaning takes precedence over a demonstrated old
defect. Get-only leaves remain get-only. Same-leaf list/get actions stay together.

Implement against shared host primitives and the installed public CLI. Use fake
CDP tests for request rejection, native values/types/unknown fields, pagination,
duplicates/count changes, local filters, errors/auth expiry and detail identity.
List tests also cover default offline, live without publication, refresh/offline
equality and prior data/capture preservation after rejected acquisitions.
For a reviewed source assembly, qualify each source separately and check native
children against their own captures before checking the approved parent mapping.
Retain each source's scope/total/quality through offline replay; never compare
an assembled parent count to a fabricated native parent total. A failed required
source fails the aggregate; it does not become an empty child array.

Run focused checks while editing, followed by the repository-required gates.
Do not repeat broad passing gates without changed code or unresolved risk.

## 3. Pack once and perform one business acceptance

Use the single `leaf.py pack` command for one or more leaves:

```bash
rtk proxy "$MIGRATION_PYTHON" -I tools/leaf-dev/leaf.py pack --output /path/to/task/delivery leaf_packages/liquidity/example.one leaf_packages/liquidity/example.two
```

Use actual assigned paths. The output directory must be new; it contains one ZIP
per leaf, `SHA256SUMS` and `delivery.json` containing identities, filenames and ZIP
SHA256 values. There are no per-file, host or dependency hashes.
The same package contents produce the same ZIP bytes despite timestamps or source
permissions. Keep the accepted delivery immutable. Changed source needs a new
candidate and affected-leaf verification; unchanged leaves retain their evidence.
The helper neither installs packages nor claims business acceptance.

Install these ZIPs into a task config using public lifecycle commands. Run them
with the verified installed interpreter outside the checkout, with checkout import
paths absent. Positive installed execution and module-origin/dependency checks
establish independence; static package checks alone do not.

Perform the complete local business acceptance **once per exact candidate ZIP**:

- Positive nonempty production evidence for every declared action, including
  genuine native get identities. Empty results, auth failure or business failure
  do not qualify an action.
- For lists, applicable live/refresh/offline and scoped filters; compare each
  offline result to its own captured refresh input. Separate acquisitions can
  legitimately change, so historical counts are not fixed assertions.
- Same-input reference/candidate comparison of complete native records, types,
  exact amounts, scope, identity, counts and multiplicity; explain proven native
  corrections rather than silently normalizing differences.
- Explicit Duckdog import/readback where a supported import contract applies;
  compare full DuckDB/Parquet records and original acquisition metadata. Use an
  isolated data root. [Import rules](duckdog-import.md) govern support; settings
  support does not establish runtime/date-partition support. A pending required
  import contract is a blocker, not permission to invent one.

Use the generic recorder instead of writing a new capture script for every leaf:

```bash
rtk proxy "$MIGRATION_PYTHON" -I tools/leaf-dev/leaf.py capture --directory /path/to/task/private/example-list --config-dir /path/to/task/config -- liquidity list example.one --live --limit 0 --require-complete
rtk proxy "$MIGRATION_PYTHON" -I tools/leaf-dev/leaf.py compare /path/to/task/reference.json /path/to/task/private/example-list/envelope.json --expected-pointer /records --actual-pointer /data
```

Supply the actual leaf/scope and task-owned browser environment. Capture accepts
only list/get/refresh, creates a new private directory, and saves original native
bodies, requests without headers/cookies, and the CLI envelope. Its public summary
contains counts/status, never business values. Store raw inputs outside packages
and commits. Compare preserves JSON types, decimal values, array order and
multiplicity; object-key order is irrelevant. It compares already established
matching scopes and never performs acquisition or infers business equivalence.
The ticket owns the small reference adapter needed to produce comparable records;
the shared tool contains no business dispatcher.

## 4. Keep HTTP delivery short

After local business acceptance, upload **those exact ZIPs and SHA256SUMS** to a
batch/revision-specific directory on cn.ant. It is a file server only. Use the
existing server; do not run the CLI, browser, business queries or Duckdog there.

Then run one local lifecycle smoke against the actual HTTP directory URL:

```bash
rtk proxy "$MIGRATION_PYTHON" -I tools/leaf-dev/leaf.py http-smoke --delivery /path/to/task/delivery --base-url http://file-server/batch/revision --work-dir /path/to/task/http-smoke
```

An existing SSH local forward is an acceptable HTTP URL. The helper checks the
local ZIP checksum, downloads each remote ZIP once with the host's bounded
downloader, and checks its SHA256 against the accepted delivery. It installs that
exact downloaded file through public CLI into disposable local config, then
uninstalls it. Package and adapter validation belong to the host installer.
Only a sanitized `http-smoke.json` remains; no browser/profile or business query
is used. This exercises HTTP download plus local install/uninstall; it does not
make a second URL installation request.
This completes HTTP acceptance. Do not rerun production UAT, historical replay,
cache/Duckdog loops or rebuild a host merely because the same bytes traveled over
HTTP. A checksum/content mismatch stops delivery; changed business code requires
new affected-leaf evidence.

## 5. Review, integrate and finish

Refresh the graph and analyze against actual default master before review/commit.
Complete required tests/lint/format/doc checks and OCR with zero findings before
opening the batch PR. CI, code review, business acceptance and HTTP lifecycle are
separate evidence fields; one does not substitute for another. Preserve the
intentionally disabled OCR GitHub workflow; use the configured local OCR workflow.

Publish compact sanitized evidence in the batch issue/PR: chosen host and accepted ZIP
SHA256 values, counts, capture time/scope, native comparison differences, checks and any
limitations. Keep raw material private. Maintain current usage/contracts in the
package README/manifest; do not add dated development diaries, version-process
narratives, ADR copies or local per-batch acceptance histories.

Integrate reviewed batches serially against their exact accepted revision. A
leaf-only merge reuses the matching host and package acceptance: the coordinator
installs the accepted ZIPs into daily config and checks the installed identities. It does not repeat the business loop on master for unchanged bytes.
Host changes get their own distribution proof once. Preserve all accepted daily
installations and empty storage bindings; clean only task-owned business data,
cache, Parquet and private responses. Uninstall alone does not delete retained
Duckdog rows. Keep configuration, SSO/profile and unrelated worktrees/data.

Count a leaf only after its complete declared action set passes all required
gates. Transfer blocked whole leaves with evidence and a destination issue;
never shrink the total inventory or count an incomplete leaf delivered. The
coordinator records per-member status for partially delivered batches in the
[batch index](batches.md), then updates the parent ticket. Members without a
status inherit the batch status; a delivered batch cannot contain unfinished
members. Launching
another batch requires its own assignment; preparing these tools starts no leaves.
