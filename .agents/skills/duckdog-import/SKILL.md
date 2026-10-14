---
name: duckdog-import
description: Import dogopencli live JSON into duckdog DuckDB and Parquet datasets. Use for requested dataset imports or full settings replacement; inspection alone does not authorize import.
---

# Duckdog import

Duckdog is the independent dataset layer defined in dogopencli's `CONTEXT.md`, not an installed CLI. Read [the initial spec](../../../docs/design/duckdog-v0.1.0.md) before changing storage policies or adding a leaf.

## Supported imports

The helper supports complete settings and reference-directory acquisitions declared
in [the import contracts](../../../docs/design/duckdog-settings-import-contracts.md).
Inspect `scripts/import_settings.py` REGISTRY for supported selectors and identity
columns. Retirement or activity decisions are separate from importer support.

Selectors omit `dogopencli/` and terminal `list`. Each live acquisition uses `dogopencli <leaf> list --live --limit 0 --offset 0 --require-complete --format json`. Import `.data` and `.meta` directly, not the temporary CLI cache.

Other leaves need a declared import contract. Runtime additionally needs verified business-date partitions, identity and replay policy; this settings helper does not import runtimes. Calendars, ledger accounts and business-lines are on the user's retirement list and are excluded from this importer.

## Retired pricing selectors

B01 (#164, specification #172) retires all six pricing resources. Factors and
strategies are removed from the active import registry. Live acquisition, saved
`--input` publication, and direct publication refuse before reading input or
changing storage. Existing DuckDB/Parquet datasets remain available for historical
read-only analysis; no cleanup runs.

## Execute

1. Resolve the repository and private dataset root. Default: `<dogopencli repository>/duckdog-data`, already excluded from Git. An explicit root takes precedence. Inspect existing contents before reusing a root. For a design-only request, prepare the design without running a live import.
2. Use a Python environment with `duckdb`. Prefer the project environment; the user's DI environment is an available fallback. If missing, prepare an isolated environment when installation is authorized. Do not change product dependencies or guess a `duckdog` executable.
3. Before live browser work, follow repository browser instructions. Reuse authenticated Liquidity CDP. Human SSO remains human-controlled. Never use ports 9330–9340.
4. Run one selector at a time:

   ```bash
   rtk proxy <python-with-duckdb> <skill-directory>/scripts/import_settings.py \
     --root <private-dataset-root> --selector liquidity/reference/banks
   rtk proxy <python-with-duckdb> <skill-directory>/scripts/import_settings.py \
     --root <private-dataset-root> --selector liquidity/reference/entities
   ```

   `--input <private-json-file>` accepts an existing complete live envelope when its provenance and scope are established. Simulated data and cached envelopes are rejected.
5. Read the committed registry, views and Parquet back. Verify counts, completeness and capture time. Entities' `instId` stays a string; duplicate `instCode` values stay intact. Complete empty results produce zero-row current datasets.
6. Report selector, count, capture time, database/relation, Parquet path and pending cleanup. Separate synthetic acceptance from production ingestion. Do not print raw business records, authentication data or unredacted failures.

## Publication

Validate source, capability, unfiltered scope, completeness, counts and native identity before publication. Settings use full replacement, never row updates or merges. Parquet preserves full JSON, including nested and unknown fields; DuckDB views expose selected identifier columns as strings.

One writer owns a root. Verify a new Parquet generation, switch view and registry in a transaction, then remove superseded generations for that leaf. Failed imports preserve the current dataset. Settings retain no business history. Identical content reuses a generation; older captures cannot overwrite newer ones. Process-interruption leftovers are cleaned after the next successful replacement. Power-loss durability is not guaranteed.

For ANY, map selector `liquidity/reference/entities` to relation `liquidity_reference_entities`, column `instId`. Import preserves all source states. A `VALID`-only selection view requires an explicit policy and configuration; import does not edit dogopencli configuration.

## Validate locally

Run `scripts/verify_import.py` with the same interpreter. Checks use synthetic envelopes and temporary directories, without production queries or real dataset changes.
