# Dogopencli

An inquiry-only CLI for payment, collection, liquidity and FX operations, intended
for one person on one machine. Install the leaves you need, discover their commands
with progressive help, and query live data or replay a local snapshot.

**Developing or migrating a leaf?** Start with [tools/leaf-dev](tools/leaf-dev/README.md)
for the handbook, interfaces, workflow, runnable example and helpers.

## Get started

Python 3.10+ is required. Live inquiries also require Google Chrome and access to
the relevant platform application. From a checkout:

```bash
uv sync --extra dev
uv run dogopencli -h --format text
uv run dogopencli plugins list --format text
uv run dogopencli domain list --format text
```

Examples below use `dogopencli`; prefix it with `uv run` when using the checkout's
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
There is no update, replace or plugin-version command. The former
`plugins install-pilots` entry point has been removed.

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

Valid incomplete results remain usable with warnings. `--require-complete` rejects
incomplete acquisitions; unknown identity or total semantics remain unknown.
`--require-fresh` rejects stale cache; otherwise stale records remain readable and
marked. Supported offline filters select saved rows and do not establish backend
absence or extend the captured scope. FX individual-trade identity/total semantics
remain unproven; collection cost has a verified single-request capacity boundary.

Login uses a dedicated Chrome profile and shared SSO, verifying each enabled
application independently. Human role/MFA input stays manual. `auth check` does not
launch or repair Chrome. Domain enable/disable controls access and preserves cache
and observations. Browser settings live under `[auth]`; never use CDP ports
9330–9340 in this repository.

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
| `duckdog.duckdb` | Default retained dataset database; configurable via `[duckdog].path`. |

Each list leaf initializes one empty `_record VARCHAR` table on first installation.
Subsequent loading/reinstallation validates the retained binding and table.
Duckdog and cache are shared host foundations, not separately installed plugins.

## Edit leaf documentation

```bash
dogopencli gui
```

Open the printed localhost URL and choose an installed leaf's **Edit documentation**
form. Preview shares CLI rendering; save validates and atomically updates the
installed `leaf.json`. Stale edits require reload. Technical declarations are
read-only in the form. README, source directories and original ZIPs are independent
and are not synchronized. Changes apply on later invocations. The GUI has no
business-query, login, import or package-management buttons.

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

Further reading: [documentation index](docs/README.md), [domain vocabulary](CONTEXT.md),
[plugin lifecycle spec](https://github.com/proletariat64/dogopencli/issues/239),
[domain component guide](docs/agents/domain-components.md) and
[packaging helper](tools/leaf-dev/plugin-helper.md).
