# Dogopencli

An inquiry-only CLI for payment, collection, liquidity, and FX operations.
Dogopencli is designed for one person on one machine: query supported platform
endpoints through a dedicated Chrome session, save a temporary local result, and
read it offline as JSON or a table.

Business operations are read-only. Login manages local browser authentication;
refresh and prune change local caches.

## Quick start

You need Python 3.10 or newer. Live queries also require Google Chrome, access to
the relevant operations platform, and a human to complete company SSO.
Help, data descriptions, and existing cached results work offline.

### Install

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
dogopencli --version
```

For a packaged installation, download a wheel from
[Releases](https://github.com/proletariat64/dogopencli/releases) and install the
downloaded file with `python -m pip install /path/to/downloaded.whl`.

### Configure a source

Create `~/.config/dogopencli/config.toml` and enable the source you want to query.
For example, to query payment transaction-cost configurations:

```toml
[sources.payment_cost]
kind = "cdp"
```

Source keys for payment and collection are listed below. Liquidity queries and FX
trade queries do not require entries under `[sources]`.

### Log in, refresh, and read

```bash
dogopencli login
dogopencli auth check
dogopencli refresh payment cost
dogopencli payment cost list --format table
```

`login` checks the selected domain, opens headed Chrome when human SSO is needed,
and verifies authentication again after switching to headless Chrome. The default
domain is `payment`; collection queries use that session too. For other domains:

```bash
dogopencli login --domain liquidity
dogopencli auth check --domain liquidity
dogopencli login --domain fx
dogopencli auth check --domain fx
```

`auth check` inspects the existing session. It does not launch or repair Chrome.
Authentication in one domain does not establish access to another.

## Discover commands and data

Use the installed CLI as the current command reference:

```bash
dogopencli help --format text
dogopencli help collection --format text
dogopencli help liquidity cash balances list --format text
dogopencli describe liquidity cash balances list --format text
dogopencli snapshot
dogopencli snapshot liquidity --format json
```

`help` documents parameters, defaults, constraints, effects, and errors. It
returns JSON by default; `--format text` is intended for reading in a terminal.
`describe` provides field definitions, JSON Schema, and evidence about the data
without fetching business records.

`snapshot` shows the installed command tree and local cache metadata without
starting a browser or querying the backend. A discoverable command may be
unsupported or retired; those commands return `UNSUPPORTED_CAPABILITY` rather
than attempting a request. Availability describes implementation support, not
current authentication or backend health.

## Query modes and cache behavior

| Action | Behavior |
| --- | --- |
| List, or `fx trade`, without `--live` | Replay the saved temporary result offline. |
| Query with `--live` | Query through an existing authenticated browser without replacing the business-result cache. |
| `refresh <path>` | Acquire data and atomically replace that query's cache when the result is nonempty and accepted. |
| Supported `get` | Query native details online; details are not cached. |
| `<path> prune` | Delete only that query's temporary cache, offline. |

Each enabled list-like query owns one temporary result, including its acquired
scope and quality evidence. A nonempty refresh for another range replaces the
previous range. A valid empty refresh, hard failure, or strict completeness
rejection preserves the previous result. After an empty refresh, an offline read
can therefore still return the older nonempty result; check the refresh metadata.

An offline query with no business filters replays the saved scope. Explicit
filters apply only where the command documents a reliable local mapping. Queries
never refresh implicitly or fall back to live access on a cache miss.

The cache is not a historical store. External **duckdog** datasets own imports,
history, merging, and analysis. See the
[cache decision](docs/adr/0020-temporary-query-cache-and-duckdog.md) for the current
contract and the cash-account composite-query exception.

### Display and quality controls

Most lists accept these options; check each command's help for exact support:

| Option | Meaning |
| --- | --- |
| `--format json` / `--format table` | Machine-readable output, or a terminal table; JSON is the default. |
| `--limit N --offset N` | Display window; defaults are 100 and 0. `--limit 0` displays all remaining matches. |
| `--fields id,currency` | Select top-level record fields while retaining quality metadata. |
| `--require-fresh` | Reject cached results older than the configured TTL. |
| `--require-complete` | Reject results without the required coverage proof; an incomplete refresh is not published. |

Display limits do not change backend collection budgets or prove full coverage.
Usable incomplete results can succeed with warnings by default. Freshness and
completeness are independent, and the capture time does not establish the source
record's business observation time.

## Supported areas

### Payment and collection

The table omits the `dogopencli` prefix. Configure each source as
`[sources.<key>]` with `kind = "cdp"` unless using the channel snapshot alternative.

| Area | Query | Refresh | Source key |
| --- | --- | --- | --- |
| Payment channels | `payment channel list` | `refresh payment channel` | `payment_channel` |
| Payment costs | `payment cost list` | `refresh payment cost` | `payment_cost` |
| Payment SLA baselines | `payment sla baselines list` / `get --id ID` | `refresh payment sla` | `payment_sla` |
| Same-bank transfer rules | `payment rules same-bank-transfer list` | `refresh payment rules same-bank-transfer` | `payment_rules_same_bank_transfer` |
| Cost-reduction rules | `payment rules cost-reduction list` | `refresh payment rules cost-reduction` | `payment_rules_cost_reduction` |
| Retry rules | `payment rules retry list` | `refresh payment rules retry` | `payment_rules_retry` |
| Bank-switch rules | `payment rules bank-switch list` | `refresh payment rules bank-switch` | `payment_rules_bank_switch` |
| PTR cases | `payment ptr cases list` | `refresh payment ptr cases` | `payment_ptr_cases` |
| PTR orders | `payment ptr orders list` | `refresh payment ptr orders` | `payment_ptr_orders` |
| Collection costs | `collection cost list` | `refresh collection cost` | `collection_cost` |
| Collection SLA configurations | `collection sla configs list` / `get --id ID` | `refresh collection sla` | `collection_sla` |
| Collection VA rules | `collection va rules list` / `get --id ID` | `refresh collection va` | `collection_va` |
| VA capacity | `collection va capacity list` | `refresh collection va capacity` | `collection_va_capacity` |
| Clearing systems | `collection clearing-system list` | `refresh collection clearing-system` | `collection_clearing_system` |
| Card templates | `collection card-template list` | `refresh collection card-template` | `collection_card_template` |
| Account-isolation rules | `collection account-isolation list` | `refresh collection account-isolation` | `collection_account_isolation` |

Cost queries return fee configurations, not actual transaction charges. SLA
queries return configured targets, not observed payment arrival times. PTR
queries read existing cases and orders; they do not start trial runs. PTR order
queries and refreshes require a bounded update-time range; consult their help.

Payment channel queries also support an explicitly configured private snapshot
source. This is a bounded alternative dataset, not proof of complete production
coverage; see [ADR 0005](docs/adr/0005-channel-snapshot-source.md).

### Liquidity

Liquidity covers implemented queries under `cash`, `forecast`, `operations`,
`investment`, `risk`, `rules`, `network`, `reference`, `pricing`, and `ledger`.
Some paths remain discoverable but do not execute. Use `snapshot liquidity` to
check availability and `help` to inspect the specific query.

For example, refresh balances and then read the saved result:

```bash
dogopencli refresh liquidity cash balances
dogopencli liquidity cash balances list --format table
dogopencli liquidity cash balances list --live --limit 0
dogopencli liquidity cash balances prune
```

The online cash-balance default entity is `ALIPAYGM`. Paired `--from-date` and
`--to-date` select inclusive daily observations in GMT+08; omitting them selects
latest snapshots. Daily `balance` means closing book balance. Amounts and missing
values retain their source meaning; unavailable balances are not filled with zero.

Online `--entity ANY` uses native `instId` values from a configured read-only
duckdog selector. It freezes that finite selection for the acquisition. Offline
replay uses the saved selection without reopening duckdog.

### FX individual trades

`fx trade` queries FX Shield individual `RiskStandardTrade` records:

```bash
dogopencli fx trade --live --trade-id YOUR_TRADE_ID
dogopencli refresh fx trade
dogopencli fx trade --format table
dogopencli fx trade prune
```

Replace the example ID with a real value. Online queries without an ID or dates
use the previous complete GMT+08 day. Explicit dates must be paired; bcode,
customer-ID, and scene filters require time bounds. Collection is limited to
100 pages and 120 seconds, independently of the display limit.

Native record identity and total-count semantics remain unverified, so FX results
remain incomplete and `--require-complete` rejects them. Offline FX business
filters are not supported; use live queries or refresh for a different scope.

## Configuration and local state

| Setting | Default |
| --- | --- |
| Configuration file | `~/.config/dogopencli/config.toml` |
| Query cache | `~/.local/share/dogopencli/cache.sqlite3` |
| Dedicated Chrome profile | `~/.local/share/dogopencli/chrome/` |
| CDP port | `9222` |
| Cache TTL | 72 hours |

Configuration precedence is an explicit authentication `--config-dir`, then
`DOGOPENCLI_CONFIG_DIR`, then `DOGOPENCLI_CONFIG`, then the default location.
The first two select a directory; `DOGOPENCLI_CONFIG` selects a file.

Optional cache settings:

```toml
[cache]
path = "/absolute/path/to/cache.sqlite3"
ttl_hours = 72
```

Keep the cache on a local Linux filesystem. Its SQLite WAL and POSIX locking
requirements exclude Windows DrvFS/9p and network filesystems. Concurrent refresh
conflicts return `LOCKED`.

Use a dedicated browser profile with only one Chrome process owning it. Do not
use CDP ports **9330–9340**. `dogopencli logout` clears and verifies the dedicated
local authentication; it does not delete query caches or revoke company-wide SSO.
Keep cookies, tokens, profiles, private datasets, and raw production responses out
of Git and shared logs.

### Optional duckdog selectors

Install DuckDB support only when using features that read external selectors:

```bash
python -m pip install -e '.[duckdog]'
```

For online cash balances with `--entity ANY`, configure an existing database and
an entity relation or view containing valid native `instId` values:

```toml
[duckdog]
path = "/absolute/path/to/duckdog.duckdb"

