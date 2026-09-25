# Collection cost CLI argument UAT

Observed: 2026-09-26
Scope: general
Status: snapshot

## Result and execution boundary

All **84 CLI acceptance cases passed** on branch `feat/21-collection-cost`, local version `0.1.3`. This expands the initial three UAT checks in [implementation verification](2026-09-26-collection-cost-verification.md). Coverage includes every declared collection cost list option, help aliases and formats, refresh, describe, representative boundaries, invalid values and conflicting options. It does not claim every possible argument permutation or every production failure mode.

The runner launched the actual installed entry point through `uv run --no-sync dogopencli` in separate processes. `--no-sync` kept dependency resolution outside UAT; all listed arguments reached dogopencli. All business requests used the same fixed read-only collection transaction-cost inquiry. The matrix contains seven live-list cases and one refresh case; an additional read-only refresh rebuilt the temporary cache when continuing interrupted harness execution. Other cases used the private cache, offline help/describe, local fault setup or argument rejection.

Command output was captured in memory for assertions; this report contains no business rows, account values or credentials. Refresh used a private temporary directory under ignored `tmp/`. Cache-only cases pointed their temporary auth configuration at an unavailable localhost port to detect accidental browser dependence. Help and describe used a nonexistent config path. Temporary cache and configuration were removed after the run; the user's normal cache/configuration were not changed by this UAT.

Freshness failure was induced by setting TTL=0 only in temporary configuration. Incompleteness rejection was checked by changing only `backend_complete` in the temporary local cache, not by altering production data or claiming a naturally incomplete backend response. These are local-state UAT cases. Production auth/permission failures, transport interruption and malformed backend responses remain covered by synthetic SIT rather than intentionally induced production failures.

The harness initially mishandled the JSON argument-error envelope for invalid `--format text`, then a missing `--format` value. Both were harness parsing errors, not CLI defects. The harness was corrected; passing cases were retained and all remaining cases completed using a new private cache. Results below aggregate the completed cases across these executions. No application code changes were needed.

## Argument coverage

| Surface | Successful cases | Boundary and rejection cases |
| --- | --- | --- |
| Default list | Default limit 100/offset 0, cache source, correct quality metadata | Empty cache in JSON and table modes |
| `--limit` | 1, 2, above total; live and cached | Zero, negative, noninteger, missing value; conflict with `--all` |
| `--offset` | 0, 1, exactly total, beyond total; live and cached | Negative, noninteger, missing value; conflict with `--all` |
| `--all` | Complete live/cached lists in JSON/table | Explicit limit or offset rejected |
| `--live` | Defaults, display window, all rows, projections, JSON/table, quality flags | No cache created by live cases; `--live=false` rejected |
| `--require-fresh` | Fresh cache and live, including live while cache TTL=0 | Stale cache rejected in JSON/table; value assignment rejected |
| `--require-complete` | Complete live/cached data, JSON/table | Incomplete temporary metadata rejected in JSON/table; value assignment rejected |
| `--format` | Explicit JSON and table; quality header/row counts checked | Unsupported text/yaml and missing value; table runtime-error stderr |
| `--fields` | Multiple fields, nested rate configuration preserved, whitespace trimmed, absent field omitted; live/cache and table | Empty, whitespace/comma-only and missing value |
| `-h`, `--help` | All relevant groups/leaves, JSON/text, no valid config | Explicit `help collection cost list` also succeeds |
| `refresh collection cost` | Explicit complete refresh to temporary cache | Unsupported `--live` and `--format json` rejected; output format is fixed JSON |
| `describe collection cost list` | `--format json` and `--format text`, no valid config | Query flag `--live` and output format table rejected |
| Unverified options | No arbitrary cost type or bank filter | `--cost-type`, `--bank-account` rejected |

## Executed cases

Commands below use `uv run dogopencli` for normal manual use. All commands were isolated by temporary configuration in the runner. Cases marked local state require the setup described above; do not modify a normal cache to reproduce them.

