# Dogopencli

An inquiry-only CLI for payment, collection, liquidity and FX operations, for one
person on one machine. Business inquiries read production; refresh and prune
change local cache only. Output formats are **json** and **text**.

## Install and configure

Python 3.10+ is required; live inquiries also require Google Chrome and platform
access. Install the project and explicitly copy the four pilot leaf packages:

```bash
python -m pip install -e .
dogopencli plugins install-pilots --config-dir ~/.config/dogopencli
```

An existing destination is never silently replaced. Replace or remove individual
folders directly under `<effective-config-directory>/plugins/<domain>/<leaf>/`.
The manifest is `leaf.json`; the complete dotted leaf name must match its folder.
Valid installed leaves become available on the next invocation, subject to the
domain switch. Invalid leaves appear as inventory diagnostics independently of
healthy leaves. This pilot introduces no package/version manager or hot loading.

`--config-dir` overrides `DOGOPENCLI_CONFIG_DIR`, then `DOGOPENCLI_CONFIG` (file),
then the default `~/.config/dogopencli/config.toml`.
A basic optional configuration is:

```toml
[cache]
ttl_hours = 72

[duckdog]
path = "duckdog.duckdb"
```

New leaf cache is `leaf-cache.sqlite3` beside the effective config. Duckdog defaults
to `duckdog.duckdb` there. First installation creates one empty `_record VARCHAR`
table per list leaf; later loading validates the binding and table. No business
records are imported. Removing a leaf cleans its cache after a successful scan,
preserving Duckdog tables/data. Malformed folders and unavailable roots do not
count as confirmed removal. Retained bindings validate existing data on reinstall.

## Query the pilots

All actions follow the domain and use the same dotted leaf name:

```bash
dogopencli login
dogopencli auth check
dogopencli domain list
dogopencli payment list sla.baselines --help --format text
dogopencli payment describe sla.baselines --format json
dogopencli payment list sla.baselines --live
dogopencli payment get sla.baselines NATIVE_ID
dogopencli payment refresh sla.baselines
dogopencli payment list sla.baselines --limit 0
dogopencli payment prune sla.baselines
```

Discover commands progressively with `dogopencli -h`, `dogopencli payment -h`,
`dogopencli payment list -h`, then `dogopencli payment list sla.baselines -h`.
Help uses `-h` or `--help` only; positional `help` commands are unsupported.
Root and navigation groups list their immediate children; executable command help
shows that invocation's arguments and options. Help reads local declarations
without loading adapters, initializing storage, changing caches, or opening a
browser. `describe` explains the leaf's business meaning and record fields;
adding `-h` documents the describe invocation instead.

| Domain | Leaf | Operations |
| --- | --- | --- |
| payment | sla.baselines | list, get |
| collection | cost | list |
| liquidity | reference.entities | list |
| fx | trade | list |

Only these four business leaves are installed by the pilot helper. Legacy leaf
command paths and top-level refresh/describe/prune paths are detached. Later
migration and old-code removal are tracked separately in
[#218](https://github.com/proletariat64/dogopencli/issues/218).

Default list is offline cache replay; a miss returns `CACHE_MISS`. `--live` does
not publish. Refresh atomically replaces the whole slot with an accepted nonempty
acquisition, including scope and quality evidence. Empty refresh, strict rejection
and hard failures preserve the previous rows and capture time. Different scopes
replace rather than accumulate. Get performs native detail lookup with no cache.

`--limit` defaults to 100; zero shows all remaining rows after `--offset`.
`--fields` projects native fields. Display controls do not truncate acquisition
or cache publication. Native values and unknown fields are preserved.

Business output has `data`, `meta`, `error`. Valid incomplete records return with
warnings; `--require-complete` rejects incomplete results. Unknown identity or
native total semantics remain unknown. `--require-fresh` rejects stale cache;
otherwise stale data remains readable and visibly marked. Supported offline
filters only select saved records and cannot extend their acquisition scope.

Collection cost uses its verified single-request capacity. FX individual-trade
identity and total semantics remain unproven: do not interpret its reported total
or a page count as proof of completeness. Read each leaf's help/description before
selecting a scope or interpreting business fields.

## Authentication and domain controls

Login targets enabled domains, using one dedicated Chrome profile and shared SSO
while verifying each application's session. Human role/MFA input stays manual.
Authentication in one domain does not prove another's access.

```bash
dogopencli login --domain payment --domain fx
dogopencli auth check --domain liquidity
dogopencli domain disable payment
dogopencli domain enable payment
```

`auth check` does not launch or repair Chrome. Disabling a domain preserves its
cache and recorded observations. Browser settings remain under `[auth]` (profile,
cdp_url, chrome_bin). Never use CDP ports 9330–9340 in this repository.

## Documentation editor

```bash
dogopencli gui --config-dir ~/.config/dogopencli
```

Open the printed localhost URL, select an installed leaf and choose **Edit
documentation**. The basic schema renders a structured form for summary, purpose,
limitations, parameter explanations, field meanings/units and examples. Technical
declarations are read-only in the form; direct manifest editing remains possible.
Preview uses the same renderer as CLI help/describe. Save validates and atomically
replaces the manifest; a revision conflict requires reload. Avoid simultaneous
manual writes during a save: unrelated editors do not participate in the GUI's
advisory lock. Changes apply on later invocations. The GUI provides no business
query, login, import or package-management buttons.

## Development

`make bootstrap` prepares the worktree environment, code graph and isolated
Chrome/CDP profile, then checks enabled domains' authentication without starting
SSO. Domain auth failures are reported in the final copyable startup prompt;
they do not fail browser setup. Browser setup failures still fail bootstrap.
Run `source tmp/bootstrap-browser/env.sh` to activate its configuration in your
shell. To also log in, use `make bootstrap BOOTSTRAP_DOMAIN=payment` (or
`liquidity` / `fx`); explicit login requires successful headless verification.

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
ruff check .
ruff format --check .
make doc-guard
```

Tests exercise the new CLI with scripted browser/CDP responses and isolated real
storage. Obsolete legacy command assertions are replaced; native parser, cache,
transport and authentication checks remain. Production UAT and GUI interaction
are separate evidence from automated tests.

See [CONTEXT.md](CONTEXT.md), [ADRs](docs/adr/),
[implementation spec](https://github.com/proletariat64/dogopencli/issues/219) and
[installed-leaf decision](docs/adr/0022-installed-leaf-pilots.md).
