# Liquidity R01 retirement implementation

Specification: [#175](https://github.com/proletariat64/dogopencli/issues/175).
Delivery tracker: [R01 #167](https://github.com/proletariat64/dogopencli/issues/167).
B01's separate pricing decision remains [#164](https://github.com/proletariat64/dogopencli/issues/164).

## Resources and reasons

| Resource | Retirement basis |
| --- | --- |
| cash groups | Selected obsolete grouping configuration; dated source evidence is historical |
| investment strategies | Selected obsolete strategy configuration; dated source evidence is historical |
| rules notification | Selected discontinued notification configuration; dated source evidence is historical |
| ledger customers | Business confirmation that the model is unused |
| ledger accounts, INNER and OUTER | Business confirmation that both models are unused |
| reference business-lines | Selected obsolete directory; dated source evidence is historical |
| reference calendars | Selected historical calendar coverage does not establish current support |

Recent ledger source timestamps do not revoke business-confirmed retirement.
Configuration age and calendar coverage do not establish source-system shutdown.
No new date thresholds or backend availability conclusions are introduced.

## CLI and acquisition boundaries

The seven list and actual refresh paths remain recognizable. Legacy valid scope,
projection, pagination and quality options reach `UNSUPPORTED_CAPABILITY`, exit 1,
with null data, resource-specific retirement reason and #167. Missing formerly
required scope also reaches retirement. Invalid option syntax remains a usage error.
Refusal precedes configuration loading, transport creation, cache reads and
publication, including absent and populated caches. Actual prune routes are removed.

Active list/acquisition registrations and field entries exclude these resources.
Help, describe and snapshot report retirement without an executable schema or
acquisition examples. Native source definitions and historical UAT evidence remain
historical; source-module release evidence is not the current supported registry.
The full inventory is derived from current registration rather than old totals.

Ownership is assessed per capability: `/bankAccountGroupQuery.json` remains
available for active cash group-balances. Independent existing native gets for
investment strategies, notification rules and ledger customers remain unchanged.
Other retired-only list endpoints have no active acquisition registration. Forecast
adjustments remain unchanged; pricing strategies remain owned exclusively by B01.
Parent navigation and deferred get paths are not broadened into retirement.

## External importer

The confirmed external settings helper previously registered cash/groups (`id`),
investment/strategies (`strategyRuleCode`), rules/notification (`id`) and
ledger/customers (`customerNo`, `version`). The retained
[owner patch](../../scripts/patches/r01-duckdog-import.patch) rejects all four at
ordinary selection, saved `--input`, validation and direct publication boundaries.
Rejection precedes input reads, acquisition, directory creation and DuckDB/Parquet
publication. Calendars, ledger/accounts and business-lines remain excluded.

The installed helper was updated after checking original hashes. Its 11 synthetic
verification checks pass, including refusal with absent and existing storage;
reverse patch checking confirms deployed files. Merging this repository does not
deploy the external patch to other installations. Those owners must independently
check and apply the retained patch. No new importer is introduced.

## Storage and verification evidence

Public CLI tests use fake CDP/transport spies and temporary SQLite. They cover all
seven resources, both ledger scopes, live/offline/refresh, valid legacy options,
absent storage, seeded historical slots, unusable acquisition configuration and
unavailable Chrome. Requests and transport creation remain zero during refusal;
seeded SQLite bytes stay identical. Discovery, removed prune, direct historical
source bindings and active shared group-balances are checked independently.

Read-only inventory covers 71 files across the known local dataset root, saved
audit inputs and CLI cache/sidecars. The dataset root contains 18 datasets with no
R01 registry rows; current CLI configuration declares no duckdog paths/selectors.
All 71 hashes remained unchanged after refusal smoke; hashes are retained privately. This bounded inventory
does not prove that all saved JSON or external stores were inspected. Existing
datasets, generations, registry, saved inputs and temporary slots are preserved;
no import, migration, deletion or schema rewrite is part of retirement.

Production-configured local refusal smoke passed 24/24 invocations: seven
resources, with INNER/OUTER tested separately, in offline/live/refresh modes.
Linux `strace -f` recorded zero connect/send operations. This verifies local
refusal with normal production configuration; it is not an authenticated source
read. Required repository gates, independent review and remote PR checks are
reported separately in the implementation PR. No retired
production endpoint is queried for retirement acceptance; authenticated active
inquiry UAT remains a separate boundary. No shared browser or authentication state
is touched.