[duckdog.selectors]
"liquidity/reference/entities" = "entities"
```

Relative database paths resolve against the configuration file's directory.
Dogopencli opens this input read-only; it does not create a database, accept
arbitrary SQL, or automatically import query results into duckdog. Other selector
consumers document their requirements in their command help and design contracts.
Ordinary offline cache reads do not need DuckDB.

## Using results in scripts and agents

Business query JSON uses `data`, `meta`, and `error`. Check the exit status and
`error` before consuming records, then inspect `meta` for scope, freshness,
completeness, counts, and warnings. A successful exit alone does not prove full
coverage. `--fields` preserves quality metadata.

Help and descriptions return their own document formats; authentication commands
use a separate output envelope. Business queries generally exit `0` on success,
`1` on runtime failure, `2` on argument or configuration errors, and `130` on
interruption. Authentication commands use `1` for argument and runtime errors.
Diagnostics go to stderr.

Field names, identifiers, and units are specific to each contract. Consult
`describe` before joining records or interpreting amounts and timestamps. Keep
null, missing values, empty strings, and zero distinct.

| Error | Next step |
| --- | --- |
| `CONFIG_ERROR` | Check the configuration path and required source entry. |
| `CACHE_MISS` / `CACHE_STALE` | Explicitly refresh the relevant query. |
| `INCOMPLETE_RESULT` | Inspect coverage warnings and the command's scope constraints. |
| `AUTH_REQUIRED` / `BROWSER_UNAVAILABLE` | Run `login` for the relevant domain and check Chrome diagnostics. |
| `LOCKED` | Wait for the active operation to finish and retry. |
| `BUSINESS_QUERY_FAILED` / `INVALID_RESPONSE` | Investigate the backend failure or contract mismatch; do not treat it as an empty result. |
| `UNSUPPORTED_CAPABILITY` | Check command availability; the path is not executable in this version. |

## Development

Each worktree uses its own virtual environment and source binding. With Python
3.10+, uv, rtk, code-review-graph, and Google Chrome installed, run:

```bash
rtk proxy make bootstrap
source tmp/bootstrap-browser/env.sh
```

Bootstrap installs locked dependencies, updates the current worktree's code
graph, and provisions a dedicated browser, configuration, and cache under the
ignored `tmp/bootstrap-browser/` directory. It waits for human SSO when needed
and reports success only after headless authentication verification. Select a
different domain with `make bootstrap BOOTSTRAP_DOMAIN=liquidity` or
`BOOTSTRAP_DOMAIN=fx`. It does not copy another profile's cookies.

Source the generated environment file before running CLI commands in that shell;
`make` cannot update its parent shell. Close the worktree's dedicated Chrome
before removing the worktree.

Run the repository checks:

```bash
rtk proxy make test
rtk proxy make lint
rtk proxy make doc-guard test-doc-guard
```

Tests use sanitized fixtures, fake browser responses, and temporary local caches.
Local checks and CI do not establish production acceptance for every command.
Production validation requires the relevant permissions and stays inquiry-only.

## Documentation

- [Documentation index](docs/README.md): specifications, contracts, research, and acceptance evidence.
- [Domain vocabulary](CONTEXT.md): business objects, identities, units, and distinctions.
- [Architecture decisions](docs/adr/): implementation decisions and their scope.
- [Changelog](CHANGELOG.md): behavior changes and migration notes.
- [Contributor instructions](AGENTS.md): repository workflows and constraints.
- [GitHub Issues](https://github.com/proletariat64/dogopencli/issues): requirements and defects.
- [Releases](https://github.com/proletariat64/dogopencli/releases): published packages and release notes.

Contract and acceptance reports record observations for a particular date,
account, and scope. Consult those reports for production evidence; command
availability alone does not establish current backend coverage.