| ID | Case | Mode | Command | Expected exit / error | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | help collection -h json | offline help | `uv run dogopencli collection -h --format json` | 0 | PASS |
| 2 | help collection -h text | offline help | `uv run dogopencli collection -h --format text` | 0 | PASS |
| 3 | help collection --help json | offline help | `uv run dogopencli collection --help --format json` | 0 | PASS |
| 4 | help collection --help text | offline help | `uv run dogopencli collection --help --format text` | 0 | PASS |
| 5 | help collection cost -h json | offline help | `uv run dogopencli collection cost -h --format json` | 0 | PASS |
| 6 | help collection cost -h text | offline help | `uv run dogopencli collection cost -h --format text` | 0 | PASS |
| 7 | help collection cost --help json | offline help | `uv run dogopencli collection cost --help --format json` | 0 | PASS |
| 8 | help collection cost --help text | offline help | `uv run dogopencli collection cost --help --format text` | 0 | PASS |
| 9 | help collection cost list -h json | offline help | `uv run dogopencli collection cost list -h --format json` | 0 | PASS |
| 10 | help collection cost list -h text | offline help | `uv run dogopencli collection cost list -h --format text` | 0 | PASS |
| 11 | help collection cost list --help json | offline help | `uv run dogopencli collection cost list --help --format json` | 0 | PASS |
| 12 | help collection cost list --help text | offline help | `uv run dogopencli collection cost list --help --format text` | 0 | PASS |
| 13 | help refresh collection -h json | offline help | `uv run dogopencli refresh collection -h --format json` | 0 | PASS |
| 14 | help refresh collection -h text | offline help | `uv run dogopencli refresh collection -h --format text` | 0 | PASS |
| 15 | help refresh collection --help json | offline help | `uv run dogopencli refresh collection --help --format json` | 0 | PASS |
| 16 | help refresh collection --help text | offline help | `uv run dogopencli refresh collection --help --format text` | 0 | PASS |
| 17 | help refresh collection cost -h json | offline help | `uv run dogopencli refresh collection cost -h --format json` | 0 | PASS |
| 18 | help refresh collection cost -h text | offline help | `uv run dogopencli refresh collection cost -h --format text` | 0 | PASS |
| 19 | help refresh collection cost --help json | offline help | `uv run dogopencli refresh collection cost --help --format json` | 0 | PASS |
| 20 | help refresh collection cost --help text | offline help | `uv run dogopencli refresh collection cost --help --format text` | 0 | PASS |
| 21 | help describe collection cost list -h json | offline help | `uv run dogopencli describe collection cost list -h --format json` | 0 | PASS |
| 22 | help describe collection cost list -h text | offline help | `uv run dogopencli describe collection cost list -h --format text` | 0 | PASS |
| 23 | help describe collection cost list --help json | offline help | `uv run dogopencli describe collection cost list --help --format json` | 0 | PASS |
| 24 | help describe collection cost list --help text | offline help | `uv run dogopencli describe collection cost list --help --format text` | 0 | PASS |
| 25 | explicit help | offline help | `uv run dogopencli help collection cost list` | 0 | PASS |
| 26 | describe json | offline describe | `uv run dogopencli describe collection cost list --format json` | 0 | PASS |
| 27 | describe text | offline describe | `uv run dogopencli describe collection cost list --format text` | 0 | PASS |
| 28 | missing cache [] | local state | `uv run dogopencli collection cost list` | 1 / CACHE_MISS | PASS |
| 29 | missing cache ['--format', 'table'] | local state | `uv run dogopencli collection cost list --format table` | 1 / CACHE_MISS | PASS |
| 30 | live defaults | production read-only | `uv run dogopencli collection cost list --live` | 0 | PASS |
| 31 | live limit and offset | production read-only | `uv run dogopencli collection cost list --live --limit 2 --offset 1` | 0 | PASS |
| 32 | live all explicit JSON and quality flags | production read-only | `uv run dogopencli collection cost list --live --all --format json --require-fresh --require-complete` | 0 | PASS |
| 33 | live fields projection | production read-only | `uv run dogopencli collection cost list --live --fields itemId,costRateConfigList --limit 2` | 0 | PASS |
| 34 | live table projection | production read-only | `uv run dogopencli collection cost list --live --limit 2 --fields itemId,itemType --format table` | 0 | PASS |
| 35 | live all complete table | production read-only | `uv run dogopencli collection cost list --live --all --require-complete --format table --fields itemId,itemType` | 0 | PASS |
| 36 | explicit refresh | production read-only + local cache | `uv run dogopencli refresh collection cost` | 0 | PASS |
| 37 | cached all quality flags | cached | `uv run dogopencli collection cost list --all --require-fresh --require-complete` | 0 | PASS |
| 38 | cached defaults | cached | `uv run dogopencli collection cost list` | 0 | PASS |
| 39 | cached explicit JSON | cached | `uv run dogopencli collection cost list --format json` | 0 | PASS |
| 40 | cached limit one | cached | `uv run dogopencli collection cost list --limit 1` | 0 | PASS |
| 41 | cached offset only | cached | `uv run dogopencli collection cost list --offset 1` | 0 | PASS |
| 42 | cached limit offset | cached | `uv run dogopencli collection cost list --limit 2 --offset 1` | 0 | PASS |
| 43 | cached offset zero | cached | `uv run dogopencli collection cost list --offset 0` | 0 | PASS |
| 44 | cached offset at total | cached | `uv run dogopencli collection cost list --offset 556` | 0 | PASS |
| 45 | cached offset beyond total | cached | `uv run dogopencli collection cost list --offset 557` | 0 | PASS |
| 46 | cached limit above total | cached | `uv run dogopencli collection cost list --limit 557` | 0 | PASS |
| 47 | cached fields projection | cached | `uv run dogopencli collection cost list --fields itemId,costRateConfigList --limit 2` | 0 | PASS |
| 48 | cached unknown field omitted | cached | `uv run dogopencli collection cost list --fields unverifiedAbsentField --limit 1` | 0 | PASS |
| 49 | cached whitespace fields | cached | `uv run dogopencli collection cost list --fields ' itemId , itemType ' --limit 1` | 0 | PASS |
| 50 | cached table projection | cached | `uv run dogopencli collection cost list --format table --fields itemId,itemType --limit 2` | 0 | PASS |
| 51 | cached all complete table | cached | `uv run dogopencli collection cost list --all --require-complete --format table --fields itemId,itemType` | 0 | PASS |
| 52 | cached empty table | cached | `uv run dogopencli collection cost list --format table --offset 556` | 0 | PASS |
| 53 | reject ['--limit', '0'] | argument rejection | `uv run dogopencli collection cost list --limit 0` | 2 / INVALID_ARGUMENT | PASS |
| 54 | reject ['--limit', '-1'] | argument rejection | `uv run dogopencli collection cost list --limit -1` | 2 / INVALID_ARGUMENT | PASS |
| 55 | reject ['--limit', 'abc'] | argument rejection | `uv run dogopencli collection cost list --limit abc` | 2 / INVALID_ARGUMENT | PASS |
| 56 | reject ['--limit'] | argument rejection | `uv run dogopencli collection cost list --limit` | 2 / INVALID_ARGUMENT | PASS |
| 57 | reject ['--offset', '-1'] | argument rejection | `uv run dogopencli collection cost list --offset -1` | 2 / INVALID_ARGUMENT | PASS |
| 58 | reject ['--offset', 'abc'] | argument rejection | `uv run dogopencli collection cost list --offset abc` | 2 / INVALID_ARGUMENT | PASS |
| 59 | reject ['--offset'] | argument rejection | `uv run dogopencli collection cost list --offset` | 2 / INVALID_ARGUMENT | PASS |
| 60 | reject ['--all', '--limit', '1'] | argument rejection | `uv run dogopencli collection cost list --all --limit 1` | 2 / INVALID_ARGUMENT | PASS |
| 61 | reject ['--all', '--offset', '0'] | argument rejection | `uv run dogopencli collection cost list --all --offset 0` | 2 / INVALID_ARGUMENT | PASS |
| 62 | reject ['--format', 'text'] | argument rejection | `uv run dogopencli collection cost list --format text` | 2 / INVALID_ARGUMENT | PASS |
| 63 | reject ['--format', 'yaml'] | argument rejection | `uv run dogopencli collection cost list --format yaml` | 2 / INVALID_ARGUMENT | PASS |
| 64 | reject ['--format'] | argument rejection | `uv run dogopencli collection cost list --format` | 2 / INVALID_ARGUMENT | PASS |
| 65 | reject ['--fields', ''] | argument rejection | `uv run dogopencli collection cost list --fields ''` | 2 / INVALID_ARGUMENT | PASS |
| 66 | reject ['--fields', ' , '] | argument rejection | `uv run dogopencli collection cost list --fields ' , '` | 2 / INVALID_ARGUMENT | PASS |
| 67 | reject ['--fields'] | argument rejection | `uv run dogopencli collection cost list --fields` | 2 / INVALID_ARGUMENT | PASS |
| 68 | reject ['--bank-account', 'X'] | argument rejection | `uv run dogopencli collection cost list --bank-account X` | 2 / INVALID_ARGUMENT | PASS |
| 69 | reject ['--cost-type', 'FUND_IN_VA_FEE'] | argument rejection | `uv run dogopencli collection cost list --cost-type FUND_IN_VA_FEE` | 2 / INVALID_ARGUMENT | PASS |
| 70 | reject ['--require-fresh=false'] | argument rejection | `uv run dogopencli collection cost list --require-fresh=false` | 2 / INVALID_ARGUMENT | PASS |
| 71 | reject ['--require-complete=false'] | argument rejection | `uv run dogopencli collection cost list --require-complete=false` | 2 / INVALID_ARGUMENT | PASS |
| 72 | reject ['--live=false'] | argument rejection | `uv run dogopencli collection cost list --live=false` | 2 / INVALID_ARGUMENT | PASS |
| 73 | invalid argument table error | argument rejection | `uv run dogopencli collection cost list --limit 0 --format table` | 2 / INVALID_ARGUMENT | PASS |
| 74 | reject unsupported ['refresh', 'collection', 'cost', '--live'] | argument rejection | `uv run dogopencli refresh collection cost --live` | 2 / INVALID_ARGUMENT | PASS |
| 75 | reject unsupported ['refresh', 'collection', 'cost', '--format', 'json'] | argument rejection | `uv run dogopencli refresh collection cost --format json` | 2 / INVALID_ARGUMENT | PASS |
| 76 | reject unsupported ['describe', 'collection', 'cost', 'list', '--live'] | argument rejection | `uv run dogopencli describe collection cost list --live` | 2 / INVALID_ARGUMENT | PASS |
| 77 | reject unsupported ['describe', 'collection', 'cost', 'list', '--format', 'table'] | argument rejection | `uv run dogopencli describe collection cost list --format table` | 2 / INVALID_ARGUMENT | PASS |
| 78 | stale cache allowed by default | local state | `uv run dogopencli collection cost list --limit 1` | 0 | PASS |
| 79 | require fresh rejects stale JSON | local state | `uv run dogopencli collection cost list --require-fresh` | 1 / CACHE_STALE | PASS |
| 80 | require fresh rejects stale table | local state | `uv run dogopencli collection cost list --require-fresh --format table` | 1 / CACHE_STALE | PASS |
| 81 | live require fresh independent of stale cache | production read-only | `uv run dogopencli collection cost list --live --require-fresh --require-complete --limit 1` | 0 | PASS |
| 82 | incomplete local metadata allowed by default | local metadata fault injection | `uv run dogopencli collection cost list --limit 1` | 0 | PASS |
| 83 | require complete rejects local incomplete [] | local metadata fault injection | `uv run dogopencli collection cost list --require-complete` | 1 / INCOMPLETE_RESULT | PASS |
| 84 | require complete rejects local incomplete ['--format', 'table'] | local metadata fault injection | `uv run dogopencli collection cost list --require-complete --format table` | 1 / INCOMPLETE_RESULT | PASS |

## Counts and limits

Final refresh and complete offline read each contained **556 records**. The total is an observation, not a fixed assertion or server capacity guarantee. Live requests retained complete-scope validation before display slicing.

- offline help: 25 cases.
- offline describe: 2 cases.
- local state: 5 cases.
- production read-only: 7 cases.
- production read-only + local cache: 1 cases.
- cached: 16 cases.
- argument rejection: 25 cases.
- local metadata fault injection: 3 cases.
