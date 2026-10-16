# Installed leaf plugins and four pilots

Status: accepted; implements [spec #219](https://github.com/proletariat64/dogopencli/issues/219)
Date: 2026-10-17

## Context

The completed domain foundation owns authentication, domain switches and recorded
operational observations. Business leaves need independent local installation,
one command spelling and common cache/storage/documentation behavior. Keeping old
leaf registration and syntax would leave two active owners of the same inquiries.

## Decision

A configuration owns `plugins/<domain>/<dotted-leaf-name>/leaf.json` and a local
Python inquiry adapter. Folder and declared identity must agree. The global ID is
`domain.name`. Startup discovers valid leaves and reports broken ones independently.
There is no package/version manager, hot loading or separate leaf enable switch.
Domain enablement and authentication remain authoritative.

All actions follow the domain: `payment list sla.baselines`,
`payment get sla.baselines <id>`, `payment refresh sla.baselines`,
`payment describe sla.baselines`. Help and maintenance use the same dotted name.
Formatted output supports `json` and `text` only. Legacy public leaf registrations
are detached; implementations remain for the separate migration/cleanup #218.

Common runtime owns collection orchestration, result policy, one cache slot per
list, rendering and storage registration. Adapters own verified native contracts,
parsing and paging policy. Native business fields retain their values and types.
ADR 0019's usable-incomplete policy remains: warnings and unknown totals/identity
stay visible; strict completeness rejects incomplete candidates.

ADR 0020's single-slot cache behavior remains. A nonempty accepted refresh replaces
the whole saved scope; empty/error/strict rejection preserves it. Live never
publishes. Uniform TTL applies to FX too. Confirmed folder removal cleans only that
leaf's new cache; malformed folders and failed scans preserve it.

Each list registers one configured Duckdog relation. First installation initializes
an empty `_record VARCHAR` table; later loads validate ownership and structure.
Registration is local and acquires no business data. Uninstall retains tables;
reinstall validates them. No import or cache-to-Duckdog population is included.
The effective configuration defaults to a local `duckdog.duckdb` unless
`[duckdog].path` specifies another database. Relation names are manifest bindings,
not inferred from user-facing business fields.

One basic manifest schema supplies help, description and localhost form fields.
The form edits documentation prose, meanings, units and examples. Technical
identity, operations, parameter contracts and native record identity are locked.
Preview shares the CLI renderer. Save validates, detects stale edits and atomically
replaces the manifest; there is no autosave or live reload. Existing loopback,
Host/Origin and mutation-token protections apply.

## Consequences

This supersedes ADR 0021's static leaf contributions, legacy compatibility and
per-leaf enable requirements for installed leaves, preserving its domain/auth/
browser/state foundation. It expands the GUI from inventory to documentation
editing. It extends ADR 0020's external read-only Duckdog boundary only to empty
initialization and binding validation; imports/history remain separate.

The pilots are payment `sla.baselines` list/get, collection `cost` list, liquidity
`reference.entities` list and FX `trade` list. Four-domain production UAT and
GUI interaction evidence are required independently of automated checks. FX's
166-row reference reproduction is comparison evidence, never a fixed future count
or proof of completeness. Later migration and old-code deletion remain #218.
