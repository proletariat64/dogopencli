# Dogopencli

An inquiry-only CLI for payment, collection, liquidity and FX operations, intended
for one person on one machine. Install the leaves you need, discover their commands
with progressive help, and query live data or replay a local snapshot.
Use the [durable workflow](docs/agents/export-import-workflow.md) to export an
exact native scope online and explicitly import it into local Duckdog offline.
Query cache, saved exports and committed imports are separate outcomes.

**Developing or migrating a leaf?** Start with [tools/leaf-dev](tools/leaf-dev/README.md)
for the handbook, interfaces, workflow, runnable example and helpers.

## Get started

### Install the CLI

With [uv](https://docs.astral.sh/uv/getting-started/installation/) available, run
the installer from a checkout (Linux/macOS, Bash):

```bash
./install.sh install
./install.sh update
./install.sh uninstall
```

`install` always overwrites the single installed program, even at the same version.
`update` resolves/prepares the replacement through uv before replacing the
program; it no longer pre-uninstalls. No old versions or rollback copies are kept.
Uninstall preserves configuration, browser login, installed business leaves,
cache and Duckdog data. The installer does not install Chrome or log in.

The installer selects Python 3.12 through uv and installs runtime dependencies
without development extras. It reuses the uv cache and reinstalls only the CLI,
retaining compatible dependencies. It installs a snapshot,
so later checkout edits require another install. The default uv tool directory on
Linux is `~/.local/share/uv/tools/dogopencli`, with the command in `~/.local/bin`.
Use `UV_TOOL_DIR` / `UV_TOOL_BIN_DIR` to change these locations; use the same
settings for all three actions. The script prints the command path and any PATH
setup needed.

To install a delivered wheel or another checkout, pass its source explicitly:

```bash
./install.sh install /path/to/dogopencli-VERSION-py3-none-any.whl
./install.sh update /path/to/checkout
./install.sh install https://example.com/dogopencli-VERSION-py3-none-any.whl
```

Installed uv tools also support `dogopencli uninstall` and
`dogopencli update --source /path/to/wheel-or-checkout`. Release-installer users
can use `dogopencli update --to VERSION` to download a checksummed version from
the recorded AntCode/GitHub origin without keeping a checkout or installer.
See [release and publication](docs/agents/releasing.md) for curl installation,
CLI Release targets, plugin-site deployment and plugin publication commands.

### Develop from source

Python 3.12+ is required. Live inquiries also require Google Chrome and access to
the relevant platform application. From a checkout:

```bash
uv venv --python 3.12
uv sync --extra dev
uv run dogopencli -h --format text
uv run dogopencli plugins list --format text
uv run dogopencli domain list --format text
```

The examples below use `dogopencli`; prefix it with `uv run` when using the checkout's
environment. An editable pip installation is also supported:
`python -m pip install -e '.[dev]'`.

Enable the domain if necessary, then explicitly install one bundled leaf:

```bash
dogopencli domain enable payment
dogopencli plugins install bundled:payment.sla.baselines
dogopencli payment -h --format text
dogopencli payment list -h --format text
dogopencli payment list sla.baselines -h --format text
dogopencli payment describe sla.baselines --format text
```

Bundled availability does not mean installed. The current bundled inquiries are:

| Domain | Dotted leaf name | Business operations |
| --- | --- | --- |
| payment | sla.baselines | list, get |
| collection | cost | list |
| liquidity | reference.entities | list |
| fx | trade | list |

Each list also receives host-owned refresh and prune commands; describe is shared.
Only installed declarations appear in domain/operation help. Use `-h` or `--help`;
positional `help` commands are unsupported. Navigation help shows immediate
children; leaf-action help shows that invocation's arguments and options.

## Install and remove leaves

Install accepts exactly one local directory, ordinary ZIP, direct HTTP(S) ZIP URL
or bundled identity:

```bash
dogopencli plugins install /path/to/leaf-directory
dogopencli plugins install /path/to/leaf.zip
dogopencli plugins install https://example.com/leaf.zip
dogopencli plugins install bundled:collection.cost
dogopencli plugins list --format text
dogopencli plugins uninstall collection.cost
```

Source names are arbitrary; identity comes from the root `leaf.json`. Install
creates an independent snapshot, validates the adapter interface and registers or
validates storage. The domain must already be enabled. Normal installation does
not log in, acquire business data or run production UAT.

Existing identities are rejected without overwriting installed code or local
manifest edits. To reinstall deliberately, uninstall then install. Uninstall is
noninteractive and idempotent for an absent leaf; it also works for broken or
disabled leaves. It removes the installed files and owned temporary query cache,
preserving Duckdog data, binding history, credentials and original source packages.
There is no plugin update, replace or plugin-version command. CLI updates use
the separate installed-host lifecycle commands described above.

`plugins list` reports bundled availability, installed declarations and diagnostics.
List and help read declarations without loading adapters, initializing storage,
cleaning caches or opening a browser. Installation is not proof of production
qualification.

## Authenticate and query

```bash
dogopencli login --domain payment
dogopencli auth check --domain payment
dogopencli payment list sla.baselines --live
dogopencli payment get sla.baselines NATIVE_ID
dogopencli payment refresh sla.baselines
dogopencli payment list sla.baselines --limit 0
dogopencli payment prune sla.baselines
```

Replace `NATIVE_ID` with an actual identity obtained from the list. Read the leaf's
help for query parameters and describe for business meanings and limitations.

| Command | Behavior |
| --- | --- |
| `list` | Replays the saved local snapshot; no snapshot returns `CACHE_MISS`. |
| `list --live` | Acquires current data without publishing cache. |
| `get` | Reads native detail for a supported leaf; no detail cache. |
| `refresh` | Acquires data and publishes an accepted nonempty snapshot. |
| `prune` | Clears that list leaf's temporary query cache. |
| `describe` | Explains the leaf, record fields, identity and limitations. |

Refresh replaces the entire saved scope, rather than accumulating history. Empty
acquisition, strict-completeness rejection and hard failure preserve the previous
rows and capture time. Queries and refresh do not import records into Duckdog.

Business output uses `data`, `meta`, `error`; formats are `json` (default) and
`text`. `--limit` defaults to 100; zero displays all remaining rows after `--offset`.
`--fields` projects native fields. These display options do not truncate acquisition
or cache publication. Native values and unknown fields are retained.

Explicitly qualified usable incomplete results return with warnings and exit 0. `--require-complete` is available on every List, Get and Refresh and rejects
incomplete acquisitions without candidate data. It does not expand scope or
change freshness. Unknown identity or total semantics remain unknown. Default
Refresh may publish qualified nonempty incomplete results with their gaps;
[shared result policy](docs/agents/result-policy.md) defines diagnostics, process
statuses and publication metadata.
`--require-fresh` rejects stale cache; otherwise stale records remain readable and
marked. Supported offline filters select saved rows and do not establish backend
absence or extend the captured scope. FX uses the native transaction number
`uniqueId` as record identity and checks unique arrivals against native `totalCount`;
collection cost has a verified single-request capacity boundary.

Login uses a dedicated Chrome profile and shared SSO, verifying each enabled
application independently. Human role/MFA input stays manual. `auth check` does not
launch or repair Chrome. Domain enable/disable controls access and preserves cache
and observations. Browser settings live under `[auth]`; never use CDP ports
9330–9340 in this repository.

## Export and import

Prepare one exact inquiry, execute its Export Run, then inspect the saved export
before preparing an offline import:

```bash
dogopencli workflow plan create --leaf payment.sla.baselines --parameters '{}'
dogopencli workflow plan show --plan PLAN_ID
dogopencli workflow export create --plan PLAN_ID
dogopencli workflow export run --run RUN_ID
dogopencli workflow export show --export EXPORT_ID
dogopencli workflow import plan --export EXPORT_ID --action preserve
dogopencli workflow import apply --plan IMPORT_PLAN_ID
dogopencli workflow observation show --export EXPORT_ID
```

Replace each placeholder with the ID returned by the corresponding command.
Parameter keys use CLI spelling without `--`; repeatable values use arrays.
Completed exports retain records and acquisition evidence before display limits
or field projection. `export show` proves acquisition; `observation show` reads
the imported rows and receipt from Duckdog.

`preserve` adds a scoped observation without changing current dataset rows.
Reapplying the same export/action/destination is idempotent. `replace-full`
publishes a complete exact query as current data; inspect its import preview
before applying it. Complete-empty replacement clears that namespace.

Incomplete exports remain inspectable. Importing one requires an explicit
leaf-declared full-List `preserve` qualification covering the entire artifact;
it does not permit current-data replacement. Get, detail-composed and historical
exports do not use this exception. See the
[workflow guide](docs/agents/export-import-workflow.md) for the full contract.

Historical coverage, [keyed reconciliation](docs/agents/keyed-history.md),
[range replacement](docs/agents/range-replacement.md) and
[repair](docs/agents/repair-workflow.md) require their own declared scope and
evidence. A date filter does not establish daily or all-time coverage. Get-only
exports without a registered dataset binding cannot be imported into Duckdog.

### Observe and repeat work

In a second terminal, inspect or watch one exact task:

```bash
dogopencli workflow export status --run RUN_ID
dogopencli workflow export watch --run RUN_ID
dogopencli workflow import status --plan IMPORT_PLAN_ID
dogopencli workflow import watch --plan IMPORT_PLAN_ID
dogopencli workflow status
```

Status and watch read saved metadata offline. Watch supports `--snapshot` for
one frame and `--until-settled` to stop after settlement; Ctrl+C stops the observer.
These commands do not execute an export or import.

Saved targets retain inquiry intent through `workflow target create`, `plan`
and `run`. A `following` policy freezes a new cutoff at each explicit planning
call; it is not an automatic scheduler. Target execution exports data, while
import remains a separate explicit action.

## Configuration and local storage

Configuration precedence is `--config-dir`, `DOGOPENCLI_CONFIG_DIR`,
`DOGOPENCLI_CONFIG` (a file), then `~/.config/dogopencli/config.toml`.
For an isolated workspace, pass the same `--config-dir` to every command.

```toml
[cache]
ttl_hours = 72

[duckdog]
path = "duckdog.duckdb"
```

Locations relative to the effective configuration directory:

| Location | Purpose |
| --- | --- |
| `plugins/<domain>/<dotted-leaf>/` | Installed manifest, adapter and resources. |
| `leaf-registry.sqlite3` | Persistent storage bindings and ownership history. |
| `leaf-cache.sqlite3` | Temporary query snapshots, one slot per list leaf. |
| `workflow/` | Plans, execution metadata and immutable export artifacts. |
| `duckdog.duckdb` | Default retained dataset database; configurable via `[duckdog].path`. |

Each list leaf initializes one empty `_record VARCHAR` table on first installation.
Subsequent loading/reinstallation validates the retained binding and table.
Duckdog and cache are shared host foundations, not separately installed plugins.

## Edit leaf documentation

```bash
dogopencli gui
```

Open the printed localhost URL. Domain cards on the left show local enablement,
recorded authentication and installed query counts. Select a domain to view its
query cards on the right; search matches query names, descriptions and operations.
Cards show saved-row counts, capture times and the last query outcome separately.
Missing saved data and unavailable cache metadata have distinct labels; saved-row
counts describe the last stored snapshot, not total available data or offline readiness.
Choose **Edit documentation** to open the documentation workspace: structured editing on the left,
reading or CLI text preview on the right. Changes update the preview without
saving; **Save documentation** validates and atomically updates the installed `leaf.json`.
Stale edits require reload, and leaving a draft asks before discarding changes.
Technical declarations are available in a read-only disclosure. README, source
directories and original ZIPs are independent and are not synchronized. Changes apply on later invocations. The GUI has no
business-query, login, import or package-management buttons.

Under **Console**, select **System** (`info & storage`) to inspect configuration,
installation, temporary Cache snapshots and retained Duckdog datasets. The panel
is read-only. Expand storage sections to filter or search leaf/dataset metadata;
individual business records are excluded. Cache rows describe saved snapshots,
while Duckdog rows are explicitly catalog estimates. Missing resources and
unavailable metadata remain distinct; **Reload information** rereads local metadata.

## Develop and migrate

Use the [development handbook](tools/leaf-dev/handbook.md) for adapter contracts
and the [migration procedure](tools/leaf-dev/workflow.md) with the assigned
batch ticket for scope and acceptance. Standalone migration packages live under
root `leaf_packages/`; four bundled pilot resources remain under the host source.
Each inquiry requires its own native business proof. Unsupported placeholders
are not automatic migration targets.

```bash
uv run python -m pytest -q
uv run ruff check .
uv run ruff format --check .
make doc-guard
```

`make bootstrap` prepares the worktree environment, code graph and isolated Chrome
profile, then checks authentication without starting SSO. Activate its settings
with `source tmp/bootstrap-browser/env.sh`. For explicit login use
`make bootstrap BOOTSTRAP_DOMAIN=payment` (or `liquidity` / `fx`). Read repository
browser instructions before browser/authentication work. Local tests, review,
production business UAT, merge and release are separate evidence.

## Release and publication

CLI releases require a clean, attached `master` matching freshly fetched
GitHub `origin/master`. Commit and push the intended source changes first;
include matching versions in `pyproject.toml`, `src/dogopencli/__init__.py` and
the root package entry in `uv.lock`. Preserve unrelated local work in a stash
or a separate checkout before releasing. Untracked files also block release.

```bash
make release DRY_RUN=1
make release TARGET=antcode
# Or select GitHub as the artifact host:
make release TARGET=github
```

AntCode is the default artifact host; GitHub remains the source and tag origin.
Dry run reports the plan only. A real release runs checks and an isolated
install/update/uninstall smoke test, pushes the source tag, then publishes and
verifies release assets. The command never increments the version or pushes
source commits. Use `RETRY=1` when retrying the same tag or publishing it to a
second provider.

CLI release, plugin-site deployment and plugin ZIP publication are independent.
For provider login, version-pinned curl installation, `release-site`,
`deploy-site`, `release-plugin` and `publish-plugin`, read
[release and publication](docs/agents/releasing.md). Site deployment runs on the
target host and has its own service and routing prerequisites.

Further reading: [documentation index](docs/README.md), [domain vocabulary](GLOSSARY.md),
[plugin lifecycle spec](https://github.com/proletariat64/dogopencli/issues/239),
[domain component guide](docs/agents/domain-components.md) and
[leaf development tool](tools/leaf-dev/README.md).
